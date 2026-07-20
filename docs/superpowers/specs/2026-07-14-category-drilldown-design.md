# Category Drill-Down (ST3) — Design

**Date**: 2026-07-14
**Status**: approved pending user review
**Source requirement**: `docs/moneymanager-feature-reference.md` ST3 — tap a category in Stats → subcategory breakdown, monthly trend for that category, and its transaction list. Subcategory data is already stored; only the read paths and UI are missing.

**User decisions (2026-07-14)**: dedicated route (not modal/inline); mixed but explicitly labelled time windows; subcategory chips act as an active filter.

## Goal

From the Stats donut legend, open a per-category page that answers three questions: what is this category made of (subcategories), how has it moved over time (12-month trend), and which transactions produced it. Selecting a subcategory narrows the trend and the list.

## Requirements

1. Route `/stats/category/:category?direction=expense|income`; browser back works; the URL is reloadable.
2. Subcategory breakdown + transaction list scoped to **30 days** (so totals reconcile with the donut slice the user tapped); trend scoped to **12 months**, each section labelling its own window.
3. Subcategory chips ("All" + present subcategories with %) filter the trend and the transaction list. `selectedSub` is local UI state, not a URL param.
4. Reuse `GET /v1/transactions` for the list (add a `subcategory` filter) rather than inventing a list endpoint.
5. Existing invariants hold: `/v1` envelope, JWT via `router_v1`, thin route → service, `float()` at the service boundary, `isAnimationActive={false}` on the new chart, taxonomy stays the single source of truth.

## Chosen approach

Two new stat endpoints + one new filter on the existing transactions endpoint (approach B of three considered). Rejected: a single composite endpoint (breaks the one-endpoint-per-stat pattern and refetches the unchanging breakdown on every chip click) and overloading `/v1/stats/categories` with a `group_by` param (modal behaviour, less readable). With separate endpoints TanStack Query caches each piece independently: changing chip refetches only trend + list.

## Architecture

### Services — `server/services/stats.py`

Both read from `real_transactions`, matching `by_category`.

> **Invariant note (must be stated in code):** spending stats exclude internal rows (`real_transactions`); balance math includes them (`transactions`). These are deliberately opposite scopes — see `accounts.balances` / `balance_history`.

```python
def subcategory_breakdown(conn, category: str | None, days_back: int, direction: str) -> list[dict]
# -> [{"subcategory": str, "total": float, "count": int, "percentage": float}]
```
Groups by `subcategory` within one category, same sign filter and percentage math as `by_category` (percentages computed in Python over the returned rows; `float()` cast before returning). `subcategory IS NULL` collapses to the label `"No subcategory"`. Ordered by total DESC.

```python
def category_trend(conn, category: str | None, months: int, direction: str,
                   subcategory: str | None = None) -> list[dict]
# -> [{"month": "YYYY-MM", "total": float}] ascending, continuous axis
```
Monthly sums for one category, optionally narrowed to one subcategory. Totals are **positive magnitudes** via `SUM(ABS(eur_amount))`, matching `by_category` — so an expense trend rises when spending rises rather than plunging negative. **Months with no activity are emitted as `0.0`, not omitted** — a category routinely skips months and a gapped line would misread as continuous. Builds the continuous month axis in Python over the last `months` months (same technique as `balance_history`, but zero-filled rather than carried forward — different semantics: a flow, not a balance).

**`category IS NULL` handling**: the donut labels uncategorised rows `'Uncategorized'` via `COALESCE`. Both functions take `category: str | None` where `None` means "the uncategorised bucket" and produces SQL `category IS NULL`; the route layer maps the literal path segment `Uncategorized` to `None`. A literal `category = 'Uncategorized'` comparison would silently return nothing.

**`subcategory` filtering** in `category_trend` mirrors the same rule: the sentinel label `"No subcategory"` maps to `subcategory IS NULL`.

### Transactions filter — `server/services/transactions.py`

`list_transactions` gains a keyword-only `subcategory: str | None` beside the existing `category`, appending `subcategory = %s` (or `subcategory IS NULL` for the sentinel) to `conditions`. Route `GET /v1/transactions` gains the matching optional query param. No new endpoint.

