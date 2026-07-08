from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_SECRET = "test-webhook-secret-for-pytest!!"


@pytest.fixture
def client():
    from fintracker.server.app import create_app

    return TestClient(create_app())


class TestSyncRoute:
    def test_missing_secret_returns_401(self, client):
        resp = client.post("/sync")
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self, client):
        resp = client.post("/sync", headers={"X-Webhook-Secret": "wrong"})
        assert resp.status_code == 401

    def test_valid_secret_starts_sync(self, client):
        with patch("fintracker.server.routes.sync.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/sync", headers={"X-Webhook-Secret": _SECRET})
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"
        mock_thread.return_value.start.assert_called_once()

    def test_days_back_default_is_2(self, client):
        with patch("fintracker.server.routes.sync.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/sync", headers={"X-Webhook-Secret": _SECRET})
        assert resp.json()["days_back"] == 2

    def test_days_back_custom_value(self, client):
        with patch("fintracker.server.routes.sync.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/sync?days_back=7", headers={"X-Webhook-Secret": _SECRET})
        assert resp.json()["days_back"] == 7
        assert mock_thread.call_args[1]["args"] == (7,)

    def test_days_back_above_max_returns_422(self, client):
        resp = client.post("/sync?days_back=91", headers={"X-Webhook-Secret": _SECRET})
        assert resp.status_code == 422

    def test_days_back_zero_returns_422(self, client):
        resp = client.post("/sync?days_back=0", headers={"X-Webhook-Secret": _SECRET})
        assert resp.status_code == 422
