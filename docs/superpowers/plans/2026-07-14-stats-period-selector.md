# Stats Period Selector (ST1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Stats a Week/Month/Year period selector with prev/next navigation over real calendar periods, so month-over-month comparison is possible, and have the category drill-down inherit the selected period.

**Architecture:** All calendar math lives in one pure frontend module (`lib/period.ts`); the backend stays calendar-agnostic, receiving explicit `date_from`/`date_to` and filtering a half-open range. The two stats services drop `days_back` for dates (their only callers, the routes, change with them); `list_transactions` gains optional dates and keeps `days_back` as a transitional bridge owned by the future T1. Period state lives in the URL so reload/share preserve it and the drill-down inherits it.

**Tech Stack:** Python/FastAPI/psycopg3 (backend), React 18 + TypeScript + react-router-dom + TanStack Query (frontend), pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-07-14-stats-period-selector-design.md` (normative).

## Global Constraints

- Dashboard routes on `router_v1` (JWT), envelope `{"data": ...}`, `-> dict`, thin route → service.
- **`float()` at the service boundary** (psycopg Decimal → JSON string otherwise).
- Spending stats read `real_transactions` (internal excluded) — opposite scope from balance math. Unchanged here.
- Date filter is **half-open**: `booking_date >= %s AND booking_date < %s::date + INTERVAL '1 day'` so `date_to` is inclusive without an off-by-one. `booking_date` is stored at midnight UTC (normalizer appends `T00:00:00Z`), so whole-day periods have no tz edge.
- **Span cap counts inclusively**: reject when `(date_to - date_from).days + 1 > 366`. A leap year is exactly 366 inclusive days and MUST be admitted — exclusive counting rejects Feb-inclusive leap years (bug surfaces in 2028).
- Weeks are **ISO, Monday-start**. Anchors are **canonical**: a week anchor is always that week's Monday; every function returning an anchor returns the normalised form.
- URL params are **untrusted**: `parsePeriodParams` is the single parse entry point; bad input falls back to the current month, never `Invalid Date` or a throw.
- `isAnimationActive={false}` on charts. English labels / Italian error messages.
- Gates: `uv run pytest -q`, `uv run ruff check .`, `uv run pyrefly check` (repo root); `npm run test && npm run lint && npm run build` (from `frontend/`). `git commit` triggers lefthook.
- TDD: failing test first, RED evidence in the report.

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/lib/period.ts` (new) | Pure calendar math: bounds, shift, label, current anchor, param parsing |
| `src/fintracker/server/routes/api.py` | `_validate_date_range` helper; stats routes take `date_from`/`date_to`; transactions route gains optional dates |
| `src/fintracker/server/services/stats.py` | `by_category` + `subcategory_breakdown` switch `days_back` → `date_from`/`date_to` |
| `src/fintracker/server/services/transactions.py` | `list_transactions` gains optional `date_from`/`date_to`, keeps `days_back` |
| `frontend/src/api/{types,client,queries}.ts` | `date_from`/`date_to` threaded through stats + transactions calls |
| `frontend/src/pages/Stats/StatsPage.tsx` + `.module.css` | Granularity control + prev/next navigator; period from URL |
| `frontend/src/pages/CategoryDetail/CategoryDetailPage.tsx` | Inherit period from URL for breakdown + list; trend stays 12 months |

---

### Task 1: `lib/period.ts` — pure calendar module

**Files:**
- Create: `frontend/src/lib/period.ts`
- Test: `frontend/src/tests/period.test.ts` (new)

**Interfaces:**
- Produces (consumed by Tasks 5 & 6):
  - `type Granularity = 'week' | 'month' | 'year'`
  - `periodBounds(g, anchor) -> { from: string; to: string }` (inclusive, `YYYY-MM-DD`)
  - `shiftPeriod(g, anchor, delta: 1 | -1) -> string` (canonical anchor)
  - `formatPeriodLabel(g, anchor) -> string`
  - `currentAnchor(g) -> string`
  - `parsePeriodParams(granularity: string | null, anchor: string | null) -> { granularity: Granularity; anchor: string }`

All frontend commands run from `frontend/`.

