# Revolut Real-Time Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Tasker webhook receiver + Enable Banking 6h scheduler to a FastAPI service on Railway, storing all transactions in Neon Postgres and sending Telegram notifications on new inserts.

**Architecture:** Single FastAPI process on Railway free tier. APScheduler runs the Enable Banking sync every 6h inside the same process. Both ingestion paths converge on a shared Pydantic `NormalizedTransaction` model before hitting the DB. Existing `src/` modules are refactored (not rewritten) to use the new shared model.

**Tech Stack:** FastAPI, Uvicorn, APScheduler, Pydantic v2, psycopg2-binary, httpx, pytest, Railway, Neon (Postgres)

---

## File Map

**New files:**
- `src/models/__init__.py`
- `src/models/transaction.py` — shared `NormalizedTransaction` (Pydantic)
- `src/models/tasker.py` — `TaskerPayload`
- `src/models/reconciliation.py` — `ReconciliationMatch`, `ReconciliationResult`
- `src/models/notification.py` — `TelegramMessage`
- `src/normalizer/hash.py` — `eb_dedup_hash`, `tasker_dedup_hash` (shared by both paths)
- `src/ingestion/tasker_parser.py` — `TaskerPayload → NormalizedTransaction`
- `src/storage/reconcile.py` — find pending match, update to verified
- `src/notifications/__init__.py`
- `src/notifications/telegram.py` — send Telegram message via Bot API
- `src/server/__init__.py`
- `src/server/routes/__init__.py`
- `src/server/routes/webhook.py` — `POST /webhook/tasker`
- `src/server/scheduler.py` — 6h EB sync APScheduler job
- `src/server/app.py` — FastAPI app wiring
- `scripts/migrate_schema.py` — ALTER TABLE for status/source/source_id columns
- `railway.toml` — Railway deployment config
- `tests/test_hash.py`
- `tests/test_tasker_parser.py`
- `tests/test_reconcile.py`
- `tests/test_webhook.py`

**Modified files:**
- `pyproject.toml` — add fastapi, uvicorn, apscheduler, pytest-asyncio
- `config/settings.py` — add TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_SECRET, ENABLE_BANKING_PRIVATE_KEY_B64
- `src/normalizer/normalize.py` — replace dataclass with Pydantic model, use `hash.py`, `booking_date` becomes `datetime`
- `src/storage/db_insert.py` — import model from `src.models.transaction`, add status/source/source_id to INSERT, add single-insert function
- `src/ingestion/fetch_transactions.py` — support `ENABLE_BANKING_PRIVATE_KEY_B64` env var (for Railway)
- `tests/test_normalizer.py` — update imports and assertions for new types

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add packages to pyproject.toml**

Replace the `dependencies` block:
```toml
dependencies = [
    "anthropic>=0.30.0",
    "apscheduler>=3.10.0",
    "fastapi>=0.115.0",
    "httpx>=0.28.1",
    "pgvector>=0.4.2",
    "psycopg2-binary>=2.9.9",
    "pydantic>=2.0.0",
    "python-dotenv>=1.2.2",
    "pyjwt[cryptography]>=2.8.0",
    "cryptography>=48.0.0",
    "uvicorn[standard]>=0.32.0",
]
```

Replace the `[dependency-groups]` dev block:
```toml
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-httpx>=0.35.0",
    "httpx>=0.28.1",
    "ruff>=0.8.0",
]
```

- [ ] **Step 2: Sync dependencies**

```powershell
uv sync
```
Expected: resolves and installs fastapi, uvicorn, apscheduler, pydantic.

- [ ] **Step 3: Commit**

```powershell
git add pyproject.toml uv.lock
git commit -m "feat: add fastapi, uvicorn, apscheduler, pydantic dependencies"
```

---

## Task 2: Shared Pydantic models

**Files:**
- Create: `src/models/__init__.py`
- Create: `src/models/transaction.py`
- Create: `src/models/tasker.py`
- Create: `src/models/reconciliation.py`
- Create: `src/models/notification.py`

- [ ] **Step 1: Create `src/models/__init__.py`**

```python
```
(empty)

- [ ] **Step 2: Create `src/models/transaction.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class NormalizedTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    dedup_hash: str
    booking_date: datetime
    amount: float
    currency: str
    eur_amount: float
    description: str | None = None
    merchant_name: str | None = None
    account_id: str | None = None
    is_internal: bool = False
    category: str | None = None
    subcategory: str | None = None
    status: Literal["pending", "verified"] = "verified"
    source: Literal["tasker", "enable_banking"] = "enable_banking"
    source_id: str | None = None
```

- [ ] **Step 3: Create `src/models/tasker.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TaskerPayload(BaseModel):
    raw_text: str
    amount: str | None = None
    currency: str | None = None
    merchant: str | None = None
    direction: Literal["debit", "credit"] | None = None
    device_timestamp: datetime
    parse_status: Literal["ok", "failed"] = "ok"
```

- [ ] **Step 4: Create `src/models/reconciliation.py`**

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReconciliationMatch(BaseModel):
    pending_id: int
    pending_dedup_hash: str


class ReconciliationResult(BaseModel):
    match: ReconciliationMatch | None
    action: Literal["reconciled", "inserted", "skipped"]
```

- [ ] **Step 5: Create `src/models/notification.py`**

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TelegramMessage(BaseModel):
    text: str
    parse_mode: Literal["HTML", "Markdown"] = "HTML"
```

- [ ] **Step 6: Verify models import cleanly**

```powershell
uv run python -c "from src.models.transaction import NormalizedTransaction; from src.models.tasker import TaskerPayload; print('OK')"
```
Expected: `OK`

- [ ] **Step 7: Commit**

```powershell
git add src/models/
git commit -m "feat: add shared Pydantic models (NormalizedTransaction, TaskerPayload, etc.)"
```

---

## Task 3: Extract dedup hash to `src/normalizer/hash.py`

**Files:**
- Create: `src/normalizer/hash.py`
- Create: `tests/test_hash.py`
- Modify: `src/normalizer/normalize.py` (import from hash.py)
- Modify: `tests/test_normalizer.py` (update import)

