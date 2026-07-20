# Stats Period Selector (ST1) — Design

**Date**: 2026-07-14
**Status**: approved pending user review
**Source requirement**: `docs/moneymanager-feature-reference.md` ST1 — period selector (Weekly / Monthly / Annually) with year/month navigation. Today `StatsPage` is hardcoded to `days_back=30` and the whole read layer only understands rolling windows.

**User decisions (2026-07-14)**: navigable **calendar** periods (not rolling windows); **week + month + year** granularities; the category drill-down **inherits the selected period** for its breakdown and transaction list, while its trend stays a 12-month series.

## Goal

Let the user answer "what did June actually cost me, and how does it compare to May?" — which a rolling 30-day window can never answer, because its totals shift every day. Stats gains a granularity selector and prev/next navigation over real calendar periods, and the drill-down follows the period the user is looking at.

## Why calendar periods, not rolling windows

Every read function currently filters `booking_date >= NOW() - (N * INTERVAL '1 day')` (`by_category`, `subcategory_breakdown`, `list_transactions`). Rolling windows make period-over-period comparison impossible and make totals non-reproducible: the same "last 30 days" query returns different numbers tomorrow. Calendar periods have stable boundaries, which is what makes month-over-month meaningful.

## Requirements

1. Granularities: `week` (ISO, Monday–Sunday), `month`, `year`. Prev/next navigation within the chosen granularity.
2. Period state lives in the **URL** (`?granularity=month&anchor=2026-06`), not component state — reload and share preserve it, and the drill-down inherits it by propagation.
3. `by_category` and `subcategory_breakdown` take an inclusive `date_from` / `date_to` range instead of `days_back`.
4. `list_transactions` gains optional `date_from` / `date_to` and **keeps** `days_back` (transitional — see below).
5. The drill-down's subcategory breakdown and transaction list use the inherited period; its trend stays a rolling 12-month series with its own explicit label.
6. Existing invariants hold: `/v1` envelope, JWT via `router_v1`, thin route → service, `float()` at the service boundary, spending stats read `real_transactions`, `isAnimationActive={false}` on charts, English labels / Italian error messages.

## Architecture

### Where calendar math lives

The backend stays ignorant of calendar semantics: it receives two explicit dates and filters. All granularity logic lives in one frontend module, because the frontend needs boundary math anyway to render the label and to step prev/next — computing it server-side too would duplicate it.

### Backend — `server/services/stats.py`

```python
def by_category(conn, date_from: date, date_to: date, direction: str = "expense") -> list[dict]
def subcategory_breakdown(conn, category: str | None, date_from: date, date_to: date, direction: str) -> list[dict]
```

`days_back` is **removed** from both — their only callers are the stats routes, updated in the same change, so no dual path is introduced.

Date filter, in both:
```sql
AND booking_date >= %s
AND booking_date < %s::date + INTERVAL '1 day'
```
`date_to` is **inclusive**; the half-open upper bound is what makes the last day's rows count without an off-by-one. Do not switch to `<=` on a timestamp column — a row at `2026-06-30T14:00Z` would still be included but the intent would be less obvious, and a future date-only comparison would silently drop it.

### Backend — `server/services/transactions.py`

`list_transactions` gains keyword-only `date_from: date | None = None`, `date_to: date | None = None`. When both are supplied they replace the `days_back` condition; otherwise the existing `days_back` condition applies unchanged.

> **Transitional dual path, with an owner.** `days_back` stays only because `TransactionsPage` still uses it; converting that page to calendar periods is **T1** (month navigation on Transactions) and will remove `days_back` from this function. This mirrors how the project already handled the legacy unversioned API mount — a bridge with a named successor, not an open-ended compatibility shim. Do not add new callers of `days_back`.

### Backend — `server/routes/api.py`

Stats routes take `date_from: date` and `date_to: date` as required query params (FastAPI parses `YYYY-MM-DD` into `date` natively):

```
GET /v1/stats/categories?date_from=&date_to=&direction=
GET /v1/stats/categories/{category}/subcategories?date_from=&date_to=&direction=
GET /v1/transactions?...&date_from=&date_to=      # optional, alongside days_back
```

`/v1/stats/categories/{category}/trend` is unchanged — it stays a rolling `months` series.

**Validation** in a shared helper so all three routes behave identically: reject `date_from > date_to`, and reject spans longer than **366 days counted inclusively** (`(date_to - date_from).days + 1 > 366`). A leap year is exactly 366 inclusive days, so the cap must admit it — counting exclusively would reject February-inclusive leap years and the bug would surface only in 2028. Both checks raise `HTTPException(422)` with a specific message.

### Frontend — `src/lib/period.ts` (new, pure)

The single home for calendar math. No React, no network — fully unit-testable.

