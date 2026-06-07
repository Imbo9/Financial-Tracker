from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReconciliationMatch(BaseModel):
    pending_id: int
    pending_dedup_hash: str


class ReconciliationResult(BaseModel):
    match: ReconciliationMatch | None
    action: Literal["reconciled", "inserted", "skipped"]
