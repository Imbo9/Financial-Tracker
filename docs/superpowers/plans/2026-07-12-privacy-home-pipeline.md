# Privacy Migration: Home Pipeline + At-Rest Encryption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **STATUS: PLAN ONLY — user explicitly requested NOT to execute yet (2026-07-12).**
> Railway stays for now: `just-comfort` keeps serving API + webhook. Only `sync-cron` is
> replaced at cutover (Fase C), and only with the user's go.

**Goal:** No cloud provider ever stores readable transaction content: `description` and `merchant_name` are Fernet-encrypted before they reach Neon, Telegram notifications stop carrying amounts/merchants, and the batch pipeline moves from Railway `sync-cron` to the user's home PC (Task Scheduler) so plaintext processing happens only on hardware the user controls.

**Architecture:** Application-layer encryption at the storage boundary (encrypt on INSERT/UPDATE, decrypt on SELECT) with dual-read (Fernet-token prefix detection) so plaintext legacy rows keep working during rollout. Dedup hashes are computed from plaintext at the normalize stage, *before* storage, so all historical hashes stay valid. A `sync_runs` heartbeat table + `/health/sync` endpoint + MacroDroid daily check replace Railway's implicit "cron ran" signal.

**Tech Stack:** Python 3.12, `cryptography.fernet` (already a dependency via pyjwt), psycopg3, Alembic, FastAPI, Windows Task Scheduler (PowerShell registration), MacroDroid.

## Global Constraints

- **Hash stability is sacred**: `eb_dedup_hash` / `tasker_dedup_hash` / `manual_dedup_hash` and `_legacy_amount_repr` are NOT touched. Hashes are computed from plaintext in `normalize.py` / `tasker_parser.py` / `create_manual` before any encryption.
- **Reconciliation matches on `amount + currency + booking_date::date`** — none of these get encrypted, so `_FIND_PENDING_MATCH` is untouched.
- **Fields encrypted at rest**: exactly `transactions.description` and `transactions.merchant_name`. Amounts, dates, currency, category, account_id stay plaintext (SQL stats and filters depend on them).
- **No runtime DDL** — the only schema change (`sync_runs`) goes through Alembic. Alembic runs ONLY against the local Docker DB; production upgrade is a user-gated runbook step.
- **PSD2 limit 4 calls/account/24h** — the cutover sequence in Fase C is ordered so home and Railway crons NEVER both run in the same day.
- **Secrets**: the Fernet key is a `SecretStr` in settings; never logged, never committed. `config/.env.prod` joins the gitignore/hook-protected set.
- Ruff line-length 100; `log = logging.getLogger(__name__)`; no `print()` outside root shims; plain `from fintracker.x import y` imports.
- Every commit passes lefthook (gitleaks + ruff + pyrefly + pytest on staged .py).
- The frontend contract does NOT change: `/v1` responses carry decrypted plaintext exactly as today.

## Current → Target

| Component | Today | After |
|---|---|---|
| Batch pipeline host | Railway `sync-cron` (cloud, sees plaintext) | Home PC, Task Scheduler 4×/day |
| Neon `description`/`merchant_name` | plaintext | Fernet ciphertext (`gAAAAA…`) |
| Neon amounts/dates/categories | plaintext | plaintext (needed for SQL stats) |
| Telegram per-transaction message | `🔴 -12.50 EUR · Esselunga [verified]` | `🔴 Nuova transazione [verified] — dettagli sulla dashboard` |
| API server + `/webhook/tasker` | Railway `just-comfort` | unchanged (Railway, EU) — decrypts on read |
| Cron-health signal | Railway dashboard red runs | `sync_runs` heartbeat + `/health/sync` + MacroDroid daily check |
| Claude categorization | merchant_name → Anthropic | unchanged (decrypted in memory just for the API call) — stricter option deferred |

## File Structure

