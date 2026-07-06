import hmac
import logging
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
import config.settings as settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_TOKEN_TTL_SECONDS = 86400
_ISSUER = "fimbook-api"
_AUDIENCE = "fimbook-dashboard"

# Single-user app: one global failure window is enough. Trade-off: an attacker can
# temporarily lock out the only user — preferable to unlimited credential stuffing.
_MAX_FAILED = 5
_WINDOW_SECONDS = 900
_failed_attempts: deque[float] = deque()
_attempts_lock = threading.Lock()

# Logout revocation is in-memory: single uvicorn worker, and a restart un-revokes
# tokens until their exp — accepted for a single-user app over adding DB state.
_revoked_jtis: dict[str, float] = {}
_revoked_lock = threading.Lock()


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


def _revoke(jti: str, exp: float) -> None:
    now = time.time()
    with _revoked_lock:
        for stale in [k for k, v in _revoked_jtis.items() if v < now]:
            del _revoked_jtis[stale]
        _revoked_jtis[jti] = exp


def _is_revoked(jti: str) -> bool:
    with _revoked_lock:
        return jti in _revoked_jtis


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def _bcrypt_cost(hashed: str) -> int:
    try:
        return int(hashed.split("$")[2])
    except (IndexError, ValueError):
        raise EnvironmentError("APP_PASSWORD_HASH is not a valid bcrypt hash")


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Checked when the username is wrong, at the same cost as the real hash, so both
    failure paths take equal time — otherwise timing would reveal whether a username exists.

    Lazy (not module-level) so importing this module doesn't require APP_PASSWORD_HASH."""
    return bcrypt.hashpw(
        b"#invalid#", bcrypt.gensalt(_bcrypt_cost(settings.APP_PASSWORD_HASH))
    ).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # bcrypt rejects some inputs (e.g. NUL bytes) — treat as wrong password, not a 500
        return False


def _make_jwt() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": settings.APP_USERNAME,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=_TOKEN_TTL_SECONDS),
        "jti": uuid.uuid4().hex,
    }
    return pyjwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict:
    """Validate a session JWT — signature, claims, subject, revocation.

    Raises pyjwt.InvalidTokenError on any failure.
    """
    payload = pyjwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=["HS256"],
        issuer=_ISSUER,
        audience=_AUDIENCE,
        options={"require": ["exp", "iat", "sub", "jti"]},
    )
    if not hmac.compare_digest(str(payload["sub"]).encode(), settings.APP_USERNAME.encode()):
        raise pyjwt.InvalidTokenError("unknown subject")
    if _is_revoked(payload["jti"]):
        raise pyjwt.InvalidTokenError("token revoked")
    return payload


@router.post("/login")
def login(body: LoginRequest, response: Response) -> dict:
    if _too_many_failures():
        log.warning("Login locked out — too many failed attempts")
        raise HTTPException(status_code=429, detail="Too many failed attempts — try later")
    user_ok = hmac.compare_digest(body.username.encode(), settings.APP_USERNAME.encode())
    pass_ok = _verify_password(
        body.password, settings.APP_PASSWORD_HASH if user_ok else _dummy_hash()
    )
    if not (user_ok and pass_ok):
        _record_failure()
        log.warning("Failed login attempt")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _clear_failures()
    response.set_cookie(
        key="jwt",
        value=_make_jwt(),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=_TOKEN_TTL_SECONDS,
    )
    return {"ok": True}


@router.post("/logout", status_code=204)
def logout(response: Response, jwt: str | None = Cookie(default=None)) -> None:
    if jwt:
        try:
            payload = verify_token(jwt)
            _revoke(payload["jti"], payload["exp"])
        except pyjwt.InvalidTokenError:
            pass  # expired or junk cookie — nothing to revoke
    response.delete_cookie(
        key="jwt",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )
