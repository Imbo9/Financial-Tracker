import hmac
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

import psycopg2.extras
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import Field

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


@router.get("/transactions")
async def list_transactions(
    _: Annotated[None, Depends(_require_auth)],
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=200)] = 50,
    days_back: Annotated[int, Field(ge=1, le=365)] = 30,
    category: str | None = None,
    direction: str | None = Query(default=None, pattern="^(income|expense)$"),
    search: str | None = None,
) -> dict:
    conditions = [f"booking_date >= NOW() - INTERVAL '{days_back} days'"]
    params: list[Any] = []

    if category:
        conditions.append("category = %s")
        params.append(category)
    if direction == "income":
        conditions.append("amount > 0")
    elif direction == "expense":
        conditions.append("amount < 0")
    if search:
        conditions.append("(merchant_name ILIKE %s OR description ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT COUNT(*) AS total FROM real_transactions WHERE {where}",
                params,
            )
            total = cur.fetchone()["total"]
            cur.execute(
                f"""SELECT id, dedup_hash, booking_date, amount, currency, eur_amount,
                           description, merchant_name, account_id, is_internal,
                           category, subcategory, status, source, created_at
                    FROM real_transactions
                    WHERE {where}
                    ORDER BY booking_date DESC
                    LIMIT %s OFFSET %s""",
                params + [page_size, offset],
            )
            rows = [_row_to_dict(r) for r in cur.fetchall()]

    return {"items": rows, "total": total, "page": page, "page_size": page_size}
