# Transactions Month Navigation (T1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed 90-day window on TransactionsPage with `‹ giugno 2026 ›` calendar-month navigation, period held in the URL, reusing `lib/period.ts` and the ST1 `date_from`/`date_to` transactions API.

**Architecture:** Frontend-only. TransactionsPage reads a month anchor from the URL (`?anchor=YYYY-MM`), resolves bounds via `periodBounds`, and fetches that month via `date_from`/`date_to`. The Daily/Monthly view toggle and monthly grouping are removed (daily grouping stays). No backend change — `list_transactions` already accepts the dates and keeps `days_back` as a fallback.

**Tech Stack:** React 18 + TypeScript + react-router-dom + TanStack Query + framer-motion, vitest.

**Spec:** `docs/superpowers/specs/2026-07-21-transactions-month-nav-design.md` (normative).

## Global Constraints

- All calendar math comes from `lib/period.ts` — no inline date arithmetic in the page.
- `parsePeriodParams` is the sole URL parser; a bad/missing `anchor` falls back to the current month. Granularity is pinned to `'month'` on this page.
- Period state lives in the URL (`?anchor=`), NOT `useState`.
- No backend change. `days_back` is retained on the API as a rolling-window fallback (no frontend caller uses it after this).
- English labels; Italian error/empty messages ("Impossibile caricare…", "Nessuna transazione…"), matching the app.
- Frontend gate green: `npm run test && npm run lint && npm run build` from `frontend/`.
- TDD: failing test first, RED evidence in the report.

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/pages/Transactions/TransactionsPage.tsx` | Month navigation + month-scoped fetch; toggle/monthly grouping removed |
| `frontend/src/pages/Transactions/TransactionsPage.module.css` | Swap the `.toggle*` rules for month-navigator rules |
| `frontend/src/tests/TransactionsPage.test.tsx` | Router wrapper + period-from-URL / navigation / no-toggle assertions |

---

### Task 1: Month navigation on TransactionsPage

**Files:**
- Modify: `frontend/src/pages/Transactions/TransactionsPage.tsx`
- Modify: `frontend/src/pages/Transactions/TransactionsPage.module.css`
- Test: `frontend/src/tests/TransactionsPage.test.tsx`

**Interfaces:**
- Consumes: `lib/period.ts` (`periodBounds`, `shiftPeriod`, `formatPeriodLabel`, `parsePeriodParams`), the transactions list API's `date_from`/`date_to` (ST1).
- Produces: user-facing behaviour; no downstream consumers.

All frontend commands run from `frontend/` (or `npm --prefix "C:/Users/filip/Documents/Projects/Financial_tracker/frontend" run <script>` with the absolute path; `npx vitest` from within `frontend/`).

- [ ] **Step 1: Rewrite the test** — replace `frontend/src/tests/TransactionsPage.test.tsx` with a version that wraps the page in a `MemoryRouter` (the page now uses `useSearchParams`) and uses a hoisted, inspectable `listMock`:

```tsx
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { TransactionsPage } from '../pages/Transactions/TransactionsPage';

const { tx, listMock, taxonomyMock } = vi.hoisted(() => ({
  tx: {
    id: 1, dedup_hash: 'x', booking_date: '2026-07-01T00:00:00Z', amount: -12.5,
    currency: 'EUR', eur_amount: -12.5, description: null, merchant_name: 'Esselunga',
    account_id: null, is_internal: false, category: 'Groceries', subcategory: null,
    status: 'verified' as const, source: 'enable_banking', created_at: '2026-07-01T00:00:00Z',
  },
  listMock: vi.fn(),
  taxonomyMock: vi.fn(),
}));

vi.mock('../api/client', () => ({
  api: {
    transactions: { list: listMock },
    taxonomy: { get: taxonomyMock },
  },
}));

