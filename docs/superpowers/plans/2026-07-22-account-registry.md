# Account Registry (SP-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `accounts` into a first-class registry that can hold user-created non-API accounts (cash/savings/cards), and wire the existing add-transaction form to a chosen account.

**Architecture:** One Alembic migration extends `accounts` with `type`/`is_manual`/`currency`/`created_at`. The `accounts` service gains CRUD (create/get/update/delete) alongside a LEFT-JOIN'd `balances()`; `/v1/accounts` grows POST/PATCH/DELETE. `balance_history` stops applying manual openings retroactively. Frontend: an account picker in `AddTransactionModal` and a create/edit modal on `AccountsPage`.

**Tech Stack:** Python 3 · FastAPI · psycopg3 · Alembic · pydantic v2 · pytest · React 18 + TypeScript · TanStack Query · react-hook-form + zod · Vitest.

## Global Constraints

- Schema changes are **Alembic only**, hand-written `op.execute` SQL — no autogenerate, no runtime DDL. `down_revision` chains `0002` → `0003`.
- **`float()` at every service boundary**: psycopg returns `Decimal`, which pydantic v2 serializes as a JSON *string*. Cast money to `float` before returning from services/routes.
- Dashboard API is under `/v1`, JWT-guarded (`router_v1`), success envelope `{"data": ...}`, error envelope `{"error": {"code", "message"}}` via `HTTPException`.
- Account type enum is defined **once** in `accounts.ACCOUNT_TYPES` (`cash | bank | card | savings`); pydantic models and any validation derive from it — never re-hardcode the list.
- Manual account ids are namespaced `manual:<uuid4-hex>` so they never collide with EB uids.
- Manual account `opening_balance` = the account's balance as of creation (wallet-style); it must not appear retroactively in `balance_history`.
- Backend commands: `uv run pytest ... -v`, `uv run ruff check .`, `uv run pyrefly check`. Frontend commands run from `frontend/`: `npx vitest run <file>`, `npm run build`, `npm run lint`.
- `git commit` is gated by lefthook (gitleaks + ruff + pyrefly + pytest on staged `.py`). Do not bypass.

---

### Task 1: Migration 0003 — extend `accounts`

**Files:**
- Create: `migrations/versions/0003_account_registry.py`

**Interfaces:**
- Produces: `accounts` table gains columns `type TEXT NOT NULL DEFAULT 'bank'`, `is_manual BOOL NOT NULL DEFAULT FALSE`, `currency CHAR(3) NOT NULL DEFAULT 'EUR'`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0003_account_registry.py`:

```python
"""accounts: type/is_manual/currency/created_at for the manual-account registry (SP-1)"""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS type        TEXT        NOT NULL DEFAULT 'bank',
    ADD COLUMN IF NOT EXISTS is_manual   BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS currency    CHAR(3)     NOT NULL DEFAULT 'EUR',
    ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE accounts
    DROP COLUMN IF EXISTS type,
    DROP COLUMN IF EXISTS is_manual,
    DROP COLUMN IF EXISTS currency,
    DROP COLUMN IF EXISTS created_at;
""")
```

- [ ] **Step 2: Apply it against the local Docker DB and verify the round-trip**

Run:
```bash
docker compose up db -d
uv run alembic upgrade head
uv run alembic current
```
Expected: `alembic current` prints `0003 (head)`. If Docker is unavailable, note it — Task 10's integration fixture applies the migration and is the authoritative check.

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/0003_account_registry.py
git commit -m "feat(db): extend accounts with type/is_manual/currency/created_at (SP-1)"
```

---

### Task 2: `accounts.balances()` → LEFT JOIN + registry columns

**Files:**
- Modify: `src/fintracker/server/services/accounts.py`
- Test: `tests/test_services.py`

**Interfaces:**
- Produces: `balances(conn) -> dict` where each account is
  `{account_id, balance, display_name, type, currency, is_manual, opening_balance}`.
  Accounts with zero transactions appear (balance = opening). `assets`/`liabilities` unchanged.

- [ ] **Step 1: Rewrite the two existing balances tests to expect LEFT JOIN + new columns**

In `tests/test_services.py`, replace `test_accounts_balances_splits_assets_liabilities` and `test_accounts_balances_inner_joins_openings_only` with:

```python
def test_accounts_balances_splits_assets_liabilities():
    conn = _conn_returning(
        [
            {"account_id": "a", "balance": 100.0, "display_name": "Main",
             "type": "bank", "currency": "EUR", "is_manual": False, "opening_balance": 90.0},
            {"account_id": "b", "balance": -40.0, "display_name": None,
             "type": "card", "currency": "EUR", "is_manual": False, "opening_balance": 0.0},
        ]
    )
    out = accounts.balances(conn)
    assert out["assets"] == 100.0
    assert out["liabilities"] == 40.0
    assert out["accounts"][0]["display_name"] == "Main"
    assert out["accounts"][0]["type"] == "bank"
    assert out["accounts"][0]["is_manual"] is False


def test_accounts_balances_left_joins_all_registered_accounts():
    conn, cur = _conn_with_cursor([])
    accounts.balances(conn)
    sql = cur.execute.call_args[0][0]
    # LEFT JOIN from accounts: a manual account with zero transactions still shows its
    # opening balance. Scope is driven by the accounts table (stale EB uids aren't in it).
    assert "FROM accounts a" in sql
    assert "LEFT JOIN transactions" in sql
    assert "COALESCE(SUM(t.eur_amount), 0)" in sql
    assert "opening_balance" in sql
    assert "real_transactions" not in sql
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_services.py -k accounts_balances -v`
Expected: FAIL (old code is INNER JOIN and the mock rows now carry keys the code doesn't read yet / SQL assertions don't match).

- [ ] **Step 3: Rewrite `balances()`**

Replace the body of `balances` in `src/fintracker/server/services/accounts.py`:

```python
from psycopg.rows import dict_row


def balances(conn) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        # LEFT JOIN from accounts so a registered account with no transactions still
        # shows (opening + 0). transactions (not real_transactions): internal rows count
        # for EB-balance reconciliation. Scope = the accounts table; stale post-renewal
        # EB uids are absent from it and correctly excluded.
        cur.execute(
            """SELECT a.account_uid AS account_id,
                      ROUND((a.opening_balance + COALESCE(SUM(t.eur_amount), 0))::numeric, 2)
                        AS balance,
                      a.display_name, a.type, a.currency, a.is_manual, a.opening_balance
               FROM accounts a
               LEFT JOIN transactions t ON t.account_id = a.account_uid
               GROUP BY a.account_uid, a.opening_balance, a.display_name,
                        a.type, a.currency, a.is_manual
               ORDER BY balance DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
    account_list = [
        {
            "account_id": r["account_id"],
            "balance": float(r["balance"]),
            "display_name": r["display_name"],
            "type": r["type"],
            "currency": r["currency"],
            "is_manual": r["is_manual"],
            "opening_balance": float(r["opening_balance"]),
        }
        for r in rows
    ]
    assets = round(sum(a["balance"] for a in account_list if a["balance"] > 0), 2)
    liabilities = round(abs(sum(a["balance"] for a in account_list if a["balance"] < 0)), 2)
    return {"assets": assets, "liabilities": liabilities, "accounts": account_list}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_services.py -k accounts_balances -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/accounts.py tests/test_services.py
