import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_JWT_SECRET = os.environ.get("JWT_SECRET", "test-jwt-secret-for-pytest-tests!!!")

FAKE_ROW = {
    "id": 1,
    "dedup_hash": "abc123",
    "booking_date": datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
    "amount": -4.27,
    "currency": "EUR",
    "eur_amount": -4.27,
    "description": "Test tx",
    "merchant_name": "Merchant",
    "account_id": "acc1",
    "is_internal": False,
    "category": "Eating Out",
    "subcategory": None,
    "status": "verified",
    "source": "enable_banking",
    "source_id": None,
    "created_at": datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
}


@pytest.fixture
def client():
    from src.server.app import create_app

    return TestClient(create_app())


def _token(**overrides):
    now = datetime.now(UTC)
    payload = {
        "sub": "testuser",
        "iss": "fimbook-api",
        "aud": "fimbook-dashboard",
        "iat": now,
        "exp": now + timedelta(hours=1),
        "jti": "test-jti",
    }
    payload.update(overrides)
    return pyjwt.encode(payload, _JWT_SECRET, algorithm="HS256")


@pytest.fixture
def auth_client():
    from src.server.app import create_app

    c = TestClient(create_app())
    r = c.post("/auth/login", json={"username": "testuser", "password": "testpassword"})
    assert r.status_code == 200
    return c


def _mock_conn(fetchall_result=None, fetchone_result=None):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fetchall_result or []
    mock_cur.fetchone.return_value = fetchone_result or {"total": 0}
    mock_cur.__enter__ = lambda s: s
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn


class TestTransactionsList:
    def test_missing_auth_returns_401(self, client):
        resp = client.get("/transactions")
        assert resp.status_code == 401

    def test_invalid_jwt_returns_401(self, client):
        client.cookies.set("jwt", "not.a.valid.jwt")
        resp = client.get("/transactions")
        assert resp.status_code == 401

    def test_expired_jwt_returns_401(self, client):
        client.cookies.set("jwt", _token(exp=datetime.now(UTC) - timedelta(seconds=1)))
        resp = client.get("/transactions")
        assert resp.status_code == 401

    def test_wrong_subject_returns_401(self, client):
        client.cookies.set("jwt", _token(sub="intruder"))
        resp = client.get("/transactions")
        assert resp.status_code == 401

    def test_token_without_jti_returns_401(self, client):
        payload_token = _token()
        decoded = pyjwt.decode(
            payload_token, _JWT_SECRET, algorithms=["HS256"], audience="fimbook-dashboard"
        )
        del decoded["jti"]
        client.cookies.set("jwt", pyjwt.encode(decoded, _JWT_SECRET, algorithm="HS256"))
        resp = client.get("/transactions")
        assert resp.status_code == 401

    def test_returns_paginated_response(self, auth_client):
        with patch(
            "src.storage.db_insert.get_connection",
            return_value=_mock_conn([FAKE_ROW], {"total": 1}),
        ):
            resp = auth_client.get("/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == 1
        assert data["items"][0]["merchant_name"] == "Merchant"

    def test_days_back_above_365_returns_422(self, auth_client):
        resp = auth_client.get("/transactions?days_back=366")
        assert resp.status_code == 422

    def test_page_defaults_to_1(self, auth_client):
        with patch(
            "src.storage.db_insert.get_connection", return_value=_mock_conn([], {"total": 0})
        ):
            resp = auth_client.get("/transactions")
        assert resp.json()["page"] == 1

    def test_direction_income_filters_positive_amounts(self, auth_client):
        with patch(
            "src.storage.db_insert.get_connection", return_value=_mock_conn([], {"total": 0})
        ):
            resp = auth_client.get("/transactions?direction=income")
        assert resp.status_code == 200

    def test_direction_invalid_returns_422(self, auth_client):
        resp = auth_client.get("/transactions?direction=both")
        assert resp.status_code == 422

    def test_search_filter_accepted(self, auth_client):
        with patch(
            "src.storage.db_insert.get_connection", return_value=_mock_conn([], {"total": 0})
        ):
            resp = auth_client.get("/transactions?search=costa")
        assert resp.status_code == 200


class TestCreateTransaction:
    def test_missing_auth_returns_401(self, client):
        resp = client.post("/transactions", json={})
        assert resp.status_code == 401

    def test_missing_required_fields_returns_422(self, auth_client):
        resp = auth_client.post("/transactions", json={"amount": -5.0})
        assert resp.status_code == 422

    def test_create_returns_201(self, auth_client):
        body = {
            "booking_date": "2026-06-08T12:00:00Z",
            "amount": -12.50,
            "currency": "EUR",
            "eur_amount": -12.50,
            "merchant_name": "Costa Coffee",
            "category": "Eating Out",
        }
        returned_row = dict(
            FAKE_ROW,
            id=99,
            amount=-12.50,
            eur_amount=-12.50,
            merchant_name="Costa Coffee",
            category="Eating Out",
            source="manual",
        )
        mock_cur = MagicMock()
        mock_cur.rowcount = 1
        mock_cur.fetchone.return_value = returned_row
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        with patch("src.storage.db_insert.get_connection", return_value=mock_conn):
            resp = auth_client.post("/transactions", json=body)

        assert resp.status_code == 201
        assert resp.json()["merchant_name"] == "Costa Coffee"

    def test_duplicate_returns_409(self, auth_client):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        body = {
            "booking_date": "2026-06-08T12:00:00Z",
            "amount": -12.50,
            "currency": "EUR",
            "eur_amount": -12.50,
        }
        with patch("src.storage.db_insert.get_connection", return_value=mock_conn):
            resp = auth_client.post("/transactions", json=body)
        assert resp.status_code == 409


FAKE_CATEGORY_ROW = {"category": "Eating Out", "total": 16.00, "count": 2}
FAKE_MONTHLY_ROW = {
    "month": "2026-06",
    "income": 2198.80,
    "expenses": 114.25,
}


class TestStats:
    def test_categories_missing_auth_returns_401(self, client):
        resp = client.get("/stats/categories")
        assert resp.status_code == 401

    def test_categories_returns_list_with_percentages(self, auth_client):
        with patch(
            "src.storage.db_insert.get_connection", return_value=_mock_conn([FAKE_CATEGORY_ROW])
        ):
            resp = auth_client.get("/stats/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["category"] == "Eating Out"
        assert data[0]["total"] == 16.00
        assert data[0]["count"] == 2
        assert data[0]["percentage"] == 100.0

    def test_monthly_missing_auth_returns_401(self, client):
        resp = client.get("/stats/monthly")
        assert resp.status_code == 401

    def test_monthly_returns_list_with_net(self, auth_client):
        with patch(
            "src.storage.db_insert.get_connection", return_value=_mock_conn([FAKE_MONTHLY_ROW])
        ):
            resp = auth_client.get("/stats/monthly")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["income"] == 2198.80
        assert data[0]["expenses"] == 114.25
        assert abs(data[0]["net"] - (2198.80 - 114.25)) < 0.01


FAKE_ACCOUNT_ROW = {"account_id": "revolut-main", "balance": 1234.56}


class TestAccounts:
    def test_missing_auth_returns_401(self, client):
        resp = client.get("/accounts")
        assert resp.status_code == 401

    def test_returns_accounts_list(self, auth_client):
        with patch(
            "src.storage.db_insert.get_connection", return_value=_mock_conn([FAKE_ACCOUNT_ROW])
        ):
            resp = auth_client.get("/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert "assets" in data
        assert "liabilities" in data
        assert "accounts" in data
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["account_id"] == "revolut-main"
        assert data["accounts"][0]["balance"] == 1234.56
