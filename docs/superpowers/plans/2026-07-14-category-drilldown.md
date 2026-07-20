# Category Drill-Down (ST3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tapping a category in the Stats donut legend opens a dedicated page showing its subcategory breakdown, a 12-month trend, and its transactions — with subcategory chips filtering the trend and list.

**Architecture:** Two new read-only stat services (`subcategory_breakdown`, `category_trend`) exposed as two `/v1` routes, plus a `subcategory` filter added to the existing transactions endpoint (no new list endpoint). A new React route `/stats/category/:category` renders the three sections; TanStack Query caches each independently so a chip click refetches only trend + list.

**Tech Stack:** Python/FastAPI/psycopg3 (backend), React 18 + TypeScript + react-router-dom + TanStack Query + recharts (frontend), pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-07-14-category-drilldown-design.md` (normative).

## Global Constraints

- Dashboard routes live on `router_v1` only (JWT enforced by the router), envelope `{"data": ...}`, `-> dict` annotation, thin route → service.
- **`float()` at the service boundary.** psycopg returns `Decimal`; uncast, pydantic v2 serializes it as a JSON *string*. Every numeric field returned must be a Python `float`.
- **Spending stats read `real_transactions`** (internal rows excluded), matching `by_category`. This is deliberately the OPPOSITE scope from `accounts.balances` / `balance_history`, which read `transactions` (internal included) so they reconcile with EB balances. State this in a comment where it could confuse.
- **Totals are positive magnitudes**: `SUM(ABS(eur_amount))`, matching `by_category`, so an expense trend rises as spending rises.
- **`Uncategorized` is a synthetic label** from `COALESCE(category, 'Uncategorized')`. It must map to SQL `category IS NULL`. A literal `category = 'Uncategorized'` silently returns nothing. The mapping lives in exactly one place: `_category_or_null` in `routes/api.py`.
- **`No subcategory`** is the equivalent sentinel for `subcategory IS NULL`, in both the breakdown output and the filters that accept it.
- **Trend gaps are zero-filled** (`0.0`), NOT carried forward — it is a flow, unlike `balance_history` which is a stock.
- New recharts series MUST set `isAnimationActive={false}` (rAF freezes in background tabs, leaving charts blank).
- UI copy: **English** section titles/labels ("All", "12-Month Trend", "See all"), **Italian** error messages ("Impossibile caricare…"), matching the existing app.
- Gates: `uv run pytest -q`, `uv run ruff check .`, `uv run pyrefly check` (backend, run from repo root); `npm run test && npm run lint && npm run build` (frontend, run from `frontend/`). `git commit` triggers lefthook.
- TDD: failing test first, RED evidence in the report.

## File Structure

| File | Responsibility |
|---|---|
| `src/fintracker/server/services/stats.py` | + `subcategory_breakdown`, + `category_trend` (read-only aggregations) |
| `src/fintracker/server/services/transactions.py` | + `subcategory` filter on `list_transactions` |
| `src/fintracker/server/routes/api.py` | + `_category_or_null` mapping, 2 wrappers, 2 routes, 1 new query param |
| `frontend/src/api/{types,client,queries}.ts` | + 2 types, 2 client calls, 2 query factories, `subcategory` filter |
| `frontend/src/pages/CategoryDetail/CategoryDetailPage.tsx` + `.module.css` | The drill-down page (3 sections) |
| `frontend/src/App.tsx` | + protected route `/stats/category/:category` |
| `frontend/src/pages/Stats/StatsPage.tsx` | legend items become navigating buttons |

**Deliberate non-reuse:** the drill-down's transaction rows are a purpose-built compact row (merchant · date · amount). The TransactionsPage row shows a category icon and category label, which are redundant here — the category *is* the page. This is a different presentation for a different context, not duplication; do NOT extract or share a row component.

---

### Task 1: `subcategory_breakdown` service

**Files:**
- Modify: `src/fintracker/server/services/stats.py` (append one function)
- Test: `tests/test_services.py` (append)

**Interfaces:**
- Produces: `subcategory_breakdown(conn, category: str | None, days_back: int, direction: str) -> list[dict]` → `[{"subcategory": str, "total": float, "count": int, "percentage": float}]`, ordered by total DESC. `category=None` means the uncategorised bucket. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_services.py` (helpers `_conn_with_cursor(rows) -> (conn, cur)` and `_conn_returning(rows) -> conn` already exist at the top of the file):

