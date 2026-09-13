#!/usr/bin/env python3
"""
process_payslip.py — Extracts structured data from German payslips (Gehaltsabrechnung)
and bank statements (Kontoauszug) using a pluggable AI backend.

Backend is selected automatically via FINANZIQ_BACKEND env var or auto-detected.
See core/adapter.py for supported backends: claude | antigravity | ollama

Usage:
    python scripts/process_payslip.py
    python scripts/process_payslip.py --file data/raw/2026/07/payslip.pdf
    python scripts/process_payslip.py --from-downloads   # organise + process in one step
    python scripts/process_payslip.py --force            # reprocess already-seen files
    python scripts/process_payslip.py --dir /path/to/pdfs
"""

import json
import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Ensure UTF-8 output on Windows (emoji / German chars in prompts)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── Paths & imports ───────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
_SCRIPTS  = Path(__file__).parent

for _p in (str(_SCRIPTS), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.adapter import get_adapter

# ── Config ────────────────────────────────────────────────────────────────────
RAW_DIR       = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
MANIFEST_FILE = PROCESSED_DIR / "manifest.json"
OUTPUT_FILE   = PROCESSED_DIR / "data.json"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return {"processed_files": []}


def save_manifest(manifest: dict):
    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_output() -> dict:
    if OUTPUT_FILE.exists():
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    return {"payslips": [], "bank_statements": []}


def save_output(data: dict):
    OUTPUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def pdf_to_text(path: Path) -> str:
    """Extract raw text from PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        print("  pdfplumber not installed. Run: pip install pdfplumber")
        sys.exit(1)

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n--- PAGE BREAK ---\n\n".join(pages)


def find_pdfs(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.suffix.lower() == ".pdf")


def _extract_json(raw: str) -> dict:
    """Extract a JSON object from model output that may contain prose or markdown fences."""
    import re as _re
    text = raw.strip()

    if "```" in text:
        m = _re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()

    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])

    # Unwrap first element if model returned an array
    start = text.find("[")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    lst = json.loads(text[start : i + 1])
                    if isinstance(lst, list) and lst:
                        return lst[0]

    raise ValueError(f"No JSON object found in model output. First 300 chars:\n{raw[:300]}")


# ── Prompts ───────────────────────────────────────────────────────────────────

PAYSLIP_PROMPT = """You are a financial data extraction assistant specializing in German payslips (Gehaltsabrechnung).

Extract ALL financial data from this German payslip and return ONLY valid JSON (no markdown, no explanation).

Return this exact structure:
{
  "period": {
    "month": <integer 1-12>,
    "year": <integer>,
    "label": "<Month Year in English, e.g. July 2026>"
  },
  "employee": {
    "name": "<full name>",
    "personnel_number": "<Personalnummer>",
    "employer": "<company name>"
  },
  "gross": {
    "total": <number>,
    "components": [
      {"code": "<Lohnart code>", "description": "<name>", "amount": <number>}
    ]
  },
  "deductions": {
    "tax": {
      "income_tax": <number>,
      "solidarity_surcharge": <number>,
      "church_tax": <number>,
      "total": <number>
    },
    "social_security": {
      "health_insurance": <number>,
      "pension": <number>,
      "unemployment": <number>,
      "care_insurance": <number>,
      "total": <number>
    }
  },
  "net_income": {
    "net_pay": <number>,
    "payout": <number>,
    "employer_supplements": [
      {"code": "<Nr>", "description": "<name>", "amount": <number>}
    ]
  },
  "cumulative_ytd": {
    "gross_ytd": <number>,
    "tax_ytd": <number>
  },
  "bank": {
    "account_holder": "<name>",
    "iban": "<IBAN>",
    "bank_name": "<bank>"
  },
  "notes": "<any special notes, e.g. correction, Nachberechnung>"
}

Use negative numbers for deductions. Extract ALL amounts accurately.
German number format: 1.234,56 → 1234.56 in JSON.
If a field is not present, use null.
"""

BANK_PROMPT = """You are a financial data extraction assistant specializing in German bank statements (Kontoauszug).

Extract ALL transactions from this German bank statement (Kontoauszug) and return ONLY valid JSON (no markdown, no explanation).

Return this exact structure:
{
  "period": {
    "month": <integer 1-12>,
    "year": <integer>,
    "statement_number": <integer>,
    "label": "<Month Year in English>"
  },
  "account": {
    "holder": "<name>",
    "iban": "<IBAN>",
    "bank_name": "<bank name>"
  },
  "balance": {
    "opening": <number>,
    "closing": <number>,
    "opening_date": "<YYYY-MM-DD>",
    "closing_date": "<YYYY-MM-DD>"
  },
  "transactions": [
    {
      "date": "<YYYY-MM-DD>",
      "description": "<cleaned merchant/purpose description>",
      "raw_description": "<original text>",
      "amount": <number, negative=debit, positive=credit>,
      "type": "<Lastschrift|Kartenzahlung|Gutschrift|Dauerauftrag|Überweisung|Auszahlung|Entgelt|other>",
      "category": "<one of: Groceries|Dining|Shopping|Transport|Utilities|Rent|Healthcare|Insurance|Childcare|Income|Salary|Benefits|Banking|Entertainment|Other — use exactly one of these>",
      "merchant": "<clean merchant name>"
    }
  ],
  "summary": {
    "total_credits": <number>,
    "total_debits": <number>,
    "transaction_count": <integer>
  }
}

Categorization rules:
- Herkules, LIDL, PENNY, ALDI, Bereket, Baris Markt, Spicelands → Groceries
- KFC, Kaiyo, Zam Zam, Jamoona, restaurants → Dining
- Woolworth, Rossmann, DM Drogerie → Shopping
- Vodafone, Deutsche Post → Utilities
- PayPal purchases → Shopping (unless clearly another category)
- Bilstein Miete → Rent
- Bilstein Nebenkosten → Utilities
- Kindergartengebühr → Childcare
- Stadtwerke → Utilities
- Lohn/Gehalt / salary deposits → Salary
- Bundesagentur für Arbeit / Kindergeld → Benefits
- Auszahlung Geldautomat → Banking
- American Express settlement → Banking
- Entgeltabrechnung / bank fees → Banking
- Arzt, Dr., Apotheke, medical → Healthcare

German number format: 1.234,56 → 1234.56 in JSON.
Use negative for debits, positive for credits.
"""

# ── Deterministic parsers (tried first; AI fallback if below confidence) ──────

CONFIDENCE_THRESHOLD = 80  # % — skip AI if deterministic score >= this


def _try_deterministic_payslip(pdf_path: Path) -> dict | None:
    try:
        if str(Path(__file__).parent) not in sys.path:
            sys.path.insert(0, str(Path(__file__).parent))
        from parsers.payslip_parser import parse_payslip
        result = parse_payslip(pdf_path)
        conf = result.get("_confidence", 0)
        print(f"    [det] confidence={conf}%", end="")
        if conf >= CONFIDENCE_THRESHOLD:
            print(" - using deterministic result")
            return result
        print(f" — falling back to AI")
        return None
    except Exception as e:
        print(f"    [det] parser error: {e} — falling back to AI")
        return None


def _try_deterministic_bank(pdf_path: Path) -> dict | None:
    try:
        if str(Path(__file__).parent) not in sys.path:
            sys.path.insert(0, str(Path(__file__).parent))
        from parsers.bank_parser import parse_bank_statement
        result = parse_bank_statement(pdf_path)
        conf = result.get("_confidence", 0)
        print(f"    [det] confidence={conf}%", end="")
        if conf >= CONFIDENCE_THRESHOLD:
            print(" - using deterministic result")
            return result
        print(f" — falling back to AI")
        return None
    except Exception as e:
        print(f"    [det] parser error: {e} — falling back to AI")
        return None


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_payslip(pdf_path: Path, adapter) -> dict:
    print(f"  Extracting payslip: {pdf_path.name}")
    data = _try_deterministic_payslip(pdf_path)
    if data is None:
        backend_name = adapter.__name__.split(".")[-2]
        print(f"    [ai ] calling {backend_name} backend …")
        pdf_text = pdf_to_text(pdf_path)
        raw  = adapter.extract_pdf_text(pdf_text, PAYSLIP_PROMPT)
        data = _extract_json(raw)
    data["_source_file"] = str(pdf_path.relative_to(ROOT))
    data["_processed_at"] = datetime.now().isoformat()
    return data


def extract_bank_statement(pdf_path: Path, adapter) -> dict:
    print(f"  Extracting bank statement: {pdf_path.name}")
    data = _try_deterministic_bank(pdf_path)
    if data is None:
        backend_name = adapter.__name__.split(".")[-2]
        print(f"    [ai ] calling {backend_name} backend …")
        pdf_text = pdf_to_text(pdf_path)
        raw  = adapter.extract_pdf_text(pdf_text, BANK_PROMPT)
        data = _extract_json(raw)
    data["_source_file"] = str(pdf_path.relative_to(ROOT))
    data["_processed_at"] = datetime.now().isoformat()
    return data


def classify_pdf(pdf_path: Path) -> str:
    name = pdf_path.name.lower()
    if any(k in name for k in ["payslip", "payroll", "gehalts", "lohn", "netto",
                                "brutto", "abrechnung", "bezuege"]):
        return "payslip"
    if any(k in name for k in ["konto", "auszug", "statement", "bank"]):
        return "bank"
    print(f"    [auto] '{pdf_path.name}' -> bank statement (no payslip keywords)")
    return "bank"


# ── Main ──────────────────────────────────────────────────────────────────────

def process_file(pdf_path: Path, adapter, output: dict, manifest: dict, force: bool = False):
    rel = str(pdf_path.relative_to(ROOT))

    if not force and rel in manifest["processed_files"]:
        print(f"  Already processed: {pdf_path.name}")
        return

    kind = classify_pdf(pdf_path)

    try:
        if kind == "payslip":
            data = extract_payslip(pdf_path, adapter)
            key = (data["period"]["year"], data["period"]["month"])
            output["payslips"] = [p for p in output["payslips"]
                                  if (p["period"]["year"], p["period"]["month"]) != key]
            output["payslips"].append(data)
            output["payslips"].sort(key=lambda p: (p["period"]["year"], p["period"]["month"]))
        else:
            data = extract_bank_statement(pdf_path, adapter)
            key = (data["period"]["year"], data["period"]["month"])
            output["bank_statements"] = [b for b in output["bank_statements"]
                                         if (b["period"]["year"], b["period"]["month"]) != key]
            output["bank_statements"].append(data)
            output["bank_statements"].sort(key=lambda b: (b["period"]["year"], b["period"]["month"]))

        manifest["processed_files"].append(rel)
        save_output(output)
        save_manifest(manifest)
        print(f"  Done: {pdf_path.name}")

    except subprocess.TimeoutExpired:
        print(f"  Timeout on {pdf_path.name} — skipping, re-run later to retry")
    except Exception as e:
        import traceback
        print(f"  Error processing {pdf_path.name}: {e}")
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Process payslips and bank statements")
    parser.add_argument("--file", type=Path, help="Process a specific PDF file")
    parser.add_argument("--force", action="store_true", help="Re-process already processed files")
    parser.add_argument("--dir", type=Path, default=RAW_DIR,
                        help="Directory to scan (default: data/raw)")
    parser.add_argument("--from-downloads", action="store_true",
                        help="First organise downloads/ → data/raw/YYYY/MM/, then process new files")
    args = parser.parse_args()

    # ── Step 0: organise downloads if requested ───────────────────────────────
    if args.from_downloads:
        if str(Path(__file__).parent) not in sys.path:
            sys.path.insert(0, str(Path(__file__).parent))
        from organize_downloads import organize
        print("Organising downloads/ ...\n")
        organize()
        print()

    # ── Step 1: select backend ────────────────────────────────────────────────
    try:
        adapter = get_adapter()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    backend_name = adapter.__name__.split(".")[-2]
    print(f"Backend: {backend_name}\n")

    # ── Step 2: find files ────────────────────────────────────────────────────
    manifest = load_manifest()
    output   = load_output()

    if args.file:
        files = [args.file.resolve()]
    else:
        files = find_pdfs(args.dir)
        if not files:
            print(f"No PDF files found in {args.dir}")
            sys.exit(0)

    print(f"Found {len(files)} PDF(s) to check\n")

    for pdf in files:
        process_file(pdf, adapter, output, manifest, force=args.force)

    save_output(output)
    save_manifest(manifest)

    print(f"\nData saved to {OUTPUT_FILE}")
    print(f"  Payslips: {len(output['payslips'])}")
    print(f"  Bank statements: {len(output['bank_statements'])}")
    print(f"\nRun  python launch.py  to open the dashboard.")


if __name__ == "__main__":
    main()
