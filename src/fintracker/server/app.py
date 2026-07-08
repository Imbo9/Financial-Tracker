import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fintracker.server.routes.api import router_legacy as api_legacy
from fintracker.server.routes.api import router_v1 as api_v1
from fintracker.server.routes.auth import router as auth_legacy
from fintracker.server.routes.auth import router_v1 as auth_v1
from fintracker.server.routes.sync import router as sync_router
from fintracker.server.routes.webhook import router as webhook_router
from fintracker.settings import settings, setup_logging

setup_logging()

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

    # Registering on StarletteHTTPException (not fastapi.HTTPException) also covers
    # starlette's own routing errors (e.g. 404 on unknown paths) with one handler.
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never leak validation internals to clients; details go to the log only.
        log.warning("Request validation failed: %s", exc.errors())
        return JSONResponse(
            status_code=422,
            content={"error": {"code": 422, "message": "Invalid request"}},
        )

    # Machine endpoints — permanently unversioned (MacroDroid + manual curl)
    app.include_router(webhook_router)
    app.include_router(sync_router)

    # Dashboard API — versioned. Legacy mount kept until the frontend ships /v1
    # (removed in Task 5.8).
    app.include_router(api_v1, prefix="/v1")
    app.include_router(auth_v1, prefix="/v1")
    app.include_router(api_legacy)
    app.include_router(auth_legacy)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
