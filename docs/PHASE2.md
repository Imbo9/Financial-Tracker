# Phase 2 / Phase 3 — design & roadmap (reference)

Reference material moved out of CLAUDE.md to keep it lean. Tracks what is operational vs pending.

## What is operational (as of 2026-06-10)

| Component | Status | Notes |
|-----------|--------|-------|
| Neon Postgres (EU Frankfurt) | ✅ Live | project `cool-butterfly-25110592` |
| FastAPI backend on Railway (`just-comfort`) | ✅ Live | JWT auth, REST API, webhook |
| MacroDroid → Tasker webhook → Telegram | ✅ Live | ~2s real-time notifications |
| Enable Banking batch sync 4×/day | ✅ Live | via Railway cron service `sync-cron` |
| Reconciliation (pending → verified) | ✅ Live | `reconcile_or_insert` |
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
├── /auth/login|logout        → JWT cookie
└── APScheduler               → REMOVED (moved to sync-cron)

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
2. **n8n on Oracle Cloud** — still blocked on ARM A1 capacity in Milan; alternative: keep Railway cron
3. **CSV import** — manual bulk import for historical data from other sources
4. **Semantic search** — embeddings already in schema (`vector(1536)`), not yet populated
5. **Dashboard enhancements** — transaction filtering, search, date ranges in UI
6. **Enable Banking session renewal** — session expires every 90 days, manual renewal via `uv run python src/auth/enable_banking_auth.py`

## Revolut Developer API (researched, not implemented)

Direct Revolut Open Banking API explored but **not viable for personal use**:
- Webhooks exist (`TransactionCreated`) but require **eIDAS certificate** (regulated TPP only)
- Sandbox tested: CSR generated, JWKs at `https://imbo9.github.io/eb-callback/jwks.json`
- Production blocked by eIDAS — not pursuing
- **Solution chosen**: Tasker (Android) intercepts Revolut push notifications

## Oracle Cloud status

- Account created, Home Region: Italy Northwest (Milan)
- ARM A1 capacity exhausted in Milan — retry during off-peak hours (2-6 AM) or use Frankfurt
- Frankfurt region subscription blocked on new free-tier accounts
- Workaround: Railway cron service covers the scheduled sync use case
