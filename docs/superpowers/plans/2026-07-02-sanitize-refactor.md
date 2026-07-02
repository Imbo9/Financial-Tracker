# Sanitize Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all duplication and dead code, fix the cron-reconciliation data-integrity bug, and add the four approved operational criticals (login rate limiting, ECB cache TTL, sync-failure alert, session-expiry warning).

**Architecture:** Unify the two divergent EB sync implementations (`pipeline.py` insert-only path vs `scheduler.run_eb_sync` reconcile path) into one shared module `src/sync/eb_sync.py` used by both the Railway cron and `POST /sync`. Consolidate SQL/connection helpers in `src/storage/db_insert.py`. Everything else is deletion of dead code and small extractions.

**Tech Stack:** Python 3 / FastAPI / psycopg2 / pytest / ruff (line-length 100, rules E,F,I) — React/TS/Vite frontend.

**User decisions already made (2026-07-02):**
- Cron notifies Telegram for newly inserted transactions (same as `/sync`). No notify flag.
- All four operational criticals in scope.
- Commit existing uncommitted work first, as separate commits.

**Baseline:** `ruff check .` passes, 124 tests pass. Every task must end green.

---

### Task 0: Commit existing finished work

The working tree has a finished security-hardening diff plus the untracked frontend. Commit as three logical units before refactoring.

**Files:** no code changes — git only. Plus one local (uncommitted) hygiene edit.

- [ ] **Step 1: Commit the security hardening diff**

```bash
git add src/server/app.py src/server/routes/api.py src/server/routes/webhook.py src/storage/db_insert.py src/storage/reconcile.py .gitignore docs/PHASE2.md
git commit -m "security: parameterize INTERVAL/LIMIT queries, sanitize webhook 422 detail, share INSERT_SQL, configure server logging"
```

- [ ] **Step 2: Commit the frontend and the MCP wrapper script**

```bash
git add frontend/ scripts/codex_mcp.py
git commit -m "feat: add Fimbook React frontend (deployed on Vercel) and codex MCP env wrapper"
```

- [ ] **Step 3: Commit the docs**

```bash
git add docs/INSIGHTS.md docs/superpowers/plans/2026-06-08-api-routes-frontend-wiring.md docs/superpowers/plans/2026-06-10-guidelines-review-skill.md docs/superpowers/plans/2026-07-02-sanitize-refactor.md
git commit -m "docs: add project insights and pending plan documents"
```

- [ ] **Step 4: Local hygiene (do NOT commit — file is gitignored)**

Edit `frontend/.env.local`: delete the line `VITE_API_TOKEN=...` (dead credential from the removed API_SECRET auth). Keep `VITE_API_URL=/api`.

- [ ] **Step 5: Verify clean tree**

Run: `git status --porcelain`
Expected: empty output.

---

### Task 1: Shared DB connection context manager

`webhook.py:23-29` (`get_conn`) and `api.py:59-65` (`_get_conn`) are identical context managers; `src/sync/eb_sync.py` (Task 6) will be a third caller.

**Files:**
- Modify: `src/storage/db_insert.py` (add `connection`)
- Modify: `src/server/routes/api.py:59-65` and all `_get_conn()` call sites
- Modify: `src/server/routes/webhook.py:23-29` and its call site
- Test: `tests/test_api_routes.py`, `tests/test_webhook.py` (patch targets move)

- [ ] **Step 1: Add `connection` to `src/storage/db_insert.py`**

Add `from contextlib import contextmanager` to the imports, then below `get_connection`:

```python
@contextmanager
def connection(database_url: str):
    """Context-managed psycopg2 connection — closes on exit."""
    conn = get_connection(database_url)
    try:
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 2: Use it in `api.py`**

Delete the local `_get_conn` definition and the now-unused `from contextlib import contextmanager` import. Change the import line to:

```python
from src.storage.db_insert import connection, get_connection
```

(keep `get_connection` imported only if still referenced — it will not be; then import just `connection`). Replace all four `with _get_conn() as conn:` with:

```python
    with connection(settings.DATABASE_URL) as conn:
