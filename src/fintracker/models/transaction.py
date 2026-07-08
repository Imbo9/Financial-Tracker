from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class NormalizedTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    dedup_hash: str
    booking_date: datetime
    amount: Decimal
    currency: str
    eur_amount: Decimal
    description: str | None = None
    merchant_name: str | None = None
    account_id: str | None = None
    is_internal: bool = False
    category: str | None = None
    subcategory: str | None = None
    status: Literal["pending", "verified"] = "verified"
    source: Literal["tasker", "enable_banking", "manual"] = "enable_banking"
    source_id: str | None = None
