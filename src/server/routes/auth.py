import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
import config.settings as settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _make_jwt() -> str:
    payload = {
        "sub": settings.APP_USERNAME,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return pyjwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


@router.post("/login")
def login(body: LoginRequest, response: Response) -> dict:
    valid = body.username == settings.APP_USERNAME and _verify_password(
        body.password, settings.APP_PASSWORD_HASH
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    response.set_cookie(
        key="jwt",
        value=_make_jwt(),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=86400,
    )
    return {"ok": True}


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.set_cookie(
        key="jwt",
        value="",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=0,
    )