```
Create:
  src/fintracker/security/__init__.py        (empty package marker)
  src/fintracker/security/crypto.py          encrypt_field / decrypt_field, Fernet singleton
  scripts/encrypt_backfill.py                one-shot encrypt/decrypt of historical rows
  scripts/run_pipeline_home.ps1              home cron wrapper (env file, logging)
  scripts/register_home_cron.ps1             Task Scheduler registration (4 daily triggers)
  migrations/versions/0002_sync_runs.py      heartbeat table
  tests/test_crypto.py
Modify:
  src/fintracker/settings.py                 DATA_ENCRYPTION_KEY, TELEGRAM_DETAIL, FINTRACKER_ENV_FILE override
  src/fintracker/storage/db_insert.py        encrypted_row() choke point
  src/fintracker/storage/reconcile.py        use encrypted_row(); encrypt merchant in UPDATEs
  src/fintracker/server/services/transactions.py  decrypt on read; Python-side search; encrypt create_manual
  src/fintracker/categorizer/categorize.py   decrypt merchant before Claude call
  src/fintracker/notifications/telegram.py   detail="minimal" message
  src/fintracker/sync/eb_sync.py             pass detail; write sync_runs heartbeat
  src/fintracker/server/routes/webhook.py    pass detail
  src/fintracker/server/app.py               /health/sync endpoint
  tests/conftest.py                          DATA_ENCRYPTION_KEY test key
  tests/test_telegram.py                     minimal-message cases
  tests/integration/test_reconcile_pg.py     decrypt-aware assertions
  .gitignore                                 config/.env.prod, logs/
Local-only (not committed):
  .claude settings + protect hook            add config/.env.prod to deny/protect patterns
  CLAUDE.md                                  invariants + architecture updates (gitignored file)
```

Readers/writers of the two encrypted fields (verified by grep, 2026-07-12): writes go through `db_insert.INSERT_SQL` (pipeline, webhook, reconcile step 3, create_manual) and `reconcile` UPDATEs; reads are `services/transactions.py` (list + RETURNING) and `categorizer/categorize.py`. `stats.py` and `accounts.py` never touch them.

---

## Fase A — Code (Tasks 1–7, committable independently, no prod impact until deployed)

### Task 1: Settings — key, detail level, env-file override

**Files:**
- Modify: `src/fintracker/settings.py`
- Test: `tests/test_settings.py` (append), `tests/conftest.py`

**Interfaces:**
- Produces: `settings.DATA_ENCRYPTION_KEY: SecretStr` (default empty), `settings.TELEGRAM_DETAIL: Literal["full","minimal"]` (default `"minimal"`), env var `FINTRACKER_ENV_FILE` overriding which env file Settings loads. `validate_server_settings()` also requires `DATA_ENCRYPTION_KEY`.

- [ ] **Step 1: conftest test key** — append to `tests/conftest.py` (before any settings import, with the other setdefaults; add `import base64` at the top). Derived from a readable constant so it is self-evidently not a real secret and gitleaks stays quiet:

```python
# Deterministic Fernet key for tests (32 readable bytes, b64url-encoded)
os.environ.setdefault(
    "DATA_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(b"unit-test-key-unit-test-key-32b!").decode(),
)
```

- [ ] **Step 2: failing tests** — append to `tests/test_settings.py`:

```python
def test_data_encryption_key_loaded_from_env():
    from fintracker.settings import settings

    assert settings.DATA_ENCRYPTION_KEY.get_secret_value() != ""


def test_telegram_detail_defaults_minimal():
    from fintracker.settings import settings

    assert settings.TELEGRAM_DETAIL == "minimal"


def test_validate_server_settings_requires_encryption_key(monkeypatch):
    from pydantic import SecretStr

    from fintracker.settings import settings

    monkeypatch.setattr(settings, "DATA_ENCRYPTION_KEY", SecretStr(""))
    with pytest.raises(OSError, match="DATA_ENCRYPTION_KEY"):
        settings.validate_server_settings()
```

(`import pytest` already present in that file; add if missing.)

- [ ] **Step 3: run** `uv run pytest tests/test_settings.py -q` — expected: new tests FAIL (unknown field / attribute).

- [ ] **Step 4: implement** in `src/fintracker/settings.py`:

Add `import os` to the imports. Change `model_config` to:

```python
    model_config = SettingsConfigDict(
        # FINTRACKER_ENV_FILE lets the home cron point at config/.env.prod without touching dev's .env
        env_file=os.environ.get("FINTRACKER_ENV_FILE", str(ROOT / "config" / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )
```

After the `ANTHROPIC_API_KEY` field add:

```python
    # Data-at-rest encryption (Fernet). Generate:
    # uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    DATA_ENCRYPTION_KEY: SecretStr = SecretStr("")
```

After `TELEGRAM_CHAT_ID` add:

```python
    # "minimal" hides amount/merchant in notifications — the Bot API is not E2E
    TELEGRAM_DETAIL: Literal["full", "minimal"] = "minimal"
```

In `validate_server_settings`, add to the checked dict:

```python
                "DATA_ENCRYPTION_KEY": self.DATA_ENCRYPTION_KEY.get_secret_value(),
```

- [ ] **Step 5: run** `uv run pytest tests/test_settings.py -q` — expected: PASS. Then full suite `uv run pytest -q` — expected: 157+ passed.
- [ ] **Step 6: commit** — `git commit -m "feat: settings for at-rest encryption key, telegram detail, env-file override"`

### Task 2: Crypto module

**Files:**
- Create: `src/fintracker/security/__init__.py` (empty), `src/fintracker/security/crypto.py`
- Test: `tests/test_crypto.py`

**Interfaces:**
- Produces: `encrypt_field(value: str | None) -> str | None`, `decrypt_field(value: str | None) -> str | None`, `_TOKEN_PREFIX = "gAAAAA"`. Dual-read: `decrypt_field` returns non-token values unchanged (legacy plaintext). Missing key → `OSError` on first use.

- [ ] **Step 1: failing tests** — `tests/test_crypto.py`:

```python
import pytest
from pydantic import SecretStr

from fintracker.security import crypto
from fintracker.security.crypto import decrypt_field, encrypt_field


def test_roundtrip():
    token = encrypt_field("Esselunga Milano")
    assert token is not None and token.startswith("gAAAAA")
    assert decrypt_field(token) == "Esselunga Milano"


def test_none_passthrough():
    assert encrypt_field(None) is None
    assert decrypt_field(None) is None


def test_legacy_plaintext_passthrough():
    assert decrypt_field("Esselunga Milano") == "Esselunga Milano"


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(crypto.settings, "DATA_ENCRYPTION_KEY", SecretStr(""))
    crypto._fernet.cache_clear()
    with pytest.raises(OSError, match="DATA_ENCRYPTION_KEY"):
        encrypt_field("x")
    crypto._fernet.cache_clear()
```

- [ ] **Step 2: run** `uv run pytest tests/test_crypto.py -q` — expected: FAIL (module not found).
- [ ] **Step 3: implement** — `src/fintracker/security/crypto.py`:

```python
import logging
from functools import lru_cache

from cryptography.fernet import Fernet

from fintracker.settings import settings

log = logging.getLogger(__name__)

# Fernet tokens are versioned (first byte 0x80 → base64 "gAAAAA"): rows without this
# prefix are legacy plaintext from before the backfill and pass through unchanged.
_TOKEN_PREFIX = "gAAAAA"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.DATA_ENCRYPTION_KEY.get_secret_value()
    if not key:
        raise OSError("DATA_ENCRYPTION_KEY not set — required for data-at-rest encryption")
    return Fernet(key)


def encrypt_field(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_field(value: str | None) -> str | None:
    # Decrypt errors on a token-prefixed value propagate: corruption must be loud.
    if value is None or not value.startswith(_TOKEN_PREFIX):
        return value
    return _fernet().decrypt(value.encode()).decode()
```

- [ ] **Step 4: run** `uv run pytest tests/test_crypto.py -q` — expected: 4 PASS.
- [ ] **Step 5: commit** — `git commit -m "feat: Fernet field encryption with dual-read for legacy plaintext"`

### Task 3: Write path — encrypt on INSERT/UPDATE

**Files:**
- Modify: `src/fintracker/storage/db_insert.py`, `src/fintracker/storage/reconcile.py`
- Test: `tests/test_reconcile.py` (unchanged — mock cursor), `tests/integration/test_reconcile_pg.py`

**Interfaces:**
- Consumes: `encrypt_field` from Task 2.
- Produces: `db_insert.encrypted_row(tx: NormalizedTransaction) -> dict` — model_dump with `description`/`merchant_name` encrypted. All INSERT_SQL executions go through it.

- [ ] **Step 1: implement `encrypted_row`** in `src/fintracker/storage/db_insert.py` (after INSERT_SQL):

```python
from fintracker.security.crypto import encrypt_field

_ENCRYPTED_FIELDS = ("description", "merchant_name")


def encrypted_row(tx: NormalizedTransaction) -> dict:
    row = tx.model_dump()
    for field in _ENCRYPTED_FIELDS:
        row[field] = encrypt_field(row[field])
    return row
```

Then switch both call sites in the same file: `rows = [encrypted_row(t) for t in transactions]` and `cur.execute(INSERT_SQL, encrypted_row(tx))`.

- [ ] **Step 2: switch reconcile** in `src/fintracker/storage/reconcile.py`: import `from fintracker.security.crypto import encrypt_field` and `from fintracker.storage.db_insert import INSERT_SQL as _INSERT, encrypted_row`; step-3 insert becomes `cur.execute(_INSERT, encrypted_row(tx))`; in BOTH `_UPDATE_TO_VERIFIED` executions replace the `tx.merchant_name` parameter with `encrypt_field(tx.merchant_name)`.
- [ ] **Step 3: run unit suite** `uv run pytest -q` — expected: PASS (conftest provides the key; mock-based reconcile test is parameter-agnostic).
- [ ] **Step 4: integration proof** — `docker compose up db -d`, then `uv run pytest -m integration -q`. Any assertion in `tests/integration/test_reconcile_pg.py` that reads `merchant_name`/`description` straight from a SELECT now sees a `gAAAAA…` token. Update each occurrence (find them: `grep -n "merchant_name\|description" tests/integration/test_reconcile_pg.py`) with the pattern:

```python
from fintracker.security.crypto import decrypt_field
# before: assert row["merchant_name"] == "Esselunga"
assert decrypt_field(row["merchant_name"]) == "Esselunga"
```

Add one explicit at-rest assertion to the fresh-insert test:

```python
    assert row["merchant_name"].startswith("gAAAAA")  # ciphertext at rest
```

- [ ] **Step 5: run** `uv run pytest -m integration -q` — expected: PASS.
- [ ] **Step 6: commit** — `git commit -m "feat: encrypt description/merchant_name at the storage write boundary"`

### Task 4: Read path — decrypt in services and categorizer

**Files:**
- Modify: `src/fintracker/server/services/transactions.py`, `src/fintracker/categorizer/categorize.py`
- Test: `tests/test_services.py` (adjust if it asserts raw fields), `tests/test_api_routes.py` (should pass unchanged — API returns plaintext)

**Interfaces:**
- Consumes: `decrypt_field`, `encrypt_field`.
- Produces: `list_transactions` returns decrypted rows; `search` filters Python-side; `create_manual` stores ciphertext, returns plaintext.

- [ ] **Step 1: rewrite `list_transactions`** in `src/fintracker/server/services/transactions.py` — add imports `from fintracker.security.crypto import decrypt_field, encrypt_field` and a row helper, replace the function body:

```python
def _decrypt_row(row: dict) -> dict:
    row["description"] = decrypt_field(row["description"])
    row["merchant_name"] = decrypt_field(row["merchant_name"])
    return row


def list_transactions(
    conn,
    *,
    page: int,
    page_size: int,
    days_back: int,
    category: str | None,
    direction: str | None,
    search: str | None,
) -> dict:
    conditions = ["booking_date >= NOW() - (%s * INTERVAL '1 day')"]
    params: list[Any] = [days_back]
    if category:
        conditions.append("category = %s")
        params.append(category)
    if direction == "income":
        conditions.append("amount > 0")
    elif direction == "expense":
        conditions.append("amount < 0")
    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with conn.cursor(row_factory=dict_row) as cur:
        if search:
            # Encrypted columns can't be ILIKEd in SQL — decrypt and filter here.
            # Single-user volume (thousands of rows per window) keeps this cheap.
            cur.execute(
                f"SELECT {_SELECT_COLS} FROM real_transactions WHERE {where}"
                " ORDER BY booking_date DESC",
                params,
            )
            rows = [_decrypt_row(dict(r)) for r in cur.fetchall()]
            needle = search.lower()
            rows = [
                r
                for r in rows
                if needle in (r["merchant_name"] or "").lower()
                or needle in (r["description"] or "").lower()
            ]
            total = len(rows)
            rows = rows[offset : offset + page_size]
        else:
            cur.execute(f"SELECT COUNT(*) AS total FROM real_transactions WHERE {where}", params)
            total = cur.fetchone()["total"]
            cur.execute(
                f"""SELECT {_SELECT_COLS}
                    FROM real_transactions
                    WHERE {where}
                    ORDER BY booking_date DESC
                    LIMIT %s OFFSET %s""",
                [*params, page_size, offset],
            )
            rows = [_decrypt_row(dict(r)) for r in cur.fetchall()]

    return {"items": rows, "total": total, "page": page, "page_size": page_size}
```

- [ ] **Step 2: `create_manual`** — encrypt before insert, decrypt the RETURNING row:

```python
def create_manual(conn, data: dict) -> dict | None:
    """Insert a manual transaction. Returns the row, or None on duplicate."""
    data = {
        **data,
        "dedup_hash": manual_dedup_hash(
            data["booking_date"].isoformat(), data["amount"], data["currency"]
        ),
        "description": encrypt_field(data["description"]),
        "merchant_name": encrypt_field(data["merchant_name"]),
        "is_internal": False,
        "status": "verified",
        "source": "manual",
        "source_id": None,
    }
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_INSERT_RETURN, data)
        row = cur.fetchone()
    conn.commit()
    return _decrypt_row(dict(row)) if row else None
```

(dedup_hash is computed from `booking_date+amount+currency` only — encryption cannot affect it.)

- [ ] **Step 3: categorizer** in `src/fintracker/categorizer/categorize.py` — import `from fintracker.security.crypto import decrypt_field`; the merchant list becomes:

```python
        merchants = [decrypt_field(r[1]) or "Unknown" for r in batch]
```

