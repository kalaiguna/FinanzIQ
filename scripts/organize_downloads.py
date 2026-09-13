#!/usr/bin/env python3
"""
organize_downloads.py — Moves PDFs from downloads/ into data/raw/YYYY/MM/

Handles all naming patterns found in this project:
  Brutto-Netto-Abrechnung 2024 07 Juli.pdf   → data/raw/2024/07/  (YYYY MM Name)
  Brutto-Netto-Abrechnung Juli 2024.pdf      → data/raw/2024/07/  (Name YYYY)
  BruttoNetto-Bezuege-2022-07-Juli.pdf       → data/raw/2022/07/
  Konto_...-Auszug_2026_0007.PDF             → data/raw/2026/07/
  Jul22.PDF  / July2023.PDF / Jul2024.PDF    → bank statement short formats
  Sep22.PDF  / Sep2023.PDF  / Sep2024.PDF    → bank statement short formats

Usage:
    python scripts/organize_downloads.py           # move files
    python scripts/organize_downloads.py --dry-run # preview only
    python scripts/organize_downloads.py --copy    # keep originals in downloads/
"""

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
DOWNLOADS_DIR = ROOT / "downloads"
PDF_SUBDIRS = ["payslips", "bank_statements"]  # kassenbons/ is handled by process_receipts.py
RAW_DIR = ROOT / "data" / "raw"

# ── Month name tables ─────────────────────────────────────────────────────────

# 3-letter English abbreviations (covers Jan, Feb, Mar, Apr, May, Jun,
#   Jul, Aug, Sep, Oct, Nov, Dec — also handles July→Jul via prefix match)
ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Full German and English month names (checked before abbreviations — longer = safer)
FULL = {
    # German
    "januar": 1, "februar": 2, "maerz": 3, "märz": 3,
    "april": 4, "mai": 5, "juni": 6, "juli": 7,
    "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
    # English
    "january": 1, "february": 2, "march": 3,
    "june": 6, "july": 7,
    "october": 10, "december": 12,
}


def parse_year_month(filename: str):
    """
    Try four strategies in order. Returns (year, month) or (None, None).

    Strategy 1 — YYYY + separator + optional-zeros + month-number
        Handles: "2026 07", "2026_0007", "2022-07-Juli"
    Strategy 2 — 4-digit year anywhere + full month name or 3-letter abbrev
        Handles: "April 2023", "Apr2023", "July2023", "Jun2024"
    Strategy 3 — 3-letter abbrev immediately followed by 2-digit year
        Handles: "Apr22", "Dec21", "Jul22", "Sep22"
    Strategy 4 — 3-letter abbrev immediately followed by 4-digit year (no separator)
        Handles edge cases missed by Strategy 2
    """
    name = filename.lower()

    # Strategy 1: YYYY + non-digit(s) + optional leading zeros + 1-or-2-digit month
    m = re.search(r"(20\d{2})\D+0*([1-9]|1[0-2])(?!\d)", name)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 2000 <= y <= 2099 and 1 <= mo <= 12:
            return y, mo

    # Strategy 2: find a 4-digit year (anywhere, no word-boundary requirement)
    ym = re.search(r"(20\d{2})", name)
    if ym:
        y = int(ym.group(1))
        # Check full names first (longer strings are more specific)
        for word in sorted(FULL, key=len, reverse=True):
            if word in name:
                return y, FULL[word]
        # Then 3-letter abbreviations
        for abbr, num in ABBR.items():
            if abbr in name:
                return y, num

    # Strategy 3: 3-letter month abbreviation + exactly 2 digits = year (20YY)
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(\d{2})(?!\d)", name)
    if m:
        mo = ABBR[m.group(1)]
        y = 2000 + int(m.group(2))
        if 2000 <= y <= 2099:
            return y, mo

    # Strategy 4: 3-letter abbreviation immediately before 4-digit year (e.g. apr2023)
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(20\d{2})", name)
    if m:
        return int(m.group(2)), ABBR[m.group(1)]

    return None, None


def organize(dry_run: bool = False, copy: bool = False) -> tuple[int, int]:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    for sub in PDF_SUBDIRS:
        (DOWNLOADS_DIR / sub).mkdir(exist_ok=True)

    pdfs = sorted(
        p
        for sub in PDF_SUBDIRS
        for p in (DOWNLOADS_DIR / sub).iterdir()
        if p.suffix.lower() == ".pdf"
    )
    if not pdfs:
        print(f"No PDFs found in downloads/payslips/ or downloads/bank_statements/")
        return 0, 0

    print(f"Found {len(pdfs)} PDF(s) in downloads/\n")

    # Build a map: (dest_dir, md5) -> filename, to detect exact-content duplicates
    seen_hashes: dict[tuple, str] = {}

    moved, skipped = 0, 0
    for pdf in pdfs:
        year, month = parse_year_month(pdf.name)

        if year is None:
            print(f"  [warn] Cannot parse date from '{pdf.name}' -- skipped")
            print(f"         Rename to include YYYY_MM or MonthYYYY and re-run.")
            skipped += 1
            continue

        dest_dir = RAW_DIR / str(year) / f"{month:02d}"
        dest = dest_dir / pdf.name
        size = pdf.stat().st_size
        tag = "[dry-run] " if dry_run else ""
        action = "copy" if copy else "move"

        # Skip exact-content duplicates going to the same folder (MD5 hash)
        md5 = hashlib.md5(pdf.read_bytes()).hexdigest()
        dest_key = (dest_dir, md5)
        if dest_key in seen_hashes:
            print(
                f"  [skip]  {tag}'{pdf.name}' is byte-for-byte identical to "
                f"'{seen_hashes[dest_key]}' already sent to data/raw/{year}/{month:02d}/ -- skipped"
            )
            skipped += 1
            continue
        seen_hashes[dest_key] = pdf.name

        if dest.exists():
            print(f"  [skip]  {tag}'{pdf.name}' already exists at destination")
            skipped += 1
            continue

        print(f"  [ok]    {tag}{action}: {pdf.name}  ->  data/raw/{year}/{month:02d}/")

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            if copy:
                shutil.copy2(pdf, dest)
            else:
                shutil.move(str(pdf), str(dest))

        moved += 1

    verb = "Would move" if dry_run else ("Copied" if copy else "Moved")
    print(f"\n{verb} {moved} file(s), skipped {skipped}.")
    return moved, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Move PDFs from downloads/ to data/raw/YYYY/MM/ based on filename."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would happen without moving files")
    parser.add_argument("--copy", action="store_true",
                        help="Copy files instead of moving (keep originals in downloads/)")
    args = parser.parse_args()

    organize(dry_run=args.dry_run, copy=args.copy)


if __name__ == "__main__":
    main()
