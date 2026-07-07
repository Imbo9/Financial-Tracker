import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config.settings as settings
from src.server.routes.api import router as api_router
from src.server.routes.auth import router as auth_router
from src.server.routes.sync import router as sync_router
from src.server.routes.webhook import router as webhook_router

settings.setup_logging()

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings.validate_server_settings()
    app = FastAPI(
        title="Revolut Finance Ingestion", docs_url=None, redoc_url=None, openapi_url=None
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # Financial data must never land in shared caches (Vercel proxy sits in front)
    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(webhook_router)
    app.include_router(sync_router)
    app.include_router(api_router)
    app.include_router(auth_router)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
