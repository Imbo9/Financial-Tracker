import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fintracker.server.deps import require_jwt
from fintracker.server.services import accounts, stats, transactions
from fintracker.storage.db import db_conn

log = logging.getLogger(__name__)

# Dual routers: same handlers, legacy keeps today's bare shapes for the live
# frontend; /v1 wraps in {"data": ...}. Legacy router dies in Task 5.8.
router_v1 = APIRouter(dependencies=[Depends(require_jwt)])
router_legacy = APIRouter(dependencies=[Depends(require_jwt)])


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


def _list_transactions(
    page: int,
    page_size: int,
    days_back: int,
    category: str | None,
    direction: str | None,
    search: str | None,
) -> dict:
    with db_conn() as conn:
        return transactions.list_transactions(
            conn,
            page=page,
            page_size=page_size,
            days_back=days_back,
            category=category,
            direction=direction,
            search=search,
        )


def _create_transaction(body: ManualTransactionIn) -> dict:
    with db_conn() as conn:
        row = transactions.create_manual(conn, body.model_dump())
    if row is None:
        raise HTTPException(status_code=409, detail="Duplicate transaction")
    return row


def _stats_categories(days_back: int) -> list[dict]:
    with db_conn() as conn:
        return stats.by_category(conn, days_back)


def _stats_monthly(months: int) -> list[dict]:
    with db_conn() as conn:
        return stats.monthly(conn, months)


def _accounts() -> dict:
    with db_conn() as conn:
        return accounts.balances(conn)


PageQ = Annotated[int, Field(ge=1)]
PageSizeQ = Annotated[int, Field(ge=1, le=500)]
DaysBackQ = Annotated[int, Field(ge=1, le=365)]
MonthsQ = Annotated[int, Field(ge=1, le=24)]
DirectionQ = Annotated[str | None, Query(pattern="^(income|expense)$")]


@router_v1.get("/transactions")
def list_transactions_v1(
    page: PageQ = 1,
    page_size: PageSizeQ = 50,
    days_back: DaysBackQ = 30,
    category: str | None = None,
    direction: DirectionQ = None,
    search: str | None = None,
) -> dict:
    return {"data": _list_transactions(page, page_size, days_back, category, direction, search)}


@router_legacy.get("/transactions")
def list_transactions_legacy(
    page: PageQ = 1,
    page_size: PageSizeQ = 50,
    days_back: DaysBackQ = 30,
    category: str | None = None,
    direction: DirectionQ = None,
    search: str | None = None,
) -> dict:
    return _list_transactions(page, page_size, days_back, category, direction, search)


@router_v1.post("/transactions", status_code=201)
def create_transaction_v1(body: ManualTransactionIn) -> dict:
    return {"data": _create_transaction(body)}


@router_legacy.post("/transactions", status_code=201)
def create_transaction_legacy(body: ManualTransactionIn) -> dict:
    return _create_transaction(body)


@router_v1.get("/stats/categories")
def stats_categories_v1(days_back: DaysBackQ = 30) -> dict:
    return {"data": _stats_categories(days_back)}


@router_legacy.get("/stats/categories")
def stats_categories_legacy(days_back: DaysBackQ = 30) -> list[dict]:
    return _stats_categories(days_back)


@router_v1.get("/stats/monthly")
def stats_monthly_v1(months: MonthsQ = 12) -> dict:
    return {"data": _stats_monthly(months)}


@router_legacy.get("/stats/monthly")
def stats_monthly_legacy(months: MonthsQ = 12) -> list[dict]:
    return _stats_monthly(months)


@router_v1.get("/accounts")
def accounts_v1() -> dict:
    return {"data": _accounts()}


@router_legacy.get("/accounts")
def accounts_legacy() -> dict:
    return _accounts()