- [ ] **Step 1: Write failing tests in `tests/test_hash.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizer.hash import eb_dedup_hash, tasker_dedup_hash


class TestEbDedupHash:
    def test_deterministic(self):
        h1 = eb_dedup_hash("2024-01-15", -25.50, "Coffee Shop", "EUR")
        h2 = eb_dedup_hash("2024-01-15", -25.50, "Coffee Shop", "EUR")
        assert h1 == h2

    def test_uses_absolute_amount(self):
        assert eb_dedup_hash("2024-01-15", -25.50, "shop", "EUR") == \
               eb_dedup_hash("2024-01-15", 25.50, "shop", "EUR")

    def test_case_insensitive_description(self):
        assert eb_dedup_hash("2024-01-15", 10.0, "Coffee Shop", "EUR") == \
               eb_dedup_hash("2024-01-15", 10.0, "COFFEE SHOP", "EUR")

    def test_only_date_prefix_used(self):
        assert eb_dedup_hash("2024-01-15T12:30:00Z", 10.0, "shop", "EUR") == \
               eb_dedup_hash("2024-01-15", 10.0, "shop", "EUR")

    def test_sha256_length(self):
        assert len(eb_dedup_hash("2024-01-15", 10.0, "shop", "EUR")) == 64

    def test_different_amounts_differ(self):
        assert eb_dedup_hash("2024-01-15", 10.00, "shop", "EUR") != \
               eb_dedup_hash("2024-01-15", 10.01, "shop", "EUR")

    def test_different_currencies_differ(self):
        assert eb_dedup_hash("2024-01-15", 10.0, "shop", "EUR") != \
               eb_dedup_hash("2024-01-15", 10.0, "shop", "USD")


class TestTaskerDedupHash:
    def test_deterministic(self):
        from datetime import datetime, timezone
        ts = datetime(2024, 1, 15, 14, 32, 0, tzinfo=timezone.utc)
        assert tasker_dedup_hash(ts, 12.50, "EUR") == tasker_dedup_hash(ts, 12.50, "EUR")

    def test_sha256_length(self):
        from datetime import datetime, timezone
        ts = datetime(2024, 1, 15, 14, 32, 0, tzinfo=timezone.utc)
        assert len(tasker_dedup_hash(ts, 12.50, "EUR")) == 64

    def test_differs_from_eb_hash(self):
        from datetime import datetime, timezone
        ts = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        eb = eb_dedup_hash("2024-01-15", 12.50, "shop", "EUR")
        tk = tasker_dedup_hash(ts, 12.50, "EUR")
        assert eb != tk

    def test_truncates_to_minute(self):
        from datetime import datetime, timezone
        ts1 = datetime(2024, 1, 15, 14, 32, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 15, 14, 32, 45, tzinfo=timezone.utc)
        assert tasker_dedup_hash(ts1, 12.50, "EUR") == tasker_dedup_hash(ts2, 12.50, "EUR")
```

- [ ] **Step 2: Run tests, confirm they fail**

```powershell
uv run pytest tests/test_hash.py -v
```
Expected: `ImportError: cannot import name 'eb_dedup_hash'`

- [ ] **Step 3: Create `src/normalizer/hash.py`**

```python
import hashlib
from datetime import datetime


def eb_dedup_hash(date: str, amount: float, description: str, currency: str) -> str:
    # SHA-256(date[:10] + "|" + abs(amount) + "|" + desc_lower + "|" + currency)
    # NEVER change this formula — it would invalidate all historical hashes.
    payload = f"{date[:10]}|{abs(amount)}|{description.lower()}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()


def tasker_dedup_hash(timestamp: datetime, amount: float, currency: str) -> str:
    # Truncate to minute so 14:32:45 and 14:32:00 produce the same hash.
    minute = timestamp.strftime("%Y-%m-%dT%H:%M")
    payload = f"tasker|{minute}|{abs(amount)}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 4: Run tests, confirm they pass**

```powershell
uv run pytest tests/test_hash.py -v
```
Expected: all 11 tests PASS.

- [ ] **Step 5: Update `src/normalizer/normalize.py` to import from hash.py**

Replace the `_dedup_hash` function definition and its import:

Remove lines 1-3 (`import hashlib`) and the `_dedup_hash` function (lines 78-82).

Add at top of imports:
```python
from src.normalizer.hash import eb_dedup_hash
```

In the `normalize()` function, replace the call:
```python
dedup = _dedup_hash(date_str, amount, description, currency)
```
with:
```python
dedup = eb_dedup_hash(date_str, amount, description, currency)
```

- [ ] **Step 6: Update `tests/test_normalizer.py` to import from hash.py**

Replace:
```python
from src.normalizer.normalize import _dedup_hash, _is_internal, normalize
```
with:
```python
from src.normalizer.hash import eb_dedup_hash as _dedup_hash
from src.normalizer.normalize import _is_internal, normalize
```

- [ ] **Step 7: Run full test suite, confirm all pass**

```powershell
uv run pytest tests/ -v
```
Expected: all existing tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/normalizer/hash.py tests/test_hash.py src/normalizer/normalize.py tests/test_normalizer.py
git commit -m "refactor: extract dedup hash to normalizer/hash.py, shared by both ingestion paths"
```

---

## Task 4: Refactor `normalize.py` to return Pydantic `NormalizedTransaction`

**Files:**
- Modify: `src/normalizer/normalize.py`
- Modify: `src/storage/db_insert.py`
- Modify: `tests/test_normalizer.py`

The dataclass `NormalizedTransaction` in `normalize.py` is replaced by the Pydantic model from `src.models.transaction`. `booking_date` changes from `str` to `datetime`. The `raw` field is dropped (not stored in DB). `status` and `source` fields are added with defaults.

- [ ] **Step 1: Update `tests/test_normalizer.py` assertions for new types**

Replace the `TestNormalize.test_basic` method:
```python
def test_basic(self):
    from datetime import datetime, timezone
    txs = normalize([self._tx()], "acc1", ecb_rates={})
    assert len(txs) == 1
    t = txs[0]
    assert t.currency == "EUR"
    assert t.eur_amount == -25.50
    assert t.booking_date == datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
    assert t.account_id == "acc1"
    assert not t.is_internal
    assert len(t.dedup_hash) == 64
    assert t.status == "verified"
    assert t.source == "enable_banking"
```

- [ ] **Step 2: Run tests, confirm test_basic fails (still returns string booking_date)**

```powershell
uv run pytest tests/test_normalizer.py::TestNormalize::test_basic -v
```
Expected: FAIL — `AssertionError` on `booking_date`.

- [ ] **Step 3: Refactor `src/normalizer/normalize.py`**

