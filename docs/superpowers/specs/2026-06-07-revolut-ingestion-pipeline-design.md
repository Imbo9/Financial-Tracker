# Revolut Ingestion Pipeline — Design Spec

**Date:** 2026-06-07
**Status:** Approved
**Scope:** Two-path transaction ingestion (Tasker real-time + Enable Banking 6h sync) → Neon Postgres + Telegram notifications. No Oracle Cloud dependency.

---

## 1. Architecture Overview

```
Revolut push notification
        ↓
Tasker (Android) — regex parses notification, HTTP POST to Railway
        ↓
POST /webhook/tasker  (FastAPI, always-on on Railway free tier)
        ↓                                    ↑
   Neon Postgres  ←————————————  APScheduler (every 6h)
   (EU Frankfurt)                Enable Banking API fetch
        ↓
   Telegram Bot  ←— fires on new insert (both paths)
```

**Single Railway process:**
- FastAPI serves the webhook endpoint
- APScheduler runs the 6h Enable Banking sync in a background thread
- All existing `src/` modules reused (fetch_transactions, normalizer, db_insert)
- New `src/notifications/telegram.py` for alerts
- New `src/server/app.py` entry point

---

## 2. Data Flow

### Path A — Tasker (real-time, ~2s latency)

1. Revolut fires push notification
2. Tasker profile (trigger: app = `com.revolut.revolut`) applies configurable regex
3. Tasker POSTs JSON to `POST /webhook/tasker` with `X-Webhook-Secret` header
4. Webhook validates secret → parses `TaskerPayload` (Pydantic)
5. `tasker_parser.py` converts payload → `NormalizedTransaction` (`status=pending`, `source=tasker`)
6. Dedup hash computed: `SHA-256('tasker|' + timestamp_minute + '|' + abs(amount) + '|' + currency)`
7. `db_insert.py` upserts → Telegram notification fires immediately

### Path B — Enable Banking 6h sync

1. APScheduler triggers every 6h
2. Existing `fetch_transactions.py` fetches from Enable Banking API
3. `normalize.py` produces `NormalizedTransaction` (`status=verified`, `source=enable_banking`)
4. For each transaction, `reconcile.py` runs first:
   - **Match found** (pending row with same amount + currency + timestamp ±10min): update row → `status=verified`, `booking_date` corrected, `dedup_hash` replaced with EB hash. No Telegram notification (already sent).
   - **No match**: insert as new `verified` row → Telegram notification fires.

### Parse failure resilience

If Tasker regex fails to parse the notification text, Tasker still POSTs with `parse_status=failed`. The webhook stores the raw text as a `pending` row with `amount=null`, `merchant_name=null`. Telegram sends a warning notification so the user can inspect and adjust the regex.

---

## 3. Shared Data Models (Pydantic)

All modules share types from `src/models/`. Both ingestion paths converge on `NormalizedTransaction` before touching the DB.

### `src/models/transaction.py`

```python
class NormalizedTransaction(BaseModel):
    dedup_hash: str
    booking_date: datetime
    amount: Decimal
    currency: str
    eur_amount: Decimal
    description: str | None
    merchant_name: str | None
    account_id: str | None
    is_internal: bool = False
    status: Literal["pending", "verified"] = "verified"
    source: Literal["tasker", "enable_banking"] = "enable_banking"
    source_id: str | None = None
```

### `src/models/tasker.py`

```python
class TaskerPayload(BaseModel):
    raw_text: str
    amount: str | None          # None if parse_status=failed
    currency: str | None
    merchant: str | None
    direction: Literal["debit", "credit"] | None
    device_timestamp: datetime
    parse_status: Literal["ok", "failed"] = "ok"
```

### `src/models/reconciliation.py`

```python
class ReconciliationMatch(BaseModel):
    pending_id: int
    pending_dedup_hash: str

class ReconciliationResult(BaseModel):
    match: ReconciliationMatch | None
    action: Literal["reconciled", "inserted", "skipped"]
```

### `src/models/notification.py`

```python
class TelegramMessage(BaseModel):
    text: str
    parse_mode: Literal["HTML", "Markdown"] = "HTML"
```

---

## 4. Module Structure