```python
def test_subcategory_breakdown_adds_percentages_and_floats():
    conn = _conn_returning(
        [
            {"subcategory": "Fuel", "total": 75.0, "count": 3},
            {"subcategory": "Tolls & Parking", "total": 25.0, "count": 1},
        ]
    )
    out = stats.subcategory_breakdown(conn, "Car", days_back=30, direction="expense")
    assert [r["percentage"] for r in out] == [75.0, 25.0]
    assert all(isinstance(r["total"], float) for r in out)


def test_subcategory_breakdown_uncategorized_uses_is_null():
    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(conn, None, days_back=30, direction="expense")
    sql = cur.execute.call_args[0][0]
    # 'Uncategorized' is a COALESCE label, not a stored value — a literal
    # comparison would silently return nothing.
    assert "category IS NULL" in sql
    assert "category = %s" not in sql


def test_subcategory_breakdown_named_category_is_parameterised():
    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(conn, "Car", days_back=30, direction="expense")
    sql, params = cur.execute.call_args[0]
    assert "category = %s" in sql
    assert params[0] == "Car"


def test_subcategory_breakdown_null_subcategory_gets_sentinel_label():
    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(conn, "Car", days_back=30, direction="expense")
    assert "'No subcategory'" in cur.execute.call_args[0][0]


def test_subcategory_breakdown_income_flips_sign_filter():
    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(conn, "Salary", days_back=30, direction="income")
    assert "amount > 0" in cur.execute.call_args[0][0]


def test_subcategory_breakdown_empty_does_not_divide_by_zero():
    conn = _conn_returning([])
    assert stats.subcategory_breakdown(conn, "Car", days_back=30, direction="expense") == []
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_services.py -q -k subcategory_breakdown`
Expected: 6 failures — `AttributeError: module ... has no attribute 'subcategory_breakdown'`.

- [ ] **Step 3: Implement** — append to `src/fintracker/server/services/stats.py`:

```python
def subcategory_breakdown(
    conn, category: str | None, days_back: int, direction: str
) -> list[dict]:
    """Subcategory split inside one category. `category=None` is the uncategorised bucket.

    Reads real_transactions (internal rows excluded) like by_category — the opposite
    scope from balance_history, which must include them to match EB balances.
    """
    # Both fixed literals, never user input: direction is route-validated, and the
    # category filter shape depends only on whether category is None.
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
                  AND booking_date >= NOW() - (%s * INTERVAL '1 day')
                GROUP BY subcategory
                ORDER BY total DESC""",
            [*params, days_back],
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["total"] = float(r["total"])
    grand_total = sum(r["total"] for r in rows) or 1
    for r in rows:
        r["percentage"] = round(r["total"] / grand_total * 100, 1)
    return rows
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest tests/test_services.py -q` → all pass. Then `uv run pytest -q && uv run ruff check . && uv run pyrefly check` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/stats.py tests/test_services.py
git commit -m "feat: subcategory breakdown service for category drill-down"
```

---

### Task 2: `category_trend` service

**Files:**
- Modify: `src/fintracker/server/services/stats.py` (append one function)
- Test: `tests/test_services.py` (append)

**Interfaces:**
- Consumes: `date`, `timedelta` (already imported at the top of stats.py for `balance_history`).
- Produces: `category_trend(conn, category: str | None, months: int, direction: str, subcategory: str | None = None) -> list[dict]` → exactly `months` ascending points `[{"month": "YYYY-MM", "total": float}]`, gaps zero-filled. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_services.py` (helper `_month_shift(back: int) -> str` already exists in this file from the balance-history work):

```python
def test_category_trend_zero_fills_empty_months():
    m2 = _month_shift(2)
    conn = _conn_returning([{"month": m2, "total": 40.0}])

    series = stats.category_trend(conn, "Car", months=3, direction="expense")

    assert [p["month"] for p in series] == [m2, _month_shift(1), _month_shift(0)]
    # flow, not stock: a quiet month is 0.0, never the previous month's value
    assert [p["total"] for p in series] == [40.0, 0.0, 0.0]
    assert all(isinstance(p["total"], float) for p in series)


def test_category_trend_returns_exactly_months_points():
    conn = _conn_returning([])
    series = stats.category_trend(conn, "Car", months=12, direction="expense")
    assert len(series) == 12
    assert series[-1]["month"] == _month_shift(0)
    assert {p["total"] for p in series} == {0.0}


def test_category_trend_named_subcategory_is_parameterised():
    conn, cur = _conn_with_cursor([])
    stats.category_trend(conn, "Car", months=6, direction="expense", subcategory="Fuel")
    sql, params = cur.execute.call_args[0]
    assert "subcategory = %s" in sql
    assert "Fuel" in params


def test_category_trend_sentinel_subcategory_uses_is_null():
    conn, cur = _conn_with_cursor([])
    stats.category_trend(
        conn, "Car", months=6, direction="expense", subcategory="No subcategory"
    )
    sql, params = cur.execute.call_args[0]
    assert "subcategory IS NULL" in sql
    assert "No subcategory" not in params


def test_category_trend_without_subcategory_adds_no_filter():
    conn, cur = _conn_with_cursor([])
    stats.category_trend(conn, "Car", months=6, direction="expense")
    assert "subcategory" not in cur.execute.call_args[0][0]


def test_category_trend_uses_absolute_amounts():
    conn, cur = _conn_with_cursor([])
    stats.category_trend(conn, "Car", months=6, direction="expense")
    # expenses must trend upward as spending grows, not plunge negative
    assert "ABS(eur_amount)" in cur.execute.call_args[0][0]
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_services.py -q -k category_trend`
Expected: 6 failures — `AttributeError: module ... has no attribute 'category_trend'`.

- [ ] **Step 3: Implement** — append to `src/fintracker/server/services/stats.py`:

```python
def category_trend(
    conn,
    category: str | None,
    months: int,
    direction: str,
    subcategory: str | None = None,
) -> list[dict]:
    """Monthly spend for one category, optionally one subcategory.

    A flow, not a stock: months with no activity are 0.0. (balance_history carries
    the previous value forward instead — do not copy that behaviour here.)
    """
    sign_filter = "amount > 0" if direction == "income" else "amount < 0"
    category_filter = "category IS NULL" if category is None else "category = %s"
    params: list = [] if category is None else [category]
    sub_filter = ""
    if subcategory == "No subcategory":
        sub_filter = "AND subcategory IS NULL"
    elif subcategory:
        sub_filter = "AND subcategory = %s"
        params.append(subcategory)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT TO_CHAR(DATE_TRUNC('month', booking_date), 'YYYY-MM') AS month,
                       ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total
                FROM real_transactions
                WHERE {sign_filter}
                  AND {category_filter}
                  {sub_filter}
                GROUP BY 1
                ORDER BY 1""",
            params,
        )
        rows = cur.fetchall()

    totals = {r["month"]: float(r["total"]) for r in rows}
    current = date.today().replace(day=1)
    start = current
    for _ in range(months - 1):
        start = (start - timedelta(days=1)).replace(day=1)

    series: list[dict] = []
    cursor_month = start
    while cursor_month <= current:
        key = cursor_month.strftime("%Y-%m")
        series.append({"month": key, "total": totals.get(key, 0.0)})
        next_month = cursor_month.month % 12 + 1
        cursor_month = date(cursor_month.year + (cursor_month.month == 12), next_month, 1)
    return series
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest tests/test_services.py -q` → all pass. Then `uv run pytest -q && uv run ruff check . && uv run pyrefly check` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/stats.py tests/test_services.py
git commit -m "feat: per-category monthly trend service (zero-filled flow series)"
```

---

### Task 3: `subcategory` filter on the transactions list

**Files:**
- Modify: `src/fintracker/server/services/transactions.py` (`list_transactions`)
- Modify: `src/fintracker/server/routes/api.py` (`_list_transactions` wrapper + `list_transactions_v1` route)
- Test: `tests/test_services.py` and `tests/test_api_routes.py` (append)

**Interfaces:**
- Produces: `list_transactions(conn, *, page, page_size, days_back, category, direction, search, subcategory)` — new keyword-only `subcategory: str | None`. Route `GET /v1/transactions` gains optional `subcategory` query param. Consumed by Task 5.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_services.py`:

```python
def test_list_transactions_named_subcategory_is_parameterised():
    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn,
        page=1,
        page_size=50,
        days_back=30,
        category="Car",
        direction=None,
        search=None,
        subcategory="Fuel",
    )
    sql, params = cur.execute.call_args[0]
    assert "subcategory = %s" in sql
    assert "Fuel" in params


def test_list_transactions_sentinel_subcategory_uses_is_null():
    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn,
        page=1,
        page_size=50,
        days_back=30,
        category="Car",
        direction=None,
        search=None,
        subcategory="No subcategory",
    )
    sql, params = cur.execute.call_args[0]
    assert "subcategory IS NULL" in sql
    assert "No subcategory" not in params
```

and append to `tests/test_api_routes.py` inside the existing transactions test class (or as a new test at module level, matching the file's style):

```python
def test_transactions_accepts_subcategory_filter(auth_client):
    with patch(
        "fintracker.storage.db.get_pool",
        return_value=_mock_pool(_mock_conn([FAKE_ROW], {"total": 1})),
    ):
        resp = auth_client.get("/v1/transactions?category=Car&subcategory=Fuel")
    assert resp.status_code == 200
```

Add `from fintracker.server.services import transactions` to the imports of `tests/test_services.py` if it is not already imported (the file currently imports `accounts, stats`).

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_services.py -q -k subcategory`
Expected: the two new service tests FAIL with `TypeError: list_transactions() got an unexpected keyword argument 'subcategory'`.

- [ ] **Step 3: Implement** — three edits.

1. `src/fintracker/server/services/transactions.py`, extend the signature:

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
) -> dict:
```

and insert immediately after the existing `if category:` block:

```python
    if subcategory == "No subcategory":
        conditions.append("subcategory IS NULL")
    elif subcategory:
        conditions.append("subcategory = %s")
        params.append(subcategory)
```

2. `src/fintracker/server/routes/api.py`, extend the wrapper:

```python
def _list_transactions(
    page: int,
    page_size: int,
    days_back: int,
    category: str | None,
    direction: str | None,
    search: str | None,
    subcategory: str | None,
) -> dict:
    with db_conn() as conn:
        return transactions.list_transactions(
            conn,
            page=page,
            page_size=page_size,
            days_back=days_back,
            category=category,
            direction=direction,
            search=search,
            subcategory=subcategory,
        )
```

3. `src/fintracker/server/routes/api.py`, extend the route:

```python
@router_v1.get("/transactions")
def list_transactions_v1(
    page: PageQ = 1,
    page_size: PageSizeQ = 50,
    days_back: DaysBackQ = 30,
    category: str | None = None,
    direction: DirectionQ = None,
    search: str | None = None,
    subcategory: str | None = None,
) -> dict:
    return {
        "data": _list_transactions(
            page, page_size, days_back, category, direction, search, subcategory
        )
    }
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest -q && uv run ruff check . && uv run pyrefly check` → all clean (the existing transactions tests must still pass; `subcategory` defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/transactions.py src/fintracker/server/routes/api.py tests/test_services.py tests/test_api_routes.py
git commit -m "feat: subcategory filter on transactions list"
```

---

### Task 4: Two drill-down stat routes

**Files:**
- Modify: `src/fintracker/server/routes/api.py` (constant + mapping helper + 2 wrappers + 2 routes)
- Test: `tests/test_api_routes.py` (append a class)

**Interfaces:**
- Consumes: `stats.subcategory_breakdown` (Task 1), `stats.category_trend` (Task 2), existing `DaysBackQ` / `MonthsQ` / `DirectionQ`.
- Produces:
  `GET /v1/stats/categories/{category}/subcategories?days_back=&direction=` → `{"data": [SubcategoryStat]}`
  `GET /v1/stats/categories/{category}/trend?months=&direction=&subcategory=` → `{"data": [CategoryTrendPoint]}`
  Consumed by Task 5.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_api_routes.py`:

```python
class TestCategoryDrilldown:
    def test_subcategories_missing_auth_returns_401(self, client):
        resp = client.get("/v1/stats/categories/Car/subcategories")
        assert resp.status_code == 401

    def test_trend_missing_auth_returns_401(self, client):
        resp = client.get("/v1/stats/categories/Car/trend")
        assert resp.status_code == 401

    def test_subcategories_returns_float_totals(self, auth_client):
        row = {"subcategory": "Fuel", "total": Decimal("75.00"), "count": 3}
        with patch(
            "fintracker.storage.db.get_pool",
            return_value=_mock_pool(_mock_conn([row])),
        ):
            resp = auth_client.get("/v1/stats/categories/Car/subcategories")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data[0]["total"], float)
        assert isinstance(data[0]["percentage"], float)

    def test_trend_returns_float_totals(self, auth_client):
        with patch(
            "fintracker.storage.db.get_pool",
            return_value=_mock_pool(_mock_conn([])),
        ):
            resp = auth_client.get("/v1/stats/categories/Car/trend?months=3")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 3
        assert all(isinstance(p["total"], float) for p in data)

    def test_trend_months_above_24_returns_422(self, auth_client):
        resp = auth_client.get("/v1/stats/categories/Car/trend?months=25")
        assert resp.status_code == 422

    def test_category_with_space_round_trips(self, auth_client):
        with patch("fintracker.server.routes.api.stats.subcategory_breakdown") as mocked:
            mocked.return_value = []
            resp = auth_client.get("/v1/stats/categories/Eating%20Out/subcategories")
        assert resp.status_code == 200
        assert mocked.call_args[0][1] == "Eating Out"

    def test_uncategorized_label_maps_to_none(self, auth_client):
        with patch("fintracker.server.routes.api.stats.subcategory_breakdown") as mocked:
            mocked.return_value = []
            resp = auth_client.get("/v1/stats/categories/Uncategorized/subcategories")
        assert resp.status_code == 200
        # the synthetic COALESCE label must become NULL, not a literal search
        assert mocked.call_args[0][1] is None
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_api_routes.py -q -k CategoryDrilldown`
Expected: failures — the auth tests get 404 instead of 401 (route missing), the rest error for the same reason.

- [ ] **Step 3: Implement** — in `src/fintracker/server/routes/api.py`.

Add near the other module-level constants (above the wrappers):

```python
# The donut labels NULL-category rows 'Uncategorized' via COALESCE. Map that synthetic
# label back to NULL here — the one place it is translated — so drill-down queries don't
# search for a literal category with that name and silently return nothing.
UNCATEGORIZED_LABEL = "Uncategorized"


def _category_or_null(category: str) -> str | None:
    return None if category == UNCATEGORIZED_LABEL else category
```

Add the wrappers next to `_stats_balance_history`:

```python
def _stats_subcategories(category: str, days_back: int, direction: str) -> list[dict]:
    with db_conn() as conn:
        return stats.subcategory_breakdown(
            conn, _category_or_null(category), days_back, direction
        )


def _stats_category_trend(
    category: str, months: int, direction: str, subcategory: str | None
) -> list[dict]:
    with db_conn() as conn:
        return stats.category_trend(
            conn, _category_or_null(category), months, direction, subcategory
        )
```

Add the routes after `stats_balance_history_v1`:

```python
@router_v1.get("/stats/categories/{category}/subcategories")
def stats_subcategories_v1(
    category: str, days_back: DaysBackQ = 30, direction: DirectionQ = None
) -> dict:
    return {"data": _stats_subcategories(category, days_back, direction or "expense")}


@router_v1.get("/stats/categories/{category}/trend")
def stats_category_trend_v1(
    category: str,
    months: MonthsQ = 12,
    direction: DirectionQ = None,
    subcategory: str | None = None,
) -> dict:
    return {
        "data": _stats_category_trend(category, months, direction or "expense", subcategory)
    }
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest tests/test_api_routes.py -q` → all pass; then `uv run pytest -q && uv run ruff check . && uv run pyrefly check` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/routes/api.py tests/test_api_routes.py
git commit -m "feat: /v1 subcategory-breakdown and category-trend endpoints"
```

---

### Task 5: CategoryDetailPage + frontend data layer + route

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/queries.ts`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/CategoryDetail/CategoryDetailPage.tsx`
- Create: `frontend/src/pages/CategoryDetail/CategoryDetailPage.module.css`
- Test: `frontend/src/tests/CategoryDetailPage.test.tsx` (new)

**Interfaces:**
- Consumes: the two endpoints from Task 4 and the `subcategory` filter from Task 3.
- Produces: route `/stats/category/:category?direction=` rendering the page. Consumed by Task 6 (which navigates to it).

All frontend commands run from `frontend/`.

- [ ] **Step 1: Write the failing test** — create `frontend/src/tests/CategoryDetailPage.test.tsx`:

```tsx
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { CategoryDetailPage } from '../pages/CategoryDetail/CategoryDetailPage';

const { subcategoriesMock, trendMock, listMock } = vi.hoisted(() => ({
  subcategoriesMock: vi.fn(),
  trendMock: vi.fn(),
  listMock: vi.fn(),
}));

vi.mock('../api/client', () => ({
  api: {
    stats: { subcategories: subcategoriesMock, categoryTrend: trendMock },
    transactions: { list: listMock },
  },
}));

beforeEach(() => {
  subcategoriesMock.mockReset().mockResolvedValue([
    { subcategory: 'Fuel', total: 75, count: 3, percentage: 75 },
    { subcategory: 'Tolls & Parking', total: 25, count: 1, percentage: 25 },
  ]);
  trendMock.mockReset().mockResolvedValue([
    { month: '2026-06', total: 40 },
    { month: '2026-07', total: 60 },
  ]);
  listMock.mockReset().mockResolvedValue({
    items: [
      {
        id: 1, dedup_hash: 'h', booking_date: '2026-07-02T00:00:00Z', amount: -20,
        currency: 'EUR', eur_amount: -20, description: null, merchant_name: 'Q8',
        account_id: 'a', is_internal: false, category: 'Car', subcategory: 'Fuel',
        status: 'verified', source: 'enable_banking', created_at: '2026-07-02T00:00:00Z',
      },
    ],
    total: 1, page: 1, page_size: 20,
  });
});

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={['/stats/category/Car?direction=expense']}>
        <Routes>
          <Route path="/stats/category/:category" element={<CategoryDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CategoryDetailPage', () => {
  it('renders all three sections for the category', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Car')).toBeInTheDocument());
    expect(screen.getByText('12-Month Trend')).toBeInTheDocument();
    expect(screen.getByText('Fuel')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Q8')).toBeInTheDocument());
  });

  it('refetches trend and transactions narrowed to a chosen subcategory', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Fuel')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Fuel/ }));

    await waitFor(() =>
      expect(trendMock).toHaveBeenCalledWith(
        expect.objectContaining({ category: 'Car', subcategory: 'Fuel' }),
      ),
    );
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'Car', subcategory: 'Fuel' }),
    );
  });
});
```

- [ ] **Step 2: Run to verify RED**

Run (from `frontend/`): `npx vitest run src/tests/CategoryDetailPage.test.tsx`
Expected: FAIL — cannot resolve `../pages/CategoryDetail/CategoryDetailPage`.

- [ ] **Step 3: Implement** — six edits.

1. `frontend/src/api/types.ts` — append, and extend `TransactionFilters` with `subcategory?: string;`:

```ts
export interface SubcategoryStat {
  subcategory: string;
  total: number;
  count: number;
  percentage: number;
}

