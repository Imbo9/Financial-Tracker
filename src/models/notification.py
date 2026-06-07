from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TelegramMessage(BaseModel):
    text: str
    parse_mode: Literal["HTML", "Markdown"] = "HTML"
