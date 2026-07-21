import logging
from datetime import date
from typing import Any

from psycopg.rows import dict_row

from fintracker.normalizer.hash import manual_dedup_hash
from fintracker.storage.db_insert import INSERT_SQL

log = logging.getLogger(__name__)

_INSERT_RETURN = (
    INSERT_SQL
    + """
RETURNING id, dedup_hash, booking_date, amount, currency, eur_amount,
          description, merchant_name, account_id, is_internal,
          category, subcategory, status, source, created_at
"""
)

_SELECT_COLS = """id, dedup_hash, booking_date, amount, currency, eur_amount,
                  description, merchant_name, account_id, is_internal,
                  category, subcategory, status, source, created_at"""


def _money_to_float(row: dict) -> dict:
    # numeric columns arrive as Decimal; uncast, pydantic v2 serializes them as JSON strings
    row["amount"] = float(row["amount"])
    row["eur_amount"] = float(row["eur_amount"])
    return row


def list_transactions(
    conn,
    *,
    page: int,
    page_size: int,
    days_back: int,
    category: str | None,
    direction: str | None,
    search: str | None,
    subcategory: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    if date_from is not None and date_to is not None:
        conditions = ["booking_date >= %s", "booking_date < %s::date + INTERVAL '1 day'"]
        params: list[Any] = [date_from, date_to]
    else:
        conditions = ["booking_date >= NOW() - (%s * INTERVAL '1 day')"]
        params = [days_back]
    if category:
        conditions.append("category = %s")
        params.append(category)
    if subcategory == "No subcategory":
        conditions.append("subcategory IS NULL")
    elif subcategory:
        conditions.append("subcategory = %s")
        params.append(subcategory)
    if direction == "income":
        conditions.append("amount > 0")
    elif direction == "expense":
        conditions.append("amount < 0")
    if search:
        conditions.append("(merchant_name ILIKE %s OR description ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM real_transactions WHERE {where}", params)
        total = cur.fetchone()["total"]
        cur.execute(
            f"""SELECT {_SELECT_COLS}
                FROM real_transactions
                WHERE {where}
                ORDER BY booking_date DESC
                LIMIT %s OFFSET %s""",
            [*params, page_size, offset],
        )
        rows = [_money_to_float(dict(r)) for r in cur.fetchall()]

    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def create_manual(conn, data: dict) -> dict | None:
    """Insert a manual transaction. Returns the row, or None on duplicate."""
    data = {
        **data,
        "dedup_hash": manual_dedup_hash(
            data["booking_date"].isoformat(), data["amount"], data["currency"]
        ),
        "is_internal": False,
        "status": "verified",
        "source": "manual",
        "source_id": None,
    }
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_INSERT_RETURN, data)
        row = cur.fetchone()
    conn.commit()
    return _money_to_float(dict(row)) if row else None