```

- [ ] **Step 3: Use it in `webhook.py`**

Delete the local `get_conn` definition and the `contextmanager` import. Change the storage import to:

```python
from src.storage.db_insert import connection, insert_transaction
```

Replace `with get_conn() as conn:` with `with connection(settings.DATABASE_URL) as conn:`.

- [ ] **Step 4: Update test patch targets**

In `tests/test_api_routes.py` replace every occurrence (7×) of the patch target:
- old: `"src.server.routes.api.get_connection"`
- new: `"src.storage.db_insert.get_connection"`

(The shared `connection()` calls `get_connection` inside `db_insert`, so patching there feeds the same mock conn through.)

In `tests/test_webhook.py` replace (2×):
- old: `patch("src.server.routes.webhook.get_conn") as mock_conn,`
- new: `patch("src.server.routes.webhook.connection") as mock_conn,`

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_api_routes.py tests/test_webhook.py -q`
Expected: all pass.

- [ ] **Step 6: Full gate + commit**

```bash
uv run ruff check .
uv run pytest -q
git add src/storage/db_insert.py src/server/routes/api.py src/server/routes/webhook.py tests/test_api_routes.py tests/test_webhook.py
git commit -m "refactor: single shared DB connection context manager in db_insert"
```

---

### Task 2: Compose `_INSERT_RETURN` from `INSERT_SQL`

`api.py:22-35` re-lists all 14 columns already defined in `db_insert.INSERT_SQL`.

**Files:**
- Modify: `src/server/routes/api.py:22-35`

- [ ] **Step 1: Replace the duplicated statement**

Add `INSERT_SQL` to the db_insert import in `api.py`:

```python
from src.storage.db_insert import INSERT_SQL, connection
```

Replace the whole `_INSERT_RETURN = """..."""` block with:

```python
_INSERT_RETURN = INSERT_SQL + """
RETURNING id, dedup_hash, booking_date, amount, currency, eur_amount,
          description, merchant_name, account_id, is_internal,
          category, subcategory, status, source, created_at
"""
```

- [ ] **Step 2: Run tests + commit**

```bash
uv run pytest tests/test_api_routes.py -q
uv run ruff check .
git add src/server/routes/api.py
git commit -m "refactor: derive _INSERT_RETURN from shared INSERT_SQL"
```

---

### Task 3: Move `reconcile.py` mid-file import to the top

**Files:**
- Modify: `src/storage/reconcile.py:51`

- [ ] **Step 1: Relocate the import**

Delete line 51 (`from src.storage.db_insert import INSERT_SQL as _INSERT  # noqa: E402`) and place it with the other project imports at the top (after the `sys.path.insert` line, alongside the models imports):

```python
from src.models.reconciliation import ReconciliationMatch, ReconciliationResult
from src.models.transaction import NormalizedTransaction
from src.storage.db_insert import INSERT_SQL as _INSERT
```

- [ ] **Step 2: Run tests + commit**

```bash
uv run pytest tests/test_reconcile.py -q
uv run ruff check .
git add src/storage/reconcile.py
git commit -m "refactor: move INSERT_SQL import to top of reconcile.py"
```

---

### Task 4: Delete dead `TelegramMessage` model

`src/models/notification.py` defines `TelegramMessage`, imported nowhere (verified by grep — only docs mention it).

**Files:**
- Delete: `src/models/notification.py`

- [ ] **Step 1: Confirm no references, delete, verify**

```bash
git grep -n "TelegramMessage\|models.notification" -- "*.py"
```
Expected: only `src/models/notification.py` itself.

```bash
git rm src/models/notification.py
uv run pytest -q
git commit -m "refactor: remove unused TelegramMessage model"
```

---

### Task 5: Extract `setup_logging()`

`pipeline.py:10-14` and `src/server/app.py` duplicate the identical `logging.basicConfig` block; the format string must stay in sync.

**Files:**
- Modify: `config/settings.py` (add function at the end)
- Modify: `pipeline.py:10-14`
- Modify: `src/server/app.py` (the `logging.basicConfig(...)` block)

- [ ] **Step 1: Add to `config/settings.py`**

Add `import logging` to the imports, and at the end of the file:

```python
def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
```

