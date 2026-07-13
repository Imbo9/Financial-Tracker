# Balance History (AC3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Absolute total-balance-over-time line chart in AccountsPage, backed by a one-shot Enable Banking balance calibration that also makes the accounts list / net worth absolute.

**Architecture:** New `accounts` table (Alembic 0002, hand-written like the baseline) stores per-account opening balances. A one-shot script reads current real balances from EB (`GET /accounts/{uid}/balances`) and derives `opening = eb_balance − SUM(all deltas)`. A stats service builds the monthly cumulative series (openings + running transaction sums, carry-forward through empty months) served at `GET /v1/stats/balance-history`; the accounts service LEFT JOINs openings so every displayed balance is absolute.

**Tech Stack:** Python/FastAPI/psycopg3/Alembic (backend), httpx for EB, React+TS+TanStack Query+recharts (frontend), pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-07-13-balance-history-design.md` (normative).

## Global Constraints

- Alembic-only DDL; the new revision is **hand-written** `op.execute` SQL like `migrations/versions/0001_baseline.py` (no autogenerate — the repo has no ORM metadata). `revision = "0002"`, `down_revision = "0001"`.
- Dashboard API only under `/v1`, envelope `{"data": ...}`, JWT via `router_v1`, `-> dict` annotation style, **`float()` cast at the service boundary** (pydantic v2 serializes Decimal as JSON string otherwise — the app's #1 landmine).
- Privacy invariant untouched: categorizer/EB code sends nothing new anywhere; the balances call is EB-only.
- Balance math includes `is_internal=TRUE` rows (they move real money) and excludes `account_id IS NULL` rows (manual entries, consistent with the accounts page).
- New recharts series MUST set `isAnimationActive={false}` (background-tab rAF freeze lesson).
- Gates per commit (lefthook): ruff, pyrefly, pytest, gitleaks. Frontend gate: `npm run test && npm run lint && npm run build` from `frontend/`.
- TDD: failing test before implementation, RED evidence in report. Windows host: backend commands from repo root via `uv run`, frontend from `frontend/`.
- `settings.ENABLE_BANKING_ACCOUNT_IDS` is a plain `list[str]` attribute (not SecretStr).

---

### Task 1: Alembic revision 0002 — `accounts` table

**Files:**
- Create: `migrations/versions/0002_accounts.py`

**Interfaces:**
- Produces: table `accounts(account_uid TEXT PK, display_name TEXT, opening_balance NUMERIC NOT NULL DEFAULT 0, eb_balance NUMERIC, calibrated_at TIMESTAMPTZ)` — consumed by Tasks 3, 4, 6.

- [ ] **Step 1: Write the revision** (hand-written, mirroring the baseline's style):

```python
"""accounts: per-account opening balances for absolute balance math (spec 2026-07-13)"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS accounts (
    account_uid     TEXT PRIMARY KEY,
    display_name    TEXT,
    opening_balance NUMERIC     NOT NULL DEFAULT 0,
    eb_balance      NUMERIC,
    calibrated_at   TIMESTAMPTZ
);
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accounts;")
```

- [ ] **Step 2: Verify structurally**

Run: `uv run alembic heads` — expected: `0002 (head)`. Then `uv run alembic history` — expected: `0001 -> 0002`. (A live `upgrade head` runs against local Docker PG only if `docker compose up db -d` succeeds — attempt it; if the Docker daemon is down, note it in the report: prod apply happens in Task 8.)

- [ ] **Step 3: Full suite still green**

Run: `uv run pytest -q` — expected: 188 passed (migrations aren't imported by tests).

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0002_accounts.py
git commit -m "feat: accounts table for opening balances (alembic 0002)"
```

---

### Task 2: `fetch_balances` on the EB client

**Files:**
- Modify: `src/fintracker/ingestion/fetch_transactions.py` (add import + one function; touch nothing else)
- Test: `tests/test_fetch_balances.py` (new)

**Interfaces:**
- Consumes: existing `_get(client, path, **params)` helper in the same module.
- Produces: `fetch_balances(client: httpx.Client, account_uid: str) -> Decimal` — consumed by Task 3.

- [ ] **Step 1: Write the failing tests** — `tests/test_fetch_balances.py`:

```python
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from fintracker.ingestion import fetch_transactions as ft


def _patch_get(monkeypatch, payload):
    monkeypatch.setattr(ft, "_get", lambda client, path, **params: payload)


def test_prefers_closing_booked_balance(monkeypatch):
    _patch_get(
        monkeypatch,
        {
            "balances": [
                {"balance_type": "ITAV", "balance_amount": {"currency": "EUR", "amount": "10.00"}},
                {"balance_type": "CLBD", "balance_amount": {"currency": "EUR", "amount": "42.50"}},
            ]
        },
    )
    assert ft.fetch_balances(MagicMock(), "acc-1") == Decimal("42.50")


def test_falls_back_to_first_balance(monkeypatch):
    _patch_get(
        monkeypatch,
        {"balances": [{"balance_type": "ITAV", "balance_amount": {"currency": "EUR", "amount": "7.10"}}]},
    )
    assert ft.fetch_balances(MagicMock(), "acc-1") == Decimal("7.10")


def test_warns_on_non_eur_currency(monkeypatch, caplog):
    _patch_get(
        monkeypatch,
        {"balances": [{"balance_type": "CLBD", "balance_amount": {"currency": "USD", "amount": "5.00"}}]},
    )
    with caplog.at_level("WARNING"):
        assert ft.fetch_balances(MagicMock(), "acc-1") == Decimal("5.00")
    assert "USD" in caplog.text


def test_empty_balances_raises(monkeypatch):
    _patch_get(monkeypatch, {"balances": []})
    with pytest.raises(ValueError):
        ft.fetch_balances(MagicMock(), "acc-1")
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_fetch_balances.py -q`
Expected: 4 failures — `AttributeError: module ... has no attribute 'fetch_balances'`.

- [ ] **Step 3: Implement** — in `src/fintracker/ingestion/fetch_transactions.py`, add `from decimal import Decimal` to the imports and this function right after `_get`:

```python
def fetch_balances(client: httpx.Client, account_uid: str) -> Decimal:
    """Current balance for one account; prefers closing-booked (CLBD) per Berlin Group."""
    data = _get(client, f"/accounts/{account_uid}/balances")
    balances = data.get("balances") or []
    if not balances:
        raise ValueError(f"No balances returned for account {account_uid}")
    chosen = next((b for b in balances if b.get("balance_type") == "CLBD"), balances[0])
    amount = chosen["balance_amount"]
    if amount.get("currency") != "EUR":
        log.warning(
            "Account %s balance is in %s — treating as EUR per app convention",
            account_uid,
            amount.get("currency"),
        )
    return Decimal(amount["amount"])
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest tests/test_fetch_balances.py -q` → 4 passed; then `uv run pytest -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/ingestion/fetch_transactions.py tests/test_fetch_balances.py
git commit -m "feat: EB balances fetch (CLBD-preferred) for calibration"
```

---

### Task 3: Calibration script

**Files:**
- Create: `scripts/calibrate_balances.py`
- Test: `tests/test_calibrate_balances.py` (new)

**Interfaces:**
- Consumes: `fetch_balances` (Task 2), `accounts` table (Task 1), `direct_connection()` from `fintracker.storage.db`, `settings.ENABLE_BANKING_ACCOUNT_IDS: list[str]`.
- Produces: `calibrate(conn, client, account_uids: list[str]) -> dict[str, dict]` (uid → {eb_balance, delta_sum, opening} as Decimals); CLI entry.

- [ ] **Step 1: Write the failing test** — `tests/test_calibrate_balances.py`:

```python
from decimal import Decimal
from unittest.mock import MagicMock

import scripts.calibrate_balances as cal  # pyrefly: ignore[missing-import]


def _conn_with_cursor(delta_sum):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (delta_sum,)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_opening_is_eb_balance_minus_known_deltas(monkeypatch):
    monkeypatch.setattr(cal, "fetch_balances", lambda client, uid: Decimal("150.00"))
    monkeypatch.setattr(cal.time, "sleep", lambda s: None)
    conn, cur = _conn_with_cursor(Decimal("-50.00"))

    out = cal.calibrate(conn, MagicMock(), ["acc-1"])

    assert out["acc-1"]["opening"] == Decimal("200.00")  # 150 − (−50)
    upsert_sql, upsert_params = cur.execute.call_args_list[1].args
    assert "ON CONFLICT (account_uid) DO UPDATE" in upsert_sql
    assert upsert_params == ("acc-1", Decimal("200.00"), Decimal("150.00"))
    assert conn.commit.called


def test_calibrates_every_account_with_delay(monkeypatch):
    calls = []
    monkeypatch.setattr(cal, "fetch_balances", lambda client, uid: Decimal("10.00"))
    monkeypatch.setattr(cal.time, "sleep", lambda s: calls.append(s))
    conn, _cur = _conn_with_cursor(Decimal("0"))

    out = cal.calibrate(conn, MagicMock(), ["a", "b", "c"])

    assert set(out) == {"a", "b", "c"}
    assert calls == [2, 2]  # delay between accounts, not before the first
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_calibrate_balances.py -q`
Expected: `ModuleNotFoundError: No module named 'scripts.calibrate_balances'`.

- [ ] **Step 3: Write the script** — `scripts/calibrate_balances.py`:

```python
"""One-shot balance calibration: opening = EB current balance − sum of known deltas.

