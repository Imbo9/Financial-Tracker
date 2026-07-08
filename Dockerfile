# ── Stage 1: dipendenze con uv ───────────────────────────────────
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Stage 2: immagine finale ──────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY pipeline.py ./
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/src"
ENV PYTHONUNBUFFERED=1

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

CMD ["sh", "-c", "uvicorn fintracker.server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
