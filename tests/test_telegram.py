import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.transaction import NormalizedTransaction
from src.notifications.telegram import build_message, send_telegram


def _tx(**kwargs):
    defaults = {
        "dedup_hash": "abc123",
        "booking_date": datetime(2026, 6, 7, 14, 32, 0, tzinfo=UTC),
        "amount": -12.50,
        "currency": "EUR",
        "eur_amount": -12.50,
        "merchant_name": "Esselunga",
        "status": "pending",
        "source": "tasker",
    }
    defaults.update(kwargs)
    return NormalizedTransaction(**defaults)


class TestBuildMessage:
    def test_debit_pending(self):
        msg = build_message(_tx(amount=-12.50, status="pending", merchant_name="Esselunga"))
        assert "🔴" in msg
        assert "12.50" in msg
        assert "Esselunga" in msg
        assert "pending" in msg

    def test_credit_verified(self):
        msg = build_message(_tx(amount=50.0, status="verified", merchant_name="Mario Rossi"))
        assert "🟢" in msg
        assert "50.0" in msg
        assert "verified" in msg

    def test_parse_failed(self):
        msg = build_message(_tx(amount=0.0, status="pending", merchant_name=None))
        assert "⚠️" in msg

    def test_debit_verified(self):
        msg = build_message(_tx(amount=-12.50, status="verified", merchant_name="Netflix"))
        assert "🔴" in msg
        assert "12.50" in msg


class TestSendTelegram:
    def test_send_calls_telegram_api(self):
        with patch("src.notifications.telegram.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.return_value.raise_for_status = MagicMock()
            send_telegram("test message", token="tok", chat_id="123")
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert "sendMessage" in call_kwargs[0][0]

    def test_send_skipped_when_no_token(self):
        with patch("src.notifications.telegram.httpx.post") as mock_post:
            send_telegram("test message", token="", chat_id="123")
            mock_post.assert_not_called()

    def test_send_exception_is_swallowed(self):
        with patch("src.notifications.telegram.httpx.post", side_effect=Exception("timeout")):
            send_telegram("test", token="tok", chat_id="123")  # must not raise

    def test_notify_transaction_delegates(self):
        from src.notifications.telegram import notify_transaction

        with patch("src.notifications.telegram.send_telegram") as mock_send:
            notify_transaction(
                _tx(amount=-5.0, merchant_name="Netflix"), token="tok", chat_id="123"
            )
            mock_send.assert_called_once()
            assert "Netflix" in mock_send.call_args[0][0]
