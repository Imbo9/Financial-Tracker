from datetime import UTC

import pytest
from fastapi.testclient import TestClient

from fintracker.server.routes import auth as auth_module

_USERNAME = "testuser"
_PASSWORD = "testpassword"


@pytest.fixture
def client():
    from fintracker.server.app import create_app

    return TestClient(create_app())


class TestLogin:
    def test_wrong_password_returns_401(self, client):
        r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": "wrong"})
        assert r.status_code == 401
        assert "jwt" not in client.cookies

    def test_wrong_username_returns_401(self, client):
        r = client.post("/v1/auth/login", json={"username": "nobody", "password": _PASSWORD})
        assert r.status_code == 401

    def test_missing_body_returns_422(self, client):
        r = client.post("/v1/auth/login", json={})
        assert r.status_code == 422


class TestLoginHardening:
    def test_non_ascii_username_returns_401_not_500(self, client):
        r = client.post("/v1/auth/login", json={"username": "tèst-üser", "password": _PASSWORD})
        assert r.status_code == 401

    def test_nul_byte_password_returns_401_not_500(self, client):
        r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": "pass\x00word"})
        assert r.status_code == 401

    def test_overlong_password_returns_422(self, client):
        r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": "x" * 129})
        assert r.status_code == 422

    def test_empty_username_returns_422(self, client):
        r = client.post("/v1/auth/login", json={"username": "", "password": _PASSWORD})
        assert r.status_code == 422


class TestTokenClaims:
    def test_token_carries_hardening_claims(self, client):
        import jwt as pyjwt

        client.post("/v1/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        payload = pyjwt.decode(
            client.cookies["jwt"],
            auth_module.settings.JWT_SECRET.get_secret_value(),
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
            auth_module.settings.JWT_SECRET.get_secret_value(),
            algorithm="HS256",
        )
        with pytest.raises(pyjwt.InvalidTokenError):
            auth_module.verify_token(token)


class TestLogout:
    def test_logout_revokes_token_server_side(self, client):
        import jwt as pyjwt

        client.post("/v1/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        token = client.cookies["jwt"]
        auth_module.verify_token(token)  # valid before logout
        client.post("/v1/auth/logout")
        with pytest.raises(pyjwt.InvalidTokenError):
            auth_module.verify_token(token)

    def test_logout_without_cookie_still_204(self, client):
        r = client.post("/v1/auth/logout")
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
            r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": "wrong"})
            assert r.status_code == 401
        r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        assert r.status_code == 429

    def test_successful_login_clears_the_counter(self, client):
        for _ in range(4):
            client.post("/v1/auth/login", json={"username": _USERNAME, "password": "wrong"})
        r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        assert r.status_code == 200
        r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": "wrong"})
        assert r.status_code == 401  # counter reset - not 429


class TestLoginV1:
    def test_success_returns_200_and_envelope(self, client):
        r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        assert r.status_code == 200
        assert r.json() == {"data": {"ok": True}}
        assert "jwt" in client.cookies

    def test_wrong_password_returns_401_error_shape(self, client):
        r = client.post("/v1/auth/login", json={"username": _USERNAME, "password": "wrong"})
        assert r.status_code == 401
        assert r.json() == {"error": {"code": 401, "message": "Invalid credentials"}}


class TestLogoutV1:
    def test_logout_v1_returns_204(self, client):
        client.post("/v1/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        r = client.post("/v1/auth/logout")
        assert r.status_code == 204

    def test_logout_v1_clears_cookie(self, client):
        client.post("/v1/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        assert "jwt" in client.cookies
        client.post("/v1/auth/logout")
        assert not client.cookies.get("jwt")


class TestMe:
    def test_me_without_cookie_returns_401(self, client):
        r = client.get("/v1/auth/me")
        assert r.status_code == 401
        assert r.json() == {"error": {"code": 401, "message": "Unauthorized"}}

    def test_me_with_garbage_token_returns_401(self, client):
        client.cookies.set("jwt", "not.a.valid.jwt")
        r = client.get("/v1/auth/me")
        assert r.status_code == 401

    def test_me_with_valid_cookie_returns_username(self, client):
        client.post("/v1/auth/login", json={"username": _USERNAME, "password": _PASSWORD})
        r = client.get("/v1/auth/me")
        assert r.status_code == 200
        assert r.json() == {"data": {"username": _USERNAME}}


class TestErrorShapeGlobal:
    def test_404_unknown_path_has_error_envelope(self, client):
        r = client.get("/this/path/does/not/exist")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body
        assert body["error"]["code"] == 404

    def test_login_422_has_error_envelope_no_pydantic_details(self, client):
        r = client.post("/v1/auth/login", json={})
        assert r.status_code == 422
        assert r.json() == {"error": {"code": 422, "message": "Invalid request"}}
