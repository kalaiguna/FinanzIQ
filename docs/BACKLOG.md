# FinanzIQ — Backlog

> Forward-looking only. Completed work is in CHANGELOG.md. Architecture decisions are in CLAUDE.md.

---

## High priority

### Telegram Bot — primary input method
Send any financial document to the bot; it extracts, saves, and replies with a summary. Replaces the manual file-drop-to-folder workflow entirely.

**Document types handled:**

| What you send | Bot does | Saves to |
|---------------|----------|---------|
| Receipt photo (JPG/PNG) | `adapter.extract_image()` → validate → archive | `receipts.db` |
| Digital receipt PDF (Rossmann, DM, etc.) | extract text → `adapter.extract_pdf_text()` → validate | `receipts.db` |
| Payslip PDF | `classify_pdf()` → `extract_payslip()` | `data.json` |
| Bank statement PDF | `classify_pdf()` → `extract_bank_statement()` | `data.json` |

**Implementation notes:**
- Library: `python-telegram-bot`
- Whitelist by Telegram user ID — no public access
- Uses `core.adapter.get_adapter()` — works with all three backends (Claude, Gemini, Ollama) unchanged
- Auto-classify PDFs via `classify_pdf()` from `process_payslip.py` (payslip keywords → payslip, else bank/receipt)
- Reply with a one-line summary: store, date, total for receipts; period, gross, net for payslips
- Hosting options:
  - **Local PC**: all three backends work; bot only responds when PC is on
  - **Oracle Cloud Free VM**: Claude SDK + Gemini work from anywhere; Ollama requires installation on the VM
- Commands: `/summary`, `/receipts [month]`, `/spending [category]`

### MCP Server
Expose FinanzIQ data as MCP tools so AI assistants can query your finances conversationally.

- Tools: `finanziq_get_summary`, `finanziq_search_receipts`, `finanziq_get_transactions`, `finanziq_category_spend`
- Reads from `data.json` + `receipts.db` — no new pipeline, just a query layer
- Useful for asking Claude/Gemini "how much did I spend on groceries this year?"

---

## Medium priority

### Manual recategorization UI
Click-to-reassign a category in the Transactions tab. Currently requires editing `categorizer.py` and re-running the recategorize script — fine for infrequent fixes but friction for one-off corrections.

### Budget targets
Set a monthly ceiling per category (e.g. Groceries €400). Show progress bars on the Overview tab. Alert when approaching/exceeding.

### CSV export
One button to download filtered transactions as CSV — useful for tax prep, accountants.

### Month-over-month delta
"You spent €120 more on Groceries than last month" — a single-row summary on Overview. Low effort, high-signal.

### Mobile-responsive dashboard
`standalone.html` is not optimized for phones. The layout breaks on small screens. Chart.js supports responsive sizing — mostly a CSS task.

### Automated scheduling
Windows Task Scheduler to run the pipeline automatically (e.g. weekly) without double-clicking `run.bat`.

---

## Lower priority / deferred

### Oracle Cloud Free VM deployment
4 vCPUs, 24 GB RAM, 200 GB storage, always-on, free. Best fit if going cloud: SQLite works unchanged, Telegram Bot runs 24/7, dashboard accessible via Tailscale. Only relevant if local-only becomes a limitation.

### PDF summary export
Monthly summary as a printable PDF for records or sharing.

### Forecasting
"At this rate" spend projections for the current month or year.

### Multi-currency support
For accounts with non-EUR transactions.

### Dark/light theme toggle
Dashboard is currently dark-only.

### Public repo split
Code-only copy without personal data — for sharing or community use.

---

## Future adapter extensions

All adapters implement the same three-function interface (`extract_image`, `extract_pdf_text`, `extract_pdf_batch`) and require only a new file in `platforms/<name>/adapter.py`.

### AI runtime adapters (receipt extraction)

| Platform | Adapter approach | Vision | Notes |
|----------|-----------------|--------|-------|
| **`openai`** | `openai` SDK (GPT-4o Vision) | ✅ | Near-identical code to Antigravity adapter; paid |
| **`lmstudio`** | OpenAI-compatible HTTP at `localhost:1234` | ✅ | Share Ollama adapter with a configurable base URL env var |
| **`mistral`** | `mistralai` SDK (Pixtral-12B) | ✅ | Free tier, but more limited than Gemini's |
| **`groq`** | `groq` SDK | ❌ no vision yet | Fast text; not suitable for receipt extraction until vision ships |

`lmstudio` and `ollama` are structurally identical — both OpenAI-compatible. If `lmstudio` is needed, the Ollama adapter can be extended with a `FINANZIQ_OLLAMA_BASE_URL` / `FINANZIQ_LMSTUDIO_BASE_URL` env var rather than a separate adapter.

### IDE context adapters (config files only, no Python)

| Tool | Config file | Status |
|------|------------|--------|
| Claude Code | `CLAUDE.md` | ✅ Done |
| Antigravity | `platforms/antigravity/AGENTS.md` | ✅ Done |
| GitHub Copilot | `.github/copilot-instructions.md` | Future if needed |
| Cursor | `.cursorrules` | Future if needed |
| Continue.dev | `.continuerc.json` | Future if needed |

---

## Architecture notes

- `dashboard/index.html` is a single large file (~785 KB). If it grows, consider splitting CSS/JS with a simple bundler.
- The categorizer uses keyword rules. A UI-driven approach would let users manage rules without touching Python.
- `standalone.html` (~1.95 MB) embeds all data inline. If data grows significantly, consider lazy-loading or splitting by year.
- Receipt images are resized to 1500 px max before sending to Claude/Gemini — balances quality and token cost.
- SQLite (`receipts.db`) is the right store for receipt data at current scale. If the Telegram bot creates high write frequency, consider WAL mode: `PRAGMA journal_mode=WAL`.

---

*Last updated: 2026-09-13*
