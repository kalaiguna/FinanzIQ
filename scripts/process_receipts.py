#!/usr/bin/env python3
"""
process_receipts.py — Scan kassenbons/ inbox, extract data via AI Vision,
save to SQLite, and archive images.

Backend is selected automatically via FINANZIQ_BACKEND env var or auto-detected.
See core/adapter.py for supported backends: claude | antigravity | ollama

Usage:
    python scripts/process_receipts.py
    python scripts/process_receipts.py --force
    python scripts/process_receipts.py --dir /path/to/images
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── Paths & imports ───────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent.parent
_SCRIPTS = Path(__file__).parent

for _p in (str(_SCRIPTS), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.adapter import get_adapter
from core.prompts import RECEIPT_PROMPT, RECEIPT_TEXT_PROMPT
from parsers.receipt_parser import (
    _extract_json,
    _pdf_text,
    validate_receipt,
    PDF_BATCH_SIZE,
)

# ── Config ────────────────────────────────────────────────────────────────────
RECEIPTS_INBOX   = ROOT / "downloads" / "kassenbons"
RECEIPTS_ARCHIVE = ROOT / "data" / "receipts"
PROCESSED_DIR    = ROOT / "data" / "processed"
MANIFEST_FILE    = PROCESSED_DIR / "receipts_manifest.json"
DB_FILE          = PROCESSED_DIR / "receipts.db"
RECEIPTS_JSON    = PROCESSED_DIR / "receipts.json"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
RECEIPTS_INBOX.mkdir(parents=True, exist_ok=True)
RECEIPTS_ARCHIVE.mkdir(parents=True, exist_ok=True)

RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}

# ── Database ──────────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS receipts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            image_filename  TEXT NOT NULL,
            store           TEXT,
            store_chain     TEXT,
            address         TEXT,
            date            DATE,
            time            TEXT,
            total           REAL,
            subtotal        REAL,
            vat_7pct        REAL,
            vat_19pct       REAL,
            payment_method  TEXT,
            item_count      INTEGER,
            validation_ok   INTEGER DEFAULT 1,
            validation_note TEXT,
            processed_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id  INTEGER REFERENCES receipts(id),
            raw_name    TEXT,
            clean_name  TEXT,
            category    TEXT,
            qty         REAL DEFAULT 1,
            unit_price  REAL,
            total       REAL,
            vat_rate    TEXT
        );
    """)
    conn.commit()


def save_to_db(conn: sqlite3.Connection, data: dict, filename: str,
               validation_ok: bool, validation_note: str) -> int:
    vat = data.get("vat") or {}
    cur = conn.execute(
        """
        INSERT INTO receipts
            (image_filename, store, store_chain, address, date, time,
             total, subtotal, vat_7pct, vat_19pct, payment_method,
             item_count, validation_ok, validation_note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            filename,
            data.get("store"),
            data.get("store_chain"),
            data.get("address"),
            data.get("date"),
            data.get("time"),
            data.get("total"),
            data.get("subtotal"),
            vat.get("7pct"),
            vat.get("19pct"),
            data.get("payment_method"),
            data.get("item_count"),
            1 if validation_ok else 0,
            validation_note or None,
        ),
    )
    receipt_id = cur.lastrowid

    for item in data.get("items") or []:
        conn.execute(
            """
            INSERT INTO items
                (receipt_id, raw_name, clean_name, category, qty, unit_price, total, vat_rate)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                receipt_id,
                item.get("raw_name"),
                item.get("clean_name"),
                item.get("category"),
                item.get("qty", 1),
                item.get("unit_price"),
                item.get("total"),
                item.get("vat_rate"),
            ),
        )
    conn.commit()
    return receipt_id


# ── Manifest ──────────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return {"processed_files": []}


def save_manifest(manifest: dict):
    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Archive ───────────────────────────────────────────────────────────────────

def archive_image(image_path: Path, date_str: str | None) -> Path:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.today()
    except (ValueError, TypeError):
        dt = datetime.today()

    dest_dir = RECEIPTS_ARCHIVE / f"{dt.year:04d}" / f"{dt.month:02d}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / image_path.name
    if dest.exists():
        stem, suffix = image_path.stem, image_path.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1
    import shutil
    shutil.move(str(image_path), str(dest))
    return dest


# ── Main ──────────────────────────────────────────────────────────────────────

def find_receipts(directory: Path) -> list[Path]:
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in RECEIPT_EXTENSIONS
    )