git commit -m "feat(accounts): balances LEFT JOINs registry, surfaces type/is_manual (SP-1)"
```

---

### Task 3: Account CRUD service

**Files:**
- Modify: `src/fintracker/server/services/accounts.py`
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `ACCOUNT_TYPES: frozenset[str]` = `{"cash", "bank", "card", "savings"}`
  - `get_account(conn, account_uid: str) -> dict | None` → `{account_id, display_name, type, currency, is_manual, opening_balance}` or None
  - `create_account(conn, *, display_name: str, type: str, currency: str = "EUR", opening_balance: Decimal = Decimal("0")) -> dict` (generates `manual:<uuid>`, `is_manual=True`)
  - `update_account(conn, account_uid: str, *, display_name: str | None = None, type: str | None = None, opening_balance: Decimal | None = None) -> dict | None`
  - `delete_account(conn, account_uid: str) -> str` → one of `"deleted" | "not_found" | "protected" | "has_transactions"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_services.py`:

```python
def _dict_cursor_conn(fetchone_seq):
    """A conn whose dict_row cursor returns the given fetchone values in order."""
    from unittest.mock import MagicMock

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = list(fetchone_seq)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_account_types_are_the_single_source():
    assert accounts.ACCOUNT_TYPES == frozenset({"cash", "bank", "card", "savings"})


def test_create_account_namespaces_uid_and_marks_manual():
    row = {"account_id": "manual:x", "display_name": "Wallet", "type": "cash",
           "currency": "EUR", "is_manual": True, "opening_balance": 200.0}
    conn, cur = _dict_cursor_conn([row])
    from decimal import Decimal

    out = accounts.create_account(
        conn, display_name="Wallet", type="cash", opening_balance=Decimal("200")
    )
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO accounts" in sql and "TRUE" in sql  # is_manual literal TRUE
    assert params[0].startswith("manual:")
    assert out["opening_balance"] == 200.0 and isinstance(out["opening_balance"], float)


def test_get_account_returns_none_when_absent():
    conn, _ = _dict_cursor_conn([None])
    assert accounts.get_account(conn, "manual:nope") is None


def test_update_account_only_sets_provided_fields():
    row = {"account_id": "manual:x", "display_name": "Cash", "type": "cash",
           "currency": "EUR", "is_manual": True, "opening_balance": 0.0}
    conn, cur = _dict_cursor_conn([row])
    accounts.update_account(conn, "manual:x", display_name="Cash")
    sql, params = cur.execute.call_args[0]
    assert "display_name = %s" in sql
    assert "type = %s" not in sql and "opening_balance = %s" not in sql
    assert params == ["Cash", "manual:x"]


def test_delete_account_blocks_non_manual():
    conn, _ = _dict_cursor_conn([
        {"account_id": "eb1", "display_name": "Revolut", "type": "bank",
         "currency": "EUR", "is_manual": False, "opening_balance": 10.0},
    ])
    assert accounts.delete_account(conn, "eb1") == "protected"


def test_delete_account_blocks_when_transactions_exist():
    conn, cur = _dict_cursor_conn([
        {"account_id": "manual:x", "display_name": "Cash", "type": "cash",
         "currency": "EUR", "is_manual": True, "opening_balance": 0.0},  # get_account
        (1,),  # the "SELECT 1 FROM transactions" probe finds a row
    ])
    assert accounts.delete_account(conn, "manual:x") == "has_transactions"


def test_delete_account_deletes_empty_manual():
    conn, cur = _dict_cursor_conn([
        {"account_id": "manual:x", "display_name": "Cash", "type": "cash",
         "currency": "EUR", "is_manual": True, "opening_balance": 0.0},  # get_account
        None,  # no transactions
    ])
    assert accounts.delete_account(conn, "manual:x") == "deleted"
    assert any("DELETE FROM accounts" in c.args[0] for c in cur.execute.call_args_list)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_services.py -k "account" -v`
Expected: FAIL with `AttributeError: module 'fintracker.server.services.accounts' has no attribute 'ACCOUNT_TYPES'` (and friends).

- [ ] **Step 3: Implement the CRUD**

Add to the top of `src/fintracker/server/services/accounts.py` (imports) and below `balances`:

```python
import uuid
from decimal import Decimal