beforeEach(() => {
  listMock.mockReset().mockResolvedValue({ items: [tx], total: 1, page: 1, page_size: 500 });
  taxonomyMock.mockReset().mockResolvedValue({
    expense: { Car: ['Fuel'], Groceries: ['Supermarket'] },
    income: { Salary: [] },
  });
});

function renderAt(entry: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/transactions" element={<TransactionsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TransactionsPage', () => {
  it('fetches the month from the URL anchor', async () => {
    renderAt('/transactions?anchor=2026-06');
    await waitFor(() =>
      expect(listMock).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: '2026-06-01', date_to: '2026-06-30' }),
      ),
    );
    expect(screen.getByText('giugno 2026')).toBeInTheDocument();
  });

  it('defaults to the current month when no anchor is present', async () => {
    renderAt('/transactions');
    // current month bounds are start-of-month .. end-of-month; assert the shape, not a fixed value
    await waitFor(() => expect(listMock).toHaveBeenCalled());
    const arg = listMock.mock.calls[0][0];
    expect(arg.date_from).toMatch(/^\d{4}-\d{2}-01$/);
    expect(arg.date_to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('navigates to the next month on the arrow', async () => {
    renderAt('/transactions?anchor=2026-06');
    await waitFor(() => expect(screen.getByText('giugno 2026')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Mese successivo' }));

    await waitFor(() =>
      expect(listMock).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: '2026-07-01', date_to: '2026-07-31' }),
      ),
    );
    expect(screen.getByText('luglio 2026')).toBeInTheDocument();
  });

  it('renders fetched transactions and has no Daily/Monthly toggle', async () => {
    renderAt('/transactions?anchor=2026-07');
    await waitFor(() => expect(screen.getByText('Esselunga')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Monthly' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Daily' })).not.toBeInTheDocument();
  });

  it('filters within the loaded month via search', async () => {
    listMock.mockResolvedValue({
      items: [
        tx,
        { ...tx, id: 2, merchant_name: 'Q8', category: 'Car' },
      ],
      total: 2, page: 1, page_size: 500,
    });
    renderAt('/transactions?anchor=2026-07');
    await waitFor(() => expect(screen.getByText('Esselunga')).toBeInTheDocument());

    act(() => {
      fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'Q8' } });
    });
    await waitFor(() => expect(screen.queryByText('Esselunga')).not.toBeInTheDocument());
    expect(screen.getByText('Q8')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify RED**

Run (from `frontend/`): `npx vitest run src/tests/TransactionsPage.test.tsx`
Expected: FAIL — `listMock` is called with `days_back: 90` not date bounds; no "giugno 2026"; no "Mese successivo" button; the Monthly toggle button still exists.

- [ ] **Step 3: Rewrite the component** — replace the top of `frontend/src/pages/Transactions/TransactionsPage.tsx` down through the header/controls. Full target for the changed regions:

Imports (add router + period, drop nothing still used):

```tsx
import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { Transaction } from '../../api/types';
import { transactionQueries, taxonomyQueries } from '../../api/queries';
import { periodBounds, shiftPeriod, formatPeriodLabel, parsePeriodParams } from '../../lib/period';
import { AnimatedNumber } from '../../components/AnimatedNumber';
import { AddTransactionModal } from './AddTransactionModal';
import styles from './TransactionsPage.module.css';
```

Delete the `type ViewMode = 'daily' | 'monthly';` line, and delete the `groupByMonth` and `formatMonth` helper functions entirely. Keep `groupByDate`, `formatDate`, `categoryInitial`.

Replace the component body from `export function TransactionsPage() {` down to the start of `<main>` with:

```tsx
export function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { anchor } = parsePeriodParams('month', searchParams.get('anchor'));
  const { from, to } = periodBounds('month', anchor);

  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);

  const setAnchor = (a: string) => {
    setSearchParams(prev => {
      prev.set('anchor', a);
      return prev;
    });
  };

  const queryClient = useQueryClient();
  const { data, isPending, isError } = useQuery({
    ...transactionQueries.list({ date_from: from, date_to: to, page_size: 500 }),
  });
  const transactions = useMemo(() => data?.items ?? [], [data]);

  const { data: taxonomy } = useQuery({ ...taxonomyQueries.categories() });
  const categoryOrder = useMemo(
    () => [...Object.keys(taxonomy?.expense ?? {}), ...Object.keys(taxonomy?.income ?? {})],
    [taxonomy],
  );
  const colorOf = (cat: string | null): string => {
    const i = cat ? categoryOrder.indexOf(cat) : -1;
    return i === -1 ? 'var(--text-muted)' : `var(--chart-${(i % 8) + 1})`;
  };

  const filtered = useMemo(() =>
    search
      ? transactions.filter(t =>
          (t.merchant_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (t.description ?? '').toLowerCase().includes(search.toLowerCase()) ||
          (t.category ?? '').toLowerCase().includes(search.toLowerCase())
        )
      : transactions,
    [transactions, search]
  );

  const totalIncome   = filtered.filter(t => t.amount > 0).reduce((s, t) => s + t.eur_amount, 0);
  const totalExpenses = filtered.filter(t => t.amount < 0).reduce((s, t) => s + Math.abs(t.eur_amount), 0);

  const dailyGroups = groupByDate(filtered);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <h1 className={styles.title}>Transactions</h1>
          <button className={styles.addBtn} onClick={() => setShowAdd(true)} title="Add transaction">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>

        <div className={styles.summary}>
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Income</span>
            <AnimatedNumber value={totalIncome} prefix="€ " className={`${styles.summaryValue} ${styles.income}`} />
          </div>
          <div className={styles.summaryDivider} />
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Expenses</span>
            <AnimatedNumber value={totalExpenses} prefix="€ " className={`${styles.summaryValue} ${styles.expense}`} />
          </div>
          <div className={styles.summaryDivider} />
          <div className={styles.summaryItem}>
            <span className={styles.summaryLabel}>Net</span>
            <AnimatedNumber
              value={Math.abs(totalIncome - totalExpenses)}
              prefix={totalIncome - totalExpenses >= 0 ? '+€ ' : '-€ '}
              className={`${styles.summaryValue} ${totalIncome >= totalExpenses ? styles.income : styles.expense}`}
            />
          </div>
        </div>

        <div className={styles.controls}>
          <div className={styles.monthNav}>
            <button
              type="button"
              className={styles.navArrow}
              aria-label="Mese precedente"
              onClick={() => setAnchor(shiftPeriod('month', anchor, -1))}
            >
              ‹
            </button>
            <span className={styles.navLabel}>{formatPeriodLabel('month', anchor)}</span>
            <button
              type="button"
              className={styles.navArrow}
              aria-label="Mese successivo"
              onClick={() => setAnchor(shiftPeriod('month', anchor, 1))}
            >
              ›
            </button>
          </div>
          <div className={styles.searchWrap}>
            <svg className={styles.searchIcon} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            <input
              className={styles.search}
              placeholder="Search..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
      </header>
```

Replace the entire `<main>` block (both the `view === 'daily'` and `view === 'monthly'` branches) with a single always-daily body plus an empty state:

```tsx
      <main className={styles.main}>
        {isPending && <div className={styles.loadingMsg}>Loading…</div>}
        {isError && <div className={styles.loadingMsg}>Impossibile caricare le transazioni — riprova.</div>}
        {!isPending && !isError && filtered.length === 0 && (
          <div className={styles.loadingMsg}>Nessuna transazione in questo mese.</div>
        )}

        <AnimatePresence>
          {Object.entries(dailyGroups)
            .sort(([a], [b]) => b.localeCompare(a))
            .map(([date, txs], gi) => (
              <motion.section
                key={date}
                className={styles.group}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: gi * 0.04, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              >
                <div className={styles.groupHeader}>
                  <span className={styles.groupDate}>{formatDate(date)}</span>
                  <span className={styles.groupTotal}>
                    {txs.reduce((s, t) => s + t.eur_amount, 0) >= 0 ? '+' : ''}
                    €{Math.abs(txs.reduce((s, t) => s + t.eur_amount, 0)).toFixed(2)}
                  </span>
                </div>
                {txs.map((tx, i) => <TxRow key={tx.id} tx={tx} index={i} color={colorOf(tx.category)} />)}
              </motion.section>
            ))}
        </AnimatePresence>
      </main>
```

Leave the `{showAdd && <AddTransactionModal ... />}` line and the `TxRow` component below it unchanged.

- [ ] **Step 4: Swap the CSS** — in `frontend/src/pages/Transactions/TransactionsPage.module.css`, delete the `.toggle`, `.toggleBtn`, `.toggleBtn:hover`, and `.toggleActive` rules, and add the month-navigator rules (mirroring StatsPage's period nav so the two pages match):

```css
.monthNav { display: flex; align-items: center; gap: 8px; }
.navArrow {
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 6px;
}
.navArrow:hover { background: var(--bg-hover); }
.navLabel {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
  min-width: 120px;
  text-align: center;
}
```

- [ ] **Step 5: Run to verify GREEN**

Run (from `frontend/`): `npx vitest run src/tests/TransactionsPage.test.tsx` → all pass.
Then the full gate: `npm run test && npm run lint && npm run build` → all green. (Lint will flag any now-unused import or helper — if `groupByMonth`/`formatMonth`/`ViewMode` weren't fully removed, remove them.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Transactions/TransactionsPage.tsx frontend/src/pages/Transactions/TransactionsPage.module.css frontend/src/tests/TransactionsPage.test.tsx
git commit -m "feat(frontend): calendar-month navigation on Transactions, period in the URL"
```

---

### Task 2: Deploy and verify (controller-executed)

Frontend-only, so no Railway deploy — Vercel auto-deploys on push.

- [ ] Push `main`; wait for the Vercel deploy.
- [ ] Browser DOM check on `fimbook.vercel.app/transactions?anchor=2026-06` (user's logged-in tab): the header shows `‹ giugno 2026 ›`; clicking "Mese successivo" changes the label to "luglio 2026" and the URL `anchor` to `2026-07`; the transaction list reflects the month; there is no Daily/Monthly toggle. Read the DOM, not pixels (the MCP tab is `visibilityState: hidden`, freezing `AnimatedNumber`); if the MCP tab isn't logged in, hand this check to the user.
- [ ] Confirm a bare `fimbook.vercel.app/transactions` (no anchor) defaults to the current month.
- [ ] Update the ledger; note that `days_back` is now unused by the frontend (kept as a documented API fallback).

## Self-review notes

- **Spec coverage:** month fetch via `date_from`/`date_to` (T1 Step 3); `‹ label ›` nav + URL anchor (Step 3, `setAnchor`); granularity pinned to `month` (Step 3, `parsePeriodParams('month', …)`); toggle + monthly grouping removed (Step 3/4); summary + search stay client-side (unchanged `filtered`); `days_back` untouched on the backend (no backend task); empty state (Step 3 `<main>`); period math only in `lib/period.ts` (imports, no inline math).
- **Type consistency:** `parsePeriodParams('month', string | null)` returns `{ granularity, anchor }`; only `anchor` is destructured since granularity is constant; `periodBounds('month', anchor) -> { from, to }` feeds `date_from`/`date_to` as `YYYY-MM-DD` strings — the same shape `TransactionFilters.date_from?/date_to?` accepts (added in ST1 Task 5). `shiftPeriod('month', anchor, ±1)` returns a `YYYY-MM` anchor, round-tripping through the URL.
- **No placeholders:** every code block is complete, including the new CSS and the full rewritten component regions.
- **Router requirement:** the test MUST wrap the page in a `MemoryRouter` (the page now calls `useSearchParams`) — Step 1 does this; without it the render throws.
