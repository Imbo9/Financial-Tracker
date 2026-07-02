# Project Insights — Financial Tracker (Fimbook)

*Deep analysis snapshot, 2026-07-02. Complements CLAUDE.md (reference) and docs/PHASE2.md (roadmap) — this file records **judgments**: what is strong, what is fragile, and where the real risks live.*

---

## 1. What this project actually is

A single-user personal finance hub that solved the "banks won't give individuals webhooks" problem with a clever two-lane design:

- **Fast lane (~2s)**: Android push notification → MacroDroid → HMAC-signed webhook → `pending` row + Telegram alert. Zero API quota cost.
- **Slow lane (4×/day)**: Enable Banking PSD2 batch → normalize → **reconcile** the pending rows into `verified`. Bound by the hard PSD2 limit of 4 calls/account/24h.

The reconciliation layer (`src/storage/reconcile.py`) is the keystone: it converts two unreliable sources (parsed notification text, delayed bank data) into one consistent ledger. Everything else — categorization, dashboard, stats — sits on top of that guarantee.

## 2. Architectural strengths worth preserving

- **Idempotence everywhere.** `ON CONFLICT (dedup_hash) DO NOTHING` plus deterministic hashes means every stage can be re-run blindly. The cron job failing and re-running is a non-event.
- **Namespaced dedup hashes.** EB hashes and Tasker hashes (`"tasker|..."` prefix, minute-truncated timestamp) can never collide. This is subtle and load-bearing — documented as an invariant in CLAUDE.md, correctly so.
- **Reconciliation ordering.** `reconcile_or_insert` checks for a pending Tasker match *before* checking the EB hash, with a `_UPDATE_TO_VERIFIED_KEEP_HASH` fallback when the EB row already exists from a pre-fix sync. This handles the historical-data edge case without a migration.
- **Privacy boundary in the categorizer.** Only `merchant_name` goes to the Claude API — no amounts, dates, or account IDs. The batch prompt is cached (`cache_control: ephemeral`), failures degrade to `category=NULL` and are retried on the next run (`WHERE category IS NULL` is self-healing).
- **Vercel proxy for auth.** Rewriting `/api/*` to Railway makes the JWT cookie first-party, sidestepping the entire SameSite/CORS/third-party-cookie mess. Simpler than any CORS configuration would have been.
- **Deferred imports in `pipeline.py`.** Stage modules load only when their stage runs, so `--skip-fetch` doesn't even require EB credentials to be valid.

## 3. Known fragilities and blind spots

### Data quality
- **Missing FX rate = silently wrong data.** `_to_eur` stores the *original* amount as `eur_amount` when ECB has no rate (`normalize.py:61-68`). A THB transaction would inflate spending ~37×. Rare for a EUR/GBP/USD user, but there is no flag on the row marking "unconverted" — once stored, it is indistinguishable from a real EUR amount.
- **ECB rates cache never expires** (`_ecb_cache` module-level). Fine for the cron process (fresh interpreter per run), but `run_eb_sync` also runs inside the long-lived web server via `POST /sync` — repeated manual syncs over days would use day-one rates.
- **Reconciliation matches on `amount + currency + date` only.** Two identical purchases the same day (two €1.20 coffees) reconcile FIFO — consistent but potentially wrong pairing. Merchant names then get overwritten by EB's version via `COALESCE`, which usually fixes it, but the `source_id` linkage could be swapped.

### Operational
- **The 90-day Enable Banking session is the single point of failure.** Renewal is manual (`enable_banking_auth.py`, needs a browser). When it expires, the batch lane dies silently — the fast lane keeps producing `pending` rows that never verify. There is no expiry alert. *This is the highest-value small improvement available: a Telegram warning at T-7 days, or when a sync returns zero accounts.*
- **No alert on sync failure.** `run_eb_sync` logs and returns on fetch failure; the cron service equivalent relies on reading Railway logs. Telegram is already wired — failures should page it.
- **`/auth/login` has no rate limiting.** bcrypt slows brute force and the username check is constant-time, but nothing stops unlimited attempts against the public Railway URL. The project's own coding guidelines call for rate limiting on public endpoints.

### Code
- **`api.py` duplicates the INSERT statement.** `_INSERT_RETURN` re-lists all 14 columns because it needs `RETURNING`; `db_insert.INSERT_SQL` is now the shared canonical copy (good uncommitted refactor), but a schema change still has to touch both.
- **`reconcile.py:51` imports mid-file** (`from src.storage.db_insert import INSERT_SQL as _INSERT` after the SQL constants). Works, DRY-motivated, but a future reader will trip on it — belongs at the top with the other imports.
- **`scheduler.py` is misnamed post-refactor.** APScheduler is gone; the file now only holds `run_eb_sync` used by `POST /sync`. Renaming to `sync_runner.py` (or moving into `routes/sync.py`) would prevent the "is this dead code?" question — I asked it myself during this analysis.

## 4. State of the uncommitted work (as of this snapshot)

The working tree contains a coherent security-hardening pass that is **finished but not committed**:
- SQL injection fixes: f-string `INTERVAL '{days_back} days'` and `LIMIT {months}` → parameterized (`api.py`). These were real injectable surfaces (mitigated by FastAPI's `int` coercion, but the pattern was wrong).
- Webhook 422 no longer echoes the validation exception to the client (`webhook.py`).
- `INSERT_SQL` extracted and shared between `db_insert.py` and `reconcile.py`.
- `logging.basicConfig` added to the web server (`app.py`) — previously only `pipeline.py` configured logging, so Railway server logs depended on uvicorn's defaults.

Plus `frontend/` — the entire React app — is untracked but deployed. **The deployed production system is ahead of git.** Committing this should be the next action in any session.

## 5. Test posture

10 backend test files covering the right seams: hash determinism, normalizer edge cases, tasker parsing, reconciliation branches, webhook HMAC, JWT auth (including invalid/expired tokens), API filters/pagination. Notably good: tests were updated *with* behavior changes (`44a1942` replaced dead header tests when auth changed).

Gaps: no frontend tests at all, and no integration test that exercises the full webhook→pending→reconcile→verified lifecycle against a real Postgres (the pieces are tested separately; the FIFO edge case in §3 lives exactly in that gap).

## 6. Roadmap reality check (vs PHASE2.md)

| Item | Assessment |
|---|---|
| Multi-source gateway (Degiro, PayPal, Satispay) | Biggest architectural step; the normalizer/reconciler are Revolut-shaped in places (INTERNAL_PATTERNS, notification parsing) — expect a `source`-dispatch refactor |
| n8n on Oracle Cloud | Effectively dead (ARM capacity); Railway cron already covers it — candidate for closing out |
| Embeddings / semantic search | `vector(1536)` column exists, never populated; pure upside but no consumer yet — YAGNI until a search UI exists |
| CSV import | Cheap win, reuses the manual-transaction path (`manual_dedup_hash`) |
| Session renewal automation | Not on the roadmap but should be (see §3 operational) |

## 7. History patterns worth knowing

- The git log shows disciplined incremental delivery: design spec → plan → implementation commits (JWT auth arc, `54a440a`→`f16bc4f`, is a textbook example, including a mid-course pivot to the Vercel proxy when cross-origin cookies failed).
- Security fixes arrive in dedicated passes (`cb8ccce`, `603ec33`, the current uncommitted one) rather than mixed into features — keep doing that.
- Commit messages state *why* (e.g. `f16bc4f "proxy /api/* to Railway to resolve cross-origin cookie blocking"`) — matches the project's own guideline.
- Five commits were spent on the logo's letter "f" (`548b80b`…`3b47577`). Endearing, and a reminder that frontend styling iterations might be cheaper via `/verify` screenshots than deploy-and-look.
