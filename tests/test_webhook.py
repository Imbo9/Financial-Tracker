import hashlib
import hmac
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SECRET = "test-webhook-secret-for-pytest!!"


def _sign(body: dict) -> str:
    raw = json.dumps(body, separators=(",", ":")).encode()
    return hmac.new(_SECRET.encode(), raw, hashlib.sha256).hexdigest()


@pytest.fixture
def client():
    from src.server.app import create_app

    return TestClient(create_app())


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
    def test_missing_signature_returns_401(self, client):
        resp = client.post("/webhook/tasker", json=VALID_PAYLOAD)
        assert resp.status_code == 401

    def test_wrong_signature_returns_401(self, client):
        resp = client.post(
            "/webhook/tasker",
            json=VALID_PAYLOAD,
            headers={"X-Signature": "deadbeef"},
        )
        assert resp.status_code == 401

    def test_valid_request_returns_200(self, client):
        body = json.dumps(VALID_PAYLOAD, separators=(",", ":")).encode()
        sig = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
        with (
            patch("src.server.routes.webhook.connection") as mock_conn,
            patch("src.server.routes.webhook.insert_transaction", return_value=True),
            patch("src.server.routes.webhook.notify_transaction"),
        ):
            mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.post(
                "/webhook/tasker",
                content=body,
                headers={"X-Signature": sig, "Content-Type": "application/json"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_duplicate_returns_200_with_skipped(self, client):
        body = json.dumps(VALID_PAYLOAD, separators=(",", ":")).encode()
        sig = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
        with (
            patch("src.server.routes.webhook.connection") as mock_conn,
            patch("src.server.routes.webhook.insert_transaction", return_value=False),
            patch("src.server.routes.webhook.notify_transaction"),
        ):
            mock_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            resp = client.post(
                "/webhook/tasker",
                content=body,
                headers={"X-Signature": sig, "Content-Type": "application/json"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    def test_invalid_payload_returns_422(self, client):
        body = json.dumps({"bad": "payload"}, separators=(",", ":")).encode()
        sig = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
        resp = client.post(
            "/webhook/tasker",
            content=body,
            headers={"X-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp.status_code == 422