### API — `server/routes/api.py`

```
GET /v1/stats/categories/{category}/subcategories?days_back=30&direction=expense
GET /v1/stats/categories/{category}/trend?months=12&direction=expense&subcategory=…
```
Both on `router_v1` (JWT enforced), `{"data": [...]}` envelope, `-> dict`, reusing `DaysBackQ` / `MonthsQ` / `DirectionQ`. `{category}` is a path param, URL-encoded by the client; the wrappers translate `"Uncategorized"` → `None` before calling the service so that mapping lives in exactly one place.

### Frontend

- `api/types.ts`: `SubcategoryStat { subcategory: string; total: number; count: number; percentage: number }`, `CategoryTrendPoint { month: string; total: number }`.
- `api/client.ts`: `api.stats.subcategories({category, days_back, direction})`, `api.stats.categoryTrend({category, months, direction, subcategory})` — both `encodeURIComponent(category)` in the path, both through the shared `unwrap`.
- `api/queries.ts`: matching `statsQueries.subcategories(...)` / `statsQueries.categoryTrend(...)`; the trend query key includes `subcategory` so chip changes refetch only it.
- `pages/CategoryDetail/CategoryDetailPage.tsx` + CSS module:
  - reads `:category` via `useParams`, `direction` via `useSearchParams` (default `expense`)
  - header: back control, category name, 30-day total, explicit period label
  - subcategory chips: "All" + rows with percentage; `selectedSub` local state
  - trend: recharts `LineChart`, 12 months, section titled with its window ("12-Month Trend"), `isAnimationActive={false}`
  - transaction list: reuses the existing transaction-row presentation, capped at 20, with a "See all" link to `/transactions` pre-filtered by category

  UI copy follows the app's existing convention: **English section titles / labels** (matching "All Accounts", "Balance", "Monthly Overview") with **Italian error messages** (matching "Impossibile caricare…").
- `App.tsx`: `<Route path="/stats/category/:category" element={<CategoryDetailPage />} />` inside the existing `<ProtectedRoute>` block.
- `StatsPage.tsx`: legend items become clickable, navigating with the current tab's direction as a query param. Keyboard-accessible (real button/link semantics, not a bare `onClick` div).

### Empty and error states

Category with no subcategories at all → chips show only "All", breakdown section hidden rather than rendering an empty box. No transactions in the window → explicit empty message, not a blank area. Query failures surface a message per section (the balance-history lesson: a failed fetch must not render as a silently empty chart).

## Testing

- Services: percentages sum to ~100; `category=None` produces `category IS NULL` (SQL pinned, as with the calibration-scope test); NULL subcategories collapse to the sentinel; subcategory filter narrows the trend; empty months emitted as `0.0`; values are `float` not `Decimal`.
- Transactions service: `subcategory` filter appends the right condition; sentinel maps to `IS NULL`; existing filters unaffected.
- API: 401 unauthenticated; envelope shape; JSON numbers not strings; 422 on out-of-range `days_back` / `months`; URL-encoded category with a space round-trips.
- Frontend: page renders all three sections from mocked queries; clicking a chip refetches trend + list with the subcategory; StatsPage legend navigates to the right URL with direction preserved.

## Out of scope (YAGNI)

Period selector inside the detail page (that is ST1), second-level drill-down on subcategories, editing a transaction's category from this page, chart-colour unification with the donut (tracked separately in the taxonomy follow-ups), and caching/memoising beyond TanStack Query defaults.

## Decisions log

- Dedicated route over modal/inline: back-button and reload semantics, and three sections need room (user choice 2026-07-14).
- Mixed windows (30d breakdown+list, 12m trend), each labelled: keeps totals reconciled with the donut the user tapped while still showing real history (user choice 2026-07-14).
- Subcategory chips filter trend + list rather than being informational (user choice 2026-07-14).
- Zero-fill (not carry-forward) for trend gaps: this series is a flow, unlike `balance_history` which is a stock.
- `selectedSub` stays local state: the shareable unit is the category page; a chip is a transient view.