- [ ] **Step 2: Use it in `pipeline.py`**

Replace the `logging.basicConfig(...)` call (lines 10-14) with:

```python
settings.setup_logging()
```

(keep `import logging` — `log = logging.getLogger("pipeline")` still needs it).

- [ ] **Step 3: Use it in `src/server/app.py`**

Replace the `logging.basicConfig(...)` block with:

```python
settings.setup_logging()
```

- [ ] **Step 4: Gate + commit**

```bash
uv run ruff check .
uv run pytest -q
git add config/settings.py pipeline.py src/server/app.py
git commit -m "refactor: extract shared setup_logging into config.settings"
```

---

### Task 6: Unify EB sync — fix cron reconciliation bug (CRITICAL)

`pipeline.py` (cron, 4×/day) inserts via `insert_transactions` and never reconciles; `scheduler.run_eb_sync` (manual `/sync` only) reconciles. Pending Tasker rows are never verified by cron and get duplicated by EB rows. Fix: one shared module, used by both, with Telegram alerts for fetch failure and zero-accounts (session expiry symptom). Inserted transactions notify Telegram in both paths (user decision).

**Files:**
- Create: `src/sync/__init__.py` (empty)
- Create: `src/sync/eb_sync.py`
- Modify: `src/server/routes/sync.py:15` (import path)
- Modify: `pipeline.py` (fetch stage)
- Delete: `src/server/scheduler.py`
- Test: `tests/test_eb_sync.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eb_sync.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.reconciliation import ReconciliationResult


class TestRunEbSync:
    def test_fetch_failure_sends_alert_and_returns_zero_stats(self):
        from src.sync.eb_sync import run_eb_sync

        with (
            patch("src.sync.eb_sync.fetch_transactions", side_effect=RuntimeError("boom")),
            patch("src.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync(days_back=2)

        assert (stats.inserted, stats.reconciled, stats.skipped) == (0, 0, 0)
        mock_alert.assert_called_once()
        assert "failed" in mock_alert.call_args[0][0]

    def test_zero_accounts_sends_session_expiry_warning(self):
        from src.sync.eb_sync import run_eb_sync

        with (
            patch("src.sync.eb_sync.fetch_transactions", return_value={}),
            patch("src.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync()

        assert (stats.inserted, stats.reconciled, stats.skipped) == (0, 0, 0)
        mock_alert.assert_called_once()
        assert "session" in mock_alert.call_args[0][0]

    def test_counts_actions_and_notifies_only_inserted(self):
        from src.sync.eb_sync import run_eb_sync

        txs = [MagicMock(), MagicMock(), MagicMock()]
        actions = [
            ReconciliationResult(match=None, action="inserted"),
            ReconciliationResult(match=None, action="reconciled"),
            ReconciliationResult(match=None, action="skipped"),
        ]
        with (
            patch("src.sync.eb_sync.fetch_transactions", return_value={"acc1": [{}, {}, {}]}),
            patch("src.sync.eb_sync.fetch_ecb_rates", return_value={}),
            patch("src.sync.eb_sync.normalize", return_value=txs),
            patch("src.sync.eb_sync.connection"),
            patch("src.sync.eb_sync.reconcile_or_insert", side_effect=actions),
            patch("src.sync.eb_sync.notify_transaction") as mock_notify,
            patch("src.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync()

        assert (stats.inserted, stats.reconciled, stats.skipped) == (1, 1, 1)
        mock_notify.assert_called_once()
        mock_alert.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_eb_sync.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.sync'`

- [ ] **Step 3: Create `src/sync/__init__.py` (empty) and `src/sync/eb_sync.py`**

