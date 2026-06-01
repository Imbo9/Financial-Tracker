# Financial Tracker

Personal finance pipeline: fetches Revolut transactions via Enable Banking API, stores them in Postgres, and categorizes them with Claude AI.

## What it does

```
Revolut → Enable Banking API → Postgres + pgvector → Claude categorization
```

Runs once daily. Fetches the last 90 days of transactions across all linked Revolut accounts, normalizes and deduplicates them, then uses Claude Haiku to assign a category and subcategory to each merchant.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- An [Enable Banking](https://enablebanking.com) Production application with Revolut linked
- An [Anthropic API](https://console.anthropic.com) key

## Setup

**1. Install dependencies**
```bash
uv sync
```

**2. Start the database**
```bash
docker compose up db -d
```

**3. Configure credentials**
```bash
cp config/.env.example config/.env
```
Fill in `config/.env`:
- `ENABLE_BANKING_APP_ID` — UUID from the Enable Banking dashboard
- `ENABLE_BANKING_PRIVATE_KEY_PATH` — path to your RSA private key PEM (default: `config/private_key.pem`)
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `DATABASE_URL` — e.g. `postgresql://user:password@localhost:5432/finance`

**4. Authenticate with Revolut** (once, valid ~90 days)
```bash
uv run python src/auth/enable_banking_auth.py
```
Opens a browser for OAuth. Saves session token and account IDs to `config/.env` automatically.

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
```

## Development

```bash
uv run ruff check .          # lint
uv run ruff check --fix .    # lint + autofix
uv run pytest                # tests
uv run pytest -k "test_dedup"  # single test
```

## Architecture

| Module | Description |
|--------|-------------|
| `src/auth/enable_banking_auth.py` | One-time OAuth flow, saves tokens to `.env` |
| `src/ingestion/fetch_transactions.py` | Fetches raw transactions from Enable Banking API |
| `src/normalizer/normalize.py` | Normalizes to `NormalizedTransaction`, computes dedup hash, applies ECB FX rates |
| `src/storage/db_insert.py` | DDL + idempotent upsert (`ON CONFLICT DO NOTHING`) |
| `src/categorizer/categorize.py` | Batch categorization via Claude Haiku |
| `pipeline.py` | Orchestrates all stages with CLI flags |
| `config/settings.py` | Loads `.env`, exposes typed constants |

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
- **Session renewal**: run auth again when the session expires (~90 days)