ACCOUNT_TYPES = frozenset({"cash", "bank", "card", "savings"})

_ACCOUNT_COLS = (
    "account_uid AS account_id, display_name, type, currency, is_manual, opening_balance"
)


def _account_out(row: dict) -> dict:
    row = dict(row)
    row["opening_balance"] = float(row["opening_balance"])
    return row


def get_account(conn, account_uid: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_ACCOUNT_COLS} FROM accounts WHERE account_uid = %s", (account_uid,))
        row = cur.fetchone()
    return _account_out(row) if row else None


def create_account(
    conn, *, display_name: str, type: str, currency: str = "EUR",
    opening_balance: Decimal = Decimal("0"),
) -> dict:
    account_uid = f"manual:{uuid.uuid4().hex}"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""INSERT INTO accounts
                    (account_uid, display_name, type, currency, is_manual, opening_balance)
                VALUES (%s, %s, %s, %s, TRUE, %s)
                RETURNING {_ACCOUNT_COLS}""",
            (account_uid, display_name, type, currency, opening_balance),
        )
        row = cur.fetchone()
    conn.commit()
    return _account_out(row)


def update_account(
    conn, account_uid: str, *, display_name: str | None = None,
    type: str | None = None, opening_balance: Decimal | None = None,
) -> dict | None:
    sets: list[str] = []
    params: list = []
    if display_name is not None:
        sets.append("display_name = %s")
        params.append(display_name)
    if type is not None:
        sets.append("type = %s")
        params.append(type)
    if opening_balance is not None:
        sets.append("opening_balance = %s")
        params.append(opening_balance)
    if not sets:
        return get_account(conn, account_uid)
    params.append(account_uid)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"UPDATE accounts SET {', '.join(sets)} WHERE account_uid = %s RETURNING {_ACCOUNT_COLS}",
            params,
        )
        row = cur.fetchone()
    conn.commit()
    return _account_out(row) if row else None


def delete_account(conn, account_uid: str) -> str:
    acc = get_account(conn, account_uid)
    if acc is None:
        return "not_found"
    if not acc["is_manual"]:
        return "protected"  # EB accounts are system-managed; they reappear on calibration
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM transactions WHERE account_id = %s LIMIT 1", (account_uid,))
        if cur.fetchone() is not None:
            return "has_transactions"
        cur.execute("DELETE FROM accounts WHERE account_uid = %s", (account_uid,))
    conn.commit()
    return "deleted"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_services.py -k "account" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/accounts.py tests/test_services.py
git commit -m "feat(accounts): CRUD service with EB/manual guards (SP-1)"
```

---

### Task 4: `/v1/accounts` POST/PATCH/DELETE routes

**Files:**
- Modify: `src/fintracker/server/routes/api.py`
- Test: `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `accounts.ACCOUNT_TYPES`, `accounts.get_account/create_account/update_account/delete_account`.
- Produces: `POST /v1/accounts` (201), `PATCH /v1/accounts/{account_uid}`, `DELETE /v1/accounts/{account_uid}` — all enveloped, JWT-guarded.

- [ ] **Step 1: Write the failing route tests**

Append to `tests/test_api_routes.py` (reuse the module's `auth_client`, `_mock_conn`, `_mock_pool` helpers; read the top of the file for their exact shapes). If a helper you need is not present, read the file first.

```python
def test_create_account_returns_201(auth_client):
    row = {"account_id": "manual:abc", "display_name": "Wallet", "type": "cash",
           "currency": "EUR", "is_manual": True, "opening_balance": 200.0}
    conn = _mock_conn()
    with patch("fintracker.server.services.accounts.create_account", return_value=row), \
         patch("fintracker.server.routes.api.db_conn") as db:
        db.return_value.__enter__.return_value = conn
        r = auth_client.post(
            "/v1/accounts",
            json={"display_name": "Wallet", "type": "cash", "opening_balance": 200},
        )
    assert r.status_code == 201
    assert r.json()["data"]["account_id"] == "manual:abc"


def test_create_account_rejects_unknown_type(auth_client):
    r = auth_client.post("/v1/accounts", json={"display_name": "X", "type": "crypto"})
    assert r.status_code == 422


def test_patch_account_rejects_opening_change_on_synced(auth_client):
    eb = {"account_id": "eb1", "display_name": "Revolut", "type": "bank",
          "currency": "EUR", "is_manual": False, "opening_balance": 10.0}
    conn = _mock_conn()
    with patch("fintracker.server.services.accounts.get_account", return_value=eb), \
         patch("fintracker.server.routes.api.db_conn") as db:
        db.return_value.__enter__.return_value = conn
        r = auth_client.patch("/v1/accounts/eb1", json={"opening_balance": 999})
    assert r.status_code == 422


def test_delete_account_maps_status_to_http(auth_client):
    conn = _mock_conn()
    for status, code in [("not_found", 404), ("protected", 403), ("has_transactions", 409)]:
        with patch("fintracker.server.services.accounts.delete_account", return_value=status), \
             patch("fintracker.server.routes.api.db_conn") as db:
            db.return_value.__enter__.return_value = conn
            r = auth_client.delete("/v1/accounts/x")
            assert r.status_code == code


def test_accounts_routes_require_auth(client):
    assert client.post("/v1/accounts", json={"display_name": "X", "type": "cash"}).status_code == 401
    assert client.delete("/v1/accounts/x").status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_api_routes.py -k account -v`
Expected: FAIL (routes 404 / not defined).

- [ ] **Step 3: Add the models and routes**

In `src/fintracker/server/routes/api.py`, add the models near `ManualTransactionIn`:

```python
class AccountIn(BaseModel):
    display_name: str
    type: str
    currency: str = "EUR"
    opening_balance: Decimal = Decimal("0")

    @model_validator(mode="after")
    def _check_type(self) -> "AccountIn":
        if self.type not in accounts.ACCOUNT_TYPES:
            raise ValueError("unknown account type")
        return self


class AccountUpdate(BaseModel):
    display_name: str | None = None
    type: str | None = None
    currency: str | None = None
    opening_balance: Decimal | None = None

    @model_validator(mode="after")
    def _check_type(self) -> "AccountUpdate":
        if self.type is not None and self.type not in accounts.ACCOUNT_TYPES:
            raise ValueError("unknown account type")
        return self
```

Add the routes (place them next to `accounts_v1`):

```python
@router_v1.post("/accounts", status_code=201)
def create_account_v1(body: AccountIn) -> dict:
    with db_conn() as conn:
        return {
            "data": accounts.create_account(
                conn,
                display_name=body.display_name,
                type=body.type,
                currency=body.currency,
                opening_balance=body.opening_balance,
            )
        }


@router_v1.patch("/accounts/{account_uid}")
def update_account_v1(account_uid: str, body: AccountUpdate) -> dict:
    with db_conn() as conn:
        acc = accounts.get_account(conn, account_uid)
        if acc is None:
            raise HTTPException(status_code=404, detail="unknown account")
        if not acc["is_manual"] and (body.opening_balance is not None or body.currency is not None):
            raise HTTPException(
                status_code=422, detail="cannot change balance or currency on a synced account"
            )
        updated = accounts.update_account(
            conn,
            account_uid,
            display_name=body.display_name,
            type=body.type,
            opening_balance=body.opening_balance if acc["is_manual"] else None,
        )
        return {"data": updated}


@router_v1.delete("/accounts/{account_uid}")
def delete_account_v1(account_uid: str) -> dict:
    with db_conn() as conn:
        result = accounts.delete_account(conn, account_uid)
    errors = {
        "not_found": (404, "unknown account"),
        "protected": (403, "synced accounts cannot be deleted"),
        "has_transactions": (409, "account has transactions"),
    }
    if result in errors:
        code, msg = errors[result]
        raise HTTPException(status_code=code, detail=msg)
    return {"data": {"account_id": account_uid}}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_api_routes.py -k account -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/routes/api.py tests/test_api_routes.py
git commit -m "feat(api): /v1/accounts create/update/delete with EB guards (SP-1)"
```

---

### Task 5: Reject a manual transaction with an unknown account

**Files:**
- Modify: `src/fintracker/server/routes/api.py` (`_create_transaction`)
- Test: `tests/test_api_routes.py`

**Interfaces:**
- Consumes: `accounts.get_account`.
- Produces: `POST /v1/transactions` returns 422 when `account_id` is set but not registered.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_routes.py`:

```python
def test_manual_transaction_rejects_unknown_account(auth_client):
    conn = _mock_conn()
    with patch("fintracker.server.services.accounts.get_account", return_value=None), \
         patch("fintracker.server.routes.api.db_conn") as db:
        db.return_value.__enter__.return_value = conn
        r = auth_client.post(
            "/v1/transactions",
            json={
                "booking_date": "2026-07-01T00:00:00Z",
                "amount": -5, "eur_amount": -5, "currency": "EUR",
                "merchant_name": "Bar", "account_id": "manual:ghost",
            },
        )
    assert r.status_code == 422


def test_manual_transaction_without_account_still_creates(auth_client):
    created = dict(FAKE_ROW, account_id=None)
    conn = _mock_conn()
    with patch("fintracker.server.services.transactions.create_manual", return_value=created), \
         patch("fintracker.server.routes.api.db_conn") as db:
        db.return_value.__enter__.return_value = conn
        r = auth_client.post(
            "/v1/transactions",
            json={"booking_date": "2026-07-01T00:00:00Z", "amount": -5,
                  "eur_amount": -5, "currency": "EUR", "merchant_name": "Bar"},
        )
    assert r.status_code == 201
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_api_routes.py -k manual_transaction -v`
Expected: the unknown-account test FAILS (currently returns 201).

- [ ] **Step 3: Add the validation**

In `src/fintracker/server/routes/api.py`, replace `_create_transaction`:

```python
def _create_transaction(body: ManualTransactionIn) -> dict:
    with db_conn() as conn:
        if body.account_id is not None and accounts.get_account(conn, body.account_id) is None:
            raise HTTPException(status_code=422, detail="unknown account_id")
        row = transactions.create_manual(conn, body.model_dump())
    if row is None:
        raise HTTPException(status_code=409, detail="Duplicate transaction")
    return row
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_api_routes.py -k manual_transaction -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/routes/api.py tests/test_api_routes.py
git commit -m "feat(api): manual transaction must reference a registered account (SP-1)"
```

---

### Task 6: `balance_history` — manual openings enter at `created_at`, not retroactively

**Files:**
- Modify: `src/fintracker/server/services/stats.py` (`balance_history`)
- Test: `tests/test_services.py`

**Interfaces:**
- Produces: `balance_history(conn, months)` where non-manual openings form the flat baseline and each manual account's opening enters as a net in its `created_at` month.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_services.py`:

```python
def test_balance_history_manual_openings_are_not_retroactive():
    from unittest.mock import MagicMock

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = {"total": 0.0}
    cur.fetchall.return_value = []
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    stats.balance_history(conn, months=3)

    openings_sql = cur.execute.call_args_list[0].args[0]
    nets_sql = cur.execute.call_args_list[1].args[0]
    # Flat baseline excludes manual openings...
    assert "WHERE NOT is_manual" in openings_sql
    # ...they re-enter as a net at their creation month instead.
    assert "UNION ALL" in nets_sql
    assert "DATE_TRUNC('month', created_at)" in nets_sql
    assert "WHERE is_manual" in nets_sql
    assert "account_uid FROM accounts" in nets_sql  # transaction scope preserved
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_services.py -k manual_openings_are_not_retroactive -v`
Expected: FAIL (current openings query has no `WHERE NOT is_manual`; nets query has no UNION).

- [ ] **Step 3: Modify `balance_history`**

In `src/fintracker/server/services/stats.py`, change the two queries at the top of `balance_history` and update the docstring:

```python
def balance_history(conn, months: int = 12) -> list[dict]:
    """Monthly cumulative total balance: openings + running sum of account deltas.

    Non-manual (EB) openings are the flat baseline (their opening is the balance at
    t=-infinity). Manual openings are "balance as of creation", so they enter as a net in
    their created_at month instead of retroactively shifting the whole series. Internal
    rows count; only registered accounts (those in the accounts table) are summed, so the
    last point reconciles with net worth and stale post-renewal uids are excluded.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT COALESCE(SUM(opening_balance), 0) AS total FROM accounts WHERE NOT is_manual"
        )
        openings = float(cur.fetchone()["total"])
        cur.execute(
            """SELECT month, SUM(net) AS net FROM (
                   SELECT TO_CHAR(DATE_TRUNC('month', booking_date), 'YYYY-MM') AS month,
                          eur_amount AS net
                   FROM transactions
                   WHERE account_id IN (SELECT account_uid FROM accounts)
                   UNION ALL
                   SELECT TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') AS month,
                          opening_balance AS net
                   FROM accounts
                   WHERE is_manual
               ) x
               GROUP BY month
               ORDER BY month"""
        )
        rows = cur.fetchall()
    ...  # leave the rest of the function (nets dict, start calc, accumulation loop) unchanged