```python
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import config.settings as settings  # noqa: E402
from src.ingestion.fetch_transactions import fetch_transactions  # noqa: E402
from src.normalizer.normalize import fetch_ecb_rates, normalize  # noqa: E402
from src.notifications.telegram import notify_transaction, send_telegram  # noqa: E402
from src.storage.db_insert import connection  # noqa: E402
from src.storage.reconcile import reconcile_or_insert  # noqa: E402

log = logging.getLogger(__name__)


@dataclass
class SyncStats:
    inserted: int = 0
    reconciled: int = 0
    skipped: int = 0


def _alert(text: str) -> None:
    send_telegram(text, token=settings.TELEGRAM_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID)


def run_eb_sync(days_back: int = 2) -> SyncStats:
    """Fetch last N days from Enable Banking, reconcile pending rows, insert new ones.

    Used by both the Railway cron (via pipeline.py) and POST /sync.
    """
    log.info("EB sync started (last %d days)", days_back)
    stats = SyncStats()

    try:
        raw_by_account = fetch_transactions(days_back=days_back)
    except Exception as exc:
        log.error("EB sync fetch failed: %s", exc)
        _alert("⚠️ EB sync failed — check Railway logs")
        return stats

    if not raw_by_account:
        log.error("EB sync returned no accounts — session likely expired")
        _alert(
            "⚠️ EB sync returned no accounts — session likely expired. "
            "Renew: uv run python src/auth/enable_banking_auth.py"
        )
        return stats

    ecb_rates = fetch_ecb_rates()
    with connection(settings.DATABASE_URL) as conn:
        for account_id, raw_txs in raw_by_account.items():
            for tx in normalize(raw_txs, account_id, ecb_rates):
                result = reconcile_or_insert(conn, tx)
                if result.action == "inserted":
                    notify_transaction(
                        tx, token=settings.TELEGRAM_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID
                    )
                    stats.inserted += 1
                elif result.action == "reconciled":
                    stats.reconciled += 1
                else:
                    stats.skipped += 1

    log.info(
        "EB sync done — inserted: %d, reconciled: %d, skipped: %d",
        stats.inserted,
        stats.reconciled,
        stats.skipped,
    )
    return stats
```

- [ ] **Step 4: Run new tests**

Run: `uv run pytest tests/test_eb_sync.py -q`
Expected: 3 passed.

- [ ] **Step 5: Rewire `src/server/routes/sync.py`**

Change line 15 from `from src.server.scheduler import run_eb_sync` to:

```python
from src.sync.eb_sync import run_eb_sync
```

- [ ] **Step 6: Rewire `pipeline.py` fetch stage**

Replace the whole `if not args.skip_fetch:` block body with:

```python
    if not args.skip_fetch:
        from src.sync.eb_sync import run_eb_sync

        log.info("Syncing transactions (last %d days) ...", args.days)
        stats = run_eb_sync(days_back=args.days)
        log.info(
            "Stored %d new, reconciled %d, skipped %d",
            stats.inserted,
            stats.reconciled,
            stats.skipped,
        )
    else:
        log.info("Skipping fetch (--skip-fetch)")
```

The `from src.storage.db_insert import ...` import at the top of `main()` shrinks to `ensure_schema, get_connection` (drop `insert_transactions`).

- [ ] **Step 7: Delete the old module**

```bash
git rm src/server/scheduler.py
git grep -n "scheduler" -- "*.py"
```
Expected grep: no hits.

- [ ] **Step 8: Full gate + commit**

```bash
uv run ruff check .
uv run pytest -q
git add src/sync/ src/server/routes/sync.py pipeline.py tests/test_eb_sync.py
git commit -m "fix: cron now reconciles pending Tasker rows — unify EB sync in src/sync/eb_sync with failure and session-expiry Telegram alerts"
```

---

### Task 7: ECB cache TTL + missing-rate log severity

`_ecb_cache` never expires — the long-lived web server (`POST /sync`) reuses day-one rates forever. Missing-rate fallback stays (skipping would lose exotic-currency transactions forever) but logs at ERROR.

**Files:**
- Modify: `src/normalizer/normalize.py:26-68`
- Test: `tests/test_normalizer.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_normalizer.py`:

```python
class TestEcbCacheTtl:
    def _reset(self, mod):
        mod._ecb_cache.clear()
        mod._ecb_fetched_at = 0.0

    def test_fresh_cache_skips_refetch(self):
        import time
        from unittest.mock import patch

        import src.normalizer.normalize as mod

        self._reset(mod)
        mod._ecb_cache.update({"USD": 1.1})
        mod._ecb_fetched_at = time.monotonic()
        with patch("src.normalizer.normalize.httpx.get") as mock_get:
            rates = mod.fetch_ecb_rates()
        mock_get.assert_not_called()
        assert rates == {"USD": 1.1}
        self._reset(mod)

    def test_expired_cache_refetches_and_keeps_stale_on_failure(self):
        import time
        from unittest.mock import patch

        import src.normalizer.normalize as mod

        self._reset(mod)
        mod._ecb_cache.update({"USD": 1.1})
        mod._ecb_fetched_at = time.monotonic() - mod._ECB_TTL_SECONDS - 1
        with patch(
            "src.normalizer.normalize.httpx.get", side_effect=Exception("net down")
        ) as mock_get:
            rates = mod.fetch_ecb_rates()
        mock_get.assert_called_once()
        assert rates == {"USD": 1.1}
        self._reset(mod)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_normalizer.py -q -k Ttl`
Expected: FAIL — `AttributeError: ... has no attribute '_ecb_fetched_at'` (or `_ECB_TTL_SECONDS`).

- [ ] **Step 3: Implement**

In `src/normalizer/normalize.py` add `import time` to the stdlib imports and replace the cache block + `fetch_ecb_rates` head:

```python
_ECB_TTL_SECONDS = 12 * 3600  # ECB reference rates update once per day (~16:00 CET)
_ecb_cache: dict[str, float] = {}
_ecb_fetched_at: float = 0.0


def fetch_ecb_rates() -> dict[str, float]:
    """Return {currency: rate} where 1 EUR = rate CCY (ECB reference rates)."""
    global _ecb_fetched_at
    if _ecb_cache and time.monotonic() - _ecb_fetched_at < _ECB_TTL_SECONDS:
        return _ecb_cache
    try:
```

The `try` body is unchanged except the cache update at its end becomes:

```python
        _ecb_cache.clear()
        _ecb_cache.update(fresh)
        _ecb_fetched_at = time.monotonic()
        log.info("Loaded ECB rates for %d currencies", len(_ecb_cache))
    except Exception as exc:
        log.warning("Failed to fetch ECB rates: %s", exc)  # stale cache (if any) still returned
    return _ecb_cache
```

In `_to_eur`, change `log.warning(` to `log.error(` for the missing-rate branch.

- [ ] **Step 4: Full gate + commit**

```bash
uv run pytest tests/test_normalizer.py -q
uv run ruff check .
git add src/normalizer/normalize.py tests/test_normalizer.py
git commit -m "fix: 12h TTL on ECB rate cache; missing FX rate logs at ERROR"
```

---

### Task 8: Login rate limiting

`/auth/login` is public on Railway with no brute-force protection. Single-user app → simple global in-memory failed-attempt window (5 failures / 15 min → 429). No new dependency. Trade-off accepted: an attacker can lock out the (only) user temporarily — better than credential stuffing.

**Files:**
- Modify: `src/server/routes/auth.py`
- Test: `tests/test_auth.py` (append + autouse reset fixture)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py` (adjust the client fixture name to whatever the file already uses — it builds `TestClient(create_app())`):

```python
import pytest

from src.server.routes import auth as auth_module


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    auth_module._clear_failures()
    yield
    auth_module._clear_failures()


class TestLoginRateLimit:
    def test_locked_after_five_failures_even_with_valid_credentials(self, client):
        for _ in range(5):
            resp = client.post(
                "/auth/login", json={"username": "testuser", "password": "wrong"}
            )
            assert resp.status_code == 401
        resp = client.post(
            "/auth/login", json={"username": "testuser", "password": "testpassword"}
        )
        assert resp.status_code == 429

    def test_successful_login_clears_the_counter(self, client):
        for _ in range(4):
            client.post("/auth/login", json={"username": "testuser", "password": "wrong"})
        resp = client.post(
            "/auth/login", json={"username": "testuser", "password": "testpassword"}
        )
        assert resp.status_code == 200
        resp = client.post(
            "/auth/login", json={"username": "testuser", "password": "wrong"}
        )
        assert resp.status_code == 401  # counter reset — not 429
