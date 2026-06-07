import hmac
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from fastapi import APIRouter, Header, HTTPException

import config.settings as settings
from src.ingestion.tasker_parser import parse_tasker_payload
from src.models.tasker import TaskerPayload
from src.notifications.telegram import notify_transaction
from src.storage.db_insert import get_connection, insert_transaction

log = logging.getLogger(__name__)
router = APIRouter()


@contextmanager
def get_conn():
    conn = get_connection(settings.DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


@router.post("/webhook/tasker")
async def tasker_webhook(
    payload: TaskerPayload,
    x_webhook_secret: str | None = Header(default=None),
) -> dict:
    if not hmac.compare_digest(
        (x_webhook_secret or "").encode(),
        settings.WEBHOOK_SECRET.encode(),
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    tx = parse_tasker_payload(payload)

    with get_conn() as conn:
        inserted = insert_transaction(conn, tx)

    if inserted:
        notify_transaction(tx, token=settings.TELEGRAM_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID)
        log.info("Tasker webhook: inserted %s", tx.dedup_hash[:8])
        return {"status": "ok", "dedup_hash": tx.dedup_hash}

    log.info("Tasker webhook: duplicate skipped %s", tx.dedup_hash[:8])
    return {"status": "skipped", "dedup_hash": tx.dedup_hash}
