import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import Field

from fintracker.settings import settings
from fintracker.sync.eb_sync import run_eb_sync

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/sync")
def trigger_sync(
    background: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None),
    days_back: Annotated[int, Field(ge=1, le=90)] = 2,
) -> dict:
    if not hmac.compare_digest(
        (x_webhook_secret or "").encode(),
        settings.WEBHOOK_SECRET.get_secret_value().encode(),
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    background.add_task(run_eb_sync, days_back)
    log.info("Manual EB sync triggered via /sync (days_back=%d)", days_back)
    return {"status": "started", "days_back": days_back}