```

Note: the autouse fixture also protects the pre-existing login tests from cross-test lockout.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_auth.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_clear_failures'`.

- [ ] **Step 3: Implement in `auth.py`**

Add to imports: `import threading`, `import time`, `from collections import deque`. Below the router definition:

```python
_MAX_FAILED = 5
_WINDOW_SECONDS = 900
_failed_attempts: deque[float] = deque()
_attempts_lock = threading.Lock()


def _too_many_failures() -> bool:
    now = time.monotonic()
    with _attempts_lock:
        while _failed_attempts and now - _failed_attempts[0] > _WINDOW_SECONDS:
            _failed_attempts.popleft()
        return len(_failed_attempts) >= _MAX_FAILED


def _record_failure() -> None:
    with _attempts_lock:
        _failed_attempts.append(time.monotonic())


def _clear_failures() -> None:
    with _attempts_lock:
        _failed_attempts.clear()
```

Update `login`:

```python
@router.post("/login")
def login(body: LoginRequest, response: Response) -> dict:
    if _too_many_failures():
        raise HTTPException(status_code=429, detail="Too many failed attempts — try later")
    valid = hmac.compare_digest(body.username, settings.APP_USERNAME) and _verify_password(
        body.password, settings.APP_PASSWORD_HASH
    )
    if not valid:
        _record_failure()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _clear_failures()
    response.set_cookie(
        key="jwt",
        value=_make_jwt(),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=86400,
    )
    return {"ok": True}
```

- [ ] **Step 4: Full gate + commit**

```bash
uv run pytest tests/test_auth.py -q
uv run pytest -q
uv run ruff check .
git add src/server/routes/auth.py tests/test_auth.py
git commit -m "security: in-memory rate limit on /auth/login (5 failures / 15 min)"
```

---

### Task 9: Frontend dead code and mock data removal

`client.ts` has `transactions.update`/`delete` calling `PATCH/DELETE /transactions/:id` — endpoints that do not exist on the backend and have no frontend callers. `MOCK_*` arrays (with personal-looking data) are used only as fake initial state in `StatsPage`, flashing wrong numbers before the API responds. `vite-env.d.ts` declares the dead `VITE_API_TOKEN`.

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Stats/StatsPage.tsx:4,42-43`
- Modify: `frontend/src/vite-env.d.ts:5`

- [ ] **Step 1: Trim `client.ts`**

Delete the `update` and `delete` entries from `api.transactions` (keep `list` and `create` exactly as-is). Delete everything from `// Mock data for development` (line 65) to the end of the file, including `MOCK_TRANSACTIONS`, `MOCK_CATEGORY_STATS`, `MOCK_MONTHLY_STATS`. Remove `Transaction` from the type-import list **only if** it becomes unused — `transactions.create` still returns `Promise<Transaction>`, so it stays.

- [ ] **Step 2: Fix `StatsPage.tsx` initial state**

Line 4 becomes:

```tsx
import { api } from '../../api/client';
```

Lines 42-43 become:

```tsx
  const [categoryData, setCategoryData] = useState<CategoryStat[]>([]);
  const [monthlyData, setMonthlyData] = useState<MonthlyStat[]>([]);
```

(The page already renders correctly with empty arrays: total shows €0, charts render empty, the API populates on mount.)

- [ ] **Step 3: Remove dead env declaration**

In `frontend/src/vite-env.d.ts` delete the line `readonly VITE_API_TOKEN: string;`.

- [ ] **Step 4: Verify with the TypeScript build**