```

Leave everything from `nets = {r["month"]: float(r["net"]) for r in rows}` onward untouched.

- [ ] **Step 4: Run the affected tests to verify they pass**

Run: `uv run pytest tests/test_services.py -k balance_history -v`
Expected: PASS (the new test plus the four existing `balance_history` tests, which still hold — they mock `fetchone`/`fetchall` shapes the new SQL still uses).

- [ ] **Step 5: Commit**

```bash
git add src/fintracker/server/services/stats.py tests/test_services.py
git commit -m "fix(stats): manual openings enter balance-history at creation month (SP-1)"
```

---

### Task 7: Frontend data layer — types, client, queries

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/queries.ts`

**Interfaces:**
- Produces: `AccountType`, extended `AccountBalance`, `AccountInput`, `AccountUpdateInput`; `api.accounts.create/update/remove`; `accountQueries.create/update/remove` mutations.

- [ ] **Step 1: Extend `types.ts`**

In `frontend/src/api/types.ts`, replace `AccountBalance` and add the input types:

```typescript
export type AccountType = 'cash' | 'bank' | 'card' | 'savings';

export interface AccountBalance {
  account_id: string;
  balance: number;
  display_name: string | null;
  type: AccountType;
  currency: string;
  is_manual: boolean;
  opening_balance: number;
}

export interface AccountInput {
  display_name: string;
  type: AccountType;
  currency?: string;
  opening_balance: number;
}

export interface AccountUpdateInput {
  account_id: string;
  display_name?: string;
  type?: AccountType;
  opening_balance?: number;
}
```

- [ ] **Step 2: Extend the API client**

In `frontend/src/api/client.ts`, add the imports (`AccountBalance, AccountInput, AccountUpdateInput`) to the `type` import block and replace the `accounts` block:

```typescript
  accounts: {
    list: (): Promise<AccountsResponse> =>
      http.get('/v1/accounts').then(unwrap<AccountsResponse>),
    create: (data: AccountInput): Promise<AccountBalance> =>
      http.post('/v1/accounts', data).then(unwrap<AccountBalance>),
    update: ({ account_id, ...data }: AccountUpdateInput): Promise<AccountBalance> =>
      http
        .patch(`/v1/accounts/${encodeURIComponent(account_id)}`, data)
        .then(unwrap<AccountBalance>),
    remove: (account_id: string): Promise<{ account_id: string }> =>
      http
        .delete(`/v1/accounts/${encodeURIComponent(account_id)}`)
        .then(unwrap<{ account_id: string }>),
  },
```

- [ ] **Step 3: Add the mutations to `queries.ts`**

In `frontend/src/api/queries.ts`, replace the `accountQueries` block:

```typescript
export const accountQueries = {
  list: () => ({
    queryKey: ['accounts'] as const,
    queryFn: api.accounts.list,
  }),
  create: () => ({
    mutationKey: ['accounts', 'create'] as const,
    mutationFn: api.accounts.create,
  }),
  update: () => ({
    mutationKey: ['accounts', 'update'] as const,
    mutationFn: api.accounts.update,
  }),
  remove: () => ({
    mutationKey: ['accounts', 'remove'] as const,
    mutationFn: api.accounts.remove,
  }),
};
```

- [ ] **Step 4: Verify the type layer compiles and lints**

Run (from `frontend/`): `npm run build && npm run lint`
Expected: build + lint PASS (no type errors from the new shapes).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/queries.ts
git commit -m "feat(fe): accounts data layer — types, client CRUD, mutations (SP-1)"
```

---

### Task 8: Account picker in `AddTransactionModal`

**Files:**
- Modify: `frontend/src/pages/Transactions/AddTransactionModal.tsx`
- Test: `frontend/src/tests/AddTransactionModal.test.tsx`

**Interfaces:**
- Consumes: `accountQueries.list()`, `AccountBalance`.
- Produces: the create payload includes `account_id` (the chosen account, or omitted when none exist).

- [ ] **Step 1: Extend the existing test file**

In `frontend/src/tests/AddTransactionModal.test.tsx`, extend the `vi.mock('../api/client')` to include `accounts.list`, and add a test. Replace the mock block and add the test:

```typescript
vi.mock('../api/client', () => ({
  api: {
    taxonomy: {
      get: vi.fn().mockResolvedValue({
        expense: { Groceries: ['Supermarket'], Car: ['Fuel', 'Tolls & Parking'] },
        income: { Salary: ['Base salary'] },
      }),
    },
    transactions: { create: vi.fn().mockResolvedValue({}) },
    accounts: {
      list: vi.fn().mockResolvedValue({
        assets: 0, liabilities: 0,
        accounts: [
          { account_id: 'manual:1', balance: 200, display_name: 'Wallet',
            type: 'cash', currency: 'EUR', is_manual: true, opening_balance: 200 },
        ],
      }),
    },
  },
}));
```

Add:

```typescript
  it('sends the chosen account_id on submit', async () => {
    const { api } = await import('../api/client');
    renderModal();
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Wallet' })).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Merchant / Payee'), { target: { value: 'Bar' } });
    fireEvent.click(screen.getByRole('button', { name: /Add Expense/i }));
    await waitFor(() =>
      expect((api.transactions.create as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith(
        expect.objectContaining({ account_id: 'manual:1' }),
      ),
    );
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `npx vitest run src/tests/AddTransactionModal.test.tsx`
Expected: the new test FAILS (no `Wallet` option; payload has no `account_id`).

- [ ] **Step 3: Add the picker**

In `frontend/src/pages/Transactions/AddTransactionModal.tsx`:

Add the import and query near the taxonomy query:

```typescript
import { transactionQueries, taxonomyQueries, accountQueries } from '../../api/queries';
```

```typescript
  const { data: accountsData } = useQuery({ ...accountQueries.list() });
  const accountList = accountsData?.accounts ?? [];
  const [accountId, setAccountId] = useState<string>('');
  const effectiveAccountId = accountId || accountList[0]?.account_id || '';
```

In `onSubmit`, add `account_id` to the mutation payload:

```typescript
    mutation.mutate({
      booking_date: `${values.booking_date}T00:00:00Z`,
      amount: signed,
      eur_amount: signed,
      currency: 'EUR',
      merchant_name: values.merchant_name,
      account_id: effectiveAccountId || null,
      category: values.category || null,
      subcategory: values.subcategory || null,
      description: values.description || null,
    });
```

Add a select in the `.fields` block (after the Date field), rendered only when accounts exist:

```tsx
              {accountList.length > 0 && (
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Account</span>
                  <select
                    className={styles.input}
                    value={effectiveAccountId}
                    onChange={e => setAccountId(e.target.value)}
                  >
                    {accountList.map(a => (
                      <option key={a.account_id} value={a.account_id}>
                        {a.display_name ?? a.account_id}
                      </option>
                    ))}
                  </select>
                </label>
              )}
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `frontend/`): `npx vitest run src/tests/AddTransactionModal.test.tsx`
Expected: PASS (all tests, old and new).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Transactions/AddTransactionModal.tsx frontend/src/tests/AddTransactionModal.test.tsx
git commit -m "feat(fe): account picker in add-transaction modal (SP-1)"
```

---

### Task 9: Account management UI on `AccountsPage`

**Files:**
- Create: `frontend/src/pages/Accounts/AccountModal.tsx`
- Create: `frontend/src/pages/Accounts/AccountModal.module.css`
- Modify: `frontend/src/pages/Accounts/AccountsPage.tsx`
- Test: `frontend/src/tests/AccountModal.test.tsx`
- Test: `frontend/src/tests/AccountsPage.test.tsx`

**Interfaces:**
- Consumes: `accountQueries.list/create/update/remove`, `AccountBalance`, `AccountType`.
- Produces: a create/edit modal; `AccountsPage` shows "+ Add account" and per-row edit; EB rows expose display_name + type only.

- [ ] **Step 1: Write the AccountModal test**

Create `frontend/src/tests/AccountModal.test.tsx`:

```typescript
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { AccountModal } from '../pages/Accounts/AccountModal';

vi.mock('../api/client', () => ({
  api: {
    accounts: {
      create: vi.fn().mockResolvedValue({}),
      update: vi.fn().mockResolvedValue({}),
    },
  },
}));

function renderModal(props: Partial<Parameters<typeof AccountModal>[0]> = {}) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <AccountModal onClose={() => {}} onSaved={() => {}} account={null} {...props} />
    </QueryClientProvider>,
  );
}

describe('AccountModal', () => {
  it('creates a manual account with type and opening balance', async () => {
    const { api } = await import('../api/client');
    renderModal();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Wallet' } });
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'cash' } });
    fireEvent.change(screen.getByLabelText('Opening balance'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));
    await waitFor(() =>
      expect(api.accounts.create as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
        expect.objectContaining({ display_name: 'Wallet', type: 'cash', opening_balance: 200 }),
      ),
    );
  });

  it('hides the opening-balance field when editing a synced (EB) account', () => {
    renderModal({
      account: {
        account_id: 'eb1', balance: 10, display_name: 'Revolut', type: 'bank',
        currency: 'EUR', is_manual: false, opening_balance: 10,
      },
    });
    expect(screen.queryByLabelText('Opening balance')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `npx vitest run src/tests/AccountModal.test.tsx`
Expected: FAIL (module `AccountModal` not found).

- [ ] **Step 3: Create `AccountModal.tsx`**

Create `frontend/src/pages/Accounts/AccountModal.tsx`:

```tsx
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { accountQueries } from '../../api/queries';
import type { AccountBalance, AccountType } from '../../api/types';
import styles from './AccountModal.module.css';

const TYPES: AccountType[] = ['cash', 'bank', 'card', 'savings'];

interface Props {
  account: AccountBalance | null; // null = create
  onClose: () => void;
  onSaved: () => void;
}

export function AccountModal({ account, onClose, onSaved }: Props) {
  const isEdit = account !== null;
  const isManual = account?.is_manual ?? true;
  const [name, setName] = useState(account?.display_name ?? '');
  const [type, setType] = useState<AccountType>(account?.type ?? 'cash');
  const [opening, setOpening] = useState(String(account?.opening_balance ?? ''));

  const create = useMutation({ ...accountQueries.create(), onSuccess: onSaved });
  const update = useMutation({ ...accountQueries.update(), onSuccess: onSaved });
  const pending = create.isPending || update.isPending;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isEdit) {
      update.mutate({
        account_id: account.account_id,
        display_name: name,
        type,
        ...(isManual ? { opening_balance: Number(opening) || 0 } : {}),
      });
    } else {
      create.mutate({ display_name: name, type, opening_balance: Number(opening) || 0 });
    }
  };

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <form className={styles.form} onSubmit={submit}>
          <label className={styles.field}>
            <span className={styles.label}>Name</span>
            <input className={styles.input} value={name} onChange={e => setName(e.target.value)} />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Type</span>
            <select
              className={styles.input}
              value={type}
              onChange={e => setType(e.target.value as AccountType)}
            >
              {TYPES.map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          {isManual && (
            <label className={styles.field}>
              <span className={styles.label}>Opening balance</span>
              <input
                className={styles.input}
                type="number"
                step="0.01"
                value={opening}
                onChange={e => setOpening(e.target.value)}
              />
            </label>
          )}
          {(create.isError || update.isError) && (
            <div className={styles.error}>Impossibile salvare — riprova.</div>
          )}
          <button type="submit" disabled={pending || !name} className={styles.save}>
            {pending ? 'Saving…' : 'Save'}
          </button>
        </form>
      </div>
    </div>
  );
}
```

Create `frontend/src/pages/Accounts/AccountModal.module.css` (reuse the app's tokens; keep it minimal):

```css
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  padding: 20px;
  width: min(92vw, 360px);
}
.form { display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.label { font-size: 12px; color: var(--text-muted); }
.input {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text-primary);
  font-family: var(--font-mono);
}
.error { color: var(--expense, #e5484d); font-size: 12px; }
.save {
  margin-top: 4px;
  padding: 10px;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}
.save:disabled { opacity: 0.5; cursor: default; }
```

- [ ] **Step 4: Run the AccountModal test to verify it passes**

Run (from `frontend/`): `npx vitest run src/tests/AccountModal.test.tsx`
Expected: PASS.

- [ ] **Step 5: Wire the modal into `AccountsPage` and write its test**

In `frontend/src/tests/AccountsPage.test.tsx`: add `fireEvent` to the `@testing-library/react` import, extend the mocked `accounts` object with `create`/`update` stubs (the modal's `useMutation` reads them at render), and add the test. Replace the mocked `accounts` sub-object:

```typescript
    accounts: {
      list: vi.fn().mockResolvedValue({
        assets: 150.0,
        liabilities: 0,
        accounts: [{
          account_id: 'uid-1', balance: 150.0, display_name: 'Revolut Main',
          type: 'bank', currency: 'EUR', is_manual: false, opening_balance: 150.0,
        }],
      }),
      create: vi.fn().mockResolvedValue({}),
      update: vi.fn().mockResolvedValue({}),
    },
```

Add the test inside the `describe('AccountsPage', ...)` block:

```typescript
  it('opens the account modal from the add control', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /add account/i }));
    expect(await screen.findByLabelText('Name')).toBeInTheDocument();
  });
```

Then modify `frontend/src/pages/Accounts/AccountsPage.tsx`:

Add imports and state:

```tsx
import { useState } from 'react';
import { AccountModal } from './AccountModal';
import type { AccountBalance } from '../../api/types';
import { useQueryClient } from '@tanstack/react-query';
```

Inside the component:

```tsx
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<AccountBalance | null | undefined>(undefined);
  // undefined = closed, null = creating, object = editing
  const closeModal = () => setEditing(undefined);
  const onSaved = () => {
    queryClient.invalidateQueries({ queryKey: ['accounts'] });
    closeModal();
  };
```

In the "All Accounts" section header, add the add control, make each row editable, and render the modal:

```tsx
        <section className={styles.listSection}>
          <div className={styles.listHeader}>
            <h2 className={styles.sectionTitle}>All Accounts</h2>
            <button type="button" className={styles.addBtn} onClick={() => setEditing(null)}>
              + Add account
            </button>
          </div>
          {accounts.accounts.map((acc, i) => (
            <motion.button
              type="button"
              key={acc.account_id}
              className={styles.accountRow}
              onClick={() => setEditing(acc)}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3 }}
            >
              <div className={styles.accountIcon}>{accountIcon(acc.balance)}</div>
              <div className={styles.accountInfo}>
                <span className={styles.accountName}>{acc.display_name ?? acc.account_id}</span>
              </div>
              <AnimatedNumber
                value={acc.balance}
                prefix="€ "
                decimals={2}
                className={`${styles.accountBalance} ${acc.balance < 0 ? styles.expense : ''}`}
              />
            </motion.button>
          ))}
        </section>

        {editing !== undefined && (
          <AccountModal account={editing} onClose={closeModal} onSaved={onSaved} />
        )}
```

Update the sync note copy:

```tsx
        <div className={styles.syncNote}>
          <span className={styles.syncDot} />
          <span>EB accounts synced 4×/day · manual accounts updated by you</span>
        </div>
