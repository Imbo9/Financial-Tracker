# Transactions Month Navigation (T1) — Design

**Date**: 2026-07-21
**Status**: approved pending user review
**Source requirement**: `docs/moneymanager-feature-reference.md` T1 — `< June 2026 >` month navigation on the transaction list. Today `TransactionsPage` fetches a fixed `days_back=90` window.

**User decisions (2026-07-21)**: month-only navigation (not the full Week/Month/Year selector Stats has); remove the existing Daily/Monthly view toggle (inside a single month, "monthly" grouping is one redundant group); **keep `days_back`** on the transactions API as a rolling-window fallback rather than retiring it.

## Goal

Replace the fixed 90-day window with `‹ giugno 2026 ›` calendar-month navigation, so the transaction list shows one real month at a time and the user can step month to month. Reuses the `lib/period.ts` calendar module and the `date_from`/`date_to` support already added to the transactions API in ST1 — **no backend change**.

## Requirements

1. `TransactionsPage` fetches one calendar month via `date_from`/`date_to` (from `periodBounds`), not `days_back`.
2. Month navigation `‹ label ›` in the header; period state in the **URL** (`?anchor=YYYY-MM`), so reload/share preserve it — consistent with Stats.
3. Granularity is fixed to `month` on this page (no Week/Year control).
4. The Daily/Monthly view toggle is removed; transactions are grouped by **day** only (the former default).
5. Income/Expenses/Net summary and search stay **client-side** over the loaded month.
6. `days_back` remains a valid rolling-window fallback on the transactions API for bare/machine callers; no frontend caller uses it after this.
7. Existing invariants hold: period math only in `lib/period.ts`, `parsePeriodParams` is the sole URL parser, English labels / Italian error messages, no backend calendar math.

## Architecture

### No backend change

`list_transactions` already accepts optional `date_from`/`date_to` (ST1 Task 4) and falls back to `days_back` when they're absent. This page simply starts supplying the dates. `days_back` stays as-is: it is a rolling window (`NOW() - N days`), not calendar math, so keeping it does not reintroduce calendar logic on the backend, and it keeps a bare `GET /v1/transactions` call working (no forced 422, no server-side month default). This is a deliberate, documented deviation from the ST1 spec's note that T1 would "remove `days_back`" — retiring it would have forced either required dates or backend calendar math, both worse.

### Frontend — `TransactionsPage.tsx`

- Read the period from the URL: `const { anchor } = parsePeriodParams('month', searchParams.get('anchor'))` — granularity is pinned to `'month'`, so only `anchor` is variable. `parsePeriodParams` still guards a malformed anchor (falls back to the current month). Resolve `{ from, to } = periodBounds('month', anchor)`.
- Navigation: `setAnchor(shiftPeriod('month', anchor, ±1))` writes `?anchor=` via `useSearchParams`. Two arrow buttons (`aria-label` "Mese precedente" / "Mese successivo") flank `formatPeriodLabel('month', anchor)`.
- Query: `transactionQueries.list({ date_from: from, date_to: to, page_size: 500 })` replacing `{ days_back: 90, page_size: 500 }`.
- **Removals**: the `view` state and its `ViewMode` type, `groupByMonth`, `formatMonth`, the Daily/Monthly toggle block, and the `view === 'monthly'` render branch. Keep `groupByDate`, `formatDate`, and the daily render path. The controls row keeps the search box and gains the month navigator in place of the toggle.
- Search and the Income/Expenses/Net summary continue to operate on the fetched month (`filtered`), unchanged in mechanism. Documented semantic shift: search now covers the selected month, not a rolling 90 days.

### Empty and error states

A month with no transactions shows an explicit empty message (not a blank list). The existing `isPending` / `isError` messages are kept. Navigating to a month far in the past simply shows an empty month.

## Testing

- Frontend (`TransactionsPage.test.tsx`, new or extended): the period in the URL drives the list query with the right bounds (`?anchor=2026-06` → `date_from: '2026-06-01'`, `date_to: '2026-06-30'`); clicking "Mese successivo" re-queries with July's bounds and updates the label; a URL with no `anchor` falls back to the current month; search filters within the loaded month; no Daily/Monthly toggle remains in the DOM.
- No backend tests change (no backend change). Full frontend gate green.

## Out of scope (YAGNI)

Week/Year granularity on Transactions, server-side search, real pagination (a month fits in one 500-row page), Calendar and Total views (board T5/T7), and retiring `days_back` (kept as a fallback per the user decision).

## Decisions log

- Month-only navigation, not the full Stats selector: matches the board for this view and avoids adaptive grouping (user choice 2026-07-21).
- Remove the Daily/Monthly toggle: within a single month, monthly grouping is one redundant group; daily grouping is the meaningful view (user choice 2026-07-21).
- Keep `days_back` as a rolling-window fallback rather than retiring it: retiring would force required dates or backend calendar math, both contrary to ST1's calendar-agnostic-backend principle (user choice 2026-07-21).
- Period in the URL, granularity pinned to `month`: consistent with Stats, and `parsePeriodParams` still guards bad input.
- Search stays client-side over the loaded month: simple, instant, and the month is already in memory (YAGNI on server-side search).
