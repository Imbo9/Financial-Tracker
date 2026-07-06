import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

import config.settings as settings  # noqa: E402
from src.server.routes.api import router as api_router  # noqa: E402
from src.server.routes.auth import router as auth_router  # noqa: E402
from src.server.routes.sync import router as sync_router  # noqa: E402
from src.server.routes.webhook import router as webhook_router  # noqa: E402

settings.setup_logging()

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
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
