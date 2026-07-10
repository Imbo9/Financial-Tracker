import jwt as pyjwt
from fastapi import Cookie, HTTPException

from fintracker.server.routes.auth import verify_token


def require_jwt(jwt: str | None = Cookie(default=None)) -> dict:
    """Session guard for dashboard endpoints. Returns the JWT payload."""
    if not jwt:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return verify_token(jwt)
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Unauthorized") from None