export interface CategoryTrendPoint {
  month: string;
  total: number;
}
```

2. `frontend/src/api/client.ts` — add `SubcategoryStat, CategoryTrendPoint` to the type imports and add to the `stats` object:

```ts
    subcategories: (params: {
      category: string;
      days_back?: number;
      direction?: 'income' | 'expense';
    }): Promise<SubcategoryStat[]> => {
      const { category, ...q } = params;
      return http
        .get(`/v1/stats/categories/${encodeURIComponent(category)}/subcategories`, { params: q })
        .then(unwrap<SubcategoryStat[]>);
    },
    categoryTrend: (params: {
      category: string;
      months?: number;
      direction?: 'income' | 'expense';
      subcategory?: string;
    }): Promise<CategoryTrendPoint[]> => {
      const { category, ...q } = params;
      return http
        .get(`/v1/stats/categories/${encodeURIComponent(category)}/trend`, { params: q })
        .then(unwrap<CategoryTrendPoint[]>);
    },
```

3. `frontend/src/api/queries.ts` — append to `statsQueries`:

```ts
  subcategories: (
    category: string,
    days_back = 30,
    direction: 'income' | 'expense' = 'expense',
  ) => ({
    queryKey: ['stats', 'subcategories', category, days_back, direction] as const,
    queryFn: () => api.stats.subcategories({ category, days_back, direction }),
  }),
  categoryTrend: (
    category: string,
    months = 12,
    direction: 'income' | 'expense' = 'expense',
    subcategory?: string,
  ) => ({
    // subcategory is part of the key so picking a chip refetches only this query
    queryKey: ['stats', 'category-trend', category, months, direction, subcategory ?? null] as const,
    queryFn: () => api.stats.categoryTrend({ category, months, direction, subcategory }),
  }),
