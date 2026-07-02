import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import jwt as pyjwt
import psycopg2.extras
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import config.settings as settings
from src.normalizer.hash import manual_dedup_hash
from src.storage.db_insert import connection

log = logging.getLogger(__name__)
router = APIRouter()

_INSERT_RETURN = """
INSERT INTO transactions
    (dedup_hash, booking_date, amount, currency, eur_amount,
     description, merchant_name, account_id, is_internal, category, subcategory,
     status, source, source_id)
VALUES
    (%(dedup_hash)s, %(booking_date)s, %(amount)s, %(currency)s, %(eur_amount)s,
     %(description)s, %(merchant_name)s, %(account_id)s, %(is_internal)s,
     %(category)s, %(subcategory)s, %(status)s, %(source)s, %(source_id)s)
ON CONFLICT (dedup_hash) DO NOTHING
RETURNING id, dedup_hash, booking_date, amount, currency, eur_amount,
          description, merchant_name, account_id, is_internal,
          category, subcategory, status, source, created_at
"""


class ManualTransactionIn(BaseModel):
    booking_date: datetime
    amount: float
    currency: str = "EUR"
    eur_amount: float
    merchant_name: str | None = None
    description: str | None = None
    account_id: str | None = None
    category: str | None = None
    subcategory: str | None = None


def _require_jwt(jwt: str | None = Cookie(default=None)) -> None:
    if not jwt:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        pyjwt.decode(jwt, settings.JWT_SECRET, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _row_to_dict(row: Any) -> dict[str, Any]:
    out = dict(row)
    for k, v in out.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


@router.get("/transactions")
async def list_transactions(
    _: Annotated[None, Depends(_require_jwt)],
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=500)] = 50,
    days_back: Annotated[int, Field(ge=1, le=365)] = 30,
    category: str | None = None,
    direction: str | None = Query(default=None, pattern="^(income|expense)$"),
    search: str | None = None,
) -> dict:
    conditions = ["booking_date >= NOW() - (%s * INTERVAL '1 day')"]
    params: list[Any] = [days_back]

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

    with connection(settings.DATABASE_URL) as conn:
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


@router.post("/transactions", status_code=201)
async def create_transaction(
    body: ManualTransactionIn,
    _: Annotated[None, Depends(_require_jwt)],
) -> dict:
    dedup = manual_dedup_hash(body.booking_date.isoformat(), body.amount, body.currency)
    row_data = {
        "dedup_hash": dedup,
        "booking_date": body.booking_date,
        "amount": body.amount,
        "currency": body.currency,
        "eur_amount": body.eur_amount,
        "description": body.description,
        "merchant_name": body.merchant_name,
        "account_id": body.account_id,
        "is_internal": False,
        "category": body.category,
        "subcategory": body.subcategory,
        "status": "verified",
        "source": "manual",
        "source_id": None,
    }

    with connection(settings.DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_INSERT_RETURN, row_data)
            row = cur.fetchone()
        conn.commit()

    if row is None:
        raise HTTPException(status_code=409, detail="Duplicate transaction")

    return _row_to_dict(row)


@router.get("/stats/categories")
async def stats_categories(
    _: Annotated[None, Depends(_require_jwt)],
    days_back: Annotated[int, Field(ge=1, le=365)] = 30,
) -> list[dict]:
    with connection(settings.DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT COALESCE(category, 'Uncategorized') AS category,
                          ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total,
                          COUNT(*) AS count
                   FROM real_transactions
                   WHERE amount < 0
                     AND booking_date >= NOW() - (%s * INTERVAL '1 day')
                   GROUP BY category
                   ORDER BY total DESC""",
                (days_back,),
            )
            rows = [dict(r) for r in cur.fetchall()]

    grand_total = sum(float(r["total"]) for r in rows) or 1
    for r in rows:
        r["percentage"] = round(float(r["total"]) / grand_total * 100, 1)
    return rows


@router.get("/stats/monthly")
async def stats_monthly(
    _: Annotated[None, Depends(_require_jwt)],
    months: Annotated[int, Field(ge=1, le=24)] = 12,
) -> list[dict]:
    with connection(settings.DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT TO_CHAR(DATE_TRUNC('month', booking_date), 'YYYY-MM') AS month,
                          ROUND(SUM(CASE WHEN amount > 0
                              THEN eur_amount ELSE 0 END)::numeric, 2) AS income,
                          ROUND(SUM(CASE WHEN amount < 0
                              THEN ABS(eur_amount) ELSE 0 END)::numeric, 2) AS expenses
                   FROM real_transactions
                   GROUP BY DATE_TRUNC('month', booking_date)
                   ORDER BY DATE_TRUNC('month', booking_date) DESC
                   LIMIT %s""",
                (months,),
            )
            rows = [dict(r) for r in cur.fetchall()]

    for r in rows:
        r["net"] = round(float(r["income"]) - float(r["expenses"]), 2)
    return rows


@router.get("/accounts")
async def list_accounts(
    _: Annotated[None, Depends(_require_jwt)],
) -> dict:
    with connection(settings.DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT account_id,
                          ROUND(SUM(eur_amount)::numeric, 2) AS balance
                   FROM real_transactions
                   WHERE account_id IS NOT NULL
                   GROUP BY account_id
                   ORDER BY balance DESC"""
            )
            rows = [dict(r) for r in cur.fetchall()]

    accounts = [{"account_id": r["account_id"], "balance": float(r["balance"])} for r in rows]
    assets = round(sum(a["balance"] for a in accounts if a["balance"] > 0), 2)
    liabilities = round(abs(sum(a["balance"] for a in accounts if a["balance"] < 0)), 2)

    return {"assets": assets, "liabilities": liabilities, "accounts": accounts}
