# Phase 2 — design & roadmap (reference)

Reference material moved out of CLAUDE.md to keep it lean. This is the target design;
nothing here is operational yet. Behavioral contracts that affect current code (e.g. the
`status` field semantics) stay in CLAUDE.md under "Key invariants".

## Target architecture

```
INPUT SOURCES (agnostic gateway)
├── Enable Banking / PSD2     → batch every 6h (existing)
├── Tasker (Android)          → HTTP POST on push notification (~2s latency)
├── CSV import                → manual bulk import
└── Future: Degiro, crypto, PayPal, Satispay

        ↓  POST /ingest/{source}  ↓

n8n (self-hosted, Oracle Cloud Always-Free ARM 4vCPU/24GB)
├── Webhook node              ← receives Tasker payload instantly
├── Schedule trigger          → runs Enable Banking pipeline every 6h
├── Postgres node             → writes to Neon (managed, EU, pgvector)
├── Telegram node             → push notification to phone
└── Python node               → categorization + reconciliation logic

        ↓

Neon.tech PostgreSQL (EU, free tier, pgvector, always-on)
├── transactions table (status: pending | verified)
└── real_transactions view

        ↓

OUTPUT
├── Telegram Bot              → instant notification on transaction
├── Dashboard (Vercel)        → spending analytics
└── Claude API                → categorization + semantic search (future)
```

## Hosting (all free except Anthropic API)

| Component | Service | Cost |
|-----------|---------|------|
| Orchestration + webhooks + cron | n8n on Oracle Cloud Always-Free | €0 |
| Database | Neon.tech (EU, Frankfurt) | €0 |
| Push notifications | Telegram Bot | €0 |
| Dashboard | Vercel / GitHub Pages | €0 |
| AI categorization | Anthropic API (Claude Haiku) | pay-per-use |

### Oracle Cloud status
- Account created, Home Region: Italy Northwest (Milan)
- ARM A1 capacity exhausted in Milan — retry during off-peak hours (2-6 AM) or use Frankfurt
- Frankfurt region subscription blocked on new free-tier accounts (region limit)

## Revolut Developer API (researched, not implemented)

Direct Revolut Open Banking API explored but **not viable for personal use**:
- Webhooks exist (`TransactionCreated`) but require **eIDAS certificate** (regulated TPP only)
- No webhooks in the Open Banking scope specifically
- Sandbox tested: CSR generated (`config/revolut.csr`), JWKs at `https://imbo9.github.io/eb-callback/jwks.json`, Client ID `fb3bdd48-0b01-48dd-a65a-1cbdb81acc3d`, test account `+447253242185 / 0000`
- Production blocked by eIDAS — not pursuing

**Real-time solution chosen**: Tasker (Android) intercepts Revolut push notifications → HTTP POST to n8n webhook.

## Next steps (ordered)

1. **Migrate DB to Neon** — `pg_dump` local → Neon (EU Frankfurt), update `DATABASE_URL`
2. **Oracle Cloud VM** — retry ARM A1 in Milan off-peak or Frankfurt; install Docker + n8n
3. **Telegram Bot** — `@BotFather`, get token, configure n8n Telegram node
4. **Tasker workflow** — parse Revolut IT push notification regex, POST to n8n webhook
5. **n8n reconciliation workflow** — Tasker payload → `pending`, Enable Banking batch → `verified`
6. **Schema migration** — add `status`, `source`, `source_id` to transactions table
7. **Dashboard** — Vercel, read-only queries on Neon