- [ ] **Step 1: Write the failing test** — `frontend/src/tests/period.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  periodBounds, shiftPeriod, formatPeriodLabel, currentAnchor, parsePeriodParams,
} from '../lib/period';

describe('periodBounds', () => {
  it('month spans first to last day', () => {
    expect(periodBounds('month', '2026-06')).toEqual({ from: '2026-06-01', to: '2026-06-30' });
  });
  it('february in a leap year ends on the 29th', () => {
    expect(periodBounds('month', '2028-02')).toEqual({ from: '2028-02-01', to: '2028-02-29' });
  });
  it('year spans Jan 1 to Dec 31', () => {
    expect(periodBounds('year', '2026')).toEqual({ from: '2026-01-01', to: '2026-12-31' });
  });
  it('week runs Monday to Sunday from a Monday anchor', () => {
    expect(periodBounds('week', '2026-07-06')).toEqual({ from: '2026-07-06', to: '2026-07-12' });
  });
});

describe('shiftPeriod', () => {
  it('month rolls over December to January', () => {
    expect(shiftPeriod('month', '2026-12', 1)).toBe('2027-01');
  });
  it('month rolls back January to December', () => {
    expect(shiftPeriod('month', '2026-01', -1)).toBe('2025-12');
  });
  it('year steps by one', () => {
    expect(shiftPeriod('year', '2026', 1)).toBe('2027');
  });
  it('week steps 7 days and can cross a month boundary', () => {
    expect(shiftPeriod('week', '2026-06-29', 1)).toBe('2026-07-06');
  });
  it('week can cross a year boundary', () => {
    expect(shiftPeriod('week', '2026-12-28', 1)).toBe('2027-01-04');
  });
});

describe('formatPeriodLabel', () => {
  it('month is the Italian month name and year', () => {
    expect(formatPeriodLabel('month', '2026-06')).toBe('giugno 2026');
  });
  it('year is the bare year', () => {
    expect(formatPeriodLabel('year', '2026')).toBe('2026');
  });
  it('week shows both day/month ends and the year once', () => {
    expect(formatPeriodLabel('week', '2026-07-06')).toBe('6 lug – 12 lug 2026');
  });
});

describe('parsePeriodParams', () => {
  it('defaults to the current month on missing params', () => {
    const out = parsePeriodParams(null, null);
    expect(out.granularity).toBe('month');
    expect(out.anchor).toBe(currentAnchor('month'));
  });
  it('defaults on an unknown granularity', () => {
    expect(parsePeriodParams('banana', '2026-06').granularity).toBe('month');
  });
  it('defaults on a malformed anchor for the granularity', () => {
    expect(parsePeriodParams('month', 'not-a-date').anchor).toBe(currentAnchor('month'));
  });
  it('normalises a non-Monday week anchor to that week\'s Monday', () => {
    // 2026-07-09 is a Thursday; its Monday is 2026-07-06
    expect(parsePeriodParams('week', '2026-07-09')).toEqual({ granularity: 'week', anchor: '2026-07-06' });
  });
  it('passes a valid month through unchanged', () => {
    expect(parsePeriodParams('month', '2026-06')).toEqual({ granularity: 'month', anchor: '2026-06' });
  });
});

describe('currentAnchor', () => {
  it('month anchor is YYYY-MM shaped', () => {
    expect(currentAnchor('month')).toMatch(/^\d{4}-\d{2}$/);
  });
  it('year anchor is YYYY shaped', () => {
    expect(currentAnchor('year')).toMatch(/^\d{4}$/);
  });
  it('week anchor is a Monday (YYYY-MM-DD)', () => {
    const a = currentAnchor('week');
    expect(a).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(new Date(`${a}T00:00:00Z`).getUTCDay()).toBe(1); // Monday
  });
});
```

- [ ] **Step 2: Run to verify RED**

Run (from `frontend/`): `npx vitest run src/tests/period.test.ts`
Expected: FAIL — cannot resolve `../lib/period`.

- [ ] **Step 3: Implement** — create `frontend/src/lib/period.ts`:

```ts
export type Granularity = 'week' | 'month' | 'year';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function ymd(d: Date): string {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

// All math is done in UTC to avoid the host timezone shifting day boundaries.
function mondayOf(isoDate: string): Date {
  const d = new Date(`${isoDate}T00:00:00Z`);
  const dow = d.getUTCDay(); // 0=Sun .. 6=Sat
  const toMonday = dow === 0 ? -6 : 1 - dow;
  d.setUTCDate(d.getUTCDate() + toMonday);
  return d;
}

function isValidAnchor(g: Granularity, anchor: string): boolean {
  if (g === 'year') return /^\d{4}$/.test(anchor);
  if (g === 'month') {
    if (!/^\d{4}-\d{2}$/.test(anchor)) return false;
    const m = Number(anchor.slice(5, 7));
    return m >= 1 && m <= 12;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(anchor)) return false;
  const t = new Date(`${anchor}T00:00:00Z`).getTime();
  return !Number.isNaN(t);
}

export function periodBounds(g: Granularity, anchor: string): { from: string; to: string } {
  if (g === 'week') {
    const mon = mondayOf(anchor);
    const sun = new Date(mon);
    sun.setUTCDate(mon.getUTCDate() + 6);
    return { from: ymd(mon), to: ymd(sun) };
  }
  if (g === 'month') {
    const [y, m] = anchor.split('-').map(Number);
    return { from: `${y}-${pad(m)}-01`, to: ymd(new Date(Date.UTC(y, m, 0))) };
  }
  const y = Number(anchor);
  return { from: `${y}-01-01`, to: `${y}-12-31` };
}

export function shiftPeriod(g: Granularity, anchor: string, delta: 1 | -1): string {
  if (g === 'week') {
    const mon = mondayOf(anchor);
    mon.setUTCDate(mon.getUTCDate() + 7 * delta);
    return ymd(mon);
  }
  if (g === 'month') {
    const [y, m] = anchor.split('-').map(Number);
    const d = new Date(Date.UTC(y, m - 1 + delta, 1));
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
  }
  return String(Number(anchor) + delta);
}

export function formatPeriodLabel(g: Granularity, anchor: string): string {
  if (g === 'year') return anchor;
  if (g === 'month') {
    const [y, m] = anchor.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('it-IT', {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    });
  }
  const { from, to } = periodBounds('week', anchor);
  const dayMon = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString('it-IT', {
      day: 'numeric',
      month: 'short',
      timeZone: 'UTC',
    });
  return `${dayMon(from)} – ${dayMon(to)} ${to.slice(0, 4)}`;
}

export function currentAnchor(g: Granularity): string {
  const now = new Date();
  const y = now.getUTCFullYear();
  const m = now.getUTCMonth() + 1;
  if (g === 'week') return ymd(mondayOf(ymd(now)));
  if (g === 'month') return `${y}-${pad(m)}`;
  return String(y);
}

export function parsePeriodParams(
  granularity: string | null,
  anchor: string | null,
): { granularity: Granularity; anchor: string } {
  const g: Granularity | null =
    granularity === 'week' || granularity === 'month' || granularity === 'year' ? granularity : null;
  if (!g || !anchor || !isValidAnchor(g, anchor)) {
    return { granularity: 'month', anchor: currentAnchor('month') };
  }
  return { granularity: g, anchor: g === 'week' ? ymd(mondayOf(anchor)) : anchor };
}
```