```
src/
  models/
    transaction.py       # NormalizedTransaction (refactor existing dataclass → Pydantic)
    tasker.py            # TaskerPayload
    reconciliation.py    # ReconciliationMatch, ReconciliationResult
    notification.py      # TelegramMessage
  ingestion/
    fetch_transactions.py    # existing — unchanged logic, updated return type
    tasker_parser.py         # NEW: TaskerPayload → NormalizedTransaction
  normalizer/
    normalize.py             # existing — updated to return NormalizedTransaction (Pydantic)
    hash.py                  # NEW: dedup hash function extracted, shared by both paths
  storage/
    db_insert.py             # existing — updated to accept NormalizedTransaction (Pydantic)
    reconcile.py             # NEW: find pending match, update to verified
  notifications/
    telegram.py              # NEW: NormalizedTransaction → Telegram message + send
  server/
    app.py                   # NEW: FastAPI app + APScheduler setup
    routes/
      webhook.py             # NEW: POST /webhook/tasker handler
    scheduler.py             # NEW: 6h EB sync job definition
config/
  settings.py                # extended: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_SECRET
```

---

## 5. Schema Migration

Three new columns, all with defaults — existing rows unaffected, migration is safe to run on live data.

```sql
ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS status    TEXT DEFAULT 'verified',
  ADD COLUMN IF NOT EXISTS source    TEXT DEFAULT 'enable_banking',
  ADD COLUMN IF NOT EXISTS source_id TEXT;

-- Index for reconciliation query performance
CREATE INDEX IF NOT EXISTS idx_transactions_pending
  ON transactions (status, booking_date)
  WHERE status = 'pending';
```

---

## 6. Tasker Configuration

**Profile trigger:** Notification received, App = `com.revolut.revolut`

**Task:**
1. Apply regex to `%ntitle` + `%nttext` (configurable in Tasker variable `%revolut_regex`)
2. Extract: amount, currency, merchant, direction
3. HTTP POST to `https://<railway-url>/webhook/tasker`
   - Header: `X-Webhook-Secret: %webhook_secret`
   - Body: JSON with parsed fields + `device_timestamp` + `raw_text` + `parse_status`

**Known notification patterns (to be verified against actual device):**

The regex must handle at minimum:
- Outgoing card payment: amount + merchant name
- Incoming transfer: amount + sender name
- ATM withdrawal: amount only
- Parse failure: send raw text with `parse_status=failed`

The exact Italian notification text (e.g. "Hai pagato €12,50 a Esselunga") must be confirmed from the user's device notification history before finalising the regex. Design the regex as a Tasker variable so it can be updated without changing the webhook code.

---

## 7. Telegram Notifications

| Event | Message |
|---|---|
| Tasker path, parse ok | `🔴 -€12.50 · Esselunga [pending]` |
| Tasker path, parse failed | `⚠️ Notifica Revolut non parsata — controlla raw_text in DB` |
| EB sync, new transaction | `🟢 -€12.50 · Esselunga [verified]` |
| EB sync, reconciled | *(silent — no notification)* |
| EB sync, incoming | `🟢 +€50.00 · Mario Rossi [verified]` |

Bot token and chat ID stored as Railway env vars (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`).

---

## 8. New Environment Variables

| Variable | Where set | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | Railway + local `.env` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Railway + local `.env` | Your personal chat ID |
| `WEBHOOK_SECRET` | Railway + Tasker | Shared static secret for webhook auth |
| `ENABLE_BANKING_PRIVATE_KEY_B64` | Railway | RSA private key, base64-encoded |
| `DATABASE_URL` | Railway | Neon connection string (postgres://…) |

All existing Enable Banking env vars carry over unchanged.

---

## 9. Deployment

1. **Migrate DB to Neon**: `pg_dump` local Docker → Neon EU Frankfurt, update `DATABASE_URL`
2. **Schema migration**: run ALTER TABLE script against Neon
3. **Railway deployment**: `railway login` → `railway up`, set env vars via Railway dashboard
4. **Telegram Bot**: create via @BotFather, get chat ID via `/start` + Bot API
5. **Tasker profile**: install profile, set `%webhook_secret` + `%revolut_regex` variables
6. **Verify**: trigger a test Revolut payment, confirm DB row + Telegram notification

---

## 10. Out of Scope

- AI categorization (remains a separate manual pipeline step)
- Dashboard / web UI
- Multi-bank support beyond Revolut
- Money Manager integration
