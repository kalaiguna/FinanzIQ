# FinanzIQ — Personal Finance Dashboard

A personal finance dashboard for German payslips (DATEV format), bank statements (Kontoauszug), and store receipts (Kassenbons).
Your financial data stays on your machine — no bank credentials, no third-party sync, no fintech app storing your history. The AI extraction backend is your choice: fully local (Ollama), or cloud AI (Claude / Gemini).

→ See [About.md](docs/About.md) for a full feature overview and use cases.

---

## How it works

```
downloads/payslips/          ← drop payslip PDFs here
downloads/bank_statements/   ← drop bank statement PDFs here
downloads/kassenbons/        ← drop receipt photos (JPG/PNG) or digital PDFs here
     ↓
run.bat                      ← double-click: process everything + open dashboard
```

`run.bat` runs four steps in sequence: payslips/bank statements → kassenbons → build standalone HTML → open live dashboard. Steps with empty inboxes are skipped automatically.

**Two ways to view the dashboard:**

| Mode | How | Requires |
|------|-----|---------|
| **Live** | `python launch.py` or `run.bat` | Python running |
| **Standalone** | Open `dashboard/standalone.html` directly | Nothing — works via `file://` |

`standalone.html` is regenerated on every `run.bat`. The live mode (`index.html`) fetches JSON at runtime; the standalone has all data inlined.

---

## Setup (one-time)

```bash
pip install pdfplumber        # PDF text extraction (payslips + bank statements + digital receipts)
pip install Pillow            # image resizing for scanned receipt photos
```

**Backend — pick one:**

| Backend | How to activate | Cost |
|---------|----------------|------|
| `claude` (default) | Install Claude Code CLI — no API key needed | Subscription |
| `antigravity` | `set GEMINI_API_KEY=AIza...` (free key from aistudio.google.com) | Free tier |
| `ollama` | `ollama serve` + `ollama pull qwen2.5-vl` | Free (local) |

The backend is auto-detected from available keys and binaries. Override with `set FINANZIQ_BACKEND=antigravity` (or `claude` / `ollama`).

For `antigravity`: `pip install google-genai`
For `ollama`: `pip install requests`

---

## Monthly workflow

### All-in-one

Double-click `run.bat`. It runs all four steps:

1. `scripts/process_payslip.py` — parses new payslip/bank PDFs → `data.json`
2. `scripts/process_receipts.py` — processes new kassenbons → `receipts.db` + `receipts.json`
3. `build.py` — regenerates `dashboard/standalone.html` with data inlined
4. `launch.py` — starts the HTTP server and opens the browser

Empty inboxes are skipped without error. Processing errors print a warning but the remaining steps still run.

To run individual steps manually:
```bash
python scripts/process_payslip.py   # payslips + bank statements only
python scripts/process_receipts.py  # kassenbons only
python build.py                     # rebuild standalone.html
python launch.py                    # open live dashboard
```

**Deduplication:** already-processed files are tracked in `data/processed/manifest.json` (payslips/bank) and `data/processed/receipts_manifest.json` (kassenbons). Re-running is always safe.

The payslip script auto-detects document type from filename keywords:
- **Payslips:** `brutto-netto`, `abrechnung`, `gehalts`, `lohn`
- **Bank statements:** `konto`, `auszug`

### Kassenbons detail

Drop receipt photos (JPG/PNG) or digital PDFs (Rossmann, DM, Penny, etc.) into `downloads/kassenbons/`.

- Digital PDFs: text extracted via pdfplumber, sent to the active AI backend
- Scanned images: downsized to 1500 px max, sent to the active AI backend via Vision API
- Both saved to `receipts.db` and archived to `data/receipts/YYYY/MM/`

The active backend is selected automatically — see Setup above.

---

## Folder structure