Includes is_internal rows on purpose — top-ups/vault moves change the real balance.
Run with prod env:
  railway run --service just-comfort -- uv run python scripts/calibrate_balances.py
Re-runnable anytime: it refreshes opening_balance/eb_balance/calibrated_at per account.
"""

import logging
import time

import httpx

from fintracker.ingestion.fetch_transactions import fetch_balances
from fintracker.settings import settings
from fintracker.storage.db import direct_connection

log = logging.getLogger(__name__)

_INTER_ACCOUNT_DELAY_SEC = 2


def calibrate(conn, client: httpx.Client, account_uids: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for i, uid in enumerate(account_uids):
        if i:
            time.sleep(_INTER_ACCOUNT_DELAY_SEC)
        eb_balance = fetch_balances(client, uid)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(eur_amount), 0) FROM transactions WHERE account_id = %s",
                (uid,),
            )
            delta_sum = cur.fetchone()[0]
            opening = eb_balance - delta_sum
            cur.execute(
                "INSERT INTO accounts (account_uid, opening_balance, eb_balance, calibrated_at)"
                " VALUES (%s, %s, %s, NOW())"
                " ON CONFLICT (account_uid) DO UPDATE SET"
                " opening_balance = EXCLUDED.opening_balance,"
                " eb_balance = EXCLUDED.eb_balance,"
                " calibrated_at = EXCLUDED.calibrated_at",
                (uid, opening, eb_balance),
            )
        conn.commit()
        results[uid] = {"eb_balance": eb_balance, "delta_sum": delta_sum, "opening": opening}
        log.info("%s: eb=%s deltas=%s opening=%s", uid, eb_balance, delta_sum, opening)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with httpx.Client(timeout=30) as http_client:
        calibrate(direct_connection(), http_client, settings.ENABLE_BANKING_ACCOUNT_IDS)
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest tests/test_calibrate_balances.py -q` → 2 passed; `uv run pytest -q && uv run ruff check . && uv run pyrefly check` → clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/calibrate_balances.py tests/test_calibrate_balances.py
git commit -m "feat: one-shot EB balance calibration script"
```

---

### Task 4: `balance_history` service

**Files:**
- Modify: `src/fintracker/server/services/stats.py` (add imports + one function at the end)
- Test: `tests/test_services.py` (append)

**Interfaces:**
- Consumes: `accounts` table (Task 1), `transactions` table.
- Produces: `balance_history(conn, months: int = 12) -> list[dict]` — ascending `[{"month": "YYYY-MM", "balance": float}]` — consumed by Task 5.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_services.py` (the file already imports `MagicMock` and defines `_conn_with_cursor(rows)`; add a variant supporting fetchone+fetchall):

```python
def _month_shift(back: int) -> str:
    from datetime import date

    d = date.today().replace(day=1)
    for _ in range(back):
        d = (d - __import__("datetime").timedelta(days=1)).replace(day=1)
    return d.strftime("%Y-%m")


def _conn_for_history(openings_total, monthly_rows):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = {"total": openings_total}
    cur.fetchall.return_value = monthly_rows
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


def test_balance_history_accumulates_on_openings_with_carry_forward():
    m2, m0 = _month_shift(2), _month_shift(0)
    conn = _conn_for_history(100.0, [{"month": m2, "net": 10.0}, {"month": m0, "net": -5.0}])

    series = stats.balance_history(conn, months=3)

    assert [p["month"] for p in series] == [m2, _month_shift(1), m0]
    assert [p["balance"] for p in series] == [110.0, 110.0, 105.0]  # gap month carries forward
    assert all(isinstance(p["balance"], float) for p in series)


def test_balance_history_without_transactions_is_flat_openings():
    conn = _conn_for_history(250.0, [])

    series = stats.balance_history(conn, months=4)

    assert len(series) == 4
    assert {p["balance"] for p in series} == {250.0}
    assert series[-1]["month"] == _month_shift(0)


def test_balance_history_slices_window_but_keeps_older_accumulation():
    m3 = _month_shift(3)
    conn = _conn_for_history(0.0, [{"month": m3, "net": 40.0}])

    series = stats.balance_history(conn, months=2)

    assert len(series) == 2
    assert series[0]["month"] == _month_shift(1)
    assert series[0]["balance"] == 40.0  # older net accumulated before the window
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_services.py -q -k balance_history`
Expected: 3 failures — `AttributeError: module ... has no attribute 'balance_history'`.

- [ ] **Step 3: Implement** — in `src/fintracker/server/services/stats.py`, add `from datetime import date, timedelta` at the top and this function at the end:

```python
def balance_history(conn, months: int = 12) -> list[dict]:
    """Monthly cumulative total balance: openings + running sum of EB-account deltas.

    Internal rows count (they move real money); manual rows (account_id IS NULL) don't,
    mirroring the accounts page scope.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT COALESCE(SUM(opening_balance), 0) AS total FROM accounts")
        openings = float(cur.fetchone()["total"])
        cur.execute(
            """SELECT TO_CHAR(DATE_TRUNC('month', booking_date), 'YYYY-MM') AS month,
                      SUM(eur_amount) AS net
               FROM transactions
               WHERE account_id IS NOT NULL
               GROUP BY 1
               ORDER BY 1"""
        )
        rows = cur.fetchall()

    nets = {r["month"]: float(r["net"]) for r in rows}
    current = date.today().replace(day=1)
    start = current
    for _ in range(months - 1):
        start = (start - timedelta(days=1)).replace(day=1)
    if rows:
        first_year, first_month = map(int, rows[0]["month"].split("-"))
        start = min(start, date(first_year, first_month, 1))

    series: list[dict] = []
    running = openings
    cursor_month = start
    while cursor_month <= current:
        key = cursor_month.strftime("%Y-%m")
        running = round(running + nets.get(key, 0.0), 2)
        series.append({"month": key, "balance": running})
        next_month = cursor_month.month % 12 + 1
        cursor_month = date(cursor_month.year + (cursor_month.month == 12), next_month, 1)
    return series[-months:]
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest tests/test_services.py -q` → all pass; `uv run pytest -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/stats.py tests/test_services.py
git commit -m "feat: balance_history service — cumulative monthly series on openings"
```

---

### Task 5: `GET /v1/stats/balance-history`

**Files:**
- Modify: `src/fintracker/server/routes/api.py` (wrapper + route, after the stats routes)
- Test: `tests/test_api_routes.py` (append a class)

**Interfaces:**
- Consumes: `stats.balance_history` (Task 4), existing `MonthsQ` annotated type, `db_conn()`.
- Produces: `GET /v1/stats/balance-history?months=N` → `{"data": [{"month", "balance"}...]}` — consumed by Task 7.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_api_routes.py`:

```python
class TestBalanceHistory:
    def test_missing_auth_returns_401(self, client):
        resp = client.get("/v1/stats/balance-history")
        assert resp.status_code == 401

    def test_returns_monthly_float_series(self, auth_client):
        row = {"month": "2026-06", "net": Decimal("-50.00")}
        with patch(
            "fintracker.storage.db.get_pool",
            return_value=_mock_pool(_mock_conn([row], {"total": Decimal("100.00")})),
        ):
            resp = auth_client.get("/v1/stats/balance-history?months=2")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data[-1]["month"].count("-") == 1
        assert all(isinstance(p["balance"], float) for p in data)

    def test_months_above_24_returns_422(self, auth_client):
        resp = auth_client.get("/v1/stats/balance-history?months=25")
        assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_api_routes.py -q -k BalanceHistory`
Expected: the 401 and float-series tests FAIL with 404 (route missing); the 422 test fails the same way.

- [ ] **Step 3: Implement** — in `src/fintracker/server/routes/api.py` add after `_stats_monthly`:

```python
def _stats_balance_history(months: int) -> list[dict]:
    with db_conn() as conn:
        return stats.balance_history(conn, months)
```

and after `stats_monthly_v1`:

```python
@router_v1.get("/stats/balance-history")
def stats_balance_history_v1(months: MonthsQ = 12) -> dict:
    return {"data": _stats_balance_history(months)}
```

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest tests/test_api_routes.py -q` → all pass; full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/routes/api.py tests/test_api_routes.py
git commit -m "feat: GET /v1/stats/balance-history endpoint"
```

