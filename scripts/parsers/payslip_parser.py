"""
Deterministic parser for DATEV Brutto-Netto-Abrechnung payslips (LOGN15 / LOGN17 form).
Handles any employer that issues DATEV-format payslips; only values change month to month.

Returns a dict with a '_confidence' key (0-100).
Confidence >= 80 means all critical fields were found; caller can skip AI.
"""

import re
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # caller checks

MONTHS_DE = {
    'januar': 1, 'februar': 2, 'märz': 3, 'maerz': 3,
    'april': 4, 'mai': 5, 'juni': 6, 'juli': 7,
    'august': 8, 'september': 9, 'oktober': 10,
    'november': 11, 'dezember': 12,
}

CRITICAL = ['period', 'gross_total', 'net_pay', 'tax_total', 'payout']


# ── Number helpers ────────────────────────────────────────────────────────────

def _parse_standard(s: str) -> float | None:
    """'7.089,86' → 7089.86"""
    try:
        return float(s.strip().replace('.', '').replace(',', '.'))
    except (ValueError, AttributeError):
        return None


def _parse_compact(s: str) -> float | None:
    """'7.08986' or '91566' → 7089.86 / 915.66  (no comma; last 2 digits = cents)"""
    try:
        clean = str(s).strip().replace('.', '')
        return int(clean) / 100
    except (ValueError, AttributeError):
        return None


def _last_amount(line: str) -> float | None:
    """
    Find the last German-format amount on a line.
    Uses findall so the regex engine doesn't backtrack into partial matches.
    Example: '...7.089,86' → 7089.86
    """
    # Must start with a digit to exclude '.089,86' partial matches
    matches = re.findall(r'\d[\d.]*,\d{2}', line)
    if matches:
        return _parse_standard(matches[-1])
    return None


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_page_text(pdf_path: Path, page_index: int = 0) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        if page_index >= len(pdf.pages):
            return ''
        return pdf.pages[page_index].extract_text() or ''


# ── Field extractors ─────────────────────────────────────────────────────────

