from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TaskerPayload(BaseModel):
    raw_text: str
    amount: str | None = None
    currency: str | None = None
    merchant: str | None = None
    direction: Literal["debit", "credit"] | None = None
    device_timestamp: datetime
    parse_status: Literal["ok", "failed"] = "ok"
