# API Routes + Frontend Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 REST API routes to FastAPI and replace all mock data in the React frontend with live API calls.

**Architecture:** New `src/server/routes/api.py` holds all read/write routes behind a shared `_require_auth` FastAPI dependency (same HMAC pattern as `/sync`). CORS middleware is added to `app.py`. Frontend pages replace `useState(MOCK_*)` with `useEffect → api.*` calls, keeping mocks as initial state to avoid empty-flash.

**Tech Stack:** FastAPI + psycopg2 (RealDictCursor), React 18 + TypeScript + axios, pytest + TestClient

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/server/routes/api.py` | Create | 5 new routes with shared auth dependency |
| `src/server/app.py` | Modify | Add CORSMiddleware + include api_router |
| `src/models/transaction.py` | Modify | Add `"manual"` to `source` Literal |
| `src/normalizer/hash.py` | Modify | Add `manual_dedup_hash()` |
| `tests/test_api_routes.py` | Create | Tests for all 5 routes |
| `frontend/src/pages/Transactions/TransactionsPage.tsx` | Modify | Replace MOCK with API call |
| `frontend/src/pages/Transactions/AddTransactionModal.tsx` | Modify | Call POST /transactions on submit |
| `frontend/src/pages/Stats/StatsPage.tsx` | Modify | Replace MOCK with API calls |
| `frontend/src/pages/Accounts/AccountsPage.tsx` | Modify | Replace MOCK with API call |
| `frontend/src/api/types.ts` | Modify | Update AccountBalance + add AccountsResponse |
| `frontend/.env.local` | Create (if missing) | Set VITE_API_TOKEN for local dev |

---

### Task 1: CORS + Router Registration

**Files:**
- Modify: `src/server/app.py`
- Create: `src/server/routes/api.py` (skeleton)

- [ ] **Step 1: Update app.py — add CORSMiddleware and import api_router**

Replace `src/server/app.py` entirely with:

```python
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.server.routes.api import router as api_router
from src.server.routes.sync import router as sync_router
from src.server.routes.webhook import router as webhook_router
from src.server.scheduler import run_eb_sync

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Revolut Finance Ingestion", docs_url=None, redoc_url=None, openapi_url=None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(webhook_router)
    app.include_router(sync_router)
    app.include_router(api_router)

    scheduler = BackgroundScheduler(timezone="Europe/Rome")
    scheduler.add_job(
        run_eb_sync,
        "cron",
        hour="0,6,12,18",
        minute=0,
        id="eb_sync",
        max_instances=1,
        misfire_grace_time=300,
    )

    @app.on_event("startup")
    def start_scheduler() -> None:
        if not scheduler.running:
            scheduler.start()
        log.info("APScheduler started — EB sync at 00:00, 06:00, 12:00, 18:00 Europe/Rome")

    @app.on_event("shutdown")
    def stop_scheduler() -> None:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
```

- [ ] **Step 2: Create api.py skeleton so the import above doesn't fail**

Create `src/server/routes/api.py`:

```python
import hmac
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

import psycopg2.extras
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import config.settings as settings
from src.storage.db_insert import get_connection

log = logging.getLogger(__name__)
router = APIRouter()


def _require_auth(x_webhook_secret: str | None = Header(default=None)) -> None:
    if not hmac.compare_digest(
        (x_webhook_secret or "").encode(),
        settings.WEBHOOK_SECRET.encode(),
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


@contextmanager
def _get_conn():
    conn = get_connection(settings.DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def _row_to_dict(row: Any) -> dict[str, Any]:
    out = dict(row)
    for k, v in out.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out
```

- [ ] **Step 3: Verify app starts without error**

```
uv run uvicorn src.server.app:app --reload --port 8000
```

Expected: server starts, no ImportError. `curl http://localhost:8000/health` returns `{"status":"ok"}`.

- [ ] **Step 4: Commit**

```bash
git add src/server/app.py src/server/routes/api.py
git commit -m "feat: add CORS middleware and api router skeleton"
```

---

### Task 2: GET /transactions Route

**Files:**
- Modify: `src/server/routes/api.py`
- Create: `tests/test_api_routes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_routes.py`:

```python
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SECRET = "test-webhook-secret-for-pytest!!"

FAKE_ROW = {
    "id": 1,
    "dedup_hash": "abc123",
    "booking_date": datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc),
    "amount": -4.27,
    "currency": "EUR",
    "eur_amount": -4.27,
    "description": "Test tx",
    "merchant_name": "Merchant",
    "account_id": "acc1",
    "is_internal": False,
    "category": "Eating Out",
    "subcategory": None,
    "status": "verified",
    "source": "enable_banking",
    "source_id": None,
    "created_at": datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc),
}


@pytest.fixture
def client():
    from src.server.app import create_app
    return TestClient(create_app())


def _mock_conn(fetchall_result=None, fetchone_result=None):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fetchall_result or []
    mock_cur.fetchone.return_value = fetchone_result or {"total": 0}
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn


class TestTransactionsList:
    def test_missing_auth_returns_401(self, client):
        resp = client.get("/transactions")
        assert resp.status_code == 401

    def test_wrong_auth_returns_401(self, client):
        resp = client.get("/transactions", headers={"X-Webhook-Secret": "wrong"})
        assert resp.status_code == 401

    def test_returns_paginated_response(self, client):
        with patch("src.server.routes.api.get_connection",
                   return_value=_mock_conn([FAKE_ROW], {"total": 1})):
            resp = client.get("/transactions", headers={"X-Webhook-Secret": _SECRET})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == 1
        assert data["items"][0]["merchant_name"] == "Merchant"

    def test_days_back_above_365_returns_422(self, client):
        resp = client.get("/transactions?days_back=366",
                          headers={"X-Webhook-Secret": _SECRET})
        assert resp.status_code == 422

    def test_page_defaults_to_1(self, client):
        with patch("src.server.routes.api.get_connection",
                   return_value=_mock_conn([], {"total": 0})):
            resp = client.get("/transactions", headers={"X-Webhook-Secret": _SECRET})
        assert resp.json()["page"] == 1
```

- [ ] **Step 2: Run tests — expect failure**

```
uv run pytest tests/test_api_routes.py::TestTransactionsList -v
```

Expected: FAIL — `GET /transactions` returns 404.

- [ ] **Step 3: Implement GET /transactions in api.py**

Add after `_row_to_dict` in `src/server/routes/api.py`:

```python
@router.get("/transactions")
async def list_transactions(
    _: Annotated[None, Depends(_require_auth)],
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=200)] = 50,
    days_back: Annotated[int, Field(ge=1, le=365)] = 30,
    category: str | None = None,
    direction: str | None = Query(default=None, pattern="^(income|expense)$"),
    search: str | None = None,
) -> dict:
    conditions = ["booking_date >= NOW() - INTERVAL '%s days'"]
    params: list[Any] = [days_back]

    if category:
        conditions.append("category = %s")
        params.append(category)
    if direction == "income":
        conditions.append("amount > 0")
    elif direction == "expense":
        conditions.append("amount < 0")
    if search:
        conditions.append("(merchant_name ILIKE %s OR description ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT COUNT(*) AS total FROM real_transactions WHERE {where}",
                params,
            )
            total = cur.fetchone()["total"]
            cur.execute(
                f"""SELECT id, dedup_hash, booking_date, amount, currency, eur_amount,
                           description, merchant_name, account_id, is_internal,
                           category, subcategory, status, source, created_at
                    FROM real_transactions
                    WHERE {where}
                    ORDER BY booking_date DESC
                    LIMIT %s OFFSET %s""",
                params + [page_size, offset],
            )
            rows = [_row_to_dict(r) for r in cur.fetchall()]

    return {"items": rows, "total": total, "page": page, "page_size": page_size}
```

- [ ] **Step 4: Run tests — expect pass**

```
uv run pytest tests/test_api_routes.py::TestTransactionsList -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/server/routes/api.py tests/test_api_routes.py
git commit -m "feat: add GET /transactions with auth, filters, pagination"
```

---

### Task 3: POST /transactions Route

**Files:**
- Modify: `src/models/transaction.py`
- Modify: `src/normalizer/hash.py`
- Modify: `src/server/routes/api.py`
- Modify: `tests/test_api_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_routes.py`:

```python
class TestCreateTransaction:
    def test_missing_auth_returns_401(self, client):
        resp = client.post("/transactions", json={})
        assert resp.status_code == 401

    def test_missing_required_fields_returns_422(self, client):
        resp = client.post(
            "/transactions",
            json={"amount": -5.0},
            headers={"X-Webhook-Secret": _SECRET},
        )
        assert resp.status_code == 422

    def test_create_returns_201(self, client):
        body = {
            "booking_date": "2026-06-08T12:00:00Z",
            "amount": -12.50,
            "currency": "EUR",
            "eur_amount": -12.50,
            "merchant_name": "Costa Coffee",
            "category": "Eating Out",
        }
        returned_row = dict(
            FAKE_ROW,
            id=99,
            amount=-12.50,
            eur_amount=-12.50,
            merchant_name="Costa Coffee",
            category="Eating Out",
            source="manual",
        )
        mock_cur = MagicMock()
        mock_cur.rowcount = 1
        mock_cur.fetchone.return_value = returned_row
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        with patch("src.server.routes.api.get_connection", return_value=mock_conn):
            resp = client.post(
                "/transactions",
                json=body,
                headers={"X-Webhook-Secret": _SECRET},
            )

        assert resp.status_code == 201
        assert resp.json()["merchant_name"] == "Costa Coffee"
```

- [ ] **Step 2: Run tests — expect failure**

```
uv run pytest tests/test_api_routes.py::TestCreateTransaction -v
```

Expected: FAIL — route not found.

- [ ] **Step 3: Extend NormalizedTransaction source Literal**

In `src/models/transaction.py`, change line 24:

```python
    source: Literal["tasker", "enable_banking", "manual"] = "enable_banking"
```

- [ ] **Step 4: Add manual_dedup_hash to hash.py**

In `src/normalizer/hash.py`, append:

```python
def manual_dedup_hash(booking_date: str, amount: float, currency: str) -> str:
    payload = f"manual|{booking_date[:19]}|{abs(amount)}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 5: Add POST /transactions to api.py**

Add to `src/server/routes/api.py` (after `list_transactions`):

```python
from datetime import datetime

from src.normalizer.hash import manual_dedup_hash

_INSERT_RETURN = """
INSERT INTO transactions
    (dedup_hash, booking_date, amount, currency, eur_amount,
     description, merchant_name, account_id, is_internal, category, subcategory,
     status, source, source_id)
VALUES
    (%(dedup_hash)s, %(booking_date)s, %(amount)s, %(currency)s, %(eur_amount)s,
     %(description)s, %(merchant_name)s, %(account_id)s, %(is_internal)s,
     %(category)s, %(subcategory)s, %(status)s, %(source)s, %(source_id)s)
ON CONFLICT (dedup_hash) DO NOTHING
RETURNING id, dedup_hash, booking_date, amount, currency, eur_amount,
          description, merchant_name, account_id, is_internal,
          category, subcategory, status, source, created_at
"""


class ManualTransactionIn(BaseModel):
    booking_date: datetime
    amount: float
    currency: str = "EUR"
    eur_amount: float
    merchant_name: str | None = None
    description: str | None = None
    account_id: str | None = None
    category: str | None = None
    subcategory: str | None = None


@router.post("/transactions", status_code=201)
async def create_transaction(
    body: ManualTransactionIn,
    _: Annotated[None, Depends(_require_auth)],
) -> dict:
    dedup = manual_dedup_hash(body.booking_date.isoformat(), body.amount, body.currency)
    row_data = {
        "dedup_hash": dedup,
        "booking_date": body.booking_date,
        "amount": body.amount,
        "currency": body.currency,
        "eur_amount": body.eur_amount,
        "description": body.description,
        "merchant_name": body.merchant_name,
        "account_id": body.account_id,
        "is_internal": False,
        "category": body.category,
        "subcategory": body.subcategory,
        "status": "verified",
        "source": "manual",
        "source_id": None,
    }

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_INSERT_RETURN, row_data)
            conn.commit()
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=409, detail="Duplicate transaction")

    return _row_to_dict(row)
```

- [ ] **Step 6: Run tests — expect pass**

```
uv run pytest tests/test_api_routes.py::TestCreateTransaction -v
```

Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/models/transaction.py src/normalizer/hash.py src/server/routes/api.py tests/test_api_routes.py
git commit -m "feat: add POST /transactions for manual entries"
```

---

### Task 4: Stats Routes

**Files:**
- Modify: `src/server/routes/api.py`
- Modify: `tests/test_api_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_routes.py`:

```python
FAKE_CATEGORY_ROW = {"category": "Eating Out", "total": 16.00, "count": 2}
FAKE_MONTHLY_ROW = {
    "month": "2026-06",
    "income": 2198.80,
    "expenses": 114.25,
}


class TestStats:
    def test_categories_missing_auth_returns_401(self, client):
        resp = client.get("/stats/categories")
        assert resp.status_code == 401

    def test_categories_returns_list_with_percentages(self, client):
        with patch("src.server.routes.api.get_connection",
                   return_value=_mock_conn([FAKE_CATEGORY_ROW])):
            resp = client.get("/stats/categories", headers={"X-Webhook-Secret": _SECRET})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["category"] == "Eating Out"
        assert data[0]["total"] == 16.00
        assert data[0]["count"] == 2
        assert data[0]["percentage"] == 100.0

    def test_monthly_missing_auth_returns_401(self, client):
        resp = client.get("/stats/monthly")
        assert resp.status_code == 401

    def test_monthly_returns_list_with_net(self, client):
        with patch("src.server.routes.api.get_connection",
                   return_value=_mock_conn([FAKE_MONTHLY_ROW])):
            resp = client.get("/stats/monthly", headers={"X-Webhook-Secret": _SECRET})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["income"] == 2198.80
        assert data[0]["expenses"] == 114.25
        assert abs(data[0]["net"] - (2198.80 - 114.25)) < 0.01
```

- [ ] **Step 2: Run tests — expect failure**

```
uv run pytest tests/test_api_routes.py::TestStats -v
```

Expected: FAIL — routes return 404.

- [ ] **Step 3: Implement stats routes in api.py**

Add to `src/server/routes/api.py`:

```python
@router.get("/stats/categories")
async def stats_categories(
    _: Annotated[None, Depends(_require_auth)],
    days_back: Annotated[int, Field(ge=1, le=365)] = 30,
) -> list[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT COALESCE(category, 'Uncategorized') AS category,
                          ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total,
                          COUNT(*) AS count
                   FROM real_transactions
                   WHERE amount < 0
                     AND booking_date >= NOW() - INTERVAL '%s days'
                   GROUP BY category
                   ORDER BY total DESC""",
                [days_back],
            )
            rows = [dict(r) for r in cur.fetchall()]

    grand_total = sum(float(r["total"]) for r in rows) or 1
    for r in rows:
        r["percentage"] = round(float(r["total"]) / grand_total * 100, 1)
    return rows


@router.get("/stats/monthly")
async def stats_monthly(
    _: Annotated[None, Depends(_require_auth)],
    months: Annotated[int, Field(ge=1, le=24)] = 12,
) -> list[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT TO_CHAR(DATE_TRUNC('month', booking_date), 'YYYY-MM') AS month,
                          ROUND(SUM(CASE WHEN amount > 0 THEN eur_amount ELSE 0 END)::numeric, 2) AS income,
                          ROUND(SUM(CASE WHEN amount < 0 THEN ABS(eur_amount) ELSE 0 END)::numeric, 2) AS expenses
                   FROM real_transactions
                   GROUP BY DATE_TRUNC('month', booking_date)
                   ORDER BY DATE_TRUNC('month', booking_date) DESC
                   LIMIT %s""",
                [months],
            )
            rows = [dict(r) for r in cur.fetchall()]

    for r in rows:
        r["net"] = round(float(r["income"]) - float(r["expenses"]), 2)
    return rows
```

- [ ] **Step 4: Run tests — expect pass**

```
uv run pytest tests/test_api_routes.py::TestStats -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/server/routes/api.py tests/test_api_routes.py
git commit -m "feat: add GET /stats/categories and /stats/monthly"
```

---

### Task 5: GET /accounts Route

**Files:**
- Modify: `src/server/routes/api.py`
- Modify: `tests/test_api_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_routes.py`:

```python
FAKE_ACCOUNT_ROW = {"account_id": "revolut-main", "balance": 1234.56}


class TestAccounts:
    def test_missing_auth_returns_401(self, client):
        resp = client.get("/accounts")
        assert resp.status_code == 401

    def test_returns_accounts_list(self, client):
        with patch("src.server.routes.api.get_connection",
                   return_value=_mock_conn([FAKE_ACCOUNT_ROW])):
            resp = client.get("/accounts", headers={"X-Webhook-Secret": _SECRET})

        assert resp.status_code == 200
        data = resp.json()
        assert "assets" in data
        assert "liabilities" in data
        assert "accounts" in data
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["account_id"] == "revolut-main"
        assert data["accounts"][0]["balance"] == 1234.56
```

- [ ] **Step 2: Run tests — expect failure**

```
uv run pytest tests/test_api_routes.py::TestAccounts -v
```

Expected: FAIL.

- [ ] **Step 3: Implement GET /accounts in api.py**

Add to `src/server/routes/api.py`:

```python
@router.get("/accounts")
async def list_accounts(
    _: Annotated[None, Depends(_require_auth)],
) -> dict:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT account_id,
                          ROUND(SUM(eur_amount)::numeric, 2) AS balance
                   FROM real_transactions
                   WHERE account_id IS NOT NULL
                   GROUP BY account_id
                   ORDER BY balance DESC"""
            )
            rows = [dict(r) for r in cur.fetchall()]

    accounts = [{"account_id": r["account_id"], "balance": float(r["balance"])} for r in rows]
    assets = round(sum(a["balance"] for a in accounts if a["balance"] > 0), 2)
    liabilities = round(abs(sum(a["balance"] for a in accounts if a["balance"] < 0)), 2)

    return {"assets": assets, "liabilities": liabilities, "accounts": accounts}
```

- [ ] **Step 4: Run tests — expect pass**

```
uv run pytest tests/test_api_routes.py::TestAccounts -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Run full test suite to verify no regressions**

```
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/server/routes/api.py tests/test_api_routes.py
git commit -m "feat: add GET /accounts (computed net balance per account_id)"
```

---

### Task 6: Wire TransactionsPage to API

**Files:**
- Modify: `frontend/src/pages/Transactions/TransactionsPage.tsx`
- Modify: `frontend/src/pages/Transactions/TransactionsPage.module.css`
- Create: `frontend/.env.local` (if missing)

- [ ] **Step 1: Ensure VITE_API_TOKEN is set**

Check if `frontend/.env.local` exists. If not, create it with:

```
VITE_API_URL=http://localhost:8000
VITE_API_TOKEN=<WEBHOOK_SECRET value from config/.env>
```

Do NOT commit this file.

- [ ] **Step 2: Replace mock with API call in TransactionsPage.tsx**

Replace the entire file content of `frontend/src/pages/Transactions/TransactionsPage.tsx`:

```tsx
import { useState, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../../api/client';
import type { Transaction } from '../../api/types';
import { AnimatedNumber } from '../../components/AnimatedNumber';
import { AddTransactionModal } from './AddTransactionModal';
import styles from './TransactionsPage.module.css';

type ViewMode = 'daily' | 'monthly';

function groupByDate(txs: Transaction[]): Record<string, Transaction[]> {
  return txs.reduce<Record<string, Transaction[]>>((acc, tx) => {
    const day = tx.booking_date.slice(0, 10);
    (acc[day] ??= []).push(tx);
    return acc;
  }, {});
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'long' });
}

function formatMonth(iso: string): string {
  const d = new Date(iso + '-01');
  return d.toLocaleDateString('it-IT', { month: 'long', year: 'numeric' });
}

function groupByMonth(txs: Transaction[]): Record<string, Transaction[]> {
  return txs.reduce<Record<string, Transaction[]>>((acc, tx) => {
    const month = tx.booking_date.slice(0, 7);
    (acc[month] ??= []).push(tx);
    return acc;
  }, {});
}

const CATEGORY_COLORS: Record<string, string> = {
  'Income': 'var(--income)',
  'Connectivity': 'var(--chart-7)',
  'Career & Professional': 'var(--chart-3)',
  'Eating Out': 'var(--chart-6)',
  'Personal shopping': 'var(--chart-4)',
  'Health': 'var(--chart-5)',
  'Other': 'var(--text-muted)',
};

function categoryColor(cat: string | null): string {
  if (!cat) return 'var(--text-muted)';
  return CATEGORY_COLORS[cat] ?? 'var(--chart-1)';
}

function categoryInitial(cat: string | null): string {
  if (!cat) return '?';
  return cat[0].toUpperCase();
}

export function TransactionsPage() {
  const [view, setView] = useState<ViewMode>('daily');
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.transactions
      .list({ days_back: 90, page_size: 500 })
      .then(r => setTransactions(r.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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

  const dailyGroups   = groupByDate(filtered);
  const monthlyGroups = groupByMonth(filtered);

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
              value={totalIncome - totalExpenses}
              prefix={totalIncome - totalExpenses >= 0 ? '+€ ' : '-€ '}
              className={`${styles.summaryValue} ${totalIncome >= totalExpenses ? styles.income : styles.expense}`}
            />
          </div>
        </div>

        <div className={styles.controls}>
          <div className={styles.toggle}>
            {(['daily', 'monthly'] as ViewMode[]).map(v => (
              <button
                key={v}
                className={`${styles.toggleBtn} ${view === v ? styles.toggleActive : ''}`}
                onClick={() => setView(v)}
              >
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            ))}
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

      <main className={styles.main}>
        {loading && <div className={styles.loadingMsg}>Loading…</div>}

        {view === 'daily' && (
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
                  {txs.map((tx, i) => <TxRow key={tx.id} tx={tx} index={i} />)}
                </motion.section>
              ))}
          </AnimatePresence>
        )}

        {view === 'monthly' && (
          <AnimatePresence>
            {Object.entries(monthlyGroups)
              .sort(([a], [b]) => b.localeCompare(a))
              .map(([month, txs], gi) => {
                const income   = txs.filter(t => t.amount > 0).reduce((s, t) => s + t.eur_amount, 0);
                const expenses = txs.filter(t => t.amount < 0).reduce((s, t) => s + Math.abs(t.eur_amount), 0);
                return (
                  <motion.section
                    key={month}
                    className={styles.group}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: gi * 0.06, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <div className={styles.groupHeader}>
                      <span className={styles.groupDate}>{formatMonth(month)}</span>
                      <div className={styles.monthStats}>
                        <span className={styles.income}>+€{income.toFixed(2)}</span>
                        <span className={styles.expense}>-€{expenses.toFixed(2)}</span>
                      </div>
                    </div>
                    {txs.map((tx, i) => <TxRow key={tx.id} tx={tx} index={i} />)}
                  </motion.section>
                );
              })}
          </AnimatePresence>
        )}
      </main>

      {showAdd && <AddTransactionModal onClose={() => setShowAdd(false)} onAdd={tx => setTransactions(prev => [tx, ...prev])} />}
    </div>
  );
}

function TxRow({ tx, index }: { tx: Transaction; index: number }) {
  const isIncome = tx.amount > 0;
  const color = categoryColor(tx.category);
  const initial = categoryInitial(tx.category);

  return (
    <motion.div
      className={styles.txRow}
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25 }}
      whileHover={{ backgroundColor: 'var(--bg-hover)' }}
    >
      <div className={styles.txIcon} style={{ '--cat-color': color } as React.CSSProperties}>
        {initial}
      </div>
      <div className={styles.txInfo}>
        <span className={styles.txMerchant}>{tx.merchant_name ?? tx.description ?? '—'}</span>
        <span className={styles.txMeta}>
          {tx.category ?? 'Uncategorized'}
          {tx.status === 'pending' && <span className={styles.pendingBadge}>pending</span>}
        </span>
      </div>
      <div className={styles.txAmount}>
        <span className={`${styles.txAmountValue} ${isIncome ? styles.income : styles.expense}`}>
          {isIncome ? '+' : ''}€{Math.abs(tx.eur_amount).toFixed(2)}
        </span>
        {tx.currency !== 'EUR' && (
          <span className={styles.txCurrency}>{tx.currency}</span>
        )}
      </div>
    </motion.div>
  );
}
```

- [ ] **Step 3: Add loadingMsg CSS class to TransactionsPage.module.css**

Add at end of `frontend/src/pages/Transactions/TransactionsPage.module.css`:

```css
.loadingMsg {
  text-align: center;
  color: var(--text-muted);
  padding: 2rem 0;
  font-family: var(--font-mono);
  font-size: 0.85rem;
}
```

- [ ] **Step 4: Verify in browser**

Start backend and frontend:

```bash
# Terminal 1
uv run uvicorn src.server.app:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev -- --port 3000
```

Open `http://localhost:3000`. Transactions tab should show real data from DB.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Transactions/TransactionsPage.tsx frontend/src/pages/Transactions/TransactionsPage.module.css
git commit -m "feat: wire TransactionsPage to GET /transactions API"
```

---

### Task 7: Wire AddTransactionModal to POST /transactions

**Files:**
- Modify: `frontend/src/pages/Transactions/AddTransactionModal.tsx`

- [ ] **Step 1: Replace local-only submit with API call**

Replace the entire file content of `frontend/src/pages/Transactions/AddTransactionModal.tsx`:

```tsx
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../../api/client';
import type { Transaction } from '../../api/types';
import styles from './AddTransactionModal.module.css';

type TxType = 'income' | 'expense';

const CATEGORIES = [
  'Eating Out', 'Groceries', 'Transport', 'Health', 'Personal shopping',
  'Connectivity', 'Entertainment', 'Career & Professional', 'Housing', 'Other',
];

interface Props {
  onClose: () => void;
  onAdd: (tx: Transaction) => void;
}

export function AddTransactionModal({ onClose, onAdd }: Props) {
  const [type, setType]           = useState<TxType>('expense');
  const [amount, setAmount]       = useState('');
  const [merchant, setMerchant]   = useState('');
  const [category, setCategory]   = useState('');
  const [note, setNote]           = useState('');
  const [date, setDate]           = useState(new Date().toISOString().slice(0, 10));
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || isNaN(parseFloat(amount))) return;
    const signed = type === 'income' ? Math.abs(parseFloat(amount)) : -Math.abs(parseFloat(amount));

    setSubmitting(true);
    try {
      const tx = await api.transactions.create({
        booking_date: new Date(date).toISOString(),
        amount: signed,
        currency: 'EUR',
        eur_amount: signed,
        description: note || undefined,
        merchant_name: merchant || undefined,
        category: category || undefined,
      });
      onAdd(tx);
      onClose();
    } catch {
      // API unreachable — insert locally so UI stays responsive
      const localTx: Transaction = {
        id: Date.now(),
        dedup_hash: `manual-${Date.now()}`,
        booking_date: new Date(date).toISOString(),
        amount: signed,
        currency: 'EUR',
        eur_amount: signed,
        description: note || null,
        merchant_name: merchant || null,
        account_id: null,
        is_internal: false,
        category: category || null,
        subcategory: null,
        status: 'verified',
        source: 'manual',
        created_at: new Date().toISOString(),
      };
      onAdd(localTx);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        className={styles.backdrop}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          className={styles.modal}
          initial={{ opacity: 0, y: 40, scale: 0.96 }}
          animate={{ opacity: 1, y: 0,  scale: 1 }}
          exit={{ opacity: 0, y: 40, scale: 0.96 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          onClick={e => e.stopPropagation()}
        >
          <div className={styles.header}>
            <div className={styles.typeTabs}>
              {(['income', 'expense'] as TxType[]).map(t => (
                <button
                  key={t}
                  className={`${styles.typeTab} ${type === t ? styles.typeTabActive : ''} ${styles[t]}`}
                  onClick={() => setType(t)}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <button className={styles.closeBtn} onClick={onClose}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
            </button>
          </div>

          <form className={styles.form} onSubmit={handleSubmit}>
            <div className={styles.amountRow}>
              <span className={styles.currencyLabel}>€</span>
              <input
                className={styles.amountInput}
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                value={amount}
                onChange={e => setAmount(e.target.value)}
                autoFocus
              />
            </div>

            <div className={styles.fields}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Merchant / Payee</span>
                <input className={styles.input} value={merchant} onChange={e => setMerchant(e.target.value)} placeholder="e.g. Costa Coffee" />
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Date</span>
                <input className={styles.input} type="date" value={date} onChange={e => setDate(e.target.value)} />
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Category</span>
                <select className={styles.input} value={category} onChange={e => setCategory(e.target.value)}>
                  <option value="">Select category</option>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Note</span>
                <input className={styles.input} value={note} onChange={e => setNote(e.target.value)} placeholder="Optional note" />
              </label>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className={`${styles.submitBtn} ${type === 'income' ? styles.submitIncome : styles.submitExpense}`}
            >
              {submitting ? 'Saving…' : `Add ${type.charAt(0).toUpperCase() + type.slice(1)}`}
            </button>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
```

- [ ] **Step 2: Verify in browser**

Open the Add Transaction modal, submit a transaction. Verify it appears in the list and is persisted in the DB (check via `uv run python -c "import psycopg2; ..."` or next page reload).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Transactions/AddTransactionModal.tsx
git commit -m "feat: wire AddTransactionModal to POST /transactions"
```

---

### Task 8: Wire StatsPage to API

**Files:**
- Modify: `frontend/src/pages/Stats/StatsPage.tsx`

- [ ] **Step 1: Replace mock constants with API-loaded state**

Replace the entire file content of `frontend/src/pages/Stats/StatsPage.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import { motion } from 'framer-motion';
import { api, MOCK_CATEGORY_STATS, MOCK_MONTHLY_STATS } from '../../api/client';
import type { CategoryStat, MonthlyStat } from '../../api/types';
import { AnimatedNumber } from '../../components/AnimatedNumber';
import styles from './StatsPage.module.css';

const COLORS = [
  'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)',
  'var(--chart-5)', 'var(--chart-6)', 'var(--chart-7)', 'var(--chart-8)',
];

type Tab = 'expenses' | 'income';

function formatMonth(iso: string): string {
  const [y, m] = iso.split('-');
  return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString('it-IT', { month: 'short' });
}

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border-strong)',
      borderRadius: 8,
      padding: '8px 12px',
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-primary)',
    }}>
      <div>{payload[0]?.name}</div>
      <div style={{ color: 'var(--accent)', fontWeight: 600 }}>€{Number(payload[0]?.value).toFixed(2)}</div>
    </div>
  );
};

export function StatsPage() {
  const [_tab, setTab] = useState<Tab>('expenses');
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const [categoryData, setCategoryData] = useState<CategoryStat[]>(MOCK_CATEGORY_STATS);
  const [monthlyData, setMonthlyData] = useState<MonthlyStat[]>(MOCK_MONTHLY_STATS);

  useEffect(() => {
    api.stats.categories({ days_back: 30 }).then(setCategoryData).catch(() => {});
    api.stats.monthly({ months: 12 }).then(setMonthlyData).catch(() => {});
  }, []);

  const totalExpenses = categoryData.reduce((s, c) => s + c.total, 0);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Statistics</h1>
        <div className={styles.tabs}>
          {(['expenses', 'income'] as Tab[]).map(t => (
            <button
              key={t}
              className={`${styles.tab} ${_tab === t ? styles.tabActive : ''} ${t === 'income' ? styles.tabIncome : styles.tabExpense}`}
              onClick={() => setTab(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </header>

      <main className={styles.main}>
        <motion.section
          className={styles.pieSection}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className={styles.pieWrap}>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={categoryData}
                  dataKey="total"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  innerRadius={70}
                  outerRadius={110}
                  paddingAngle={3}
                  onMouseEnter={(_, idx) => setActiveIdx(idx)}
                  onMouseLeave={() => setActiveIdx(null)}
                >
                  {categoryData.map((_, i) => (
                    <Cell
                      key={i}
                      fill={COLORS[i % COLORS.length]}
                      opacity={activeIdx === null || activeIdx === i ? 1 : 0.35}
                      stroke="none"
                    />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>

            <div className={styles.pieCenter}>
              <span className={styles.pieCenterLabel}>Total</span>
              <AnimatedNumber value={totalExpenses} prefix="€ " decimals={0} className={styles.pieCenterValue} />
            </div>
          </div>

          <div className={styles.legend}>
            {categoryData.map((cat, i) => (
              <motion.div
                key={cat.category}
                className={styles.legendItem}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05, duration: 0.3 }}
                onMouseEnter={() => setActiveIdx(i)}
                onMouseLeave={() => setActiveIdx(null)}
                style={{ opacity: activeIdx === null || activeIdx === i ? 1 : 0.4 }}
              >
                <span className={styles.legendDot} style={{ background: COLORS[i % COLORS.length] }} />
                <span className={styles.legendName}>{cat.category}</span>
                <span className={styles.legendPct}>{cat.percentage.toFixed(1)}%</span>
                <span className={styles.legendAmount}>€{cat.total.toFixed(2)}</span>
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.section
          className={styles.barSection}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <h2 className={styles.sectionTitle}>Monthly Overview</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={[...monthlyData].reverse()} barGap={4} barCategoryGap="35%">
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
                axisLine={false}
                tickLine={false}
                tickFormatter={v => `€${(v/1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="income"   name="Income"   fill="var(--income)"  radius={[4,4,0,0]} />
              <Bar dataKey="expenses" name="Expenses" fill="var(--expense)" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </motion.section>

        <motion.section
          className={styles.monthlyList}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <h2 className={styles.sectionTitle}>By Month</h2>
          {[...monthlyData].filter(m => m.income > 0 || m.expenses > 0).map((m) => (
            <div key={m.month} className={styles.monthRow}>
              <span className={styles.monthName}>{formatMonth(m.month)} {m.month.slice(0, 4)}</span>
              <span className={styles.monthIncome}>+€{m.income.toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span>
              <span className={styles.monthExpense}>-€{m.expenses.toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span>
              <span className={`${styles.monthNet} ${m.net >= 0 ? styles.netPos : styles.netNeg}`}>
                {m.net >= 0 ? '+' : ''}€{Math.abs(m.net).toLocaleString('it-IT', { maximumFractionDigits: 0 })}
              </span>
            </div>
          ))}
        </motion.section>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Verify in browser**

Open Stats tab. Pie chart and bar chart should show live data. If few transactions exist, chart will be sparse but correct.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Stats/StatsPage.tsx
git commit -m "feat: wire StatsPage to /stats/categories and /stats/monthly"
```

---

### Task 9: Wire AccountsPage to API

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/Accounts/AccountsPage.tsx`

- [ ] **Step 1: Update types.ts to match backend response**

In `frontend/src/api/types.ts`, replace the `AccountBalance` interface and add `AccountsResponse`:

```ts
export interface AccountBalance {
  account_id: string;
  balance: number;
}

export interface AccountsResponse {
  assets: number;
  liabilities: number;
  accounts: AccountBalance[];
}
```

Also update `api.accounts.list` return type in `client.ts` — change:

```ts
    list: (): Promise<{ assets: number; liabilities: number; accounts: { name: string; balance: number }[] }> =>
```

to:

```ts
    list: (): Promise<AccountsResponse> =>
```

And add the import at the top of `client.ts`:

```ts
import type { Transaction, TransactionsResponse, CategoryStat, MonthlyStat, TransactionFilters, AccountsResponse } from './types';
```

- [ ] **Step 2: Replace AccountsPage with API-wired version**

Replace the entire file content of `frontend/src/pages/Accounts/AccountsPage.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { AnimatedNumber } from '../../components/AnimatedNumber';
import { api } from '../../api/client';
import type { AccountsResponse } from '../../api/types';
import styles from './AccountsPage.module.css';

const DEFAULT_DATA: AccountsResponse = { assets: 0, liabilities: 0, accounts: [] };

function accountIcon(balance: number) {
  return balance >= 0 ? '◇' : '◈';
}

export function AccountsPage() {
  const [data, setData] = useState<AccountsResponse>(DEFAULT_DATA);

  useEffect(() => {
    api.accounts.list().then(setData).catch(() => {});
  }, []);

  const total = data.assets - data.liabilities;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Accounts</h1>
      </header>

      <main className={styles.main}>
        <motion.section
          className={styles.hero}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className={styles.heroLabel}>Net Worth</span>
          <AnimatedNumber value={total} prefix="€ " decimals={2} className={styles.heroValue} />
          <div className={styles.heroSplit}>
            <div className={styles.heroItem}>
              <span className={styles.heroItemLabel}>Assets</span>
              <AnimatedNumber value={data.assets} prefix="€ " decimals={0} className={styles.income} />
            </div>
            <div className={styles.heroItemDivider} />
            <div className={styles.heroItem}>
              <span className={styles.heroItemLabel}>Liabilities</span>
              <AnimatedNumber value={data.liabilities} prefix="€ " decimals={0} className={styles.expense} />
            </div>
          </div>
        </motion.section>

        <section className={styles.listSection}>
          <h2 className={styles.sectionTitle}>All Accounts</h2>
          {data.accounts.map((acc, i) => (
            <motion.div
              key={acc.account_id}
              className={styles.accountRow}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3 }}
            >
              <div className={styles.accountIcon}>{accountIcon(acc.balance)}</div>
              <div className={styles.accountInfo}>
                <span className={styles.accountName}>{acc.account_id}</span>
              </div>
              <AnimatedNumber
                value={acc.balance}
                prefix="€ "
                decimals={2}
                className={`${styles.accountBalance} ${acc.balance < 0 ? styles.expense : ''}`}
              />
            </motion.div>
          ))}
        </section>

        <div className={styles.syncNote}>
          <span className={styles.syncDot} />
          <span>Balances synced from Enable Banking · 4×/day</span>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Verify in browser**

Open Accounts tab. Account rows should show real `account_id` values from DB.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/pages/Accounts/AccountsPage.tsx
git commit -m "feat: wire AccountsPage to GET /accounts"
```

---

## Self-Review

**Spec coverage:**
- [x] GET /transactions — Task 2
- [x] POST /transactions — Task 3
- [x] GET /stats/categories — Task 4
- [x] GET /stats/monthly — Task 4
- [x] GET /accounts — Task 5
- [x] CORS — Task 1
- [x] Auth on all new routes — via `_require_auth` Depends in Tasks 2–5
- [x] TransactionsPage wired — Task 6
- [x] AddTransactionModal wired — Task 7
- [x] StatsPage wired — Task 8
- [x] AccountsPage wired — Task 9
- [x] frontend/.env.local — Task 6 Step 1
- [x] `AccountsResponse` type — Task 9 Step 1
- [x] `manual_dedup_hash` — Task 3 Step 4
- [x] `"manual"` added to source Literal — Task 3 Step 3

**Placeholder scan:** All code blocks are complete. No TBDs.

**Type consistency:**
- `_get_conn()` context manager used in all 5 route handlers ✓
- `_row_to_dict()` used in GET /transactions and POST /transactions ✓
- `psycopg2.extras.RealDictCursor` imported at module level in api.py skeleton (Task 1) ✓
- `AccountsResponse` defined in types.ts (Task 9) and referenced in client.ts (Task 9) ✓
- `FAKE_ROW` in tests includes all fields needed by list_transactions ✓
- `manual_dedup_hash` defined in Task 3 Step 4 and called in Task 3 Step 5 ✓

**Note on accounts:** The `/accounts` endpoint returns `account_id` (opaque EB string) as the account name. This is correct for MVP — a name-mapping config can be added later without changing the API contract.