```ts
export type Granularity = 'week' | 'month' | 'year';

// Canonical anchor per granularity:
//   week  -> 'YYYY-MM-DD' of that week's MONDAY
//   month -> 'YYYY-MM'
//   year  -> 'YYYY'
export function periodBounds(g: Granularity, anchor: string): { from: string; to: string };  // YYYY-MM-DD, inclusive
export function shiftPeriod(g: Granularity, anchor: string, delta: 1 | -1): string;
export function formatPeriodLabel(g: Granularity, anchor: string): string;
export function currentAnchor(g: Granularity): string;
export function parsePeriodParams(
  granularity: string | null, anchor: string | null,
): { granularity: Granularity; anchor: string };
```

**Anchors are canonical.** A week anchor is always normalised to that week's Monday — every function that produces an anchor (`currentAnchor`, `shiftPeriod`, `parsePeriodParams`) returns the normalised form, so the URL has exactly one representation per period and query keys never split on an equivalent-but-different anchor.

Weeks are ISO (Monday start), matching both Italian convention and Postgres `DATE_TRUNC('week')`. `shiftPeriod` must handle year rollover (Dec→Jan), leap days (29 Feb), and week shifts crossing month/year boundaries — these are the cases the tests pin.

**URL params are untrusted input.** `parsePeriodParams` is the single entry point both pages use: an unknown granularity, a malformed anchor, or an anchor whose shape doesn't match its granularity falls back to the default (current month) rather than throwing or producing `Invalid Date`. Pages never parse the query string themselves.

### Frontend — StatsPage

Header gains a granularity segmented control (Week / Month / Year) and a `‹ label ›` navigator. Period state is read from and written to the URL via `useSearchParams` (`granularity`, `anchor`); absent params default to the current month. Category and monthly queries key on the resolved bounds, so navigation refetches naturally.

The existing **Monthly Overview** bar chart and **By Month** list stay on their own rolling 12-month series (`statsQueries.monthly`) and are deliberately NOT period-scoped — they are multi-month views by nature. Their current titles already read as such, so **no relabelling is required**; leave both sections untouched apart from continuing to render below the period-scoped donut.

### Frontend — CategoryDetailPage

Reads `granularity` / `anchor` from the query string (same defaults), resolves bounds with the same helper, and passes them to the subcategory and transaction queries. The trend stays 12 months. The header's period label reflects the inherited period rather than a hardcoded "ultimi 30 giorni". The Stats legend link propagates the current `granularity` and `anchor` alongside `direction`.

## Empty and error states

A period with no data renders explicit empty states (no transactions / no subcategories), never a blank area. Query failures surface a per-section message, unchanged from ST3. Navigating far into the past is allowed and simply shows empty periods — no artificial floor.

## Testing

- `period.ts`: month/year/week bounds; Monday-start weeks; `shiftPeriod` across Dec→Jan, Jan→Dec, and a leap day; week shift crossing a month boundary; label formatting per granularity; `currentAnchor` shape per granularity.
- Services: the range filter binds both dates; `date_to` is inclusive (a row on the last day is counted); `days_back` no longer accepted by the two stats services; `list_transactions` uses the range when both dates are given and falls back to `days_back` otherwise.
- API: 422 when `date_from > date_to`; 422 when the span exceeds 366 days; 200 with a valid range; unchanged 401 behaviour.
- Frontend: StatsPage reads the period from the URL and refetches on granularity change and on prev/next; the legend link carries granularity+anchor; CategoryDetailPage inherits the period from the URL and shows its label.

## Out of scope (YAGNI)

Month navigation on TransactionsPage (that is **T1**, which will consume the `date_from`/`date_to` support added here and retire `days_back`), side-by-side period comparison, preset shortcuts ("this month" / "last month"), custom arbitrary ranges, and adapting the drill-down trend's granularity to the selected period (explicitly rejected: a trend inside one month would be a single point).

## Decisions log

- Calendar periods over rolling windows: stable, comparable, reproducible totals (user choice 2026-07-14).
- Week + month + year, not just month + year (user choice 2026-07-14); ISO Monday-start weeks chosen to match Italian convention and Postgres' native `DATE_TRUNC('week')`, avoiding custom week arithmetic.
- Drill-down inherits the period for breakdown + list; trend stays 12 months (user choice 2026-07-14) — a trend within a single period would collapse to one point.
- Backend takes explicit dates rather than `granularity`+`anchor`: keeps the services calendar-agnostic and trivially testable, and avoids duplicating boundary math that the frontend needs regardless.
- Period state in the URL, not `useState`: reload/share preserve it and the drill-down inherits it by propagation rather than by a shared store.
- `days_back` removed from the two stats services (callers updated together) but retained on `list_transactions` as a transitional bridge owned by T1.
