# ── Stage 1: dipendenze con uv ───────────────────────────────────
FROM python:3.12-slim AS builder

# Installa uv (binary statico, nessuna dipendenza esterna)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copia solo i file di lock prima del codice → cache layer Docker
COPY pyproject.toml uv.lock ./

# Installa dipendenze in /app/.venv — no dev deps in produzione
RUN uv sync --frozen --no-dev --no-install-project


# ── Stage 2: immagine finale ──────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copia il venv compilato dallo stage builder
COPY --from=builder /app/.venv /app/.venv

# Copia il codice sorgente
COPY pipeline.py       ./
COPY config/           ./config/
COPY src/              ./src/

# Assicura che i file __init__.py esistano per i package Python
RUN touch src/__init__.py \
         src/auth/__init__.py \
         src/ingestion/__init__.py \
         src/normalizer/__init__.py \
         src/storage/__init__.py \
         src/categorizer/__init__.py \
         src/models/__init__.py \
         src/notifications/__init__.py \
         src/server/__init__.py \
         src/server/routes/__init__.py

# Usa il Python del venv senza attivarlo esplicitamente
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Directory per file temporanei della pipeline
RUN mkdir -p /tmp/revolut_pipeline

# Utente non-root per sicurezza
RUN useradd -m -u 1000 appuser && chown -R appuser /app /tmp/revolut_pipeline
USER appuser

# Entry point di default: pipeline completa
# Override in docker-compose per auth o altri comandi
ENTRYPOINT ["python", "pipeline.py"]
CMD []
