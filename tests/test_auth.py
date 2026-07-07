import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import UTC

from src.server.routes import auth as auth_module

_USERNAME = "testuser"
_PASSWORD = "testpassword"


@pytest.fixture
def client():
    from src.server.app import create_app

    return TestClient(create_app())


class TestLogin:
    def test_success_returns_200_and_sets_cookie(self, client):
        r = client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert "jwt" in client.cookies

    def test_wrong_password_returns_401(self, client):
        r = client.post("/auth/login", json={"username": _USERNAME, "password": "wrong"})
        assert r.status_code == 401
        assert "jwt" not in client.cookies

    def test_wrong_username_returns_401(self, client):
        r = client.post("/auth/login", json={"username": "nobody", "password": _PASSWORD})
        assert r.status_code == 401

    def test_missing_body_returns_422(self, client):
        r = client.post("/auth/login", json={})
        assert r.status_code == 422


class TestLoginHardening:
    def test_non_ascii_username_returns_401_not_500(self, client):
        r = client.post("/auth/login", json={"username": "tèst-üser", "password": _PASSWORD})
        assert r.status_code == 401

    def test_nul_byte_password_returns_401_not_500(self, client):
        r = client.post("/auth/login", json={"username": _USERNAME, "password": "pass\x00word"})
        assert r.status_code == 401

    def test_overlong_password_returns_422(self, client):
        r = client.post("/auth/login", json={"username": _USERNAME, "password": "x" * 129})
        assert r.status_code == 422

    def test_empty_username_returns_422(self, client):
        r = client.post("/auth/login", json={"username": "", "password": _PASSWORD})
        assert r.status_code == 422


class TestTokenClaims:
    def test_token_carries_hardening_claims(self, client):
        import jwt as pyjwt

        client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        payload = pyjwt.decode(
            client.cookies["jwt"],
            auth_module.settings.JWT_SECRET,
            algorithms=["HS256"],
            audience=auth_module._AUDIENCE,
        )
        assert payload["iss"] == auth_module._ISSUER
        assert payload["sub"] == _USERNAME
        assert "jti" in payload and "iat" in payload

    def test_verify_token_rejects_wrong_subject(self):
        from datetime import datetime, timedelta

        import jwt as pyjwt

        now = datetime.now(UTC)
        token = pyjwt.encode(
            {
                "sub": "intruder",
                "iss": auth_module._ISSUER,
                "aud": auth_module._AUDIENCE,
                "iat": now,
                "exp": now + timedelta(hours=1),
                "jti": "x",
            },
            auth_module.settings.JWT_SECRET,
            algorithm="HS256",
        )
        with pytest.raises(pyjwt.InvalidTokenError):
            auth_module.verify_token(token)


class TestLogout:
    def test_logout_returns_204(self, client):
        client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        r = client.post("/auth/logout")
        assert r.status_code == 204

    def test_logout_clears_cookie(self, client):
        client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        assert "jwt" in client.cookies
        client.post("/auth/logout")
        assert not client.cookies.get("jwt")

    def test_logout_revokes_token_server_side(self, client):
        import jwt as pyjwt

        client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        token = client.cookies["jwt"]
        auth_module.verify_token(token)  # valid before logout
        client.post("/auth/logout")
        with pytest.raises(pyjwt.InvalidTokenError):
            auth_module.verify_token(token)

    def test_logout_without_cookie_still_204(self, client):
        r = client.post("/auth/logout")
        assert r.status_code == 204


@pytest.fixture(autouse=True)
def _reset_auth_state():
    auth_module._clear_failures()
    auth_module._revoked_jtis.clear()
    yield
    auth_module._clear_failures()
    auth_module._revoked_jtis.clear()


class TestLoginRateLimit:
    def test_locked_after_five_failures_even_with_valid_credentials(self, client):
        for _ in range(5):
            r = client.post("/auth/login", json={"username": _USERNAME, "password": "wrong"})
            assert r.status_code == 401
        r = client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        assert r.status_code == 429

    def test_successful_login_clears_the_counter(self, client):
        for _ in range(4):
            client.post("/auth/login", json={"username": _USERNAME, "password": "wrong"})
        r = client.post("/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        assert r.status_code == 200
        r = client.post("/auth/login", json={"username": _USERNAME, "password": "wrong"})
        assert r.status_code == 401  # counter reset - not 429
