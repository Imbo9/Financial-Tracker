import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client():
    from src.server.app import create_app

    app = create_app()
    return TestClient(app)


VALID_PAYLOAD = {
    "raw_text": "Hai pagato €12,50 a Esselunga",
    "amount": "12.50",
    "currency": "EUR",
    "merchant": "Esselunga",
    "direction": "debit",
    "device_timestamp": "2026-06-07T14:32:00Z",
    "parse_status": "ok",
}


class TestWebhookEndpoint:
    def test_missing_secret_returns_401(self, client):
        resp = client.post("/webhook/tasker", json=VALID_PAYLOAD)
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self, client):
        resp = client.post(
            "/webhook/tasker",
            json=VALID_PAYLOAD,
            headers={"X-Webhook-Secret": "wrong"},
        )
        assert resp.status_code == 401

    def test_valid_request_returns_200(self, client):
        with (
            patch("src.server.routes.webhook.get_conn") as mock_conn,
            patch("src.server.routes.webhook.insert_transaction", return_value=True),
            patch("src.server.routes.webhook.notify_transaction"),
        ):
            mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.post(
                "/webhook/tasker",
                json=VALID_PAYLOAD,
                headers={"X-Webhook-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_duplicate_returns_200_with_skipped(self, client):
        with (
            patch("src.server.routes.webhook.get_conn") as mock_conn,
            patch("src.server.routes.webhook.insert_transaction", return_value=False),
            patch("src.server.routes.webhook.notify_transaction"),
        ):
            mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.post(
                "/webhook/tasker",
                json=VALID_PAYLOAD,
                headers={"X-Webhook-Secret": "test-secret"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    def test_invalid_payload_returns_422(self, client):
        resp = client.post(
            "/webhook/tasker",
            json={"bad": "payload"},
            headers={"X-Webhook-Secret": "test-secret"},
        )
        assert resp.status_code == 422
