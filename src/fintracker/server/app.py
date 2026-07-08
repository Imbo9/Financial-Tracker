import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import fintracker.settings as settings
from fintracker.server.routes.api import router as api_router
from fintracker.server.routes.auth import router as auth_router
from fintracker.server.routes.sync import router as sync_router
from fintracker.server.routes.webhook import router as webhook_router

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