---

### Task 6: Absolute balances in the accounts service

**Files:**
- Modify: `src/fintracker/server/services/accounts.py`
- Test: `tests/test_services.py` (modify the existing accounts test + add one)

**Interfaces:**
- Consumes: `accounts` table (Task 1).
- Produces: `balances(conn)` items gain `display_name: str | None`; `balance = opening_balance + SUM(eur_amount)` — consumed by Task 7 (frontend renders `display_name ?? account_id`).

- [ ] **Step 1: Adjust/extend the failing tests** — in `tests/test_services.py`, replace `test_accounts_balances_splits_assets_liabilities` with:

```python
def test_accounts_balances_splits_assets_liabilities():
    conn = _conn_returning(
        [
            {"account_id": "a", "balance": 100.0, "display_name": "Main"},
            {"account_id": "b", "balance": -40.0, "display_name": None},
        ]
    )
    out = accounts.balances(conn)
    assert out["assets"] == 100.0
    assert out["liabilities"] == 40.0
    assert out["accounts"][0]["display_name"] == "Main"


def test_accounts_balances_joins_openings():
    conn, cur = _conn_with_cursor([])
    accounts.balances(conn)
    sql = cur.execute.call_args[0][0]
    assert "LEFT JOIN accounts" in sql
    assert "opening_balance" in sql
```

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/test_services.py -q -k accounts`
Expected: `test_accounts_balances_joins_openings` FAILS (no JOIN in current SQL); the first test fails on missing `display_name` key.

- [ ] **Step 3: Implement** — replace the query and row mapping in `src/fintracker/server/services/accounts.py`:

```python
def balances(conn) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT t.account_id,
                      ROUND((COALESCE(a.opening_balance, 0) + SUM(t.eur_amount))::numeric, 2)
                          AS balance,
                      a.display_name
               FROM transactions t
               LEFT JOIN accounts a ON a.account_uid = t.account_id
               WHERE t.account_id IS NOT NULL
               GROUP BY t.account_id, a.opening_balance, a.display_name
               ORDER BY balance DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
    accounts = [
        {
            "account_id": r["account_id"],
            "balance": float(r["balance"]),
            "display_name": r["display_name"],
        }
        for r in rows
    ]
    assets = round(sum(a["balance"] for a in accounts if a["balance"] > 0), 2)
    liabilities = round(abs(sum(a["balance"] for a in accounts if a["balance"] < 0)), 2)
    return {"assets": assets, "liabilities": liabilities, "accounts": accounts}
