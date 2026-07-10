import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from fintracker.ingestion.tasker_parser import parse_tasker_payload
from fintracker.models.tasker import TaskerPayload
from fintracker.notifications.telegram import notify_transaction
from fintracker.settings import settings
from fintracker.storage.db import db_conn
from fintracker.storage.db_insert import insert_transaction

log = logging.getLogger(__name__)
router = APIRouter()


def _verify_signature(body: bytes, signature: str | None) -> bool:
    """Verify HMAC-SHA256(WEBHOOK_SECRET, body) == signature."""
    expected = hmac.new(
        settings.WEBHOOK_SECRET.get_secret_value().encode(), body, hashlib.sha256
    ).hexdigest()
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
        raise HTTPException(status_code=422, detail="Invalid request payload") from exc

    tx = parse_tasker_payload(payload)

    with db_conn() as conn:
        inserted = insert_transaction(conn, tx)

    if inserted:
        notify_transaction(
            tx, token=settings.TELEGRAM_TOKEN.get_secret_value(), chat_id=settings.TELEGRAM_CHAT_ID
        )
        log.info("Tasker webhook: inserted %s", tx.dedup_hash[:8])
        return {"status": "ok"}

    log.info("Tasker webhook: duplicate skipped %s", tx.dedup_hash[:8])
    return {"status": "skipped"}
