"""
Deterministic parser for German bank Konto-Auszug (account statement) PDFs — Sparkasse format.
Handles both full monthly statements and the short-format (Apr22.PDF style).

Returns a dict with '_confidence' (0-100).
Confidence >= 80 means opening balance, closing balance, period, and transactions found.
"""

import re
from pathlib import Path
from datetime import date, timedelta

_MONTH_NAMES = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December']

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from .categorizer import categorize

MONTHS_DE = {
    'januar': 1, 'februar': 2, 'märz': 3, 'maerz': 3,
    'april': 4, 'mai': 5, 'juni': 6, 'juli': 7,
    'august': 8, 'september': 9, 'oktober': 10,
    'november': 11, 'dezember': 12,
}

TX_TYPES = [
    'Kartenzahlung', 'Lastschrift', 'Gutschrift', 'Dauerauftrag',
    'Überweisung', 'Echtzeitüberweisung', 'Auszahlung Geldautom',
    'Abrechnung', 'Entgelt', 'Wertpapier', 'Umbuchung',
    'Kostenlose Buchung', 'Kontoführung', 'Rechnungsabschluss',
    'Lohn', 'Gehalt', 'Zinsen',
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_amount(s: str) -> float | None:
    """'-1.234,56' or '20.756,08' → float."""
    try:
        return float(s.strip().replace('.', '').replace(',', '.'))
    except (ValueError, AttributeError):
        return None


def _extract_all_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return '\n'.join(p.extract_text() or '' for p in pdf.pages)


def _next_month(y: int, m: int) -> tuple[int, int]:
    if m == 12:
        return y + 1, 1
    return y, m + 1


# ── Field extractors ─────────────────────────────────────────────────────────

def _find_iban(text: str) -> str | None:
    m = re.search(r'(DE\d{2}(?:\s*\d{4}){4,5})', text)
    return re.sub(r'\s+', '', m.group(1)) if m else None


def _find_statement_number(text: str) -> tuple[int | None, int | None]:
    """'Kontoauszug 1/2024' → (stmt_number=1, year=2024)"""
    m = re.search(r'Kontoauszug\s+(\d+)/(\d{4})', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _find_opening_balance(text: str) -> tuple[float | None, str | None]:
    """'Kontostand am 29.12.2023, Auszug Nr. 12 20.756,08' → (20756.08, '2023-12-29')"""
    m = re.search(
        r'Kontostand am (\d{2})\.(\d{2})\.(\d{4}),\s*Auszug Nr\.\s*\d+\s+([\d.,]+)',
        text)
    if m:
        d = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return _parse_amount(m.group(4)), d
    return None, None


def _find_closing_balance(text: str) -> tuple[float | None, str | None]:
    """
    Closing balance lines do NOT contain ', Auszug Nr.' (that's the opening format).
    Handles two forms:
      'Kontostand am 29.04.2022 um 20:03 Uhr 2.775,65'
      'Kontostand am 31.01.2024 20.123,45'
    Returns the LAST matching occurrence (some multi-page statements repeat subtotals).
    """
    # Closing balance: Kontostand line that is NOT followed by ', Auszug Nr.'
    pattern = re.compile(
        r'Kontostand am (\d{2})\.(\d{2})\.(\d{4})'
        r'(?!\s*,\s*Auszug)'           # exclude opening balance format
        r'(?:\s+um\s+[\d:]+\s+Uhr)?'  # optional time suffix
        r'\s+([\d.]+,\d{2})',
        re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if matches:
        m = matches[-1]
        d = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return _parse_amount(m.group(4)), d
    return None, None


def _derive_period(opening_date: str | None, closing_date: str | None,
                   stmt_num: int | None, stmt_year: int | None) -> dict | None:
    """
    Derive statement month/year.
    Priority: closing date month (most accurate, handles quarterly statements)
    → opening+1 month → statement number as month proxy.
    """
    if closing_date:
        try:
            y, m, _ = closing_date.split('-')
            if 2000 <= int(y) <= 2099 and 1 <= int(m) <= 12:
                return {'year': int(y), 'month': int(m), 'label': f'{_MONTH_NAMES[int(m)]} {int(y)}'}
        except Exception:
            pass
    if opening_date:
        try:
            y, m, _ = opening_date.split('-')
            ny, nm = _next_month(int(y), int(m))
            if 2000 <= ny <= 2099 and 1 <= nm <= 12:
                return {'year': ny, 'month': nm, 'label': f'{nm}/{ny}'}
        except Exception:
            pass
    if stmt_num and stmt_year and 1 <= stmt_num <= 12:
        return {'year': stmt_year, 'month': stmt_num, 'label': f'{stmt_num}/{stmt_year}'}
    return None


def _parse_transactions(text: str) -> list[dict]:
    """
    Parse transaction lines. Format:
      DD.MM.YYYYTransactionType -1.234,56
      Description line(s)...
    """
    transactions = []

    # Build a regex that matches a date prefix immediately followed by transaction type
    type_pattern = '|'.join(re.escape(t) for t in TX_TYPES)
    tx_line_re = re.compile(
        rf'(\d{{2}})\.(\d{{2}})\.(\d{{4}})({type_pattern})[^\n]*?\s+(-?[\d.]+,\d{{2}})\s*$',
        re.MULTILINE | re.IGNORECASE)

    # Also match lines where type and amount are separated (fallback)
    tx_simple_re = re.compile(
        r'^(\d{2})\.(\d{2})\.(\d{4})\s+(.+?)\s+(-?[\d.]+,\d{2})\s*$',
        re.MULTILINE)

    # Collect all transaction positions
    raw_txs = []
    for m in tx_line_re.finditer(text):
        raw_txs.append({
            'pos': m.start(),
            'date': f"{m.group(3)}-{m.group(2)}-{m.group(1)}",
            'type': m.group(4).strip(),
            'amount': _parse_amount(m.group(5)),
            'desc_start': m.end(),
        })

    # If the stricter pattern found nothing, try the simple fallback
    if not raw_txs:
        for m in tx_simple_re.finditer(text):
            raw_txs.append({
                'pos': m.start(),
                'date': f"{m.group(3)}-{m.group(2)}-{m.group(1)}",
                'type': '',
                'amount': _parse_amount(m.group(5)),
                'desc_start': m.end(),
            })

    # For each raw transaction, grab description from text between this and next tx
    for i, tx in enumerate(raw_txs):
        if tx['amount'] is None:
            continue
        end_pos = raw_txs[i + 1]['pos'] if i + 1 < len(raw_txs) else len(text)
        desc_text = text[tx['desc_start']:end_pos].strip()
        # First line of description is the merchant / purpose
        first_line = desc_text.split('\n')[0].strip() if desc_text else ''
        # Clean up IBAN / BIC noise from card payment descriptions
        merchant = re.split(r'BIC\s*/\s*IBAN', first_line)[0].strip()
        merchant = re.sub(r'\s*/\s*\w+/\w+.*$', '', merchant).strip()  # remove geo suffix
        merchant = merchant[:80]  # cap length

        category = categorize(merchant, tx['type'])

        transactions.append({
            'date': tx['date'],
            'description': first_line[:120] if first_line else tx['type'],
            'merchant': merchant or tx['type'],
            'amount': tx['amount'],
            'type': tx['type'],
            'category': category,
        })

    return transactions


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_bank_statement(pdf_path: Path) -> dict:
    """
    Deterministically parse a Konto-Auszug PDF (Sparkasse format).
    Returns structured dict matching the schema expected by process_payslip.py.
    '_confidence' is 0-100; >= 80 means all critical fields were found.
    """
    if pdfplumber is None:
        return {'_confidence': 0, '_parser': 'deterministic',
                '_error': 'pdfplumber not installed'}

    text = _extract_all_text(pdf_path)
    if not text:
        return {'_confidence': 0, '_parser': 'deterministic', '_error': 'empty PDF text'}

    iban            = _find_iban(text)
    stmt_num, year  = _find_statement_number(text)
    opening, o_date = _find_opening_balance(text)
    closing, c_date = _find_closing_balance(text)
    period          = _derive_period(o_date, c_date, stmt_num, year)
    transactions    = _parse_transactions(text)

    # Confidence: 25 pts each for period, opening, closing, >=1 transaction
    score = sum([
        period is not None,
        opening is not None,
        closing is not None,
        len(transactions) > 0,
    ])
    confidence = int(score / 4 * 100)

    total_credits = sum(t['amount'] for t in transactions if t['amount'] > 0)
    total_debits  = abs(sum(t['amount'] for t in transactions if t['amount'] < 0))

    return {
        '_confidence': confidence,
        '_parser': 'deterministic',
        'period': period or {},
        'account': {
            'holder': None,
            'iban': iban,
            'bank_name': None,
        },
        'balance': {
            'opening': opening,
            'closing': closing,
            'opening_date': o_date,
            'closing_date': c_date,
        },
        'transactions': transactions,
        'summary': {
            'total_credits': round(total_credits, 2),
            'total_debits': round(total_debits, 2),
            'transaction_count': len(transactions),
        },
    }