Run: `cd frontend; npm run build`
Expected: build succeeds with no TS errors (this catches any missed `MOCK_*` or `update`/`delete` reference).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/Stats/StatsPage.tsx frontend/src/vite-env.d.ts
git commit -m "refactor: remove dead update/delete API methods, mock data, and VITE_API_TOKEN declaration"
```

---

### Task 10: Documentation refresh

**Files:**
- Modify: `docs/PHASE2.md`
- Modify: `docs/INSIGHTS.md`
- Modify: `CLAUDE.md` (gitignored — update the file, no commit effect)

- [ ] **Step 1: Update `docs/PHASE2.md`**

- In the operational table, change the reconciliation row note to: `via reconcile_or_insert — runs in BOTH cron (pipeline.py → src/sync/eb_sync.py) and POST /sync`.
- Add rows: `Telegram alert on sync failure / session expiry | ✅ Live` and `Login rate limiting | ✅ Live (5 failures / 15 min)`.
- In the architecture diagram, delete the line `└── APScheduler → REMOVED (moved to sync-cron)` and note that both sync paths share `src/sync/eb_sync.py`.
- In "Pending / next steps": remove item 2 (n8n on Oracle Cloud) and the "Oracle Cloud status" section — decision: not pursued, Railway cron covers it. Remove item 6 (session renewal) — the warning alert now covers detection; renewal itself stays manual.

- [ ] **Step 2: Update `docs/INSIGHTS.md`**

Mark as resolved (strike or move to a "Resolved 2026-07-02" subsection): cron-reconciliation gap, ECB cache TTL, missing-FX log severity, login rate limiting, sync-failure/session alerts, `_INSERT_RETURN` duplication, mid-file import, `scheduler.py` naming, mock data, dead client methods. Keep open: FIFO same-day pairing, multi-source refactor note, no frontend tests, missing full-lifecycle integration test.

- [ ] **Step 3: Update `CLAUDE.md`**

- Batch pipeline diagram: the storage step already names `reconcile.py` — add `src/sync/eb_sync.py` as the orchestrator invoked by both `pipeline.py` (cron) and `POST /sync`.
- Remove any reference to `src/server/scheduler.py` if present; mention `SyncStats` return.
- Note the new invariant: `/auth/login` is rate-limited (5 failed attempts / 15 min, in-memory).

- [ ] **Step 4: Commit**

```bash
git add docs/PHASE2.md docs/INSIGHTS.md
git commit -m "docs: reflect unified sync, alerts, rate limiting; close n8n/Oracle track"
```

---

### Task 11: Final verification gate

- [ ] **Step 1: Full backend gate**

```bash
uv run ruff format .
uv run ruff check .
uv run pytest -q
```
Expected: format makes no changes (or re-commit if it does), lint clean, **129 tests pass** (124 baseline + 3 eb_sync + 2 ECB TTL + 2 rate-limit − 2 removed = recount at execution; all green is the requirement).

- [ ] **Step 2: Frontend gate**

Run: `cd frontend; npm run build`
Expected: clean build.

- [ ] **Step 3: Verify clean tree**

Run: `git status --porcelain`
Expected: empty (everything committed in prior tasks).

---

### Task 12: One-time production data repair (MANUAL APPROVAL REQUIRED — run after deploy)

Because cron never reconciled, the live DB may hold duplicate pairs: an unreconciled `source='tasker'` row plus a separate `source='enable_banking'` row for the same real transaction (double counting in stats). Repair only **after** the fix is deployed, or duplicates keep regenerating.

- [ ] **Step 1: Inspect (read-only, Neon MCP `run_sql` on project `cool-butterfly-25110592`)**

```sql
SELECT t.id AS tasker_id, t.status, t.booking_date::date AS day,
       t.amount, t.currency, t.merchant_name AS tasker_merchant,
       e.id AS eb_id, e.merchant_name AS eb_merchant
FROM transactions t
JOIN transactions e
  ON e.source = 'enable_banking'
 AND e.amount = t.amount
 AND e.currency = t.currency
 AND e.booking_date::date = t.booking_date::date
WHERE t.source = 'tasker'
ORDER BY day DESC;
```

- [ ] **Step 2: Review each pair with the user** — same-day identical-amount purchases can be legitimate distinct transactions; only true duplicates get deleted.

- [ ] **Step 3: Delete only the confirmed duplicate tasker rows, by explicit id list**

```sql
DELETE FROM transactions WHERE id = ANY(ARRAY[/* reviewed tasker_ids */]);
```

Do **not** run a blanket join-delete. This step requires explicit user approval at execution time.

---

## Post-plan (outside this refactor, needs user go-ahead)

Deploy both Railway services (`railway up --detach --service just-comfort` and `--service sync-cron`) and push to `main` for Vercel. Then run Task 12.
