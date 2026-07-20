import logging
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from fintracker import taxonomy
from fintracker.server.deps import require_jwt
from fintracker.server.services import accounts, stats, transactions
from fintracker.storage.db import db_conn

log = logging.getLogger(__name__)

# All dashboard routes are guarded by require_jwt and served under /v1
# (response envelope {"data": ...}). The legacy unversioned mount was removed at cutover.
router_v1 = APIRouter(dependencies=[Depends(require_jwt)])


class ManualTransactionIn(BaseModel):
    booking_date: datetime
    amount: Decimal
    currency: str = "EUR"
    eur_amount: Decimal
    merchant_name: str | None = None
    description: str | None = None
    account_id: str | None = None
    category: str | None = None
    subcategory: str | None = None

    @model_validator(mode="after")
    def _check_taxonomy(self) -> "ManualTransactionIn":
        if self.subcategory is not None and self.category is None:
            raise ValueError("subcategory requires a category")
        if self.category is not None and not taxonomy.is_valid(self.category, self.subcategory):
            raise ValueError("unknown category or subcategory")
        return self


def _list_transactions(
    page: int,
    page_size: int,
    days_back: int,
    category: str | None,
    direction: str | None,
    search: str | None,
    subcategory: str | None,
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
            subcategory=subcategory,
        )


def _create_transaction(body: ManualTransactionIn) -> dict:
    with db_conn() as conn:
        row = transactions.create_manual(conn, body.model_dump())
    if row is None:
        raise HTTPException(status_code=409, detail="Duplicate transaction")
    return row


def _stats_categories(days_back: int, direction: str) -> list[dict]:
    with db_conn() as conn:
        return stats.by_category(conn, days_back, direction)


def _stats_monthly(months: int) -> list[dict]:
    with db_conn() as conn:
        return stats.monthly(conn, months)


def _stats_balance_history(months: int) -> list[dict]:
    with db_conn() as conn:
        return stats.balance_history(conn, months)


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
    subcategory: str | None = None,
) -> dict:
    return {
        "data": _list_transactions(
            page, page_size, days_back, category, direction, search, subcategory
        )
    }


@router_v1.post("/transactions", status_code=201)
def create_transaction_v1(body: ManualTransactionIn) -> dict:
    return {"data": _create_transaction(body)}


@router_v1.get("/stats/categories")
def stats_categories_v1(days_back: DaysBackQ = 30, direction: DirectionQ = None) -> dict:
    return {"data": _stats_categories(days_back, direction or "expense")}


@router_v1.get("/stats/monthly")
def stats_monthly_v1(months: MonthsQ = 12) -> dict:
    return {"data": _stats_monthly(months)}


@router_v1.get("/stats/balance-history")
def stats_balance_history_v1(months: MonthsQ = 12) -> dict:
    return {"data": _stats_balance_history(months)}


@router_v1.get("/accounts")
def accounts_v1() -> dict:
    return {"data": _accounts()}


@router_v1.get("/categories")
def categories_v1() -> dict:
    return {"data": {"expense": taxonomy.EXPENSE_CATEGORIES, "income": taxonomy.INCOME_CATEGORIES}}