def write_receipts_json(conn: sqlite3.Connection):
    conn.row_factory = sqlite3.Row
    out = []
    for r in conn.execute("SELECT * FROM receipts ORDER BY date, id").fetchall():
        rec = dict(r)
        rec["validation_ok"] = bool(rec["validation_ok"])
        rec["items"] = [
            dict(item)
            for item in conn.execute(
                "SELECT raw_name, clean_name, category, qty, unit_price, total, vat_rate "
                "FROM items WHERE receipt_id=?",
                (rec["id"],)
            ).fetchall()
        ]
        out.append(rec)
    conn.row_factory = None
    RECEIPTS_JSON.write_text(
        json.dumps({"receipts": out}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"JSON: {RECEIPTS_JSON} ({len(out)} receipts)")


def main():
    parser = argparse.ArgumentParser(description="Process receipt images via AI Vision")
    parser.add_argument("--force", action="store_true", help="Reprocess already-seen files")
    parser.add_argument("--dir", type=Path, default=RECEIPTS_INBOX,
                        help="Folder to scan (default: downloads/kassenbons/)")
    args = parser.parse_args()

    # ── Select backend ────────────────────────────────────────────────────────
    try:
        adapter = get_adapter()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    backend_name = adapter.__name__.split(".")[-2]  # "claude" | "antigravity" | "ollama"
    print(f"Backend: {backend_name}\n")

    # ── Scan inbox ────────────────────────────────────────────────────────────
    manifest = load_manifest()
    conn = sqlite3.connect(DB_FILE)
    init_db(conn)

    receipts = find_receipts(args.dir)
    if not receipts:
        print(f"No receipt files found in {args.dir}")
        write_receipts_json(conn)
        conn.close()
        sys.exit(0)

    new_receipts = [p for p in receipts if args.force or p.name not in manifest["processed_files"]]
    skipped = len(receipts) - len(new_receipts)

    new_pdfs   = [p for p in new_receipts if p.suffix.lower() == ".pdf"]
    new_images = [p for p in new_receipts if p.suffix.lower() != ".pdf"]

    print(f"Found {len(receipts)} file(s) — {len(new_receipts)} new, {skipped} already processed")
    if new_pdfs:
        print(f"  {len(new_pdfs)} PDF(s), {len(new_images)} image(s)\n")
    else:
        print()

    processed = 0
    errors = 0

    def _save_one(data: dict, image_path: Path):
        nonlocal processed, errors
        try:
            ok, note = validate_receipt(data)
            save_to_db(conn, data, image_path.name, ok, note)
            dest = archive_image(image_path, data.get("date"))
            manifest["processed_files"].append(image_path.name)
            save_manifest(manifest)
            chain     = data.get("store_chain") or data.get("store") or "?"
            date      = data.get("date") or "?"
            total     = data.get("total")
            total_str = f"€{total:.2f}" if total is not None else "?"
            n_items   = len(data.get("items") or [])
            val_flag  = "" if ok else f"  [!] {note}"
            print(f"  OK  {chain} | {date} | {total_str} | {n_items} items{val_flag}")
            print(f"      archived -> {dest.relative_to(ROOT)}")
            processed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR saving {image_path.name}: {e}")
            traceback.print_exc()
            errors += 1

    # ── PDFs ──────────────────────────────────────────────────────────────────
    if new_pdfs:
        use_batch = backend_name == "claude" and len(new_pdfs) > 1
        if use_batch:
            pdf_texts = [_pdf_text(p) for p in new_pdfs]
            n_chunks  = (len(new_pdfs) + PDF_BATCH_SIZE - 1) // PDF_BATCH_SIZE
            print(f"  Sending {len(new_pdfs)} PDF(s) in {n_chunks} batch call(s) …")
            try:
                results = adapter.extract_pdf_batch(pdf_texts)
                for path, data in zip(new_pdfs, results):
                    _save_one(data, path)
            except Exception as e:
                import traceback
                print(f"  Batch failed ({e}), falling back to serial …")
                traceback.print_exc()
                for path in new_pdfs:
                    print(f"  Processing [PDF]: {path.name}")
                    try:
                        raw = adapter.extract_pdf_text(_pdf_text(path), RECEIPT_TEXT_PROMPT)
                        _save_one(_extract_json(raw), path)
                    except Exception as e2:
                        print(f"  ERROR: {path.name}: {e2}")
                        errors += 1
        else:
            # Serial: Gemini/Ollama, or single PDF for Claude
            for path in new_pdfs:
                print(f"  Processing [PDF]: {path.name}")
                try:
                    raw = adapter.extract_pdf_text(_pdf_text(path), RECEIPT_TEXT_PROMPT)
                    _save_one(_extract_json(raw), path)
                except Exception as e:
                    import traceback
                    print(f"  ERROR: {path.name}: {e}")
                    traceback.print_exc()
                    errors += 1

    # ── Images: always serial ─────────────────────────────────────────────────
    for image_path in new_images:
        print(f"  Processing [image]: {image_path.name}")
        try:
            raw  = adapter.extract_image(image_path, RECEIPT_PROMPT)
            data = _extract_json(raw)
            _save_one(data, image_path)
        except Exception as e:
            import traceback
            print(f"  ERROR: {image_path.name}: {e}")
            traceback.print_exc()
            errors += 1

    write_receipts_json(conn)
    conn.close()

    print(f"\nDone: {processed} processed, {errors} errors")
    if processed:
        print(f"DB: {DB_FILE}")


if __name__ == "__main__":
    main()
