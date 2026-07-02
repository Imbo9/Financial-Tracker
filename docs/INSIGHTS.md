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

> **Update 2026-07-02:** the sanitize-refactor pass (`docs/superpowers/plans/2026-07-02-sanitize-refactor.md`) resolved most of the original items in this section. Resolved: ECB cache TTL (12h), missing-FX-rate severity (now ERROR), session-expiry + sync-failure Telegram alerts, login rate limiting (5 failures / 15 min), INSERT duplication, mid-file import, `scheduler.py` (deleted — sync unified in `src/sync/eb_sync.py`), and the **cron-reconciliation bug** discovered during planning: `pipeline.py` used `insert_transactions` and never reconciled, so pending Tasker rows stayed pending forever and EB rows duplicated them. Both sync paths now share `run_eb_sync`.

### Still open
- **Missing FX rate stores the original amount** as `eur_amount` (now logged at ERROR, but still no per-row "unconverted" flag). Acceptable for a EUR-centric account; revisit if exotic currencies appear.
- **Reconciliation matches on `amount + currency + date` only.** Two identical purchases the same day (two €1.20 coffees) reconcile FIFO — consistent but potentially wrong pairing. Merchant names then get overwritten by EB's version via `COALESCE`, which usually fixes it, but the `source_id` linkage could be swapped.
- **Session renewal itself is still manual** (`enable_banking_auth.py`, needs a browser) — expiry is now *detected* (zero-accounts Telegram alert) but not automated.
- **Historical duplicates in production** from the pre-fix era may exist: tasker rows never reconciled + separate EB rows. One-time cleanup pending (Task 12 of the refactor plan) — inspect before deleting.

## 4. Uncommitted work

Resolved 2026-07-02 — the hardening pass, the entire frontend, and the docs were committed as separate commits at the start of the sanitize-refactor. Git and production are in sync again.

## 5. Test posture

10 backend test files covering the right seams: hash determinism, normalizer edge cases, tasker parsing, reconciliation branches, webhook HMAC, JWT auth (including invalid/expired tokens), API filters/pagination. Notably good: tests were updated *with* behavior changes (`44a1942` replaced dead header tests when auth changed).

Gaps: no frontend tests at all, and no integration test that exercises the full webhook→pending→reconcile→verified lifecycle against a real Postgres (the pieces are tested separately; the FIFO edge case in §3 lives exactly in that gap).

## 6. Roadmap reality check (vs PHASE2.md)

| Item | Assessment |
|---|---|
| Multi-source gateway (Degiro, PayPal, Satispay) | Biggest architectural step; the normalizer/reconciler are Revolut-shaped in places (INTERNAL_PATTERNS, notification parsing) — expect a `source`-dispatch refactor |
| n8n on Oracle Cloud | Closed 2026-07-02 — Railway cron covers it |
| Embeddings / semantic search | `vector(1536)` column exists, never populated; pure upside but no consumer yet — YAGNI until a search UI exists |
| CSV import | Cheap win, reuses the manual-transaction path (`manual_dedup_hash`) |
| Session renewal automation | Not on the roadmap but should be (see §3 operational) |

## 7. History patterns worth knowing

- The git log shows disciplined incremental delivery: design spec → plan → implementation commits (JWT auth arc, `54a440a`→`f16bc4f`, is a textbook example, including a mid-course pivot to the Vercel proxy when cross-origin cookies failed).
- Security fixes arrive in dedicated passes (`cb8ccce`, `603ec33`, the current uncommitted one) rather than mixed into features — keep doing that.
- Commit messages state *why* (e.g. `f16bc4f "proxy /api/* to Railway to resolve cross-origin cookie blocking"`) — matches the project's own guideline.
- Five commits were spent on the logo's letter "f" (`548b80b`…`3b47577`). Endearing, and a reminder that frontend styling iterations might be cheaper via `/verify` screenshots than deploy-and-look.