```

4. `frontend/src/App.tsx` — add inside the `<ProtectedRoute>` block, after the `/stats` route:

```tsx
            <Route path="/stats/category/:category" element={<CategoryDetailPage />} />
```

and the matching import:

```tsx
import { CategoryDetailPage } from './pages/CategoryDetail/CategoryDetailPage';
```

5. Create `frontend/src/pages/CategoryDetail/CategoryDetailPage.tsx`:

```tsx
import { useState } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { statsQueries, transactionQueries } from '../../api/queries';
import styles from './CategoryDetailPage.module.css';

const ALL = 'All';
const TREND_MONTHS = 12;
const DAYS_BACK = 30;
const TX_LIMIT = 20;

function formatMonth(iso: string): string {
  const [y, m] = iso.split('-');
  return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('it-IT', { month: 'short' });
}

function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString('it-IT', { day: '2-digit', month: 'short' });
}

interface TrendTooltipProps {
  active?: boolean;
  payload?: Array<{ value?: number | string }>;
  label?: string;
}

const TrendTooltip = ({ active, payload, label }: TrendTooltipProps) => {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <div>{formatMonth(label ?? '')}</div>
      <div className={styles.tooltipValue}>
        €{Number(payload[0]?.value).toLocaleString('it-IT', { minimumFractionDigits: 2 })}
      </div>
    </div>
  );
};

export function CategoryDetailPage() {
  const { category = '' } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const direction = searchParams.get('direction') === 'income' ? 'income' : 'expense';

  const [selectedSub, setSelectedSub] = useState<string>(ALL);
  const subFilter = selectedSub === ALL ? undefined : selectedSub;

  const subcategories = useQuery({
    ...statsQueries.subcategories(category, DAYS_BACK, direction),
  });
  const trend = useQuery({
    ...statsQueries.categoryTrend(category, TREND_MONTHS, direction, subFilter),
  });
  const transactions = useQuery({
    ...transactionQueries.list({
      category,
      subcategory: subFilter,
      direction,
      days_back: DAYS_BACK,
      page_size: TX_LIMIT,
    }),
  });

  const subData = subcategories.data ?? [];
  const trendData = trend.data ?? [];
  const txItems = transactions.data?.items ?? [];
  const periodTotal = subData.reduce((s, r) => s + r.total, 0);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button className={styles.back} onClick={() => navigate(-1)} aria-label="Indietro">
          ←
        </button>
        <div>
          <h1 className={styles.title}>{category}</h1>
          <span className={styles.subtitle}>
            € {periodTotal.toLocaleString('it-IT', { minimumFractionDigits: 2 })} · ultimi 30 giorni
          </span>
        </div>
      </header>

      <main className={styles.main}>
        {subData.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Subcategories</h2>
            {subcategories.isError && (
              <div className={styles.stateMsg}>Impossibile caricare le sottocategorie — riprova.</div>
            )}
            <div className={styles.chips}>
              <button
                className={`${styles.chip} ${selectedSub === ALL ? styles.chipActive : ''}`}
                onClick={() => setSelectedSub(ALL)}
              >
                {ALL}
              </button>
              {subData.map(s => (
                <button
                  key={s.subcategory}
                  className={`${styles.chip} ${selectedSub === s.subcategory ? styles.chipActive : ''}`}
                  onClick={() => setSelectedSub(s.subcategory)}
                >
                  {s.subcategory} <span className={styles.chipPct}>{s.percentage.toFixed(0)}%</span>
                </button>
              ))}
            </div>
          </section>
        )}

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>12-Month Trend</h2>
          {trend.isError && (
            <div className={styles.stateMsg}>Impossibile caricare l'andamento — riprova.</div>
          )}
          <ResponsiveContainer width="100%" height={200}>
            {/* isAnimationActive: rAF is frozen in background tabs, which would leave this blank */}
            <LineChart data={trendData}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="month"
                tickFormatter={formatMonth}
                tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--text-muted)' }}
                tickFormatter={v => `€${Math.round(v)}`}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<TrendTooltip />} />
              <Line
                type="monotone"
                dataKey="total"
                stroke="var(--accent)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Transactions</h2>
          {transactions.isError && (
            <div className={styles.stateMsg}>Impossibile caricare le transazioni — riprova.</div>
          )}
          {!transactions.isError && txItems.length === 0 && (
            <div className={styles.stateMsg}>Nessuna transazione in questo periodo.</div>
          )}
          {txItems.map((tx, i) => (
            <motion.div
              key={tx.id}
              className={styles.txRow}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03, duration: 0.25 }}
            >
              <div className={styles.txInfo}>
                <span className={styles.txMerchant}>
                  {tx.merchant_name ?? tx.description ?? '—'}
                </span>
                <span className={styles.txMeta}>{formatDay(tx.booking_date)}</span>
              </div>
              <span className={styles.txAmount}>
                €{Math.abs(tx.eur_amount).toFixed(2)}
              </span>
            </motion.div>
          ))}
          <Link
            className={styles.seeAll}
            to={`/transactions?category=${encodeURIComponent(category)}`}
          >
            See all
          </Link>
        </section>
      </main>
    </div>
  );
}
```

6. Create `frontend/src/pages/CategoryDetail/CategoryDetailPage.module.css`:

```css
.page { min-height: 100vh; background: var(--bg); padding-bottom: 88px; }