- [ ] **Step 4: run** `uv run pytest -q` — expected: PASS (fix any `test_services.py` fake-row assertions with the Task 3 decrypt pattern if they feed raw strings — plaintext fake rows still pass thanks to dual-read).
- [ ] **Step 5: commit** — `git commit -m "feat: decrypt at the read boundary; python-side search over encrypted fields"`

### Task 5: Minimal Telegram notifications

**Files:**
- Modify: `src/fintracker/notifications/telegram.py`, `src/fintracker/sync/eb_sync.py`, `src/fintracker/server/routes/webhook.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Produces: `build_message(tx, *, detail: str = "minimal")`, `notify_transaction(tx, *, token, chat_id, detail: str = "minimal")`. Both existing callers pass `detail=settings.TELEGRAM_DETAIL`.

- [ ] **Step 1: failing tests** — append to `tests/test_telegram.py`:

```python
def test_minimal_message_hides_amount_and_merchant():
    tx = _tx(amount=-12.50, merchant_name="Esselunga")  # reuse the file's tx factory
    msg = build_message(tx, detail="minimal")
    assert "Esselunga" not in msg and "12.50" not in msg
    assert msg.startswith("🔴")


def test_full_message_keeps_details():
    tx = _tx(amount=-12.50, merchant_name="Esselunga")
    msg = build_message(tx, detail="full")
    assert "Esselunga" in msg and "12.50" in msg
```

(If the file has no `_tx` factory, build a `NormalizedTransaction` inline with the same fields as `tests/test_reconcile.py::_tx`.)

- [ ] **Step 2: run** `uv run pytest tests/test_telegram.py -q` — expected: FAIL (unexpected keyword `detail`).
- [ ] **Step 3: implement** in `telegram.py`:

```python
def build_message(tx: NormalizedTransaction, *, detail: str = "minimal") -> str:
    if tx.amount == 0.0 and tx.merchant_name is None:
        return "⚠️ Notifica Revolut non parsata — controlla raw_text in DB"
    sign = "🔴" if tx.amount < 0 else "🟢"
    if detail != "full":
        # Bot API is not E2E: keep amounts and merchants off the wire
        return f"{sign} Nuova transazione [{tx.status}] — dettagli sulla dashboard"
    merchant = tx.merchant_name or "?"
    amount_str = f"{abs(tx.amount):.2f} {tx.currency}"
    return f"{sign} {'-' if tx.amount < 0 else '+'}{amount_str} · {merchant} [{tx.status}]"


def notify_transaction(
    tx: NormalizedTransaction, *, token: str, chat_id: str, detail: str = "minimal"
) -> None:
    send_telegram(build_message(tx, detail=detail), token=token, chat_id=chat_id)
```

Update the two callers to pass `detail=settings.TELEGRAM_DETAIL`: `eb_sync.py` (inside the inserted-branch `notify_transaction(...)`) and `server/routes/webhook.py:48`.

- [ ] **Step 4: run** `uv run pytest -q` — expected: PASS.
- [ ] **Step 5: commit** — `git commit -m "feat: minimal Telegram messages — no amounts/merchants over Bot API"`

### Task 6: Backfill script (encrypt / decrypt historical rows)

**Files:**
- Create: `scripts/encrypt_backfill.py`
- Test: `tests/integration/test_encrypt_backfill_pg.py`

**Interfaces:**
- Consumes: `encrypt_field`, `decrypt_field`, `_TOKEN_PREFIX`, `direct_connection`.
- Produces: CLI `uv run python scripts/encrypt_backfill.py [--decrypt] [--dry-run]`, idempotent both directions.

- [ ] **Step 1: implement** — `scripts/encrypt_backfill.py`:

```python
"""One-shot at-rest encryption of transactions.description / merchant_name.

Idempotent: already-encrypted values (Fernet "gAAAAA" prefix) are skipped.
--decrypt reverses it (rollback). --dry-run only reports counts.

Usage:
    uv run python scripts/encrypt_backfill.py --dry-run
    uv run python scripts/encrypt_backfill.py
    uv run python scripts/encrypt_backfill.py --decrypt
"""

import argparse
import logging

from fintracker.security.crypto import _TOKEN_PREFIX, decrypt_field, encrypt_field
from fintracker.settings import setup_logging
from fintracker.storage.db import direct_connection

setup_logging()
log = logging.getLogger("encrypt_backfill")


