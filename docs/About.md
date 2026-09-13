# FinanzIQ — Benefits & Use Cases

## What it solves

Most personal finance tools require you to manually enter transactions, trust a third-party app with your bank credentials, or rely on cloud services that store your sensitive financial data. FinanzIQ is different: it extracts everything automatically from documents you already have, keeps all data on your machine, and gives you a richer picture than your bank's own app — including item-level receipt detail your bank never sees.

---

## Core benefits

### 1. Zero manual data entry
Drop PDFs into a folder and run one command. Payslips, bank statements, and receipts are all parsed automatically. AI Vision reads even photo receipts, extracting every line item.

### 2. Your data, your control
No bank credentials, no OAuth, no third-party app storing your complete financial history. All extracted data lives in plain files on your machine — a JSON file and a SQLite database you can inspect anytime. The AI extraction backend is your choice:
- **Ollama** — 100% local; receipt photos and PDFs never leave your machine
- **Claude** (CLI or SDK) — uses your Anthropic subscription; data sent to Anthropic during extraction only
- **Gemini** (free tier) — data sent to Google during extraction only; 1,500 req/day free via aistudio.google.com

### 3. Item-level receipt tracking
Unlike bank statements (which only show "REWE €45.20"), FinanzIQ extracts what you actually bought: 2× Avocados, 1× Coconut milk, 1× Mustard. This is the only way to know whether you're spending more on Dairy vs Produce vs Snacks over time.

### 4. Full salary transparency
German payslips are complex — income tax, pension, health insurance, care insurance, and unemployment insurance all come out before you see your net pay. FinanzIQ shows exactly where your gross pay goes, month by month and year over year.

### 5. Works offline, no server required
The standalone dashboard embeds all data directly into the HTML file. Open it on another machine, share it, or view it on a plane — no Python, no server, no internet needed.

---

## What the dashboard shows

### Overview
- Income vs expenses ratio by month, with percentage split
- Top spending categories as a donut chart
- Salary deduction breakdown — what % goes to income tax vs pension vs health insurance
- Account balance trend over time

### Income
- Gross pay vs net pay each month
- Year-to-date cumulative income
- Income by type (salary transfers, benefits, other credits)

### Spending
- Daily spending timeline — spot unusual high-spend days
- Category breakdown — which spending category dominates?
- Top merchants ranked by total spend
- True daily cost across the period (not just active spend days)

### Transactions
- Full searchable, filterable transaction history
- Filter by year, month, or spending category
- Find any payment instantly

### Insights
- Savings rate: how much of income you actually keep
- Tax burden as a real percentage
- Grocery habits, dining-out frequency
- Smart summaries across all data

### Trends
- Multi-year gross pay, net pay, spending, and balance on one chart
- Spot salary progression, lifestyle inflation, or savings improvement over years

### Year View
- Drill into any single year: monthly category breakdown
- Compare spending patterns month-to-month within a year

### Receipts
- Spend by item category (Dairy, Produce, Meat, Bakery, Beverages, Snacks, Condiments, Pantry, Household, Clothing, Healthcare, Dining, Pfand, Photos, Discounts, Other) with % breakdown
- Store-by-store spending comparison
- Monthly receipt spend trend
- Searchable item-level table: find every time you bought something specific

---

## Use cases

| Situation | How FinanzIQ helps |
|-----------|---------------------|
| "Am I saving enough?" | Savings rate KPI, income vs expense trend across years |
| "Where does my money go?" | Category donut with %, top merchants list |
| "How much tax am I paying?" | Salary deductions breakdown per payslip |
| "Did my salary grow?" | Multi-year gross/net trend chart |
| "Am I spending more on food lately?" | Receipt category trend + grocery KPI card |
| "What did I buy at Herkules last month?" | Searchable item table filtered by store and month |
| "How much did I spend on healthcare this year?" | Year View category chart + Receipts Healthcare category |
| "I need to cut spending — where to start?" | Top merchants + category breakdown show the biggest levers |
| "Planning a budget for next year" | Trends tab shows a realistic baseline from actual data |
| "Tax return preparation" | All income, deductions, and expense categories in one place |

---

## Who benefits most

- **Employees with German payslips (DATEV format)** — full payslip parsing with deduction breakdown
- **Regular grocery shoppers** — item-level receipt tracking reveals actual food spending habits
- **People who want financial clarity without giving data to a bank or fintech app** — no third-party ever holds your full financial picture
- **Anyone building a public version** — code is employer/bank agnostic and shareable

---

*Your financial data stays on your machine. Your insights are yours.*