Full updated file:
```python
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.transaction import NormalizedTransaction
from src.normalizer.hash import eb_dedup_hash

log = logging.getLogger(__name__)

INTERNAL_PATTERNS = [
    re.compile(r"^top[\s\-]?up\b", re.IGNORECASE),
    re.compile(r"^exchanged?\s+(from|to)\b", re.IGNORECASE),
    re.compile(r"\bsavings\s+vault\b", re.IGNORECASE),
    re.compile(r"^balance\s+migration\b", re.IGNORECASE),
    re.compile(r"^revolut\s+@", re.IGNORECASE),
    re.compile(r"\b(from|to)\s+vault\b", re.IGNORECASE),
    re.compile(r"^(crypto\s+exchange|crypto\s+purchase|cryptocurrency)\b", re.IGNORECASE),
]

_ecb_cache: dict[str, float] = {}


def fetch_ecb_rates() -> dict[str, float]:
    """Return {currency: rate} where 1 EUR = rate CCY (ECB reference rates)."""
    if _ecb_cache:
        return _ecb_cache
    try:
        url = (
            "https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A"
            "?lastNObservations=1&format=jsondata"
        )
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        series = data["dataSets"][0]["series"]
        dims = data["structure"]["dimensions"]["series"]
        currency_idx = next(i for i, d in enumerate(dims) if d["id"] == "CURRENCY")
        fresh: dict[str, float] = {}
        for key, series_data in series.items():
            parts = key.split(":")
            currency = dims[currency_idx]["values"][int(parts[currency_idx])]["id"]
            obs = series_data.get("observations", {})
            if obs:
                raw_value = list(obs.values())[-1][0]
                if raw_value is None:
                    continue
                fresh[currency] = float(raw_value)
        _ecb_cache.update(fresh)
        log.info("Loaded ECB rates for %d currencies", len(_ecb_cache))
    except Exception as exc:
        log.warning("Failed to fetch ECB rates: %s", exc)
    return _ecb_cache


def _to_eur(amount: float, currency: str, rates: dict[str, float]) -> float:
    if currency == "EUR":
        return amount
    rate = rates.get(currency)
    if rate is None:
        log.warning("No ECB rate for %s — storing original amount as eur_amount", currency)
        return amount
    return amount / rate


def _is_internal(description: str) -> bool:
    return any(p.search(description) for p in INTERNAL_PATTERNS)


def _extract_merchant(raw_tx: dict) -> str:
    indicator = raw_tx.get("credit_debit_indicator", "DBIT")
    if indicator == "DBIT":
        name = (raw_tx.get("creditor") or {}).get("name", "")
    else:
        name = (raw_tx.get("debtor") or {}).get("name", "")
    if not name:
        remittance = raw_tx.get("remittance_information", [])
        name = " ".join(remittance) if isinstance(remittance, list) else str(remittance)
    name = re.sub(r"\s+\d{4,}$", "", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name or "Unknown"


def _parse_amount(raw_tx: dict) -> float:
    amount_data = raw_tx.get("transaction_amount", {})
    amount = abs(float(amount_data.get("amount", 0)))
    if raw_tx.get("credit_debit_indicator", "DBIT") == "DBIT":
        return -amount
    return amount


def _description(raw_tx: dict) -> str:
    remittance = raw_tx.get("remittance_information", [])
    if isinstance(remittance, list):
        return " | ".join(remittance).strip()
    return str(remittance).strip()


def normalize(
    raw_transactions: list[dict],
    account_id: str,
    ecb_rates: dict[str, float] | None = None,
) -> list[NormalizedTransaction]:
    if ecb_rates is None:
        ecb_rates = fetch_ecb_rates()
    results = []
    for tx in raw_transactions:
        try:
            if tx.get("status") not in ("BOOK", None):
                continue
            date_str = tx.get("booking_date", "")
            if not date_str:
                log.warning("Transaction missing booking_date, skipping: %s", tx)
                continue
            currency = (tx.get("transaction_amount") or {}).get("currency", "EUR")
            amount = _parse_amount(tx)
            booking_date = datetime(
                int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
                tzinfo=timezone.utc,
            )
            description = _description(tx)
            merchant = _extract_merchant(tx)
            eur_amount = _to_eur(amount, currency, ecb_rates)
            dedup = eb_dedup_hash(date_str, amount, description, currency)
            results.append(
                NormalizedTransaction(
                    dedup_hash=dedup,
                    booking_date=booking_date,
                    amount=amount,
                    currency=currency,
                    eur_amount=eur_amount,
                    description=description,
                    merchant_name=merchant,
                    account_id=account_id,
                    is_internal=_is_internal(description),
                    status="verified",
                    source="enable_banking",
                )
            )
        except Exception as exc:
            log.warning("Failed to normalize transaction: %s — %s", tx, exc)
    return results
```

- [ ] **Step 4: Update `src/storage/db_insert.py`**

Replace the import at the top:
```python
from src.models.transaction import NormalizedTransaction
```
(Remove the old import `from src.normalizer.normalize import NormalizedTransaction`)

Update `_INSERT` SQL to include new columns:
```python
_INSERT = """
INSERT INTO transactions
    (dedup_hash, booking_date, amount, currency, eur_amount,
     description, merchant_name, account_id, is_internal, category, subcategory,
     status, source, source_id)
VALUES
    (%(dedup_hash)s, %(booking_date)s, %(amount)s, %(currency)s, %(eur_amount)s,
     %(description)s, %(merchant_name)s, %(account_id)s, %(is_internal)s,
     %(category)s, %(subcategory)s, %(status)s, %(source)s, %(source_id)s)
ON CONFLICT (dedup_hash) DO NOTHING
"""
```

Update `insert_transactions` to use `model_dump()`:
```python
def insert_transactions(conn, transactions: list[NormalizedTransaction]) -> int:
    if not transactions:
        return 0
    rows = [t.model_dump() for t in transactions]
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, _INSERT, rows, page_size=200)
    conn.commit()
    log.info("Upserted %d rows (duplicates silently skipped)", len(rows))
    return len(rows)
```

Add `insert_transaction` (single, returns whether it was actually inserted):
```python
def insert_transaction(conn, tx: NormalizedTransaction) -> bool:
    """Insert one transaction. Returns True if inserted, False if duplicate."""
    with conn.cursor() as cur:
        cur.execute(_INSERT, tx.model_dump())
        inserted = cur.rowcount > 0
    conn.commit()
    return inserted
```

