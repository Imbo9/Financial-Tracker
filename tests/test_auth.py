import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
