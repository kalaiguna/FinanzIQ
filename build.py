#!/usr/bin/env python3
"""
build.py — Generate dashboard/standalone.html with data inlined.

The output opens directly via file:// (no HTTP server, no CORS issues).
Run after processing to keep standalone.html in sync with the latest data.

Usage:
    python build.py
    python build.py --out dashboard/standalone.html
"""

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT       = Path(__file__).parent
DATA_JSON     = ROOT / "data" / "processed" / "data.json"
RECEIPTS_JSON = ROOT / "data" / "processed" / "receipts.json"
INDEX_HTML    = ROOT / "dashboard" / "index.html"
DEFAULT_OUT   = ROOT / "dashboard" / "standalone.html"


def main():
    parser = argparse.ArgumentParser(description="Build self-contained standalone.html")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="Output path (default: dashboard/standalone.html)")
    args = parser.parse_args()

    if not DATA_JSON.exists():
        print(f"ERROR: {DATA_JSON} not found.")
        print("  Run python scripts/process_payslip.py first.")
        sys.exit(1)

    def read_text(path: Path) -> str:
        raw = path.read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")

    data_text     = read_text(DATA_JSON)
    receipts_text = read_text(RECEIPTS_JSON) if RECEIPTS_JSON.exists() else "null"

    html = INDEX_HTML.read_text(encoding="utf-8")

    # Inject both datasets as window globals, just before </head>
    injection = (
        "<script>\n"
        f"window.__EMBEDDED_DATA__ = {data_text};\n"
        f"window.__EMBEDDED_RECEIPTS__ = {receipts_text};\n"
        "</script>\n"
    )
    if "</head>" not in html:
        print("ERROR: Could not find </head> in index.html — aborting.")
        sys.exit(1)

    html = html.replace("</head>", injection + "</head>", 1)
    args.out.write_text(html, encoding="utf-8")

    kb = lambda n: f"{round(n / 1024)} KB"
    print(f"Built: {args.out.relative_to(ROOT)}")
    print(f"  data.json     : {kb(len(data_text))}")
    print(f"  receipts.json : {kb(len(receipts_text))}")
    print(f"  output size   : {kb(args.out.stat().st_size)}")
    print(f"\nOpen {args.out.name} directly in any browser — no server needed.")


if __name__ == "__main__":
    main()