```

Add the two new style rules to `frontend/src/pages/Accounts/AccountsPage.module.css` (append):

```css
.listHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.addBtn {
  background: none;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  padding: 4px 10px;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
}
```

Note: `.accountRow` changes from a `div` to a `button` — confirm the existing CSS rule works as a full-width reset (add `width: 100%; text-align: left; background: none; border: none;` to `.accountRow` if the current rule assumed a div).

- [ ] **Step 6: Run the frontend suite to verify it passes**

Run (from `frontend/`): `npx vitest run src/tests/AccountModal.test.tsx src/tests/AccountsPage.test.tsx && npm run build`
Expected: PASS + build green.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Accounts/ frontend/src/tests/AccountModal.test.tsx frontend/src/tests/AccountsPage.test.tsx
git commit -m "feat(fe): create/edit accounts on AccountsPage (SP-1)"
```

---

### Task 10: Integration tests (real Postgres)

**Files:**
- Create: `tests/integration/test_accounts_pg.py`

**Interfaces:**
- Consumes: the `db_conn` integration fixture (applies Alembic head, truncates `transactions`).
- Produces: real-PG proofs for manual-account lifecycle, delete rules, calibrate non-clobber, and balance-history reconciliation.

- [ ] **Step 1: Write the integration tests**

Create `tests/integration/test_accounts_pg.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fintracker.server.services import accounts, stats

pytestmark = pytest.mark.integration


def _clean_accounts(conn):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE accounts")
    conn.commit()


def test_manual_account_lifecycle_and_balance(db_conn):
    _clean_accounts(db_conn)
    acc = accounts.create_account(
        db_conn, display_name="Wallet", type="cash", opening_balance=Decimal("200")
    )
    uid = acc["account_id"]
    assert uid.startswith("manual:")

    # Zero-transaction account still appears with its opening balance (LEFT JOIN).
    out = accounts.balances(db_conn)
    mine = next(a for a in out["accounts"] if a["account_id"] == uid)
    assert mine["balance"] == 200.0 and mine["type"] == "cash" and mine["is_manual"] is True

    # A transaction on it moves the balance.
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO transactions
                   (dedup_hash, booking_date, amount, currency, eur_amount, account_id,
                    is_internal, status, source)
               VALUES ('m1', %s, -30, 'EUR', -30, %s, FALSE, 'verified', 'manual')""",
            (datetime(2026, 7, 5, tzinfo=UTC), uid),
        )
    db_conn.commit()
    out = accounts.balances(db_conn)
    assert next(a for a in out["accounts"] if a["account_id"] == uid)["balance"] == 170.0


def test_delete_rules(db_conn):
    _clean_accounts(db_conn)
    acc = accounts.create_account(db_conn, display_name="Wallet", type="cash")
    uid = acc["account_id"]
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO transactions
                   (dedup_hash, booking_date, amount, currency, eur_amount, account_id,
                    is_internal, status, source)
               VALUES ('m2', %s, -5, 'EUR', -5, %s, FALSE, 'verified', 'manual')""",
            (datetime(2026, 7, 6, tzinfo=UTC), uid),
        )
    db_conn.commit()
    assert accounts.delete_account(db_conn, uid) == "has_transactions"

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM transactions WHERE account_id = %s", (uid,))
    db_conn.commit()
    assert accounts.delete_account(db_conn, uid) == "deleted"
    assert accounts.get_account(db_conn, uid) is None


def test_calibrate_does_not_clobber_type_or_name(db_conn, monkeypatch):
    import scripts.calibrate_balances as cal  # pyrefly: ignore[missing-import]

    _clean_accounts(db_conn)
    # A user-typed EB account row already exists.
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO accounts (account_uid, display_name, type, is_manual, opening_balance)
               VALUES ('eb-1', 'My Revolut', 'card', FALSE, 0)"""
        )
    db_conn.commit()

    # Calibrate the EB uid for real: its ON CONFLICT DO UPDATE must touch only
    # opening/eb/calibrated and leave user-set type/display_name intact.
    monkeypatch.setattr(cal, "fetch_balances", lambda client, uid: Decimal("50.00"))
    monkeypatch.setattr(cal.time, "sleep", lambda s: None)
    cal.calibrate(db_conn, object(), ["eb-1"])

    got = accounts.get_account(db_conn, "eb-1")
    assert got["display_name"] == "My Revolut" and got["type"] == "card"
    assert got["opening_balance"] == 50.0  # opening recalibrated (50 - 0 deltas), name/type kept


def test_balance_history_reconciles_with_manual_opening(db_conn):
    _clean_accounts(db_conn)
    accounts.create_account(
        db_conn, display_name="Wallet", type="cash", opening_balance=Decimal("200")
    )
    series = stats.balance_history(db_conn, months=12)
    net_worth = accounts.balances(db_conn)
    total = net_worth["assets"] - net_worth["liabilities"]
    assert round(series[-1]["balance"], 2) == round(total, 2)  # last point == net worth
```

- [ ] **Step 2: Run the integration suite**

Run:
```bash
docker compose up db -d
uv run pytest -m integration tests/integration/test_accounts_pg.py -v
```
Expected: PASS. If Postgres is unreachable and `CI` is unset, pytest skips (by fixture design); start Docker to run for real.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_accounts_pg.py
git commit -m "test(integration): manual-account lifecycle, delete rules, calibrate isolation (SP-1)"
```

---

## Deployment (after all tasks pass review)

Backend changes ship via Railway; the migration must be applied to prod Neon **before** the backend redeploy so the new columns exist when `balances()` queries them.

```bash
# 1. Apply migration 0003 to prod Neon
railway run --service just-comfort -- uv run alembic upgrade head
# 2. Deploy backend
railway up --detach --service just-comfort
# 3. Frontend auto-deploys on push to main (Vercel)
```

Prod verification (service-level, authoritative): write a throwaway script to `scratchpad`, run it with `railway run --service just-comfort -- uv run python <script>` to create a manual account, post a transaction to it, and assert `balances()` and `balance_history()` reconcile; then delete the script. UI DOM verification requires the user to be logged in (the MCP browser tab is unauthenticated).