def _find_period(text: str) -> dict | None:
    m = re.search(r'f.r\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
    if not m:
        return None
    month_name = m.group(1).lower()
    year = int(m.group(2))
    month = MONTHS_DE.get(month_name)
    if month and 2000 <= year <= 2099:
        return {'year': year, 'month': month, 'label': f'{m.group(1)} {year}'}
    return None


def _find_gross(text: str) -> float | None:
    # "Gesamt-Brutto\nS te u er/... 7.089,86"
    m = re.search(r'Gesamt-Brutto\s*\n([^\n]+)', text)
    if m:
        return _last_amount(m.group(1))
    return None


def _find_net_pay(text: str) -> float | None:
    # "Netto-Verdienst\n...Netto-Bezüge/Netto-Abzüge 5.422,67"
    m = re.search(r'Netto-Verdienst\s*\n([^\n]+)', text)
    if m:
        return _last_amount(m.group(1))
    return None


def _find_payout(text: str) -> float | None:
    # Last comma-value on the IBAN / "K o nto" line, which follows "Auszahlungsbetrag"
    m = re.search(r'Auszahlungsbetrag\s*\n([^\n]+)', text)
    if m:
        return _last_amount(m.group(1))
    return None


def _find_tax_section(text: str) -> dict:
    """
    Header:  ...Steuerrechtliche Abzüge
    Data:    L 7.08986 91566 915,66
             S 38548 13500 135,00   (optional)

    Last comma-value on each data row = Steuerrechtliche Abzüge for that row.
    Summing all rows gives total monthly tax.
    Second pure-integer token on L rows = Lohnsteuer (compact).
    """
    result = {'income_tax': None, 'solidarity_surcharge': 0.0,
              'church_tax': 0.0, 'total': None}

    m = re.search(r'Steuerrechtliche Abz.ge\s*\n((?:[LS]\s+[^\n]+\n?)+)',
                  text, re.IGNORECASE)
    if not m:
        return result

    rows_text = m.group(1)
    tax_total = 0.0
    lohnsteuer = 0.0
    for row in re.findall(r'^[LS]\s+(.+)$', rows_text, re.MULTILINE):
        # Last standard-format amount = row tax total
        v = _last_amount(row)
        if v is not None:
            tax_total += v
        # Second pure-integer compact value = Lohnsteuer for this row
        pure_ints = re.findall(r'(?<![.\d])\d{4,6}(?![\d,])', row)
        if len(pure_ints) >= 1:
            v2 = _parse_compact(pure_ints[0])
            if v2 is not None:
                lohnsteuer += v2

    result['income_tax'] = round(lohnsteuer, 2) if lohnsteuer else round(tax_total, 2)
    result['total'] = round(tax_total, 2)
    return result


def _find_sv_section(text: str) -> dict:
    """
    Extract SV Beiträge from L rows only.
    L rows: first tokens with '.' are Brutto bases → skip.
    Pure integer tokens (no period, no comma, 3-6 digits) = Beiträge (RV, then AV).
    SV total = sum of last comma-values from all rows.
    KV and PV employee shares come from Netto-Bezüge section (codes 9996, 9984).
    """
    result = {'health_insurance': None, 'pension': None,
              'unemployment': None, 'care_insurance': None, 'total': None}

    m = re.search(r'SV-rechtliche Abz.ge\s*\n((?:[LE]\s+[^\n]+\n?)+)',
                  text, re.IGNORECASE)
    if not m:
        return result

    sv_total = 0.0
    rv = au = 0.0

    for row in re.findall(r'^([LE])\s+(.+)$', m.group(1), re.MULTILINE):
        row_type, row_data = row
        # SV total: last standard-format amount
        v = _last_amount(row_data)
        if v is not None:
            sv_total += v

        if row_type == 'L':
            # For L rows: Brutto values have a period (e.g. '7.08986')
            # Pure digits (no period, no comma) are Beiträge
            tokens = row_data.split()
            beitrag_tokens = [t for t in tokens
                              if re.match(r'^\d{3,6}$', t)]  # only digits, 3-6 chars
            if len(beitrag_tokens) >= 1:
                rv += _parse_compact(beitrag_tokens[0]) or 0
            if len(beitrag_tokens) >= 2:
                au += _parse_compact(beitrag_tokens[1]) or 0

    result['pension'] = round(rv, 2) if rv else None
    result['unemployment'] = round(au, 2) if au else None
    result['total'] = round(sv_total, 2)
    return result


def _find_netto_items(text: str) -> tuple[list, float | None, float | None]:
    """
    Parse Netto-Bezüge supplement items (9xxx codes).
    Returns (items_list, kv_employee_share, pv_employee_share).
    """
    items = []
    kv = pv = None

    m = re.search(r'Netto-Verdienst.*?\n((?:\d{4}[^\n]+\n?)+)', text, re.DOTALL)
    if not m:
        return items, kv, pv

    for line in re.findall(r'^(\d{4})\s+(.+?)\s+(\d[\d.]*,\d{2})(-?)\s*$',
                           m.group(1), re.MULTILINE):
        code, desc, amount_s, neg = line
        amount = _parse_standard(amount_s)
        if amount is None:
            continue
        if neg == '-':
            amount = -amount
        items.append({'code': code, 'description': desc.strip(), 'amount': amount})
        if code == '9996':   # Gesamtbeitrag KV: employee pays half
            kv = round(abs(amount) / 2, 2)
        if code == '9984':   # Gesamtbeitrag PV: employee pays half
            pv = round(abs(amount) / 2, 2)

    return items, kv, pv


def _find_ytd(text: str) -> dict:
    result = {'gross_ytd': None, 'tax_ytd': None}

    # Garbled "Gesamt-Brutto" → compact YTD number
    m = re.search(r'G\s*e\s*s?\s*a?\s*m\s*t\s*-?\s*B\s*r\s*u\s*t\s*t?\s*o\s+([\d.]+)',
                  text, re.IGNORECASE)
    if m:
        result['gross_ytd'] = _parse_compact(m.group(1))

    # Garbled "Lohnsteuer" → compact YTD number
    m = re.search(r'L\s+oh?\s*n\s*s\s*t\s*e\s*u\s*e\s*r\s+([\d.]+)',
                  text, re.IGNORECASE)
    if m:
        result['tax_ytd'] = _parse_compact(m.group(1))

    return result


def _find_employee(text: str) -> dict:
    result = {'name': None, 'personnel_number': None,
              'employer': None, 'tax_class': None}

    m = re.search(r'\*Pers\.-Nr\.\s+(\d+)\*', text)
    if m:
        result['personnel_number'] = m.group(1)

    m = re.search(r'Hinweise zur Abrechnung\s*\n([^\n]+)', text)
    if m:
        result['name'] = m.group(1).strip()

    # "Personal-Nr. Geburtsdatum StKlFaktor ...\n11995 141183 3 ..."
    m = re.search(r'Personal-Nr\.\s+Geburtsdatum\s+StKlFaktor[^\n]*\n(\d+)\s+(\d+)\s+(\d+)',
                  text)
    if m:
        result['tax_class'] = int(m.group(3))

    return result


def _find_iban(text: str) -> str | None:
    # German IBAN = DE + 20 digits = 22 chars total
    m = re.search(r'(DE\d{2}[\s\d]{18,24})', text)
    if m:
        iban = re.sub(r'\s+', '', m.group(1))
        return iban[:22]  # trim to standard IBAN length
    return None


def _find_gross_components(text: str) -> list:
    components = []
    m = re.search(r'Brutto-Bez.ge.*?\n((?:(?:\d{3,4}|\*{4})[^\n]+\n?)*?)Gesamt-Brutto',
                  text, re.DOTALL | re.IGNORECASE)
    if not m:
        return components
    block = m.group(1)
    for line in re.findall(
            r'^(\d{3,4})\s+(.+?)\s+[LSE]\s+[LSE]\s+[JN]\s+(\d[\d.]*,\d{2})(-?)\s*$',
            block, re.MULTILINE):
        code, desc, amount_s, neg = line
        amount = _parse_standard(amount_s)
        if amount is None:
            continue
        if neg == '-':
            amount = -abs(amount)
        components.append({'code': code, 'description': desc.strip(), 'amount': amount})
    return components


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_payslip(pdf_path: Path) -> dict:
    """
    Deterministically parse a DATEV Brutto-Netto-Abrechnung payslip.
    Returns structured dict. '_confidence' >= 80 means all critical fields found.
    """
    if pdfplumber is None:
        return {'_confidence': 0, '_parser': 'deterministic',
                '_error': 'pdfplumber not installed'}

    text = _extract_page_text(pdf_path, page_index=0)
    if not text:
        return {'_confidence': 0, '_parser': 'deterministic', '_error': 'empty PDF text'}

    period     = _find_period(text)
    gross      = _find_gross(text)
    net_pay    = _find_net_pay(text)
    tax        = _find_tax_section(text)
    sv         = _find_sv_section(text)
    netto_items, kv_share, pv_share = _find_netto_items(text)
    payout     = _find_payout(text)
    ytd        = _find_ytd(text)
    employee   = _find_employee(text)
    iban       = _find_iban(text)
    components = _find_gross_components(text)

    if kv_share is not None:
        sv['health_insurance'] = kv_share
    if pv_share is not None:
        sv['care_insurance'] = pv_share

    found = sum([
        period is not None,
        gross is not None,
        net_pay is not None,
        tax.get('total') is not None,
        payout is not None,
    ])
    confidence = int(found / len(CRITICAL) * 100)

    return {
        '_confidence': confidence,
        '_parser': 'deterministic',
        'period': period or {},
        'employee': {
            'name': employee['name'],
            'personnel_number': employee['personnel_number'],
            'employer': employee['employer'],
        },
        'gross': {
            'total': gross,
            'components': components,
        },
        'deductions': {
            'tax': {
                'income_tax': tax['income_tax'],
                'solidarity_surcharge': tax.get('solidarity_surcharge', 0.0),
                'church_tax': tax.get('church_tax', 0.0),
                'total': tax['total'],
            },
            'social_security': {
                'health_insurance': sv.get('health_insurance'),
                'pension': sv.get('pension'),
                'unemployment': sv.get('unemployment'),
                'care_insurance': sv.get('care_insurance'),
                'total': sv.get('total'),
            },
        },
        'net_income': {
            'net_pay': net_pay,
            'payout': payout,
            'employer_supplements': netto_items,
        },
        'cumulative_ytd': {
            'gross_ytd': ytd.get('gross_ytd'),
            'tax_ytd': ytd.get('tax_ytd'),
        },
        'bank': {
            'account_holder': employee['name'],
            'iban': iban,
            'bank_name': None,
        },
        'notes': f'tax_class={employee["tax_class"]}' if employee['tax_class'] else '',
    }
