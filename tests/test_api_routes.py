import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SECRET = "test-webhook-secret-for-pytest!!"

FAKE_ROW = {
    "id": 1,
    "dedup_hash": "abc123",
    "booking_date": datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc),
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
    "created_at": datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc),
}


@pytest.fixture
def client():
    from src.server.app import create_app

    return TestClient(create_app())


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

    def test_wrong_auth_returns_401(self, client):
        resp = client.get("/transactions", headers={"X-Webhook-Secret": "wrong"})
        assert resp.status_code == 401

    def test_returns_paginated_response(self, client):
        with patch(
            "src.server.routes.api.get_connection",
            return_value=_mock_conn([FAKE_ROW], {"total": 1}),
        ):
            resp = client.get("/transactions", headers={"X-Webhook-Secret": _SECRET})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == 1
        assert data["items"][0]["merchant_name"] == "Merchant"

    def test_days_back_above_365_returns_422(self, client):
        resp = client.get("/transactions?days_back=366", headers={"X-Webhook-Secret": _SECRET})
        assert resp.status_code == 422

    def test_page_defaults_to_1(self, client):
        with patch(
            "src.server.routes.api.get_connection", return_value=_mock_conn([], {"total": 0})
        ):
            resp = client.get("/transactions", headers={"X-Webhook-Secret": _SECRET})
        assert resp.json()["page"] == 1

    def test_direction_income_filters_positive_amounts(self, client):
        with patch(
            "src.server.routes.api.get_connection", return_value=_mock_conn([], {"total": 0})
        ):
            resp = client.get(
                "/transactions?direction=income", headers={"X-Webhook-Secret": _SECRET}
            )
        assert resp.status_code == 200

    def test_direction_invalid_returns_422(self, client):
        resp = client.get("/transactions?direction=both", headers={"X-Webhook-Secret": _SECRET})
        assert resp.status_code == 422

    def test_search_filter_accepted(self, client):
        with patch(
            "src.server.routes.api.get_connection", return_value=_mock_conn([], {"total": 0})
        ):
            resp = client.get("/transactions?search=costa", headers={"X-Webhook-Secret": _SECRET})
        assert resp.status_code == 200


class TestCreateTransaction:
    def test_missing_auth_returns_401(self, client):
        resp = client.post("/transactions", json={})
        assert resp.status_code == 401

    def test_missing_required_fields_returns_422(self, client):
        resp = client.post(
            "/transactions",
            json={"amount": -5.0},
            headers={"X-Webhook-Secret": _SECRET},
        )
        assert resp.status_code == 422

    def test_create_returns_201(self, client):
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

        with patch("src.server.routes.api.get_connection", return_value=mock_conn):
            resp = client.post(
                "/transactions",
                json=body,
                headers={"X-Webhook-Secret": _SECRET},
            )

        assert resp.status_code == 201
        assert resp.json()["merchant_name"] == "Costa Coffee"

    def test_duplicate_returns_409(self, client):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None  # simulate ON CONFLICT DO NOTHING
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
        with patch("src.server.routes.api.get_connection", return_value=mock_conn):
            resp = client.post(
                "/transactions",
                json=body,
                headers={"X-Webhook-Secret": _SECRET},
            )
        assert resp.status_code == 409
