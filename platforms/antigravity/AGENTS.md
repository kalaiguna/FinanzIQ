# FinanzIQ — Project Guide for Antigravity

## Runtime backend

```
FINANZIQ_BACKEND=antigravity
GEMINI_API_KEY=<from Google AI Studio — aistudio.google.com, no credit card required>
```

The `GEMINI_API_KEY` free tier allows 1,500 requests/day — far more than FinanzIQ's typical workload (~30 receipts/month).

---

## Workflow

```
downloads/
  payslips/         ← drop payslip PDFs
  bank_statements/  ← drop bank statement PDFs
  kassenbons/       ← drop receipt photos (JPG/PNG) or digital PDFs
       ↓
python scripts/process_payslip.py   → data/processed/data.json
python scripts/process_receipts.py  → data/processed/receipts.db + receipts.json
       ↓
python build.py                     → dashboard/standalone.html
python launch.py                    → live dashboard (HTTP server)
```

Or just double-click `run.bat` — runs all four steps.

---

## Key facts

- **Transactions are nested:** `bank_statements[].transactions[]` — not a flat top-level array. Any script iterating transactions must loop over both levels.
- **Re-categorize without re-parsing:** update `scripts/parsers/categorizer.py` rules, then run `scratchpad/recategorize.py` — no PDF re-parsing needed.
- **Never open `index.html` directly via `file://`** — `fetch()` is blocked by CORS. Use `python launch.py` (HTTP server) or open `dashboard/standalone.html` instead.
- **Pydantic schemas** for receipt extraction live in `core/schemas.py` — imported by all platform adapters.
- **Platform adapter** for this backend: `platforms/antigravity/adapter.py` (Gemini SDK, `response_schema=ReceiptData`).

---

## Platform adapter architecture

```
core/adapter.py          ← dispatcher (reads FINANZIQ_BACKEND env var)
platforms/claude/        ← Anthropic SDK + claude CLI
platforms/antigravity/   ← Gemini API (this platform)
platforms/ollama/        ← local models via localhost:11434
```

Switch backends:
```
set FINANZIQ_BACKEND=antigravity   ← Gemini (this platform)
set FINANZIQ_BACKEND=claude        ← Claude SDK / CLI
set FINANZIQ_BACKEND=ollama        ← local Ollama model
```

---

## Categorizer rules

`scripts/parsers/categorizer.py` — ordered `(keywords, category)` tuples. First match wins.
Rule order matters: put more specific rules before broader ones (e.g. `allianz gastro` before `allianz`).

---

## Data scope

- Bank statements and payslips: **July 2022 onwards**
- Receipts: **April 2026 onwards** (earliest available Kassenbon)