def _transform(value: str | None, *, decrypt: bool) -> str | None:
    if value is None:
        return None
    if decrypt:
        return decrypt_field(value)
    return value if value.startswith(_TOKEN_PREFIX) else encrypt_field(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decrypt", action="store_true", help="Reverse: decrypt back to plaintext")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()

    conn = direct_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, description, merchant_name FROM transactions ORDER BY id")
            rows = cur.fetchall()

        updates = []
        for row_id, desc, merch in rows:
            new_desc = _transform(desc, decrypt=args.decrypt)
            new_merch = _transform(merch, decrypt=args.decrypt)
            if (new_desc, new_merch) != (desc, merch):
                updates.append((new_desc, new_merch, row_id))

        log.info("%d/%d rows need updating (%s)", len(updates), len(rows),
                 "decrypt" if args.decrypt else "encrypt")
        if args.dry_run or not updates:
            return
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE transactions SET description = %s, merchant_name = %s WHERE id = %s",
                updates,
            )
        conn.commit()
        log.info("Done — %d rows updated", len(updates))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: integration test** — `tests/integration/test_encrypt_backfill_pg.py` (reuse the connection/truncate fixture style of `tests/integration/test_reconcile_pg.py` — same `pytestmark = pytest.mark.integration` and DB fixture):

```python
import sys

import pytest

from scripts.encrypt_backfill import main as backfill_main

pytestmark = pytest.mark.integration

_SEED = """
INSERT INTO transactions (dedup_hash, booking_date, amount, currency, eur_amount,
                          description, merchant_name)
VALUES ('bf-test-1', '2026-07-01T00:00:00Z', -5, 'EUR', -5, 'plain desc', 'Esselunga'),
       ('bf-test-2', '2026-07-02T00:00:00Z', -7, 'EUR', -7, NULL, 'Amazon')
"""


def _fields(conn) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT description, merchant_name FROM transactions"
            " WHERE dedup_hash LIKE 'bf-test-%' ORDER BY dedup_hash"
        )
        return cur.fetchall()


def test_backfill_encrypts_idempotently_and_reverses(pg_conn, monkeypatch):
    with pg_conn.cursor() as cur:
        cur.execute(_SEED)
    pg_conn.commit()

    monkeypatch.setattr(sys, "argv", ["encrypt_backfill.py"])
    backfill_main()
    encrypted = _fields(pg_conn)
    assert encrypted[0][0].startswith("gAAAAA") and encrypted[0][1].startswith("gAAAAA")
    assert encrypted[1][0] is None and encrypted[1][1].startswith("gAAAAA")

    backfill_main()  # second run: no-op
    assert _fields(pg_conn) == encrypted

    monkeypatch.setattr(sys, "argv", ["encrypt_backfill.py", "--decrypt"])
    backfill_main()
    assert _fields(pg_conn) == [("plain desc", "Esselunga"), (None, "Amazon")]
```

(Adapt the fixture name `pg_conn` to whatever `test_reconcile_pg.py` actually exposes; `scripts/` needs an empty `scripts/__init__.py` — add it — or import via `importlib` if the repo prefers scripts unpackaged.)

- [ ] **Step 3: run** `uv run pytest -m integration -q` — expected: PASS.
- [ ] **Step 4: commit** — `git commit -m "feat: idempotent at-rest encryption backfill script with rollback"`

### Task 7: sync_runs heartbeat + /health/sync

**Files:**
- Create: `migrations/versions/0002_sync_runs.py`
- Modify: `src/fintracker/sync/eb_sync.py`, `src/fintracker/server/app.py`
- Test: `tests/test_eb_sync.py` (heartbeat call), `tests/test_api_routes.py` or new `tests/test_health_sync.py`