.header {
  display: flex; align-items: center; gap: 12px;
  padding: 20px 20px 12px;
}
.back {
  background: none; border: none; cursor: pointer;
  color: var(--text-primary); font-size: 22px; line-height: 1;
  padding: 4px 8px; border-radius: 8px;
}
.back:hover { background: var(--bg-hover); }
.title { font-size: 22px; font-weight: 600; color: var(--text-primary); margin: 0; }
.subtitle { font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); }

.main { padding: 0 20px; display: flex; flex-direction: column; gap: 24px; }

.section { display: flex; flex-direction: column; gap: 12px; }
.sectionTitle {
  font-size: 13px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--text-muted); margin: 0;
}

.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  border: 1px solid var(--border); background: var(--bg-elevated);
  color: var(--text-secondary); border-radius: 999px;
  padding: 6px 12px; font-size: 13px; cursor: pointer;
}
.chip:hover { background: var(--bg-hover); }
.chipActive {
  border-color: var(--accent); color: var(--text-primary);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.chipPct { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }

.tooltip {
  background: var(--bg-elevated); border: 1px solid var(--border-strong);
  border-radius: 8px; padding: 8px 12px;
  font-family: var(--font-mono); font-size: 12px; color: var(--text-primary);
}
.tooltipValue { color: var(--accent); font-weight: 600; }

.txRow {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0; border-bottom: 1px solid var(--border);
}
.txInfo { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.txMerchant {
  font-size: 14px; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.txMeta { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
.txAmount { font-family: var(--font-mono); font-size: 14px; color: var(--text-primary); }

.seeAll {
  align-self: flex-start; margin-top: 4px;
  font-size: 13px; color: var(--accent); text-decoration: none;
}
.seeAll:hover { text-decoration: underline; }

.stateMsg {
  padding: 12px; border-radius: 8px;
  background: var(--bg-elevated); color: var(--text-muted); font-size: 13px;
}
```

- [ ] **Step 4: Run to verify GREEN**

Run (from `frontend/`): `npx vitest run src/tests/CategoryDetailPage.test.tsx` → 2 passed.
Then the full gate: `npm run test && npm run lint && npm run build` → all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/queries.ts frontend/src/App.tsx frontend/src/pages/CategoryDetail frontend/src/tests/CategoryDetailPage.test.tsx
git commit -m "feat(frontend): category drill-down page with subcategory chips, trend and transactions"
```

---

### Task 6: Make the Stats legend navigate to the drill-down

**Files:**
- Modify: `frontend/src/pages/Stats/StatsPage.tsx`
- Modify: `frontend/src/pages/Stats/StatsPage.module.css` (button reset on `.legendItem`)
- Test: `frontend/src/tests/StatsPage.test.tsx` (append)

**Interfaces:**
- Consumes: the route from Task 5.
- Produces: no downstream consumers (user-facing behaviour).

- [ ] **Step 1: Write the failing test** — append to `frontend/src/tests/StatsPage.test.tsx`. The file currently mocks `../api/client` with a `stats` object and renders `<StatsPage />`; extend its mock so `categories` resolves with one row, wrap the render in a `MemoryRouter`, and assert navigation:

```tsx
it('navigates to the category drill-down when a legend item is clicked', async () => {
  categoriesMock.mockResolvedValue([
    { category: 'Eating Out', total: 50, count: 2, percentage: 100 },
  ]);
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={['/stats']}>
        <Routes>
          <Route path="/stats" element={<StatsPage />} />
          <Route
            path="/stats/category/:category"
            element={<div>detail-for-Eating Out</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByText('Eating Out')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: /Eating Out/ }));

  await waitFor(() =>
    expect(screen.getByText('detail-for-Eating Out')).toBeInTheDocument(),
  );
});
```

Add the imports this test needs at the top of the file if absent: `MemoryRouter, Routes, Route` from `react-router-dom`.

- [ ] **Step 2: Run to verify RED**

Run (from `frontend/`): `npx vitest run src/tests/StatsPage.test.tsx`
Expected: FAIL — the legend renders a `div`, so `getByRole('button', ...)` finds nothing.

- [ ] **Step 3: Implement** — in `frontend/src/pages/Stats/StatsPage.tsx`.

Add `useNavigate` to the react-router import (add the import line if the file has none):

```tsx
import { useNavigate } from 'react-router-dom';
```

Inside `StatsPage`, next to the other hooks:

```tsx
  const navigate = useNavigate();
```

Replace the legend `motion.div` with a real button so it is keyboard-reachable, keeping the existing classes and hover behaviour:

```tsx
              <motion.button
                key={cat.category}
                type="button"
                className={styles.legendItem}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05, duration: 0.3 }}
                onMouseEnter={() => setActiveIdx(i)}
                onMouseLeave={() => setActiveIdx(null)}
                onClick={() =>
                  navigate(
                    `/stats/category/${encodeURIComponent(cat.category)}?direction=${
                      tab === 'income' ? 'income' : 'expense'
                    }`,
                  )
                }
                style={{ opacity: activeIdx === null || activeIdx === i ? 1 : 0.4 }}
              >
```

and close it with `</motion.button>` instead of `</motion.div>`.

In `frontend/src/pages/Stats/StatsPage.module.css`, extend the `.legendItem` rule so the button carries no default chrome (append these declarations to the existing rule):

```css
  background: none;
  border: none;
  width: 100%;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
```

- [ ] **Step 4: Run to verify GREEN**

Run (from `frontend/`): `npx vitest run src/tests/StatsPage.test.tsx` → all pass.
Then the full gate: `npm run test && npm run lint && npm run build` → all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Stats/StatsPage.tsx frontend/src/pages/Stats/StatsPage.module.css frontend/src/tests/StatsPage.test.tsx
git commit -m "feat(frontend): open category drill-down from the Stats legend"
```

---

### Task 7: Deploy and verify (controller-executed)

- [ ] Push `main`; `railway up --detach --service just-comfort`; Vercel auto-deploys the frontend on push.
- [ ] Poll `https://just-comfort-production-4c96.up.railway.app/v1/stats/categories/Car/trend` until it returns **401** (up + route present; 404 means the old build is still serving).
- [ ] Verify against prod data by running the real services with prod env:
      `railway run --service just-comfort -- uv run python <scratchpad>/verify_drilldown.py`
      asserting for a real category: percentages sum to ~100, trend has exactly 12 ascending points with `0.0` in quiet months, and every numeric field is a `float`.
- [ ] Browser DOM check on `fimbook.vercel.app/stats` (user's logged-in tab): clicking a legend entry lands on `/stats/category/...`, the page shows all three sections, and clicking a chip changes the rendered transaction rows. Read the DOM, not pixels — the MCP tab is `visibilityState: hidden`, so `AnimatedNumber` freezes at € 0,00 and screenshots mislead.
- [ ] Update the ledger; note any follow-ups.

## Self-review notes

- **Spec coverage:** route + back/reload (T5), mixed labelled windows (T5: 30d header/list, 12m trend title), chips filter trend+list (T5), reuse of `/v1/transactions` via a new filter (T3), `Uncategorized`→NULL in one place (T4 `_category_or_null`, pinned by a test), `No subcategory` sentinel (T1/T2/T3), zero-fill vs carry-forward (T2, asserted), `ABS` magnitudes (T2, asserted), `real_transactions` scope + opposite-scope comment (T1), empty/error states (T5), `isAnimationActive={false}` (T5), English labels + Italian errors (T5), legend a11y as a real button (T6).
- **Type consistency:** `subcategory_breakdown(conn, category, days_back, direction)` and `category_trend(conn, category, months, direction, subcategory=None)` are called with exactly these shapes in T4; `SubcategoryStat` / `CategoryTrendPoint` field names match the services' output keys (`subcategory/total/count/percentage`, `month/total`); `subcategory` is the same param name across service, route, client, and query key.
- **No placeholders:** every code step contains complete code, including the new CSS module.
- The `Uncategorized`→`None` test asserts `mocked.call_args[0][1]`, i.e. the second positional arg of `stats.subcategory_breakdown(conn, category, ...)` — the wrapper must keep passing `conn` first positionally for that index to hold.