Note on the week label: `to.slice(0, 4)` reads the year from the `YYYY-MM-DD` string directly (avoids re-parsing).

- [ ] **Step 4: Run to verify GREEN**

Run (from `frontend/`): `npx vitest run src/tests/period.test.ts` → all pass.
Then the full gate: `npm run test && npm run lint && npm run build` → all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/period.ts frontend/src/tests/period.test.ts
git commit -m "feat(frontend): pure calendar period module (bounds, shift, label, parse)"
```

---

### Task 2: `_validate_date_range` + `by_category` on a date range

**Files:**
- Modify: `src/fintracker/server/services/stats.py` (`by_category`)
- Modify: `src/fintracker/server/routes/api.py` (helper + `_stats_categories` wrapper + `stats_categories_v1` route)
- Test: `tests/test_services.py`, `tests/test_api_routes.py`

**Interfaces:**
- Produces: `by_category(conn, date_from: date, date_to: date, direction: str = "expense") -> list[dict]` (consumed by the categories route). `_validate_date_range(date_from: date, date_to: date) -> None` raising `HTTPException(422)` (consumed by Tasks 3 & 4).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_services.py` (helpers `_conn_with_cursor` / `_conn_returning` exist; `from datetime import date` may need adding to the imports):

```python
def test_by_category_binds_both_dates_and_is_inclusive_to_date_to():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    stats.by_category(conn, date(2026, 6, 1), date(2026, 6, 30), direction="expense")
    sql, params = cur.execute.call_args[0]
    assert "booking_date >= %s" in sql
    assert "< %s::date + INTERVAL '1 day'" in sql  # half-open upper bound => date_to inclusive
    assert "days_back" not in sql.lower()
    assert params == (date(2026, 6, 1), date(2026, 6, 30))
```

and to `tests/test_api_routes.py` inside a new `TestStatsPeriod` class:

```python
class TestStatsPeriod:
    def test_categories_missing_dates_returns_422(self, auth_client):
        resp = auth_client.get("/v1/stats/categories")
        assert resp.status_code == 422  # date_from/date_to now required

    def test_categories_from_after_to_returns_422(self, auth_client):
        resp = auth_client.get("/v1/stats/categories?date_from=2026-06-30&date_to=2026-06-01")
        assert resp.status_code == 422

    def test_categories_span_over_366_days_returns_422(self, auth_client):
        resp = auth_client.get("/v1/stats/categories?date_from=2025-01-01&date_to=2026-06-01")
        assert resp.status_code == 422

    def test_categories_leap_year_is_allowed(self, auth_client):
        # 2028-01-01..2028-12-31 is 366 inclusive days — must be admitted
        with patch(
            "fintracker.storage.db.get_pool",
            return_value=_mock_pool(_mock_conn([])),
        ):
            resp = auth_client.get("/v1/stats/categories?date_from=2028-01-01&date_to=2028-12-31")
        assert resp.status_code == 200

    def test_categories_valid_range_returns_200(self, auth_client):
        with patch(
            "fintracker.storage.db.get_pool",
            return_value=_mock_pool(_mock_conn([])),
        ):
            resp = auth_client.get("/v1/stats/categories?date_from=2026-06-01&date_to=2026-06-30")
        assert resp.status_code == 200
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_services.py -q -k by_category_binds` then `uv run pytest tests/test_api_routes.py -q -k TestStatsPeriod`
Expected: service test FAILS (`by_category` still takes `days_back`); route tests FAIL (endpoint still accepts no-date call → 200, and no validation).

- [ ] **Step 3: Implement**.

`src/fintracker/server/services/stats.py` — add `date` to the datetime import if missing (`from datetime import date, timedelta`), and replace `by_category`:

```python
def by_category(conn, date_from: date, date_to: date, direction: str = "expense") -> list[dict]:
    # Fixed literal, never user input: the route validates direction against income|expense.
    sign_filter = "amount > 0" if direction == "income" else "amount < 0"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT COALESCE(category, 'Uncategorized') AS category,
                       ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total,
                       COUNT(*) AS count
                FROM real_transactions
                WHERE {sign_filter}
                  AND booking_date >= %s
                  AND booking_date < %s::date + INTERVAL '1 day'
                GROUP BY category
                ORDER BY total DESC""",
            (date_from, date_to),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["total"] = float(r["total"])
    grand_total = sum(r["total"] for r in rows) or 1
    for r in rows:
        r["percentage"] = round(r["total"] / grand_total * 100, 1)
    return rows
```

`src/fintracker/server/routes/api.py` — add `from datetime import date` (alongside the existing `datetime` import) and, near the other query-type constants, the validation helper:

```python
_MAX_SPAN_DAYS = 366  # a full year; the widest supported period (leap years included)


def _validate_date_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if (date_to - date_from).days + 1 > _MAX_SPAN_DAYS:
        raise HTTPException(status_code=422, detail="date range must not exceed 366 days")
```

Replace the `_stats_categories` wrapper and `stats_categories_v1` route:

```python
def _stats_categories(date_from: date, date_to: date, direction: str) -> list[dict]:
    with db_conn() as conn:
        return stats.by_category(conn, date_from, date_to, direction)


@router_v1.get("/stats/categories")
def stats_categories_v1(
    date_from: date, date_to: date, direction: DirectionQ = None
) -> dict:
    _validate_date_range(date_from, date_to)
    return {"data": _stats_categories(date_from, date_to, direction or "expense")}
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest -q && uv run ruff check . && uv run pyrefly check`
Expected: all pass. (The existing `test_stats_by_category_*` service tests must be updated in the same step to pass dates instead of `days_back` — change their `stats.by_category(conn, days_back=30)` calls to `stats.by_category(conn, date(2026, 6, 1), date(2026, 6, 30))`; keep their assertions on `amount < 0` / `amount > 0` / percentages.)

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/stats.py src/fintracker/server/routes/api.py tests/test_services.py tests/test_api_routes.py
git commit -m "feat: category stats over an explicit date range with shared validation"
```

---

### Task 3: `subcategory_breakdown` on a date range

**Files:**
- Modify: `src/fintracker/server/services/stats.py` (`subcategory_breakdown`)
- Modify: `src/fintracker/server/routes/api.py` (`_stats_subcategories` wrapper + `stats_subcategories_v1` route)
- Test: `tests/test_services.py`, `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `_validate_date_range` (Task 2).
- Produces: `subcategory_breakdown(conn, category: str | None, date_from: date, date_to: date, direction: str) -> list[dict]`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_services.py`:

```python
def test_subcategory_breakdown_binds_date_range():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(conn, "Car", date(2026, 6, 1), date(2026, 6, 30), direction="expense")
    sql, params = cur.execute.call_args[0]
    assert "booking_date >= %s" in sql
    assert "< %s::date + INTERVAL '1 day'" in sql
    assert "days_back" not in sql.lower()
    # category param first, then the two dates
    assert params == ["Car", date(2026, 6, 1), date(2026, 6, 30)]