**Interfaces:**
- Produces: table `sync_runs(id, ran_at timestamptz default now(), inserted int, reconciled int, skipped int)`; `run_eb_sync` inserts one row per *successful* sync (also when inserted=0 — that's the freshness point; the early-return failure paths write nothing); `GET /health/sync?max_age_hours=26` → 200 `{"status":"ok","last_sync":...}` or 503 `{"status":"stale",...}` (unversioned machine endpoint, no JWT, like `/health`).

- [ ] **Step 1: migration** — `uv run alembic revision -m "sync_runs heartbeat table"`, fill in (verify `down_revision` equals the id shown by `uv run alembic heads` — the 0001 baseline):

```python
def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("inserted", sa.Integer, nullable=False),
        sa.Column("reconciled", sa.Integer, nullable=False),
        sa.Column("skipped", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
```

Apply LOCALLY ONLY: `docker compose up db -d && uv run alembic upgrade head`.

- [ ] **Step 2: heartbeat** — in `run_eb_sync`, right after the account loop (inside the `try`, before `finally`):

```python
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sync_runs (inserted, reconciled, skipped) VALUES (%s, %s, %s)",
                (stats.inserted, stats.reconciled, stats.skipped),
            )
        conn.commit()
```

- [ ] **Step 3: endpoint** — in `create_app()` next to `/health` (`server/app.py:69`), with `from datetime import UTC, datetime, timedelta` and `from fintracker.storage.db import db_conn`:

```python
    @app.get("/health/sync")
    async def health_sync(max_age_hours: int = 26) -> JSONResponse:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT MAX(ran_at) FROM sync_runs")
            last = cur.fetchone()[0]
        stale = last is None or datetime.now(UTC) - last > timedelta(hours=max_age_hours)
        body = {"status": "stale" if stale else "ok",
                "last_sync": last.isoformat() if last else None}
        return JSONResponse(status_code=503 if stale else 200, content=body)
```

- [ ] **Step 4: tests** — append to `tests/test_eb_sync.py` (reusing that file's existing fetch/normalize patching style for the success case):

```python
def test_heartbeat_written_on_success(monkeypatch):
    # arrange exactly like the file's existing happy-path test (patched fetch_transactions
    # returning one account, patched fetch_ecb_rates, MagicMock direct_connection), then:
    executed_sql = [c.args[0] for c in mock_cursor.execute.call_args_list]
    assert any("INSERT INTO sync_runs" in sql for sql in executed_sql)


def test_no_heartbeat_on_fetch_failure(monkeypatch, mock_conn):
    monkeypatch.setattr(
        "fintracker.sync.eb_sync.fetch_transactions",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    run_eb_sync(days_back=2)
    mock_conn.cursor.assert_not_called()  # early return: no DB touch, no heartbeat
```

and a new `tests/test_health_sync.py` using the app TestClient pattern from `tests/test_api_routes.py`:

```python
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch


def _client_with_last_sync(ran_at):
    cur = MagicMock()
    cur.fetchone.return_value = (ran_at,)
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch("fintracker.server.app.db_conn", return_value=ctx)


def test_health_sync_fresh(client):
    with _client_with_last_sync(datetime.now(UTC) - timedelta(hours=1)):
        resp = client.get("/health/sync")
    assert resp.status_code == 200 and resp.json()["status"] == "ok"


def test_health_sync_stale(client):
    with _client_with_last_sync(datetime.now(UTC) - timedelta(hours=48)):
        resp = client.get("/health/sync")
    assert resp.status_code == 503 and resp.json()["status"] == "stale"
```

(`client` fixture: same construction as in `tests/test_api_routes.py`.) Run `uv run pytest -q` — expected: PASS.
- [ ] **Step 5: commit** — `git commit -m "feat: sync_runs heartbeat and /health/sync freshness endpoint"`

---

## Fase B — Home runner (Task 8, still no prod impact)

### Task 8: Task Scheduler wrapper + registration

**Files:**
- Create: `scripts/run_pipeline_home.ps1`, `scripts/register_home_cron.ps1`
- Modify: `.gitignore` (add `config/.env.prod` and `logs/` lines under the credentials block)

- [ ] **Step 1: wrapper** — `scripts/run_pipeline_home.ps1`:

```powershell
# Home cron wrapper: prod env file + append log with 5MB cap. Exit code = pipeline's.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$env:FINTRACKER_ENV_FILE = Join-Path $repo "config\.env.prod"
$logDir = Join-Path $repo "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "home_cron.log"
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 5MB)) { Clear-Content $log }
"=== $(Get-Date -Format o) start ===" | Add-Content $log
& uv run python pipeline.py *>> $log
$code = $LASTEXITCODE
"=== $(Get-Date -Format o) exit $code ===" | Add-Content $log
exit $code
```

(No `--days` flag: parity with Railway — `FETCH_DAYS_BACK` comes from the env file.)

- [ ] **Step 2: registration** — `scripts/register_home_cron.ps1`:

```powershell
# Registers "Fintracker Sync" — 4 daily runs, catches up missed ones at wake/boot.
$wrapper = Join-Path $PSScriptRoot "run_pipeline_home.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wrapper`""
$triggers = "00:00", "06:00", "12:00", "18:00" | ForEach-Object {
    New-ScheduledTaskTrigger -Daily -At $_
}
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Fintracker Sync" -Action $action `
    -Trigger $triggers -Settings $settings -Force
Write-Host "Registered. Test with: Start-ScheduledTask -TaskName 'Fintracker Sync'"
```

Local times (Rome, DST-following) intentionally replace the fixed-UTC Railway schedule — the banking day is a Rome-time concept. `-StartWhenAvailable` reruns a missed slot when the PC comes back; the dedup hash makes any overlap harmless.

- [ ] **Step 3: gitignore** — append `config/.env.prod` and `logs/` to `.gitignore` (note: `config/.env.example` must STAY tracked, so no wildcard).
- [ ] **Step 4: dry test WITHOUT touching prod** — create `config/.env.prod` as a copy of local `.env` (still pointing at the local Docker DB), run `powershell -File scripts/run_pipeline_home.ps1` manually with `--skip-fetch` temporarily appended in the wrapper (or set `SKIP` by editing the line to `pipeline.py --skip-fetch --skip-categorize`), verify `logs/home_cron.log` shows "Pipeline complete" and exit 0, then restore the wrapper line. This proves wrapper + env-file plumbing without an EB call.
- [ ] **Step 5: local hardening (not committed)** — add `config/.env.prod` to the `.claude` protect-hook patterns and to the settings deny-read list, mirroring the existing `config/.env` entries.
- [ ] **Step 6: commit** — `git commit -m "feat: home Task Scheduler runner for the sync pipeline"`

---

## Fase C — Production runbook (USER-GATED — every step needs Filippo's explicit go)

Ordered to be PSD2-safe and zero-downtime. Steps C1–C4 can happen any evening; C5 is the cutover.

- [ ] **C0 — Key generation & backup (user)**: run `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, store the key in the password manager FIRST (losing it = ciphertext unrecoverable), then add `DATA_ENCRYPTION_KEY=<key>` to local `config/.env` and to `config/.env.prod`.
- [ ] **C1 — Railway env (user or agent with approval)**: add the SAME `DATA_ENCRYPTION_KEY` to `just-comfort` variables (dashboard → Variables). Do NOT deploy yet — the new code requires it at boot (`validate_server_settings`).
- [ ] **C2 — Prod schema**: `railway run --service just-comfort -- uv run alembic upgrade head` (user runs it, same pattern as the 0001 stamp) → creates `sync_runs` on Neon.
- [ ] **C3 — Deploy code**: `git push` already auto-deploys both Railway services. Verify: `/health` 200, `/health/sync` returns 503 `stale` (no heartbeat rows yet — expected), dashboard still renders old plaintext rows (dual-read).
- [ ] **C4 — Backfill Neon (user-gated, from home)**: `$env:FINTRACKER_ENV_FILE="config\.env.prod"; uv run python scripts/encrypt_backfill.py --dry-run` → review count → run without `--dry-run`. Spot-check: dashboard still shows merchant names (decrypted by the server); `SELECT merchant_name FROM transactions LIMIT 3` on Neon shows `gAAAAA…`.
- [ ] **C5 — Cutover (PSD2-safe order)**: right AFTER a scheduled Railway run completes (e.g. the 12:00 Rome run), (a) clear the Cron Schedule on `sync-cron` (dashboard → Settings → Cron Schedule → empty — service kept as rollback), (b) run `scripts/register_home_cron.ps1` on the PC. The home task takes the next slot (18:00). Zero double-fetch days.
- [ ] **C6 — Watchdog**: MacroDroid macro, daily ~10:00: HTTP GET `https://just-comfort-production-4c96.up.railway.app/health/sync` → if response ≠ 200 → phone notification "sync stantio — accendi il PC / controlla logs/home_cron.log".
- [ ] **C7 — Observe 48h**: 8 green entries in `logs/home_cron.log`, `/health/sync` 200, Telegram minimal messages arriving.
- [ ] **C8 — After 14 green days**: delete the `sync-cron` service (user-gated); update CLAUDE.md (architecture diagram, invariants: encrypted-at-rest fields + "never log decrypted values", commands: home cron), memory files, and `.env.example` (add `DATA_ENCRYPTION_KEY=`, `TELEGRAM_DETAIL=`).

## Rollback

- **Cron**: re-set `0 22,4,10,16 * * *` on `sync-cron` (dashboard) + `Disable-ScheduledTask -TaskName "Fintracker Sync"`. Never both enabled across the same day (PSD2).
- **Encryption**: `scripts/encrypt_backfill.py --decrypt` (key still required), then revert the write-path commits. Dual-read means a half-rolled-back state is always readable.
- **Telegram**: set `TELEGRAM_DETAIL=full` — no deploy needed beyond a service restart.

## Open decisions (defaults chosen, flag to Filippo before executing)

1. `TELEGRAM_DETAIL` default `minimal` — set `full` in env to keep today's messages.
2. `/health/sync` threshold 26h — tolerates a PC off for a full day before alarming.
3. The 🔴/🟢 sign still leaks transaction *direction* in minimal mode — kept for usability; drop the emoji for maximum strictness.
4. Claude categorization still sends decrypted merchant names to Anthropic (US) — unchanged in this plan; a local-rules categorizer is a separate future plan if wanted.
5. `embedding vector(1536)` column: unused and NULL today, left alone; if embeddings are ever populated they would leak merchant semantics — revisit then.

## Effort estimate

Fase A ≈ 3–4h, Fase B ≈ 1h, Fase C ≈ 1h of supervised steps spread over a day (plus 14-day observation window before C8).
