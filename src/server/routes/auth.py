import hmac
import logging
import sys
import threading
import time
from collections import deque
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

# Single-user app: one global failure window is enough. Trade-off: an attacker can
# temporarily lock out the only user — preferable to unlimited credential stuffing.
_MAX_FAILED = 5
_WINDOW_SECONDS = 900
_failed_attempts: deque[float] = deque()
_attempts_lock = threading.Lock()


def _too_many_failures() -> bool:
    now = time.monotonic()
    with _attempts_lock:
        while _failed_attempts and now - _failed_attempts[0] > _WINDOW_SECONDS:
            _failed_attempts.popleft()
        return len(_failed_attempts) >= _MAX_FAILED


def _record_failure() -> None:
    with _attempts_lock:
        _failed_attempts.append(time.monotonic())


def _clear_failures() -> None:
    with _attempts_lock:
        _failed_attempts.clear()


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
    if _too_many_failures():
        raise HTTPException(status_code=429, detail="Too many failed attempts — try later")
    valid = hmac.compare_digest(body.username, settings.APP_USERNAME) and _verify_password(
        body.password, settings.APP_PASSWORD_HASH
    )
    if not valid:
        _record_failure()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _clear_failures()
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
    response.delete_cookie(
        key="jwt",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )
