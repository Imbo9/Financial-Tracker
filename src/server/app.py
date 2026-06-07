import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI

from src.server.routes.webhook import router as webhook_router

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Revolut Finance Ingestion")
    app.include_router(webhook_router)
    return app


app = create_app()
