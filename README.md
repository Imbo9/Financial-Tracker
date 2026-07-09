# Financial Tracker

Personal finance hub: aggregates Revolut transactions via Enable Banking (PSD2) and real-time Tasker/MacroDroid notifications, stores everything in Postgres, and categorizes spending with Claude AI. FastAPI backend, React/TypeScript dashboard.

## What it does

```
Revolut ──┬── Enable Banking API ──┐
          └── MacroDroid/Tasker ───┴──→ Postgres (+ pgvector) ──→ Claude categorization ──→ Dashboard
```

A cron job syncs Enable Banking 4×/day; MacroDroid pushes real-time notifications via webhook (~2s latency) that get reconciled against the next batch sync. Claude Haiku assigns a category and subcategory to each merchant.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Node.js — for the frontend dashboard
- An [Enable Banking](https://enablebanking.com) Production application with Revolut linked
- An [Anthropic API](https://console.anthropic.com) key

## Quick start

```bash
uv sync
docker compose up db -d
uv run alembic upgrade head
```

Fill in credentials (see [Configure credentials](#configure-credentials) below), then:

```bash
uv run auth                  # one-time OAuth, valid ~90 days
uv run python pipeline.py
```

Dashboard (optional, local dev):

```bash
cd frontend
npm install
npm run dev
```

### Configure credentials

```bash
cp config/.env.example config/.env
```

Fill in `config/.env`:
- `ENABLE_BANKING_APP_ID` — UUID from the Enable Banking dashboard
- `ENABLE_BANKING_PRIVATE_KEY_PATH` — path to your RSA private key PEM (default: `config/private_key.pem`)
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `DATABASE_URL` — e.g. `postgresql://user:password@localhost:5432/finance`
- `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` — required by both the pipeline and the server (sync alerts)

`uv run auth` opens a browser for OAuth and fills in the Enable Banking session fields automatically.

## Usage

```bash
# Full pipeline (fetch + normalize + categorize)
uv run python pipeline.py

# Last 30 days only
uv run python pipeline.py --days 30

# Skip fetch (re-categorize existing transactions)
uv run python pipeline.py --skip-fetch

# Skip categorization
uv run python pipeline.py --skip-categorize

# Run the API server locally
uv run uvicorn fintracker.server.app:app --reload --port 8000
```

## Testing

```bash
# Unit tests (fast, no external dependencies — default)
uv run pytest
uv run pytest -k "test_dedup"    # single test example

# Integration tests (real Postgres)
docker compose up db -d
uv run pytest -m integration

# Frontend
cd frontend
npm run test
npm run lint
```

## Development

```bash
uv run ruff check .          # lint
uv run ruff check --fix .    # lint + autofix
uv run ruff format .         # format
uv run pyrefly check         # type check
```

## Architecture

| Module | Description |
|--------|-------------|
| `src/fintracker/auth/enable_banking_auth.py` | One-time OAuth flow, saves tokens to `.env` |
| `src/fintracker/ingestion/` | Enable Banking fetch + Tasker/MacroDroid notification parsing |
| `src/fintracker/normalizer/` | Normalizes to `NormalizedTransaction`, dedup hashes, ECB FX rates |
| `src/fintracker/storage/` | psycopg3 pool, insert, and reconciliation (`pending` → `verified`) |
| `src/fintracker/categorizer/categorize.py` | Batch categorization via Claude Haiku |
| `src/fintracker/sync/eb_sync.py` | Shared sync orchestration for `pipeline.py` and `POST /sync` |
| `src/fintracker/server/` | FastAPI app: routes, service layer, JWT auth, `/v1` envelope API |
| `src/fintracker/settings.py` | pydantic `Settings` — loads `.env`, typed config |
| `migrations/` | Alembic schema migrations — schema changes never happen at runtime |
| `pipeline.py` | Entry-point shim orchestrating all stages via CLI flags |
| `frontend/` | React + TypeScript dashboard (Vite, TanStack Query) |

## Docker

```bash
docker compose build pipeline
docker compose run --rm pipeline
docker compose run --rm pipeline --skip-categorize
```

## Notes

- **Dedup**: SHA-256 of `date|abs(amount)|description_lower|currency` — re-running is always safe
- **Rate limit**: Enable Banking enforces 4 API calls/account/24h (PSD2 regulation)
- **Privacy**: only `merchant_name` is sent to Claude API — never amounts, dates, or account IDs
- **Session renewal**: run `uv run auth` again when the session expires (~90 days)

## Further reading

Design rationale behind the current architecture (pydantic Settings, service layer, Alembic migrations, `/v1` envelope API, TanStack Query frontend): [`docs/superpowers/plans/2026-07-07-sota-refactor.md`](docs/superpowers/plans/2026-07-07-sota-refactor.md).