```
finanziq/
├── core/
│   ├── adapter.py              ← backend dispatcher (FINANZIQ_BACKEND env var + auto-detect)
│   ├── prompts.py              ← shared receipt extraction prompts
│   └── schemas.py              ← Pydantic models: ReceiptData, ReceiptItem
├── platforms/
│   ├── claude/
│   │   └── adapter.py          ← Anthropic SDK + claude CLI
│   ├── antigravity/
│   │   ├── AGENTS.md           ← project guide for Antigravity (mirrors CLAUDE.md)
│   │   └── adapter.py          ← Gemini API (google-genai SDK)
│   └── ollama/
│       └── adapter.py          ← local Ollama via OpenAI-compatible HTTP
├── scripts/
│   ├── parsers/
│   │   ├── bank_parser.py      ← German bank statement parser (Kontoauszug format)
│   │   ├── payslip_parser.py   ← DATEV payslip parser (Brutto-Netto-Abrechnung format)
│   │   ├── categorizer.py      ← merchant → spending category rules
│   │   └── receipt_parser.py   ← JSON parsing helpers, PDF text extraction, validation
│   ├── process_payslip.py      ← orchestrates payslip/bank parsing → data.json
│   ├── process_receipts.py     ← orchestrates receipt extraction → receipts.db
│   └── organize_downloads.py   ← moves PDFs from downloads/ to data/raw/
├── tests/
│   ├── conftest.py             ← pytest sys.path setup
│   └── test_core.py            ← 59 unit tests (deterministic logic only)
├── dashboard/
│   ├── index.html              ← live dashboard (fetches JSON at runtime)
│   └── standalone.html         ← self-contained dashboard (data inlined, opens via file://)
├── data/
│   ├── processed/
│   │   ├── data.json           ← payslip + bank statement data
│   │   ├── manifest.json       ← payslip/bank dedup tracker
│   │   ├── receipts.db         ← SQLite: receipts + items tables
│   │   ├── receipts.json       ← receipt data for dashboard (auto-generated)
│   │   └── receipts_manifest.json  ← receipt dedup tracker
│   ├── raw/YYYY/MM/            ← archived payslips + bank statements
│   └── receipts/YYYY/MM/       ← archived receipt images/PDFs
├── downloads/
│   ├── payslips/               ← inbox: payslip PDFs
│   ├── bank_statements/        ← inbox: bank statement PDFs
│   └── kassenbons/             ← inbox: receipt photos (JPG/PNG) + digital PDFs
├── docs/
│   ├── About.md                ← full feature overview and use cases
│   ├── CHANGELOG.md            ← version history
│   └── BACKLOG.md              ← planned features and future work
├── CLAUDE.md                   ← project guide for Claude Code
├── build.py                    ← inlines data into standalone.html
├── launch.py                   ← HTTP server + browser launcher
└── run.bat                     ← double-click: process all + build standalone + launch
```

---

## Dashboard tabs

| Tab | What you see |
|-----|-------------|
| **Overview** | KPI cards, year-wise summary chart, spending donut, salary deductions |
| **Income** | Payslip breakdown (gross, tax, social security, net), YTD chart |
| **Spending** | Daily timeline, category breakdown, top merchants |
| **Transactions** | Searchable/filterable table of all bank transactions |
| **Insights** | Savings rate, tax burden, grocery habits, and other smart summaries |
| **Trends** | Full multi-year timeline — gross pay, net pay, spending, and balance |
| **Year View** | Drill into one year: monthly breakdown, category spending, year savings |
| **Receipts** | Item-level receipt data: category donut, store breakdown, monthly trend, searchable items table |

All tabs respond to the **Year** and **Month** filter dropdowns (top right), except Trends which always shows the full timeline.

---

## Transaction categories (bank statements)

`scripts/parsers/categorizer.py` maps merchant names to categories using keyword rules:

`Income` · `Salary` · `Rent` · `Childcare` · `Groceries` · `Dining` · `Utilities` · `Transport` · `Healthcare` · `Insurance` · `Entertainment` · `Shopping` · `Banking` · `Other`

To fix a miscategorized merchant: add a keyword to the matching rule in `categorizer.py`, then re-run the recategorize script (see CLAUDE.md for the snippet). No PDF re-parsing needed.

## Receipt item categories

`Dairy` · `Produce` · `Meat` · `Bakery` · `Beverages` · `Snacks` · `Condiments` · `Pantry` · `Household` · `Clothing` · `Pfand` · `Dining` · `Healthcare` · `Photos` · `Discounts` · `Other`

Assigned by the AI backend during extraction. No manual rules — re-run `process_receipts.py --force` to re-extract if needed.

---

## Supported documents

| Type | Supported |
|------|-----------|
| Payslips | DATEV Brutto-Netto-Abrechnung format |
| Bank statements | German bank Kontoauszug PDF |
| Receipt photos | Any store — JPG, PNG (one receipt per image) |
| Digital receipts | Rossmann, DM, Penny, and other stores with PDF e-receipts |
| Other banks / employers | Not supported |

---

## Privacy

- **Your stored data is always local** — `data.json`, `receipts.db`, and archived files stay on your disk
- **No bank credentials, no OAuth, no third-party app** storing your financial history
- The HTTP server listens on `localhost` only
- **AI extraction**: Ollama is 100% local. Claude and Gemini send receipt photos/PDF text to Anthropic/Google during extraction only — your processed output never leaves your machine

---

## Docs

| File | Contents |
|------|---------|
| [docs/About.md](docs/About.md) | Full feature overview, use cases, who benefits |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Version history |
| [docs/BACKLOG.md](docs/BACKLOG.md) | Future features and planned work |
