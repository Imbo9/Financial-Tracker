import hmac
import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field

import config.settings as settings
from src.sync.eb_sync import run_eb_sync

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/sync")
async def trigger_sync(
    x_webhook_secret: str | None = Header(default=None),
    days_back: Annotated[int, Field(ge=1, le=90)] = 2,
) -> dict:
    if not hmac.compare_digest(
        (x_webhook_secret or "").encode(),
        settings.WEBHOOK_SECRET.encode(),
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    threading.Thread(target=run_eb_sync, args=(days_back,), daemon=True).start()
    log.info("Manual EB sync triggered via /sync (days_back=%d)", days_back)
    return {"status": "started", "days_back": days_back}
