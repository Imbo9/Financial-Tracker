import pytest
from fastapi import HTTPException

from fintracker.server.deps import require_jwt


def test_require_jwt_missing_cookie():
    with pytest.raises(HTTPException) as exc:
        require_jwt(jwt=None)
    assert exc.value.status_code == 401


def test_require_jwt_garbage_token():
    with pytest.raises(HTTPException) as exc:
        require_jwt(jwt="not-a-jwt")
    assert exc.value.status_code == 401