- [ ] **Step 5: Run full test suite**

```powershell
uv run pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/normalizer/normalize.py src/storage/db_insert.py tests/test_normalizer.py
git commit -m "refactor: NormalizedTransaction as Pydantic model, booking_date as datetime, add status/source fields"
```

---

## Task 5: Extend `settings.py` + RSA key fallback in `fetch_transactions.py`

**Files:**
- Modify: `config/settings.py`
- Modify: `src/ingestion/fetch_transactions.py`

On Railway, files can't be mounted — the RSA private key must come from an env var (base64-encoded). This task adds `ENABLE_BANKING_PRIVATE_KEY_B64` as a fallback when the PEM file doesn't exist.

- [ ] **Step 1: Add new settings to `config/settings.py`**

Append to the end of the file:
```python
# Telegram
TELEGRAM_TOKEN: str = _get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID: str = _get("TELEGRAM_CHAT_ID")

# Webhook
WEBHOOK_SECRET: str = _get("WEBHOOK_SECRET")

# Enable Banking — base64 private key for cloud deployments (overrides file path)
ENABLE_BANKING_PRIVATE_KEY_B64: str = _get("ENABLE_BANKING_PRIVATE_KEY_B64")
```

- [ ] **Step 2: Update `_make_jwt()` in `src/ingestion/fetch_transactions.py`**

Replace the line `pem = settings.ENABLE_BANKING_PRIVATE_KEY_PATH.read_text()` with:
```python
    if settings.ENABLE_BANKING_PRIVATE_KEY_B64:
        import base64
        pem = base64.b64decode(settings.ENABLE_BANKING_PRIVATE_KEY_B64).decode()
    else:
        pem = settings.ENABLE_BANKING_PRIVATE_KEY_PATH.read_text()
```

- [ ] **Step 3: Verify import**

```powershell
uv run python -c "import config.settings as s; print('TELEGRAM_TOKEN:', bool(s.TELEGRAM_TOKEN) or 'not set (ok for now)')"
```
Expected: prints without error.

- [ ] **Step 4: Commit**

```powershell
git add config/settings.py src/ingestion/fetch_transactions.py
git commit -m "feat: add Telegram/webhook settings, support base64 RSA key for cloud deploy"
```

---

## Task 6: Schema migration script

**Files:**
- Create: `scripts/migrate_schema.py`

This script runs once against Neon (or local DB) to add the new columns. Safe to re-run (uses `IF NOT EXISTS` / `IF NOT EXISTS` equivalents).

- [ ] **Step 1: Create `scripts/migrate_schema.py`**

```python
"""Run once against Neon (or local DB) to add status/source/source_id columns.
Safe to re-run — uses ADD COLUMN IF NOT EXISTS.

Usage:
    uv run python scripts/migrate_schema.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config.settings as settings
from src.storage.db_insert import get_connection

_MIGRATION = """
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS status    TEXT DEFAULT 'verified',
    ADD COLUMN IF NOT EXISTS source    TEXT DEFAULT 'enable_banking',
    ADD COLUMN IF NOT EXISTS source_id TEXT;

CREATE INDEX IF NOT EXISTS idx_transactions_pending
    ON transactions (status, booking_date)
    WHERE status = 'pending';
"""


def main() -> None:
    print(f"Connecting to: {settings.DATABASE_URL[:40]}...")
    conn = get_connection(settings.DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(_MIGRATION)
    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```powershell
git add scripts/migrate_schema.py
git commit -m "feat: add schema migration script for status/source/source_id columns"
```

---

## Task 7: Tasker parser

**Files:**
- Create: `src/ingestion/tasker_parser.py`
- Create: `tests/test_tasker_parser.py`

Converts a validated `TaskerPayload` into a `NormalizedTransaction`. Tasker does the regex parsing (amount, merchant, direction) before POSTing — this module just maps the fields, handles the `parse_status=failed` case, and computes the dedup hash.

- [ ] **Step 1: Write failing tests in `tests/test_tasker_parser.py`**

```python
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.tasker_parser import parse_tasker_payload
from src.models.tasker import TaskerPayload


def _payload(**kwargs) -> TaskerPayload:
    defaults = {
        "raw_text": "Hai pagato €12,50 a Esselunga",
        "amount": "12.50",
        "currency": "EUR",
        "merchant": "Esselunga",
        "direction": "debit",
        "device_timestamp": datetime(2026, 6, 7, 14, 32, 0, tzinfo=timezone.utc),
        "parse_status": "ok",
    }
    defaults.update(kwargs)
    return TaskerPayload(**defaults)


class TestParseTaskerPayload:
    def test_debit_is_negative(self):
        tx = parse_tasker_payload(_payload(direction="debit", amount="12.50"))
        assert tx.amount == -12.50

    def test_credit_is_positive(self):
        tx = parse_tasker_payload(_payload(direction="credit", amount="50.00"))
        assert tx.amount == 50.00

    def test_status_is_pending(self):
        tx = parse_tasker_payload(_payload())
        assert tx.status == "pending"

    def test_source_is_tasker(self):
        tx = parse_tasker_payload(_payload())
        assert tx.source == "tasker"

    def test_currency_and_merchant(self):
        tx = parse_tasker_payload(_payload(currency="EUR", merchant="Esselunga"))
        assert tx.currency == "EUR"
        assert tx.merchant_name == "Esselunga"

    def test_dedup_hash_is_64_chars(self):
        tx = parse_tasker_payload(_payload())
        assert len(tx.dedup_hash) == 64

    def test_dedup_hash_deterministic(self):
        p = _payload()
        assert parse_tasker_payload(p).dedup_hash == parse_tasker_payload(p).dedup_hash

    def test_parse_failed_produces_none_amount(self):
        p = _payload(parse_status="failed", amount=None, merchant=None, direction=None)
        tx = parse_tasker_payload(p)
        assert tx.amount == 0.0
        assert tx.merchant_name is None
        assert tx.status == "pending"

    def test_booking_date_from_device_timestamp(self):
        ts = datetime(2026, 6, 7, 14, 32, 0, tzinfo=timezone.utc)
        tx = parse_tasker_payload(_payload(device_timestamp=ts))
        assert tx.booking_date == ts

    def test_is_internal_false(self):
        tx = parse_tasker_payload(_payload(merchant="Esselunga"))
        assert not tx.is_internal

    def test_eur_amount_equals_amount_for_eur(self):
        tx = parse_tasker_payload(_payload(currency="EUR", amount="12.50", direction="debit"))
        assert tx.eur_amount == -12.50