```

(The old query had no `WHERE t.account_id IS NOT NULL`? It did — keep it. `GROUP BY` gains the joined columns.)

- [ ] **Step 4: Run to verify GREEN + check API tests**

Run: `uv run pytest -q` — note `tests/test_api_routes.py::TestAccounts::test_returns_accounts_list` uses `FAKE_ACCOUNT_ROW = {"account_id": ..., "balance": ...}`: add `"display_name": None` to that fixture so the service's `r["display_name"]` access works. All green.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/accounts.py tests/test_services.py tests/test_api_routes.py
git commit -m "feat: absolute account balances via opening-balance join, display_name exposed"
```

---

### Task 7: Frontend — Balance section in AccountsPage

**Files:**
- Modify: `frontend/src/api/types.ts` (BalancePoint + AccountBalance.display_name)
- Modify: `frontend/src/api/client.ts` (stats.balanceHistory)
- Modify: `frontend/src/api/queries.ts` (statsQueries.balanceHistory)
- Modify: `frontend/src/pages/Accounts/AccountsPage.tsx` (chart section + name fallback)
- Test: `frontend/src/tests/AccountsPage.test.tsx` (new)

**Interfaces:**
- Consumes: `GET /v1/stats/balance-history` (Task 5), `display_name` (Task 6).
- Produces: user-visible chart; no downstream consumers.

- [ ] **Step 1: Write the failing test** — `frontend/src/tests/AccountsPage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { AccountsPage } from '../pages/Accounts/AccountsPage';

vi.mock('../api/client', () => ({
  api: {
    accounts: {
      list: vi.fn().mockResolvedValue({
        assets: 150.0,
        liabilities: 0,
        accounts: [{ account_id: 'uid-1', balance: 150.0, display_name: 'Revolut Main' }],
      }),
    },
    stats: {
      balanceHistory: vi.fn().mockResolvedValue([
        { month: '2026-06', balance: 100.0 },
        { month: '2026-07', balance: 150.0 },
      ]),
    },
  },
}));

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AccountsPage />
    </QueryClientProvider>,
  );
}

describe('AccountsPage', () => {
  it('renders the balance history section', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Balance')).toBeInTheDocument());
  });

  it('shows display_name when present, uid otherwise', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Revolut Main')).toBeInTheDocument());
    expect(screen.queryByText('uid-1')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify RED**

Run (from `frontend/`): `npx vitest run src/tests/AccountsPage.test.tsx`
Expected: FAIL — `api.stats.balanceHistory` missing from the mock's consumer (page never calls it yet) → 'Balance' text not found; 'Revolut Main' not rendered (page shows `account_id`).

- [ ] **Step 3: Implement** — four edits:

1. `frontend/src/api/types.ts` — extend `AccountBalance` and append:

```ts
export interface AccountBalance {
  account_id: string;
  balance: number;
  display_name: string | null;
}

export interface BalancePoint {
  month: string;
  balance: number;
}
```

2. `frontend/src/api/client.ts` — add `BalancePoint` to the type imports and inside `stats`:

```ts
    balanceHistory: (params: { months?: number } = {}): Promise<BalancePoint[]> =>
      http.get('/v1/stats/balance-history', { params }).then(unwrap<BalancePoint[]>),
```

3. `frontend/src/api/queries.ts` — append to `statsQueries`:

```ts
  balanceHistory: (months = 12) => ({
    queryKey: ['stats', 'balance-history', months] as const,
    queryFn: () => api.stats.balanceHistory({ months }),
  }),
