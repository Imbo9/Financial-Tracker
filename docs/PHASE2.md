# Phase 2 / Phase 3 — design & roadmap (reference)

Reference material moved out of CLAUDE.md to keep it lean. Tracks what is operational vs pending.

## What is operational (as of 2026-06-10)

| Component | Status | Notes |
|-----------|--------|-------|
| Neon Postgres (EU Frankfurt) | ✅ Live | project `cool-butterfly-25110592` |
| FastAPI backend on Railway (`just-comfort`) | ✅ Live | JWT auth, REST API, webhook |
| MacroDroid → Tasker webhook → Telegram | ✅ Live | ~2s real-time notifications |
| Enable Banking batch sync 4×/day | ✅ Live | via Railway cron service `sync-cron` |
| Reconciliation (pending → verified) | ✅ Live | `reconcile_or_insert` — runs in BOTH cron (`pipeline.py` → `src/sync/eb_sync.py`) and `POST /sync` |
| Telegram alert on sync failure / session expiry | ✅ Live | sent from `src/sync/eb_sync.py` |
| Login rate limiting | ✅ Live | 5 failures / 15 min, in-memory |
| Web dashboard (`fimbook.vercel.app`) | ✅ Live | React/TS, Transactions, Stats, Accounts |
| JWT auth (httpOnly cookie, Vercel proxy) | ✅ Live | HS256, bcrypt password |
| AI categorization (Claude Haiku) | ✅ Live | merchant_name only, privacy-safe |

## Architecture (current)

```
INPUT
├── Enable Banking / PSD2     → Railway cron (sync-cron) every 6h
└── Tasker (Android)          → POST /webhook/tasker (~2s latency)

        ↓

FastAPI (just-comfort, Railway)
├── /webhook/tasker           → parse → DB insert (pending) → Telegram
├── /sync                     → manual trigger
├── /transactions, /stats/*   → read API for dashboard
└── /auth/login|logout        → JWT cookie (rate-limited: 5 failures / 15 min)

Both sync paths (cron pipeline.py and POST /sync) share src/sync/eb_sync.py:
fetch → normalize → reconcile_or_insert → Telegram on new inserts + failure alerts

        ↓

Neon Postgres (EU Frankfurt)
├── transactions table        (status: pending | verified)
└── real_transactions view    (is_internal = FALSE)

        ↓

OUTPUT
├── Telegram Bot              → instant notification on transaction
└── Fimbook dashboard         → fimbook.vercel.app (Vercel, React/TS)
```

## Vercel proxy pattern

All frontend API calls go to `/api/*` which Vercel rewrites to Railway:
```json
{ "source": "/api/:path*", "destination": "https://just-comfort-production-4c96.up.railway.app/:path*" }
```
This makes cookies first-party — no SameSite=None/CORS issues.

## Pending / next steps

1. **Multi-source gateway** — additional accounts (Degiro, crypto, PayPal, Satispay)
2. **CSV import** — manual bulk import for historical data from other sources
3. **Semantic search** — embeddings already in schema (`vector(1536)`), not yet populated
4. **Dashboard enhancements** — transaction filtering, search, date ranges in UI

Session renewal stays manual (`uv run python src/auth/enable_banking_auth.py`) — expiry is
now detected by the zero-accounts Telegram alert.

n8n on Oracle Cloud: **closed 2026-07-02** — ARM A1 capacity never freed up; the Railway
cron service covers the scheduled-sync use case.

## Revolut Developer API (researched, not implemented)

Direct Revolut Open Banking API explored but **not viable for personal use**:
- Webhooks exist (`TransactionCreated`) but require **eIDAS certificate** (regulated TPP only)
- Sandbox tested: CSR generated, JWKs at `https://imbo9.github.io/eb-callback/jwks.json`
- Production blocked by eIDAS — not pursuing
- **Solution chosen**: Tasker (Android) intercepts Revolut push notifications
