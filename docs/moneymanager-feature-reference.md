# MoneyManager Feature Reference (functional requirements)

Extracted 2026-07-13 from the user's annotated Figma board
([moneymanager](https://www.figma.com/design/EHBnXJUY3pIOAoZ1YFCE6C/moneymanager?node-id=1-6822), 16 app
screenshots + 7 green arrows marking flows). **Functionality reference only — NOT a style guide**: fimbook
keeps its own design. Status column = fimbook as of 2026-07-13.

## Transactions (Trans. tab)

| # | Feature | Detail from board | fimbook status |
|---|---------|-------------------|----------------|
| T1 | Month navigation | `< June 2026 >` header on every list view | ❌ (fixed `days_back=90`) |
| T2 | View tabs | Daily / Calendar / Monthly / Total (Note unused — "No data available") | 🟡 Daily+Monthly grouping exist; no Calendar, no Total |
| T3 | Period summary header | Income / Expenses / Total for the visible period | ✅ (summary header) |
| T4 | Rich transaction rows | category **and subcategory**, account name, recurrence tag ("Revolut - Subscriptions (Every Month)") | 🟡 category only |
| T5 | Calendar view | month grid with per-day totals | ❌ |
| T6 | Monthly view (year) | months expandable into weeks (`28.06 ~ 04.07`) with income/expenses per week | ❌ |
| T7 | Total view | Budget section (+ Budget Setting), expenses vs last month %, per-account-type breakdown, **Export data to Excel** | ❌ (CSV export already a MorePage placeholder) |
| T8 | Foreign currency on row | `US$ 24.40` shown in original currency | 🟡 currency code shown, not original amount |

## Add / Edit transaction (arrows: FAB `+` → these forms)

| # | Feature | Detail | fimbook status |
|---|---------|--------|----------------|
| A1 | Three types | Income / Expense / **Transfer** (From→To accounts, **Fees** field) | 🟡 income/expense only, no transfer |
| A2 | Recurrence / installments | "Rep/Inst." control on Date row | ❌ |
| A3 | Account field | pick which account the tx belongs to | ❌ (column exists in schema, absent in form) |
| A4 | Date **with time** | `12/7/26 (Sun) 17:36` | 🟡 date only |
| A5 | Description + photo attachment | camera icon on Description | ❌ |
| A6 | Save + Continue | Continue = save and keep the form open for rapid entry | ❌ |

## Search & filters (arrows: 🔍 → search screen, ⚙ → account selector)

| # | Feature | Detail | fimbook status |
|---|---------|--------|----------------|
| S1 | Search screen | full-text + filters: Period, Account, Category, Amount Min~Max | 🟡 text search only |
| S2 | Account selector panel | filter any view by account group (Cash / Accounts / Debit Card / Savings), per-account checkboxes | ❌ |

## Stats

| # | Feature | Detail | fimbook status |
|---|---------|--------|----------------|
| ST1 | Period selector | Weekly / Monthly / **Annually** dropdown + year/month navigation | ❌ (fixed 30 days) |
| ST2 | Expense & income pies | per-category donut with % badges + amounts legend | ✅ (2026-07-12) |
| ST3 | **Category drill-down** (green arrow from legend → detail) | tap category → subcategory breakdown (All / Car rental 43% / Fuel 36% / Tolls 20%...), **monthly trend line for that category**, transaction list of that category | ❌ — data already stored (subcategory), UI missing |

## Accounts

| # | Feature | Detail | fimbook status |
|---|---------|--------|----------------|
| AC1 | Account groups | Cash / Accounts (Mediobanca Premier, Mediocredito Trentino) / Debit Card (MP Debit + 4 Revolut) / **Savings** with group subtotals | 🟡 flat EB list only |
| AC2 | Assets / Liabilities / Total header | net worth split | ✅ |
| AC3 | **Total Stats** (green arrow: 📊 icon → this screen — the node the user linked) | **balance-over-time line chart** (Feb 100,000 → July 156,276) + monthly income/expenses bar chart | 🟡 bar chart exists; balance history line ❌ |

## Cross-cutting notes

- Multi-account (Mediobanca, MP, cash, savings) presupposes the **multi-source gateway** already planned in CLAUDE.md "Next".
- Transfers between own accounts relate to the existing `is_internal` logic — a Transfer type must not pollute income/expense stats.
- Balance-over-time (AC3) needs opening balances per account: EB history alone gives running deltas, not absolute balances.
- Priority hint from the user's link anchor (node 1-6822 → Total Stats arrow): AC3 first, then ST3 (both are chart-level features on existing data).

Related deferred items: see memory `taxonomy_followups` and `.superpowers/sdd/progress.md`.
