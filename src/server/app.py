import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.server.routes.webhook import router as webhook_router
from src.server.scheduler import run_eb_sync

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Revolut Finance Ingestion")
    app.include_router(webhook_router)

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_eb_sync, "interval", hours=6, id="eb_sync")

    @app.on_event("startup")
    def start_scheduler() -> None:
        if not scheduler.running:
            scheduler.start()
        log.info("APScheduler started — EB sync every 6h")

    @app.on_event("shutdown")
    def stop_scheduler() -> None:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