```

4. `frontend/src/pages/Accounts/AccountsPage.tsx` — add imports:

```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { statsQueries } from '../../api/queries';
```

add a local month formatter above the component (2nd usage in codebase; extraction deferred by rule of three):

```tsx
function formatMonth(iso: string): string {
  const [y, m] = iso.split('-');
  return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('it-IT', { month: 'short' });
}
```

inside the component, after the accounts query:

```tsx
  const history = useQuery({ ...statsQueries.balanceHistory(12) });
  const historyData = history.data ?? [];
```

insert this section between the hero `</motion.section>` and the "All Accounts" section:

```tsx
        <section className={styles.listSection}>
          <h2 className={styles.sectionTitle}>Balance</h2>
          <ResponsiveContainer width="100%" height={200}>
            {/* isAnimationActive: background-tab rAF freeze, same as StatsPage charts */}
            <LineChart data={historyData}>
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
                tickFormatter={v => `€${Math.round(v / 1000)}k`}
                axisLine={false}
                tickLine={false}
                domain={['auto', 'auto']}
              />
              <Tooltip
                formatter={(value: number) => [`€${value.toLocaleString('it-IT')}`, 'Balance']}
                labelFormatter={formatMonth}
                contentStyle={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-strong)',
                  borderRadius: 8,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                }}
              />
              <Line
                type="monotone"
                dataKey="balance"
                stroke="var(--accent)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </section>
```

and change the account row name span to:

```tsx
                <span className={styles.accountName}>{acc.display_name ?? acc.account_id}</span>
```

- [ ] **Step 4: Run to verify GREEN**

Run (from `frontend/`): `npx vitest run src/tests/AccountsPage.test.tsx` → 2 passed; then `npm run test && npm run lint && npm run build` → all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/queries.ts frontend/src/pages/Accounts/AccountsPage.tsx frontend/src/tests/AccountsPage.test.tsx
git commit -m "feat(frontend): balance history chart and named absolute balances in Accounts"
```

---

### Task 8: Deploy, migrate, calibrate, verify (controller-executed)

**Files:**
- Modify: `CLAUDE.md` (local, gitignored: add `accounts` table to the schema block + calibration command to Commands)

**Steps:**

- [ ] Push `main`; `railway up --detach --service just-comfort`; wait for both deploys (Vercel auto).
- [ ] Prod migration: `railway run --service just-comfort -- uv run alembic upgrade head` → expect `0001 -> 0002`.
- [ ] Calibration: `railway run --service just-comfort -- uv run python scripts/calibrate_balances.py` → one log line per account with eb/deltas/opening.
- [ ] Verify API from the authenticated browser tab: `/api/v1/stats/balance-history?months=12` → ascending months, floats, last point ≈ sum of EB balances; `/api/v1/accounts` → absolute balances (no more negative net worth).
- [ ] Verify UI (DOM checks, hidden-tab-safe): AccountsPage shows "Balance" section with `path.recharts-line-curve` present; account rows show names/uids; console clean.
- [ ] CLAUDE.md: add `accounts` table DDL to the Postgres schema block and `uv run python scripts/calibrate_balances.py` (with railway run form) to Commands; note "balance math includes internal rows".
- [ ] Ledger + suites final pass.

## Self-review notes

- Spec coverage: schema (T1), EB client (T2), calibration (T3), service (T4), API (T5), accounts coherence (T6), frontend (T7), ops/docs (T8). Declared limits carried in code comments/docstrings.
- Type consistency: `fetch_balances(client, uid) -> Decimal` used identically in T3; `balance_history` dict shape matches T5 tests and T7 `BalancePoint`; `display_name` shape consistent T6↔T7.
- `_conn_with_cursor` referenced in T6's new test exists in `tests/test_services.py` since the taxonomy project (returns `(conn, cur)`).
- No placeholders; every code step is complete.
