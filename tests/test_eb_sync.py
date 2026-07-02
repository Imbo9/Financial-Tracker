import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.reconciliation import ReconciliationResult


class TestRunEbSync:
    def test_fetch_failure_sends_alert_and_returns_zero_stats(self):
        from src.sync.eb_sync import run_eb_sync

        with (
            patch("src.sync.eb_sync.fetch_transactions", side_effect=RuntimeError("boom")),
            patch("src.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync(days_back=2)

        assert (stats.inserted, stats.reconciled, stats.skipped) == (0, 0, 0)
        mock_alert.assert_called_once()
        assert "failed" in mock_alert.call_args[0][0]

    def test_zero_accounts_sends_session_expiry_warning(self):
        from src.sync.eb_sync import run_eb_sync

        with (
            patch("src.sync.eb_sync.fetch_transactions", return_value={}),
            patch("src.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync()

        assert (stats.inserted, stats.reconciled, stats.skipped) == (0, 0, 0)
        mock_alert.assert_called_once()
        assert "session" in mock_alert.call_args[0][0]

    def test_counts_actions_and_notifies_only_inserted(self):
        from src.sync.eb_sync import run_eb_sync

        txs = [MagicMock(), MagicMock(), MagicMock()]
        actions = [
            ReconciliationResult(match=None, action="inserted"),
            ReconciliationResult(match=None, action="reconciled"),
            ReconciliationResult(match=None, action="skipped"),
        ]
        with (
            patch("src.sync.eb_sync.fetch_transactions", return_value={"acc1": [{}, {}, {}]}),
            patch("src.sync.eb_sync.fetch_ecb_rates", return_value={}),
            patch("src.sync.eb_sync.normalize", return_value=txs),
            patch("src.sync.eb_sync.connection"),
            patch("src.sync.eb_sync.reconcile_or_insert", side_effect=actions),
            patch("src.sync.eb_sync.notify_transaction") as mock_notify,
            patch("src.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync()

        assert (stats.inserted, stats.reconciled, stats.skipped) == (1, 1, 1)
        mock_notify.assert_called_once()
        mock_alert.assert_not_called()
