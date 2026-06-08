import hmac
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import config.settings as settings
from src.storage.db_insert import get_connection

log = logging.getLogger(__name__)
router = APIRouter()


def _require_auth(x_webhook_secret: str | None = Header(default=None)) -> None:
    if not hmac.compare_digest(
        (x_webhook_secret or "").encode(),
        settings.WEBHOOK_SECRET.encode(),
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


@contextmanager
def _get_conn():
    conn = get_connection(settings.DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def _row_to_dict(row: Any) -> dict[str, Any]:
    out = dict(row)
    for k, v in out.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out