```

and append to `tests/test_api_routes.py` inside `TestStatsPeriod`:

```python
    def test_subcategories_require_dates_and_validate(self, auth_client):
        assert auth_client.get("/v1/stats/categories/Car/subcategories").status_code == 422
        assert auth_client.get(
            "/v1/stats/categories/Car/subcategories?date_from=2026-06-30&date_to=2026-06-01"
        ).status_code == 422
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_services.py -q -k subcategory_breakdown_binds_date_range`
Expected: FAIL — `subcategory_breakdown` still takes `days_back`.

- [ ] **Step 3: Implement**.

`src/fintracker/server/services/stats.py` — replace the query/params portion of `subcategory_breakdown` (keep the sign/category-filter and percentage logic):

```python
def subcategory_breakdown(
    conn, category: str | None, date_from: date, date_to: date, direction: str
) -> list[dict]:
    """Subcategory split inside one category. `category=None` is the uncategorised bucket.

    Reads real_transactions (internal rows excluded) like by_category — the opposite
    scope from balance_history, which must include them to match EB balances.
    """
    sign_filter = "amount > 0" if direction == "income" else "amount < 0"
    category_filter = "category IS NULL" if category is None else "category = %s"
    params: list = [] if category is None else [category]
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT COALESCE(subcategory, 'No subcategory') AS subcategory,
                       ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total,
                       COUNT(*) AS count
                FROM real_transactions
                WHERE {sign_filter}
                  AND {category_filter}
                  AND booking_date >= %s
                  AND booking_date < %s::date + INTERVAL '1 day'
                GROUP BY subcategory
                ORDER BY total DESC""",
            [*params, date_from, date_to],
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["total"] = float(r["total"])
    grand_total = sum(r["total"] for r in rows) or 1
    for r in rows:
        r["percentage"] = round(r["total"] / grand_total * 100, 1)
    return rows
```

`src/fintracker/server/routes/api.py` — replace `_stats_subcategories` and `stats_subcategories_v1`:

```python
def _stats_subcategories(
    category: str, date_from: date, date_to: date, direction: str
) -> list[dict]:
    with db_conn() as conn:
        return stats.subcategory_breakdown(
            conn, _category_or_null(category), date_from, date_to, direction
        )


@router_v1.get("/stats/categories/{category}/subcategories")
def stats_subcategories_v1(
    category: str, date_from: date, date_to: date, direction: DirectionQ = None
) -> dict:
    _validate_date_range(date_from, date_to)
    return {"data": _stats_subcategories(category, date_from, date_to, direction or "expense")}
```

The existing `subcategory_breakdown` service tests from ST3 must be updated to pass dates instead of `days_back=30` (change the call args; keep the IS NULL / parameterisation / sentinel / ABS assertions). The `_category_or_null` mapping test still asserts `mocked.call_args[0][1]` — the wrapper keeps `conn` first, `_category_or_null(category)` second, so that index is unchanged.

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest -q && uv run ruff check . && uv run pyrefly check` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/stats.py src/fintracker/server/routes/api.py tests/test_services.py tests/test_api_routes.py
git commit -m "feat: subcategory breakdown over an explicit date range"
```

---

### Task 4: `list_transactions` optional date range

**Files:**
- Modify: `src/fintracker/server/services/transactions.py` (`list_transactions`)
- Modify: `src/fintracker/server/routes/api.py` (`_list_transactions` wrapper + `list_transactions_v1` route)
- Test: `tests/test_services.py`, `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `_validate_date_range` (Task 2).
- Produces: `list_transactions(conn, *, page, page_size, days_back, category, direction, search, subcategory=None, date_from: date | None = None, date_to: date | None = None)`. Route `GET /v1/transactions` gains optional `date_from` / `date_to`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_services.py`:

```python
def test_list_transactions_uses_date_range_when_both_dates_given():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn, page=1, page_size=50, days_back=30, category=None,
        direction=None, search=None, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
    )
    sql, params = cur.execute.call_args[0]
    assert "< %s::date + INTERVAL '1 day'" in sql
    assert "INTERVAL '1 day')" not in sql or "NOW()" not in sql  # days_back window replaced
    assert date(2026, 6, 1) in params and date(2026, 6, 30) in params


def test_list_transactions_falls_back_to_days_back_without_dates():
    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn, page=1, page_size=50, days_back=30, category=None,
        direction=None, search=None,
    )
    sql, _ = cur.execute.call_args[0]
    assert "NOW() - (%s * INTERVAL '1 day')" in sql
```

and append to `tests/test_api_routes.py` inside `TestStatsPeriod`:

```python
    def test_transactions_accept_date_range(self, auth_client):
        with patch(
            "fintracker.storage.db.get_pool",
            return_value=_mock_pool(_mock_conn([FAKE_ROW], {"total": 1})),
        ):
            resp = auth_client.get("/v1/transactions?date_from=2026-06-01&date_to=2026-06-30")
        assert resp.status_code == 200

    def test_transactions_date_range_validated(self, auth_client):
        resp = auth_client.get("/v1/transactions?date_from=2026-06-30&date_to=2026-06-01")
        assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_services.py -q -k "date_range or days_back_without"`
Expected: FAIL — `list_transactions` has no `date_from`/`date_to`.

- [ ] **Step 3: Implement**.

`src/fintracker/server/services/transactions.py` — extend the signature and swap the first condition:

```python
def list_transactions(
    conn,
    *,
    page: int,
    page_size: int,
    days_back: int,
    category: str | None,
    direction: str | None,
    search: str | None,
    subcategory: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    if date_from is not None and date_to is not None:
        conditions = ["booking_date >= %s", "booking_date < %s::date + INTERVAL '1 day'"]
        params: list[Any] = [date_from, date_to]
    else:
        conditions = ["booking_date >= NOW() - (%s * INTERVAL '1 day')"]
        params = [days_back]
    if category:
        conditions.append("category = %s")
        params.append(category)
    # ... (rest of the existing subcategory/direction/search blocks unchanged)
```

Add `from datetime import date` to the top of `transactions.py` if absent.

`src/fintracker/server/routes/api.py` — thread the dates through `_list_transactions` and the route, and validate when both are present:

```python
def _list_transactions(
    page: int, page_size: int, days_back: int, category: str | None,
    direction: str | None, search: str | None, subcategory: str | None,
    date_from: date | None, date_to: date | None,
) -> dict:
    with db_conn() as conn:
        return transactions.list_transactions(
            conn, page=page, page_size=page_size, days_back=days_back,
            category=category, direction=direction, search=search,
            subcategory=subcategory, date_from=date_from, date_to=date_to,
        )


@router_v1.get("/transactions")
def list_transactions_v1(
    page: PageQ = 1,
    page_size: PageSizeQ = 50,
    days_back: DaysBackQ = 30,
    category: str | None = None,
    direction: DirectionQ = None,
    search: str | None = None,
    subcategory: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    if date_from is not None and date_to is not None:
        _validate_date_range(date_from, date_to)
    return {
        "data": _list_transactions(
            page, page_size, days_back, category, direction, search,
            subcategory, date_from, date_to,
        )
    }
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest -q && uv run ruff check . && uv run pyrefly check` → all pass (existing transactions tests untouched: dates default to `None`, `days_back` path unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/transactions.py src/fintracker/server/routes/api.py tests/test_services.py tests/test_api_routes.py
git commit -m "feat: optional date-range filter on transactions list (days_back retained)"
```

---

### Task 5: StatsPage period selector with URL state

**Files:**
- Modify: `frontend/src/api/types.ts` (`TransactionFilters` gains `date_from?`/`date_to?`)
- Modify: `frontend/src/api/client.ts` (`stats.categories` + `stats.subcategories` params)
- Modify: `frontend/src/api/queries.ts` (`statsQueries.categories` + `subcategories` signatures)
- Modify: `frontend/src/pages/Stats/StatsPage.tsx`
- Modify: `frontend/src/pages/Stats/StatsPage.module.css`
- Test: `frontend/src/tests/StatsPage.test.tsx` (append)

**Interfaces:**
- Consumes: `lib/period.ts` (Task 1), the date-range categories endpoint (Task 2).
- Produces: StatsPage reads `granularity`/`anchor` from the URL and drives the categories query by resolved bounds.

- [ ] **Step 1: Write the failing test** — append to `frontend/src/tests/StatsPage.test.tsx` (the file mocks `../api/client` and renders `<StatsPage />`; ensure `MemoryRouter` and a `categoriesMock` are available from the ST3 work):

```tsx
it('drives the categories query from the period in the URL and navigates on next', async () => {
  categoriesMock.mockResolvedValue([]);
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={['/stats?granularity=month&anchor=2026-06']}>
        <Routes>
          <Route path="/stats" element={<StatsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  // June 2026 → the categories call carries that month's bounds
  await waitFor(() =>
    expect(categoriesMock).toHaveBeenCalledWith(
      expect.objectContaining({ date_from: '2026-06-01', date_to: '2026-06-30' }),
    ),
  );

  // the label reflects the period, and clicking next moves to July
  expect(screen.getByText('giugno 2026')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Periodo successivo' }));
  await waitFor(() =>
    expect(categoriesMock).toHaveBeenCalledWith(
      expect.objectContaining({ date_from: '2026-07-01', date_to: '2026-07-31' }),
    ),
  );
});
```

- [ ] **Step 2: Run to verify RED**

Run (from `frontend/`): `npx vitest run src/tests/StatsPage.test.tsx`
Expected: FAIL — `categoriesMock` is called with `days_back`, not date bounds; no "giugno 2026" label; no "Periodo successivo" button.

- [ ] **Step 3: Implement** — five edits.

1. `frontend/src/api/types.ts` — add to `TransactionFilters`:

```ts
  date_from?: string;
  date_to?: string;
```

2. `frontend/src/api/client.ts` — change the `categories` and `subcategories` param types from `days_back?: number` to a date range:

```ts
    categories: (
      params: { date_from: string; date_to: string; direction?: 'income' | 'expense' },
    ): Promise<CategoryStat[]> =>
      http.get('/v1/stats/categories', { params }).then(unwrap<CategoryStat[]>),
```

and in `subcategories`, replace `days_back?: number` with `date_from: string; date_to: string` (the `const { category, ...q } = params` spread already forwards them as query params):

```ts
    subcategories: (params: {
      category: string;
      date_from: string;
      date_to: string;
      direction?: 'income' | 'expense';
    }): Promise<SubcategoryStat[]> => {
      const { category, ...q } = params;
      return http
        .get(`/v1/stats/categories/${encodeURIComponent(category)}/subcategories`, { params: q })
        .then(unwrap<SubcategoryStat[]>);
    },
```

3. `frontend/src/api/queries.ts` — change `categories` and `subcategories` factories to take bounds:

```ts
  categories: (date_from: string, date_to: string, direction: 'income' | 'expense' = 'expense') => ({
    queryKey: ['stats', 'categories', date_from, date_to, direction] as const,
    queryFn: () => api.stats.categories({ date_from, date_to, direction }),
  }),
```

```ts
  subcategories: (
    category: string,
    date_from: string,
    date_to: string,
    direction: 'income' | 'expense' = 'expense',
  ) => ({
    queryKey: ['stats', 'subcategories', category, date_from, date_to, direction] as const,
    queryFn: () => api.stats.subcategories({ category, date_from, date_to, direction }),
  }),
```

4. `frontend/src/pages/Stats/StatsPage.tsx` — replace `useState`-based nothing with URL-driven period. Add imports:

```tsx
import { useSearchParams } from 'react-router-dom';
import { periodBounds, shiftPeriod, formatPeriodLabel, parsePeriodParams, type Granularity } from '../../lib/period';
```

Inside `StatsPage`, above the queries:

```tsx
  const [searchParams, setSearchParams] = useSearchParams();
  const { granularity, anchor } = parsePeriodParams(
    searchParams.get('granularity'),
    searchParams.get('anchor'),
  );
  const { from, to } = periodBounds(granularity, anchor);

  const setPeriod = (g: Granularity, a: string) => {
    setSearchParams(prev => {
      prev.set('granularity', g);
      prev.set('anchor', a);
      return prev;
    });
  };
```

Change the categories query to use bounds:

```tsx
  const categories = useQuery({
    ...statsQueries.categories(from, to, tab === 'income' ? 'income' : 'expense'),
  });
```

Add the selector UI in the header (below the existing expense/income tabs). Use real buttons with `aria-label`s the test relies on:

```tsx
        <div className={styles.periodBar}>
          <div className={styles.granTabs}>
            {(['week', 'month', 'year'] as Granularity[]).map(g => (
              <button
                key={g}
                type="button"
                className={`${styles.granTab} ${granularity === g ? styles.granTabActive : ''}`}
                onClick={() => setPeriod(g, currentAnchorFor(g))}
              >
                {g === 'week' ? 'Week' : g === 'month' ? 'Month' : 'Year'}
              </button>
            ))}
          </div>
          <div className={styles.periodNav}>
            <button
              type="button"
              className={styles.periodArrow}
              aria-label="Periodo precedente"
              onClick={() => setPeriod(granularity, shiftPeriod(granularity, anchor, -1))}
            >
              ‹
            </button>
            <span className={styles.periodLabel}>{formatPeriodLabel(granularity, anchor)}</span>
            <button
              type="button"
              className={styles.periodArrow}
              aria-label="Periodo successivo"
              onClick={() => setPeriod(granularity, shiftPeriod(granularity, anchor, 1))}
            >
              ›
            </button>
          </div>
        </div>
```

When switching granularity the anchor must be reset to that granularity's current period (a month anchor `2026-06` is not a valid week anchor). Add this helper above the component, reusing `currentAnchor`:

```tsx
import { currentAnchor } from '../../lib/period';
const currentAnchorFor = (g: Granularity) => currentAnchor(g);
```

Update the legend `navigate(...)` call (from ST3) to carry the period so the drill-down inherits it:

```tsx
                onClick={() =>
                  navigate(
                    `/stats/category/${encodeURIComponent(cat.category)}` +
                      `?direction=${tab === 'income' ? 'income' : 'expense'}` +
                      `&granularity=${granularity}&anchor=${anchor}`,
                  )
                }
```

5. `frontend/src/pages/Stats/StatsPage.module.css` — append styling for the new controls (mirror the existing `.tabs`/`.tab` look):

```css
.periodBar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.granTabs { display: flex; gap: 4px; }
.granTab {
  background: none;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.granTabActive {
  border-color: var(--accent);
  color: var(--text-primary);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.periodNav { display: flex; align-items: center; gap: 8px; }
.periodArrow {
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 6px;
}
.periodArrow:hover { background: var(--bg-hover); }
.periodLabel {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
  min-width: 120px;
  text-align: center;
}
```

- [ ] **Step 4: Run to verify GREEN**

Run (from `frontend/`): `npx vitest run src/tests/StatsPage.test.tsx` → pass; then `npm run test && npm run lint && npm run build` → all green. (The existing StatsPage test that renders inside a `MemoryRouter` with no query string must still pass — it now resolves to the default current month; its `categoriesMock` assertion, if it checked `days_back`, must be updated to `expect.objectContaining({ direction: 'income' })` since the arg shape changed.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/queries.ts frontend/src/pages/Stats/StatsPage.tsx frontend/src/pages/Stats/StatsPage.module.css frontend/src/tests/StatsPage.test.tsx
git commit -m "feat(frontend): calendar period selector on Stats, period in the URL"
```

---

### Task 6: CategoryDetailPage inherits the period

**Files:**
- Modify: `frontend/src/pages/CategoryDetail/CategoryDetailPage.tsx`
- Test: `frontend/src/tests/CategoryDetailPage.test.tsx` (append)

**Interfaces:**
- Consumes: `lib/period.ts` (Task 1), the date-range subcategories + transactions endpoints (Tasks 3 & 4), `statsQueries.subcategories(category, date_from, date_to, direction)` (Task 5).
- Produces: user-facing behaviour; no downstream consumers.

- [ ] **Step 1: Write the failing test** — append to `frontend/src/tests/CategoryDetailPage.test.tsx`:

```tsx
it('inherits the period from the URL for the breakdown and transaction queries', async () => {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter
        initialEntries={['/stats/category/Car?direction=expense&granularity=month&anchor=2026-06']}
      >
        <Routes>
          <Route path="/stats/category/:category" element={<CategoryDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await waitFor(() =>
    expect(subcategoriesMock).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'Car', date_from: '2026-06-01', date_to: '2026-06-30' }),
    ),
  );
  expect(listMock).toHaveBeenCalledWith(
    expect.objectContaining({ category: 'Car', date_from: '2026-06-01', date_to: '2026-06-30' }),
  );
});
```

- [ ] **Step 2: Run to verify RED**

Run (from `frontend/`): `npx vitest run src/tests/CategoryDetailPage.test.tsx`
Expected: FAIL — the page still calls with `days_back: 30`, not date bounds.

- [ ] **Step 3: Implement** — in `frontend/src/pages/CategoryDetail/CategoryDetailPage.tsx`:

Add imports:

```tsx
import { periodBounds, parsePeriodParams } from '../../lib/period';
```

Replace the `DAYS_BACK` usage. After reading `searchParams`:

```tsx
  const { granularity, anchor } = parsePeriodParams(
    searchParams.get('granularity'),
    searchParams.get('anchor'),
  );
  const { from, to } = periodBounds(granularity, anchor);
```

Change the subcategories and transactions queries to use bounds (trend stays on months):

```tsx
  const subcategories = useQuery({
    ...statsQueries.subcategories(category, from, to, direction),
  });
  const trend = useQuery({
    ...statsQueries.categoryTrend(category, TREND_MONTHS, direction, subFilter),
  });
  const transactions = useQuery({
    ...transactionQueries.list({
      category,
      subcategory: subFilter,
      direction,
      date_from: from,
      date_to: to,
      page_size: TX_LIMIT,
    }),
  });
```

Remove the now-unused `const DAYS_BACK = 30;`. Change the header period label from the hardcoded "ultimi 30 giorni" to the inherited period:

```tsx
import { formatPeriodLabel } from '../../lib/period';
```
```tsx
          <span className={styles.subtitle}>
            € {periodTotal.toLocaleString('it-IT', { minimumFractionDigits: 2 })} · {formatPeriodLabel(granularity, anchor)}
          </span>
```

(`formatPeriodLabel`, `parsePeriodParams`, `periodBounds` all come from the one import; consolidate into a single import line.)

- [ ] **Step 4: Run to verify GREEN**

Run (from `frontend/`): `npx vitest run src/tests/CategoryDetailPage.test.tsx` → pass. The existing CategoryDetailPage tests must still pass — they render with a URL lacking period params, which now resolves to the default current month; if any asserted `days_back`, update it to the corresponding `date_from`/`date_to` for the current month, or relax to `expect.objectContaining({ category: 'Car' })`. Then `npm run test && npm run lint && npm run build` → all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CategoryDetail/CategoryDetailPage.tsx frontend/src/tests/CategoryDetailPage.test.tsx
git commit -m "feat(frontend): category drill-down inherits the selected period"
```

---

### Task 7: Deploy and verify (controller-executed)

- [ ] Push `main`; `railway up --detach --service just-comfort`; Vercel auto-deploys the frontend on push.
- [ ] Poll `https://just-comfort-production-4c96.up.railway.app/v1/stats/categories?date_from=2026-06-01&date_to=2026-06-30` until it returns **401** (up + new required-date route present; a 422 without auth still proves the route exists, but 401 fires first from the JWT guard).
- [ ] Verify against prod data with prod env by running the real services for two adjacent months and asserting the totals differ and each is stable (not a rolling window):
      `railway run --service just-comfort -- uv run python <scratchpad>/verify_period.py`
      — call `by_category` for `2026-06-01..2026-06-30` and `2026-05-01..2026-05-31`; assert both return floats, and (if data exists) that the June total is independent of "today".
- [ ] Browser DOM check on `fimbook.vercel.app/stats` (user's logged-in tab): the period bar shows Week/Month/Year + `‹ label ›`; clicking next changes the label and the donut; the URL carries `granularity`/`anchor`; opening a category from the legend lands on a drill-down whose URL carries the same period. Read the DOM, not pixels (hidden MCP tab freezes `AnimatedNumber`).
- [ ] Update the ledger; note any follow-ups (notably: T1 will retire `days_back` from `list_transactions`).

## Self-review notes

- **Spec coverage:** calendar math single-homed (T1 `period.ts`); `by_category`/`subcategory_breakdown` → dates (T2/T3); `list_transactions` optional dates + `days_back` bridge (T4); shared inclusive-span validation with leap-year admittance (T2 `_validate_date_range`, pinned by `test_categories_leap_year_is_allowed`); StatsPage selector + URL state + legend propagation (T5); drill-down inheritance + trend stays 12m (T6); Monthly Overview/By Month left untouched (T5 note); empty/error states unchanged from ST3.
- **Type consistency:** `periodBounds`/`shiftPeriod`/`parsePeriodParams`/`formatPeriodLabel`/`currentAnchor` signatures identical across T1 definition and T5/T6 use; `date_from`/`date_to` are `date` in Python and `string` (`YYYY-MM-DD`) across the API boundary; `by_category(conn, date_from, date_to, direction)` positional order matches its route call; `subcategory_breakdown(conn, category, date_from, date_to, direction)` keeps `category` at index 1 so the ST3 `_category_or_null` test's `call_args[0][1]` still holds.
- **No placeholders:** every code step is complete, including `period.ts` and the CSS.
- **Half-open bound** (`< date_to + 1 day`) is asserted in T2/T3/T4 service tests; the leap-year cap is asserted at the API layer in T2.
