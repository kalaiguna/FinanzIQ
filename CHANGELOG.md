# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] - 2026-09-13

Categorizer improvements, project documentation, and git initialisation.

### Added
- `CLAUDE.md` — project guide for Claude Code: HTTP server requirement, nested transaction
  structure, recategorize-without-reparsing pattern, categorizer priority rules, dashboard
  architecture quirks, data scope notes.
- `.gitignore` — excludes all personal financial data (`data.json`, `receipts.db`, manifests,
  `downloads/` contents, `data/raw/`, `data/receipts/`, generated `standalone.html`); keeps
  `.gitkeep` files so folder structure is preserved in the repo.
- `LICENSE` — MIT, copyright 2026 Gunasekaran Chandrasekaran.
- `CHANGELOG.md` — this file.
- `.gitkeep` files in `data/processed/`, `data/raw/`, `data/receipts/` so inbox and archive
  folders are tracked by git without committing personal data.

### Changed
- `README.md` rewritten end-to-end: correct workflow (`downloads/kassenbons/` → `run.bat`),
  HTTP server requirement, all 7 dashboard tabs documented, backend auto-detection explained.
- `scripts/parsers/categorizer.py` — expanded keyword rules across all categories:
  - Added: `'mcdonald'`, `'kentucky fried'`, `'gastro'`, `'ristorante'`, `'vgf '`,
    `'transdev'`, `'taxi '`, `'gozo channel'`, `'farmacia'`, `'apothe'`, `'nkd '`,
    `'h+m'`, `'tkmaxx'`, `'decathlon'`, `'aäa gmbh'` (Healthcare),
    `'termini b dir'`, `'termini dir. lau'`, `'roma ostiense ss'` (Transport),
    `'mamas fast food'`, `'nazar gmbh'`, `'wiener cafehaus'`, `'tiffany s kiosk'`,
    `'cafe kissler'` (Dining).
  - Removed from Childcare: `'bad vilbel'`, `'kreis'`, `'stadt bad'` — too broad, matched
    hundreds of shop addresses in Bad Vilbel city rather than childcare institutions.

## [1.1.0] - 2026-09-01

Receipt processor pipeline: Claude Vision extraction, SQLite storage, kassenbons inbox.

### Added
- `downloads/kassenbons/` — inbox folder for receipt photos (JPG/PNG) and digital receipt PDFs.
- `scripts/parsers/receipt_parser.py` — Claude Vision extraction with two backends: Anthropic SDK
  (when `ANTHROPIC_API_KEY` is set) and `claude` CLI via `--input-format stream-json` (uses Claude
  Code subscription). Images resized to 1500 px max before sending. PDF text extracted via
  pdfplumber and batched into a single Claude call. Returns structured JSON.
- `scripts/process_receipts.py` — receipt orchestrator: scans `downloads/kassenbons/`, deduplicates
  via `receipts_manifest.json`, calls `receipt_parser`, validates item sums (±€0.10), saves to
  SQLite, archives images to `data/receipts/YYYY/MM/`, exports `receipts.json` for the dashboard.
- `data/processed/receipts.db` — SQLite database: `receipts` table (one row per receipt) and
  `items` table (one row per line item with `raw_name`, `clean_name`, `category`, `qty`,
  `unit_price`, `total`, `vat_rate`).
- `data/processed/receipts.json` — receipt data as JSON for the dashboard; auto-generated on every
  run of `process_receipts.py`.
- `data/processed/receipts_manifest.json` — dedup guard: tracks processed filenames.
- Dashboard: **Receipts** tab — item-level receipt browser with store, date, total, item count,
  validation status, and expandable item list. Year filter. Reads from `receipts.json` (live) or
  `window.__EMBEDDED_RECEIPTS__` (standalone). 16-item categories: `Dairy`, `Produce`, `Meat`,
  `Bakery`, `Beverages`, `Snacks`, `Condiments`, `Pantry`, `Household`, `Clothing`, `Pfand`,
  `Dining`, `Healthcare`, `Photos`, `Discounts`, `Other`.
- `build.py` updated: injects `window.__EMBEDDED_RECEIPTS__` alongside `window.__EMBEDDED_DATA__`
  into `standalone.html`.

### Changed
- `run.bat` updated to 4 steps: payslips → kassenbons → build standalone → open dashboard.
- `CLAUDE.md` updated with receipt processing details, kassenbons inbox path, validation tolerance,
  and item category list.

## [1.0.0] - 2026-07-01

Initial build: German payslip and bank statement parsing, categorization, and dashboard.

### Added
- `scripts/parsers/payslip_parser.py` — deterministic DATEV Brutto-Netto-Abrechnung parser using
  pdfplumber and regex. Extracts gross pay, net pay, tax, social contributions, and all line items.
  Confidence threshold (`CONFIDENCE_THRESHOLD = 80`); falls back to Claude extraction when below.
- `scripts/parsers/bank_parser.py` — deterministic Kontoauszug (German bank statement) parser.
  Extracts transactions with date, merchant, amount, and type. pdfplumber-based.
- `scripts/parsers/categorizer.py` — keyword-rule categorizer: ordered `(keywords, category)`
  tuple list. First match wins. 14 categories: `Income`, `Salary`, `Rent`, `Childcare`,
  `Groceries`, `Dining`, `Utilities`, `Transport`, `Healthcare`, `Insurance`, `Entertainment`,
  `Shopping`, `Banking`, `Other`.
- `scripts/process_payslip.py` — orchestrates payslip and bank statement parsing; writes
  `data/processed/data.json` and `data/processed/manifest.json`; deduplicates via manifest.
- `data/processed/data.json` — main data store: `payslips[]` and `bank_statements[]` with nested
  `transactions[]`.
- `dashboard/index.html` — single-file dashboard (HTML + CSS + JS, ~785 KB); 7 tabs: Overview,
  Transactions, Payslips, Receipts, Analytics, Budget, Settings. Chart.js 4.4.1 (CDN). `safeRender()`
  wraps every tab so one crash does not silence others. `showPage()` calls `chart.resize()` on tab
  switch to fix 0×0 chart dimensions in hidden tabs.
- `build.py` — inlines `data.json` as `window.__EMBEDDED_DATA__` into `standalone.html`; output
  opens via `file://` with no HTTP server.
- `launch.py` — starts Python HTTP server on a free port and opens the dashboard in the browser.
- `run.bat` — double-click workflow: process payslips/bank statements → build standalone → open
  live dashboard.
- `scripts/organize_downloads.py` — moves processed PDFs from `downloads/` into
  `data/raw/YYYY/MM/` archive.
- Data scope: bank statements and payslips from **July 2022 onwards**.

[Unreleased]: https://github.com/g-aa-chandrasekaran/finanziq/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/g-aa-chandrasekaran/finanziq/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/g-aa-chandrasekaran/finanziq/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/g-aa-chandrasekaran/finanziq/releases/tag/v1.0.0
