import hashlib
import hmac
import json
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from fastapi import APIRouter, Header, HTTPException, Request

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


def _verify_signature(body: bytes, signature: str | None) -> bool:
    """Verify HMAC-SHA256(WEBHOOK_SECRET, body) == signature."""
    expected = hmac.new(settings.WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature or "", expected)


@router.post("/webhook/tasker")
async def tasker_webhook(
    request: Request,
    x_signature: str | None = Header(default=None),
) -> dict:
    body_bytes = await request.body()

    if not _verify_signature(body_bytes, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = TaskerPayload.model_validate(json.loads(body_bytes))
    except Exception as exc:
        log.warning("Webhook validation error: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    tx = parse_tasker_payload(payload)

    with get_conn() as conn:
        inserted = insert_transaction(conn, tx)

    if inserted:
        notify_transaction(tx, token=settings.TELEGRAM_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID)
        log.info("Tasker webhook: inserted %s", tx.dedup_hash[:8])
        return {"status": "ok"}

    log.info("Tasker webhook: duplicate skipped %s", tx.dedup_hash[:8])
    return {"status": "skipped"}
