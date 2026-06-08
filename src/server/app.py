import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.server.routes.sync import router as sync_router
from src.server.routes.webhook import router as webhook_router
from src.server.scheduler import run_eb_sync

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Revolut Finance Ingestion", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.include_router(webhook_router)
    app.include_router(sync_router)

    scheduler = BackgroundScheduler(timezone="Europe/Rome")
    scheduler.add_job(
        run_eb_sync,
        "cron",
        hour="0,6,12,18",
        minute=0,
        id="eb_sync",
        max_instances=1,
        misfire_grace_time=300,
    )

    @app.on_event("startup")
    def start_scheduler() -> None:
        if not scheduler.running:
            scheduler.start()
        log.info("APScheduler started — EB sync at 00:00, 06:00, 12:00, 18:00 Europe/Rome")

    @app.on_event("shutdown")
    def stop_scheduler() -> None:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
