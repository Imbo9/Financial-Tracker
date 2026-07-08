from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class TaskerPayload(BaseModel):
    raw_text: str
    amount: str | None = None
    currency: str | None = None
    merchant: str | None = None
    direction: Literal["debit", "credit"] | None = None
    device_timestamp: datetime
    parse_status: Literal["ok", "failed"] = "ok"

    @field_validator("device_timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, v: object) -> object:
        if isinstance(v, str) and "/" in v:
            # MacroDroid Italian format: DD/MM/YYYY HH:MM:SS
            return datetime.strptime(v, "%d/%m/%Y %H:%M:%S")
        return v
