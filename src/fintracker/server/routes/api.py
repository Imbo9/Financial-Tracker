import logging
from datetime import date, datetime
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

# The donut labels NULL-category rows 'Uncategorized' via COALESCE. Map that synthetic
# label back to NULL here — the one place it is translated — so drill-down queries don't
# search for a literal category with that name and silently return nothing.
UNCATEGORIZED_LABEL = "Uncategorized"

_MAX_SPAN_DAYS = 366  # a full year; the widest supported period (leap years included)


def _validate_date_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if (date_to - date_from).days + 1 > _MAX_SPAN_DAYS:
        raise HTTPException(status_code=422, detail="date range must not exceed 366 days")


def _category_or_null(category: str) -> str | None:
    return None if category == UNCATEGORIZED_LABEL else category


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


class AccountIn(BaseModel):
    display_name: str
    type: str
    currency: str = "EUR"
    opening_balance: Decimal = Decimal("0")

    @model_validator(mode="after")
    def _check_type(self) -> "AccountIn":
        if self.type not in accounts.ACCOUNT_TYPES:
            raise ValueError("unknown account type")
        return self


class AccountUpdate(BaseModel):
    display_name: str | None = None
    type: str | None = None
    opening_balance: Decimal | None = None

    @model_validator(mode="after")
    def _check_type(self) -> "AccountUpdate":
        if self.type is not None and self.type not in accounts.ACCOUNT_TYPES:
            raise ValueError("unknown account type")
        return self


def _list_transactions(
    page: int,
    page_size: int,
    days_back: int,
    category: str | None,
    direction: str | None,
    search: str | None,
    subcategory: str | None,
    date_from: date | None,
    date_to: date | None,
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
            date_from=date_from,
            date_to=date_to,
        )


def _create_transaction(body: ManualTransactionIn) -> dict:
    with db_conn() as conn:
        row = transactions.create_manual(conn, body.model_dump())
    if row is None:
        raise HTTPException(status_code=409, detail="Duplicate transaction")
    return row


def _stats_categories(date_from: date, date_to: date, direction: str) -> list[dict]:
    with db_conn() as conn:
        return stats.by_category(conn, date_from, date_to, direction)


def _stats_monthly(months: int) -> list[dict]:
    with db_conn() as conn:
        return stats.monthly(conn, months)


def _stats_balance_history(months: int) -> list[dict]:
    with db_conn() as conn:
        return stats.balance_history(conn, months)


def _stats_subcategories(
    category: str, date_from: date, date_to: date, direction: str
) -> list[dict]:
    with db_conn() as conn:
        return stats.subcategory_breakdown(
            conn, _category_or_null(category), date_from, date_to, direction
        )


def _stats_category_trend(
    category: str, months: int, direction: str, subcategory: str | None
) -> list[dict]:
    with db_conn() as conn:
        return stats.category_trend(
            conn, _category_or_null(category), months, direction, subcategory
        )


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
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    if date_from is not None and date_to is not None:
        _validate_date_range(date_from, date_to)
    return {
        "data": _list_transactions(
            page,
            page_size,
            days_back,
            category,
            direction,
            search,
            subcategory,
            date_from,
            date_to,
        )
    }


@router_v1.post("/transactions", status_code=201)
def create_transaction_v1(body: ManualTransactionIn) -> dict:
    return {"data": _create_transaction(body)}


@router_v1.get("/stats/categories")
def stats_categories_v1(date_from: date, date_to: date, direction: DirectionQ = None) -> dict:
    _validate_date_range(date_from, date_to)
    return {"data": _stats_categories(date_from, date_to, direction or "expense")}


@router_v1.get("/stats/monthly")
def stats_monthly_v1(months: MonthsQ = 12) -> dict:
    return {"data": _stats_monthly(months)}


@router_v1.get("/stats/balance-history")
def stats_balance_history_v1(months: MonthsQ = 12) -> dict:
    return {"data": _stats_balance_history(months)}


@router_v1.get("/stats/categories/{category}/subcategories")
def stats_subcategories_v1(
    category: str, date_from: date, date_to: date, direction: DirectionQ = None
) -> dict:
    _validate_date_range(date_from, date_to)
    return {"data": _stats_subcategories(category, date_from, date_to, direction or "expense")}


@router_v1.get("/stats/categories/{category}/trend")
def stats_category_trend_v1(
    category: str,
    months: MonthsQ = 12,
    direction: DirectionQ = None,
    subcategory: str | None = None,
) -> dict:
    return {"data": _stats_category_trend(category, months, direction or "expense", subcategory)}


@router_v1.get("/accounts")
def accounts_v1() -> dict:
    return {"data": _accounts()}


@router_v1.post("/accounts", status_code=201)
def create_account_v1(body: AccountIn) -> dict:
    with db_conn() as conn:
        return {
            "data": accounts.create_account(
                conn,
                display_name=body.display_name,
                type=body.type,
                currency=body.currency,
                opening_balance=body.opening_balance,
            )
        }


@router_v1.patch("/accounts/{account_uid}")
def update_account_v1(account_uid: str, body: AccountUpdate) -> dict:
    with db_conn() as conn:
        acc = accounts.get_account(conn, account_uid)
        if acc is None:
            raise HTTPException(status_code=404, detail="unknown account")
        if not acc["is_manual"] and body.opening_balance is not None:
            raise HTTPException(status_code=422, detail="cannot change balance on a synced account")
        updated = accounts.update_account(
            conn,
            account_uid,
            display_name=body.display_name,
            type=body.type,
            opening_balance=body.opening_balance if acc["is_manual"] else None,
        )
        return {"data": updated}


@router_v1.delete("/accounts/{account_uid}")
def delete_account_v1(account_uid: str) -> dict:
    with db_conn() as conn:
        result = accounts.delete_account(conn, account_uid)
    errors = {
        "not_found": (404, "unknown account"),
        "protected": (403, "synced accounts cannot be deleted"),
        "has_transactions": (409, "account has transactions"),
    }
    if result in errors:
        code, msg = errors[result]
        raise HTTPException(status_code=code, detail=msg)
    return {"data": {"account_id": account_uid}}


@router_v1.get("/categories")
def categories_v1() -> dict:
    return {"data": {"expense": taxonomy.EXPENSE_CATEGORIES, "income": taxonomy.INCOME_CATEGORIES}}