```

- [ ] **Step 2: Run tests, confirm they fail**

```powershell
uv run pytest tests/test_tasker_parser.py -v
```
Expected: `ImportError: cannot import name 'parse_tasker_payload'`

- [ ] **Step 3: Create `src/ingestion/tasker_parser.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.tasker import TaskerPayload
from src.models.transaction import NormalizedTransaction
from src.normalizer.hash import tasker_dedup_hash


def parse_tasker_payload(payload: TaskerPayload) -> NormalizedTransaction:
    """Convert a Tasker push-notification payload into a NormalizedTransaction.

    Amount is always stored as eur_amount too (no FX conversion — Revolut IT
    sends EUR amounts; non-EUR amounts will be reconciled by the EB sync).
    """
    if payload.parse_status == "failed" or payload.amount is None:
        amount = 0.0
        currency = payload.currency or "EUR"
        merchant = None
    else:
        raw_amount = abs(float(payload.amount))
        amount = -raw_amount if payload.direction == "debit" else raw_amount
        currency = payload.currency or "EUR"
        merchant = payload.merchant

    dedup = tasker_dedup_hash(payload.device_timestamp, abs(amount), currency)

    return NormalizedTransaction(
        dedup_hash=dedup,
        booking_date=payload.device_timestamp,
        amount=amount,
        currency=currency,
        eur_amount=amount,  # same as amount; EB sync will correct on reconciliation
        description=payload.raw_text,
        merchant_name=merchant,
        account_id=None,
        is_internal=False,
        status="pending",
        source="tasker",
        source_id=None,
    )
```

- [ ] **Step 4: Run tests, confirm they pass**

```powershell
uv run pytest tests/test_tasker_parser.py -v
```
Expected: all 11 tests PASS.

- [ ] **Step 5: Run full suite**

```powershell
uv run pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/ingestion/tasker_parser.py tests/test_tasker_parser.py
git commit -m "feat: add tasker_parser — converts Tasker push payload to NormalizedTransaction"
```

---

## Task 8: Reconciliation module

**Files:**
- Create: `src/storage/reconcile.py`
- Create: `tests/test_reconcile.py`

For each EB transaction: check if a verified row already exists (skip), check for a pending match (reconcile), or insert as new (notify). Uses a DB connection — tests use `unittest.mock`.

- [ ] **Step 1: Write failing tests in `tests/test_reconcile.py`**

```python
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.transaction import NormalizedTransaction
from src.storage.reconcile import reconcile_or_insert


def _tx(**kwargs) -> NormalizedTransaction:
    defaults = {
        "dedup_hash": "abc123",
        "booking_date": datetime(2026, 6, 7, 10, 0, 0, tzinfo=timezone.utc),
        "amount": -12.50,
        "currency": "EUR",
        "eur_amount": -12.50,
        "description": "Esselunga",
        "merchant_name": "Esselunga",
        "account_id": "acc1",
        "status": "verified",
        "source": "enable_banking",
    }
    defaults.update(kwargs)
    return NormalizedTransaction(**defaults)


def _mock_conn(fetchone_result=None, rowcount=1):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_result
    cur.rowcount = rowcount
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


class TestReconcileOrInsert:
    def test_skipped_when_already_verified(self):
        conn, cur = _mock_conn(fetchone_result=("verified",))
        result = reconcile_or_insert(conn, _tx())
        assert result.action == "skipped"
        assert result.match is None

    def test_reconciled_when_pending_match_found(self):
        # First fetchone: status query returns "pending"
        # Second fetchone: pending match query returns (99, "old_hash")
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.side_effect = [("pending",), (99, "old_hash")]
        cur.rowcount = 1
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = reconcile_or_insert(conn, _tx())
        assert result.action == "reconciled"
        assert result.match is not None
        assert result.match.pending_id == 99

    def test_inserted_when_no_existing_row(self):
        conn, cur = _mock_conn(fetchone_result=None, rowcount=1)
        result = reconcile_or_insert(conn, _tx())
        assert result.action == "inserted"

    def test_skipped_when_insert_is_duplicate(self):
        conn, cur = _mock_conn(fetchone_result=None, rowcount=0)
        result = reconcile_or_insert(conn, _tx())
        assert result.action == "skipped"
```

- [ ] **Step 2: Run tests, confirm they fail**

```powershell
uv run pytest tests/test_reconcile.py -v
```
Expected: `ImportError: cannot import name 'reconcile_or_insert'`

- [ ] **Step 3: Create `src/storage/reconcile.py`**

```python
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.reconciliation import ReconciliationMatch, ReconciliationResult
from src.models.transaction import NormalizedTransaction

log = logging.getLogger(__name__)

_CHECK_EXISTING = "SELECT status FROM transactions WHERE dedup_hash = %s LIMIT 1"

_FIND_PENDING_MATCH = """
SELECT id, dedup_hash
FROM transactions
WHERE status = 'pending'
  AND amount = %s
  AND currency = %s
  AND ABS(EXTRACT(EPOCH FROM (booking_date - %s))) <= 600
LIMIT 1
"""

_UPDATE_TO_VERIFIED = """
UPDATE transactions
SET dedup_hash   = %s,
    status       = 'verified',
    booking_date = %s,
    merchant_name = COALESCE(%s, merchant_name),
    account_id   = COALESCE(%s, account_id),
    source       = %s,
    source_id    = %s
WHERE id = %s
"""

_INSERT = """
INSERT INTO transactions
    (dedup_hash, booking_date, amount, currency, eur_amount,
     description, merchant_name, account_id, is_internal, category, subcategory,
     status, source, source_id)
VALUES
    (%(dedup_hash)s, %(booking_date)s, %(amount)s, %(currency)s, %(eur_amount)s,
     %(description)s, %(merchant_name)s, %(account_id)s, %(is_internal)s,
     %(category)s, %(subcategory)s, %(status)s, %(source)s, %(source_id)s)
ON CONFLICT (dedup_hash) DO NOTHING
"""


def reconcile_or_insert(conn, tx: NormalizedTransaction) -> ReconciliationResult:
    """Process one EB transaction: skip if verified, reconcile if pending match, else insert."""
    with conn.cursor() as cur:
        cur.execute(_CHECK_EXISTING, (tx.dedup_hash,))
        row = cur.fetchone()

    if row is not None:
        if row[0] == "verified":
            return ReconciliationResult(match=None, action="skipped")
        # Row exists as pending — fall through to find the pending match by amount/time
        with conn.cursor() as cur:
            cur.execute(_FIND_PENDING_MATCH, (tx.amount, tx.currency, tx.booking_date))
            match_row = cur.fetchone()
        if match_row:
            pending_id, pending_hash = match_row
            with conn.cursor() as cur:
                cur.execute(
                    _UPDATE_TO_VERIFIED,
                    (tx.dedup_hash, tx.booking_date, tx.merchant_name,
                     tx.account_id, tx.source, tx.source_id, pending_id),
                )
            conn.commit()
            log.info("Reconciled pending #%d → verified (%s)", pending_id, tx.dedup_hash[:8])
            return ReconciliationResult(
                match=ReconciliationMatch(pending_id=pending_id, pending_dedup_hash=pending_hash),
                action="reconciled",
            )

    # No existing row — insert fresh
    with conn.cursor() as cur:
        cur.execute(_INSERT, tx.model_dump())
        inserted = cur.rowcount > 0
    conn.commit()

    if inserted:
        log.info("Inserted new verified transaction %s", tx.dedup_hash[:8])
        return ReconciliationResult(match=None, action="inserted")
    return ReconciliationResult(match=None, action="skipped")
```

- [ ] **Step 4: Run tests, confirm they pass**

```powershell
uv run pytest tests/test_reconcile.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 5: Run full suite**

```powershell
uv run pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/storage/reconcile.py tests/test_reconcile.py
git commit -m "feat: add reconcile_or_insert — skip/reconcile/insert EB transactions against pending"
```

---

## Task 9: Telegram notifications

**Files:**
- Create: `src/notifications/__init__.py`
- Create: `src/notifications/telegram.py`
- Create: `tests/test_telegram.py`

Sends a formatted message via the Telegram Bot API using `httpx`. No SDK — just a direct POST.

- [ ] **Step 1: Write failing tests in `tests/test_telegram.py`**

```python
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.transaction import NormalizedTransaction
from src.notifications.telegram import build_message, send_telegram


def _tx(**kwargs):
    defaults = {
        "dedup_hash": "abc123",
        "booking_date": datetime(2026, 6, 7, 14, 32, 0, tzinfo=timezone.utc),
        "amount": -12.50,
        "currency": "EUR",
        "eur_amount": -12.50,
        "merchant_name": "Esselunga",
        "status": "pending",
        "source": "tasker",
    }
    defaults.update(kwargs)
    return NormalizedTransaction(**defaults)


class TestBuildMessage:
    def test_debit_pending(self):
        msg = build_message(_tx(amount=-12.50, status="pending", merchant_name="Esselunga"))
        assert "🔴" in msg
        assert "12.50" in msg
        assert "Esselunga" in msg
        assert "pending" in msg

    def test_credit_verified(self):
        msg = build_message(_tx(amount=50.0, status="verified", merchant_name="Mario Rossi"))
        assert "🟢" in msg
        assert "50.0" in msg
        assert "verified" in msg

    def test_parse_failed(self):
        msg = build_message(_tx(amount=0.0, status="pending", merchant_name=None))
        assert "⚠️" in msg

    def test_debit_verified(self):
        msg = build_message(_tx(amount=-12.50, status="verified", merchant_name="Netflix"))
        assert "🟢" in msg
        assert "12.50" in msg


class TestSendTelegram:
    def test_send_calls_telegram_api(self):
        with patch("src.notifications.telegram.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            send_telegram("test message", token="tok", chat_id="123")
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert "sendMessage" in call_kwargs[0][0]

    def test_send_skipped_when_no_token(self):
        with patch("src.notifications.telegram.httpx.post") as mock_post:
            send_telegram("test message", token="", chat_id="123")
            mock_post.assert_not_called()
```

- [ ] **Step 2: Run tests, confirm they fail**

```powershell
uv run pytest tests/test_telegram.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Create `src/notifications/__init__.py`**

```python
```
(empty)

- [ ] **Step 4: Create `src/notifications/telegram.py`**

```python
import logging
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.transaction import NormalizedTransaction

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"


def build_message(tx: NormalizedTransaction) -> str:
    if tx.amount == 0.0 and tx.merchant_name is None:
        return "⚠️ Notifica Revolut non parsata — controlla raw_text in DB"
    sign = "🔴" if tx.amount < 0 else "🟢"
    if tx.status == "verified":
        sign = "🟢"
    merchant = tx.merchant_name or "?"
    amount_str = f"{abs(tx.amount):.2f} {tx.currency}"
    return f"{sign} {'-' if tx.amount < 0 else '+'}{amount_str} · {merchant} [{tx.status}]"


def send_telegram(text: str, *, token: str, chat_id: str) -> None:
    if not token or not chat_id:
        log.warning("Telegram not configured — skipping notification")
        return
    try:
        resp = httpx.post(
            _API.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("Telegram notification sent")
    except Exception as exc:
        log.warning("Failed to send Telegram notification: %s", exc)


def notify_transaction(tx: NormalizedTransaction, *, token: str, chat_id: str) -> None:
    send_telegram(build_message(tx), token=token, chat_id=chat_id)
```

- [ ] **Step 5: Run tests, confirm they pass**

```powershell
uv run pytest tests/test_telegram.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 6: Run full suite**

```powershell
uv run pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/notifications/ tests/test_telegram.py
git commit -m "feat: add Telegram notification module with build_message and notify_transaction"
```

---

## Task 10: Webhook route

**Files:**
- Create: `src/server/__init__.py`
- Create: `src/server/routes/__init__.py`
- Create: `src/server/routes/webhook.py`
- Create: `tests/test_webhook.py`

FastAPI router handling `POST /webhook/tasker`. Validates the `X-Webhook-Secret` header, parses the payload, inserts to DB, sends Telegram. Uses a DB connection injected via FastAPI dependency.

- [ ] **Step 1: Write failing tests in `tests/test_webhook.py`**

```python
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client():
    from src.server.app import create_app
    app = create_app()
    return TestClient(app)


VALID_PAYLOAD = {
    "raw_text": "Hai pagato €12,50 a Esselunga",
    "amount": "12.50",
    "currency": "EUR",
    "merchant": "Esselunga",
    "direction": "debit",
    "device_timestamp": "2026-06-07T14:32:00Z",
    "parse_status": "ok",
}


class TestWebhookEndpoint:
    def test_missing_secret_returns_401(self, client):
        resp = client.post("/webhook/tasker", json=VALID_PAYLOAD)
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self, client):
        resp = client.post(
            "/webhook/tasker",
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": "wrong"},
        )
        assert resp.status_code == 401

    def test_valid_request_returns_200(self, client):
        with (
            patch("src.server.routes.webhook.get_conn") as mock_conn,
            patch("src.server.routes.webhook.insert_transaction", return_value=True),
            patch("src.server.routes.webhook.notify_transaction"),
        ):
            mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.post(
                "/webhook/tasker",
                json=VALID_PAYLOAD,
                headers={"X-Webhook-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_duplicate_returns_200_with_skipped(self, client):
        with (
            patch("src.server.routes.webhook.get_conn") as mock_conn,
            patch("src.server.routes.webhook.insert_transaction", return_value=False),
            patch("src.server.routes.webhook.notify_transaction"),
        ):
            mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.post(
                "/webhook/tasker",
                json=VALID_PAYLOAD,
                headers={"X-Webhook-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    def test_invalid_payload_returns_422(self, client):
        resp = client.post(
            "/webhook/tasker",
            json={"bad": "payload"},
            headers={"X-Webhook-Secret": "test-secret"},
        )
        assert resp.status_code == 422
```

- [ ] **Step 2: Create `src/server/__init__.py` and `src/server/routes/__init__.py`**

Both empty files:
```python
```

- [ ] **Step 3: Create `src/server/routes/webhook.py`**

```python
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import config.settings as settings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from fastapi import APIRouter, Header, HTTPException

from src.ingestion.tasker_parser import parse_tasker_payload
from src.models.tasker import TaskerPayload
from src.notifications.telegram import notify_transaction
from src.storage.db_insert import get_connection, insert_transaction

log = logging.getLogger(__name__)
router = APIRouter()


@contextmanager
def get_conn():
    conn = get_connection(settings.DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


@router.post("/webhook/tasker")
async def tasker_webhook(
    payload: TaskerPayload,
    x_webhook_secret: str | None = Header(default=None),
) -> dict:
    if x_webhook_secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    tx = parse_tasker_payload(payload)

    with get_conn() as conn:
        inserted = insert_transaction(conn, tx)

    if inserted:
        notify_transaction(tx, token=settings.TELEGRAM_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID)
        log.info("Tasker webhook: inserted %s", tx.dedup_hash[:8])
        return {"status": "ok", "dedup_hash": tx.dedup_hash}

    log.info("Tasker webhook: duplicate skipped %s", tx.dedup_hash[:8])
    return {"status": "skipped", "dedup_hash": tx.dedup_hash}
```

- [ ] **Step 4: Create minimal `src/server/app.py`** (needed for tests to import `create_app`)

```python
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI

from src.server.routes.webhook import router as webhook_router

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Revolut Finance Ingestion")
    app.include_router(webhook_router)
    return app


app = create_app()
```

- [ ] **Step 5: Add `WEBHOOK_SECRET=test-secret` to the test environment**

The webhook tests use the hardcoded string `"test-secret"`. Set it so `settings.WEBHOOK_SECRET` returns that value during tests. Add a `conftest.py` at the repo root:

```python
# conftest.py
import os
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_TOKEN", "")
os.environ.setdefault("TELEGRAM_CHAT_ID", "")
os.environ.setdefault("DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance")
```

- [ ] **Step 6: Run tests, confirm they pass**

```powershell
uv run pytest tests/test_webhook.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 7: Run full suite**

```powershell
uv run pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/server/ tests/test_webhook.py conftest.py
git commit -m "feat: add POST /webhook/tasker endpoint with secret auth, DB insert, Telegram notify"
```

---

## Task 11: APScheduler 6h sync job

**Files:**
- Create: `src/server/scheduler.py`

Defines the function that the APScheduler calls every 6 hours. It runs the full EB pipeline (fetch → normalize → reconcile_or_insert) and sends Telegram for new transactions. No separate tests (it orchestrates already-tested modules).

- [ ] **Step 1: Create `src/server/scheduler.py`**

```python
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import config.settings as settings
from src.ingestion.fetch_transactions import fetch_transactions
from src.notifications.telegram import notify_transaction
from src.normalizer.normalize import fetch_ecb_rates, normalize
from src.storage.db_insert import get_connection
from src.storage.reconcile import reconcile_or_insert

log = logging.getLogger(__name__)


def run_eb_sync(days_back: int = 2) -> None:
    """Fetch last N days from Enable Banking, reconcile pending rows, insert new ones."""
    log.info("EB sync started (last %d days)", days_back)
    try:
        raw_by_account = fetch_transactions(days_back=days_back)
    except Exception as exc:
        log.error("EB sync fetch failed: %s", exc)
        return

    ecb_rates = fetch_ecb_rates()
    conn = get_connection(settings.DATABASE_URL)
    try:
        inserted_count = reconciled_count = skipped_count = 0
        for account_id, raw_txs in raw_by_account.items():
            normalized = normalize(raw_txs, account_id, ecb_rates)
            for tx in normalized:
                result = reconcile_or_insert(conn, tx)
                if result.action == "inserted":
                    notify_transaction(
                        tx,
                        token=settings.TELEGRAM_TOKEN,
                        chat_id=settings.TELEGRAM_CHAT_ID,
                    )
                    inserted_count += 1
                elif result.action == "reconciled":
                    reconciled_count += 1
                else:
                    skipped_count += 1
    finally:
        conn.close()

    log.info(
        "EB sync done — inserted: %d, reconciled: %d, skipped: %d",
        inserted_count, reconciled_count, skipped_count,
    )
```

- [ ] **Step 2: Verify import**

```powershell
uv run python -c "from src.server.scheduler import run_eb_sync; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```powershell
git add src/server/scheduler.py
git commit -m "feat: add EB sync scheduler job (reconcile_or_insert + Telegram for new transactions)"
```

---

## Task 12: Wire APScheduler into FastAPI app

**Files:**
- Modify: `src/server/app.py`

Add APScheduler startup/shutdown lifecycle hooks that schedule `run_eb_sync` every 6 hours.

- [ ] **Step 1: Update `src/server/app.py`**

```python
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from src.server.routes.webhook import router as webhook_router
from src.server.scheduler import run_eb_sync

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Revolut Finance Ingestion")
    app.include_router(webhook_router)

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_eb_sync, "interval", hours=6, id="eb_sync")

    @app.on_event("startup")
    def start_scheduler() -> None:
        scheduler.start()
        log.info("APScheduler started — EB sync every 6h")

    @app.on_event("shutdown")
    def stop_scheduler() -> None:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")

    return app


app = create_app()
```

- [ ] **Step 2: Verify app starts without error**

```powershell
uv run python -c "from src.server.app import app; print('App created OK')"
```
Expected: `App created OK`

- [ ] **Step 3: Run full test suite (scheduler must not interfere)**

```powershell
uv run pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```powershell
git add src/server/app.py
git commit -m "feat: wire APScheduler into FastAPI lifecycle — run_eb_sync every 6h"
```

---

## Task 13: Railway deployment config

**Files:**
- Create: `railway.toml`

- [ ] **Step 1: Create `railway.toml`**

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn src.server.app:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
```

- [ ] **Step 2: Add a health endpoint to `src/server/app.py`**

Add after the router include:
```python
from fastapi.responses import JSONResponse

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
```

- [ ] **Step 3: Verify health route**

```powershell
uv run python -c "
from fastapi.testclient import TestClient
from src.server.app import create_app
client = TestClient(create_app())
r = client.get('/health')
assert r.status_code == 200
print('Health check OK')
"
```
Expected: `Health check OK`

- [ ] **Step 4: Commit**

```powershell
git add railway.toml src/server/app.py
git commit -m "feat: add Railway deployment config and /health endpoint"
```

---

## Task 14: Neon migration + Railway deploy (manual steps)

These steps are run once from the terminal, not code changes.

- [ ] **Step 1: Dump local Postgres and restore to Neon**

```powershell
# Replace <neon-connection-string> with your actual Neon URL
docker exec -it financial_tracker-db-1 pg_dump -U user finance > finance_backup.sql
psql "<neon-connection-string>" < finance_backup.sql
```

- [ ] **Step 2: Run schema migration against Neon**

Update `DATABASE_URL` in `config/.env` to point to Neon, then:
```powershell
uv run python scripts/migrate_schema.py
```
Expected: `Migration complete.`

- [ ] **Step 3: Encode the RSA private key as base64**

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("config\private_key.pem")) | clip
```
(copies the base64 string to clipboard)

- [ ] **Step 4: Deploy to Railway**

```powershell
# Install Railway CLI if not present: https://docs.railway.app/develop/cli
railway login
railway init   # link or create project
railway up
```

- [ ] **Step 5: Set env vars in Railway dashboard**

Go to Railway project → Variables → add:
- `DATABASE_URL` — Neon connection string
- `ENABLE_BANKING_APP_ID`
- `ENABLE_BANKING_SESSION_ID`
- `ENABLE_BANKING_ACCESS_TOKEN`
- `ENABLE_BANKING_ACCOUNT_IDS` — JSON array string
- `ENABLE_BANKING_PRIVATE_KEY_B64` — base64 string from Step 3
- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `WEBHOOK_SECRET` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `LOG_LEVEL` = `INFO`

- [ ] **Step 6: Get Telegram chat ID**

1. Create bot via `@BotFather` → `/newbot` → get token
2. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in browser
3. Send `/start` to the bot from your Telegram account
4. Refresh the URL — copy `chat.id` from the response

- [ ] **Step 7: Verify end-to-end**

After Railway deploy completes:
```powershell
# Replace with your Railway URL
curl -X POST https://<railway-url>/webhook/tasker `
  -H "Content-Type: application/json" `
  -H "X-Webhook-Secret: <your-secret>" `
  -d '{"raw_text":"test","amount":"1.00","currency":"EUR","merchant":"Test","direction":"debit","device_timestamp":"2026-06-07T15:00:00Z","parse_status":"ok"}'
```
Expected: `{"status":"ok","dedup_hash":"..."}` and a Telegram notification on your phone.

---

## Task 15: Tasker profile setup (on Android)

These steps are done on the Android device.

- [ ] **Step 1: Create a new Tasker Profile**

- Trigger: **Event → App → Notification → Package: com.revolut.revolut**

- [ ] **Step 2: Create the Task with these actions in order**

Action 1 — **Variable Set**:
- Name: `%notif_text`
- To: `%evtprm3` (notification text body; adjust to `%evtprm2` for title if needed)

Action 2 — **Variable Search Replace** (parse amount):
- Variable: `%notif_text`
- Search: `[€]([0-9]+[.,][0-9]{2})` (regex)
- Store Matches In: `%amount_raw`

Action 3 — **Variable Set**:
- Name: `%amount_clean`
- To: `%amount_raw1` → then replace `,` with `.` via another Variable Search Replace

Action 4 — **Variable Search Replace** (parse merchant for "a NomeMerchant"):
- Variable: `%notif_text`
- Search: `a (.+)$`
- Store Matches In: `%merchant`

Action 5 — **HTTP Request**:
- Method: POST
- URL: `https://<railway-url>/webhook/tasker`
- Headers: `X-Webhook-Secret: <your-secret>`
- Body (JSON):
```json
{
  "raw_text": "%notif_text",
  "amount": "%amount_clean",
  "currency": "EUR",
  "merchant": "%merchant1",
  "direction": "debit",
  "device_timestamp": "%TIMES",
  "parse_status": "%IF %amount_clean ~ [0-9]* ok ELSE failed"
}
```

**Note:** The exact regex patterns depend on the actual Revolut Italian notification text on your device. Check `Tasker → Last App → Notifications` to see the exact text format, then calibrate `%amount_raw` and `%merchant` patterns. The webhook accepts `parse_status=failed` gracefully — it stores the raw notification and sends a warning Telegram — so start with a simple regex and refine.

---

## Self-Review Checklist

After all tasks are complete, verify:

- [ ] `uv run pytest tests/ -v` — all green
- [ ] `uv run ruff check .` — no errors
- [ ] Railway service shows as deployed and healthy (`/health` returns 200)
- [ ] Manual test transaction via curl → DB row with `status=pending`, `source=tasker` → Telegram notification received
- [ ] Wait for EB 6h sync or trigger manually: `uv run python -c "from src.server.scheduler import run_eb_sync; run_eb_sync(days_back=2)"` → new `status=verified` rows → Telegram for genuinely new transactions
