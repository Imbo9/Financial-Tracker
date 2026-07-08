from unittest.mock import MagicMock, patch

from fintracker.models.reconciliation import ReconciliationResult


class TestRunEbSync:
    def test_fetch_failure_sends_alert_and_returns_zero_stats(self):
        from fintracker.sync.eb_sync import run_eb_sync

        with (
            patch("fintracker.sync.eb_sync.fetch_transactions", side_effect=RuntimeError("boom")),
            patch("fintracker.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync(days_back=2)

        assert (stats.inserted, stats.reconciled, stats.skipped) == (0, 0, 0)
        mock_alert.assert_called_once()
        assert "failed" in mock_alert.call_args[0][0]

    def test_zero_accounts_sends_session_expiry_warning(self):
        from fintracker.sync.eb_sync import run_eb_sync

        with (
            patch("fintracker.sync.eb_sync.fetch_transactions", return_value={}),
            patch("fintracker.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync()

        assert (stats.inserted, stats.reconciled, stats.skipped) == (0, 0, 0)
        mock_alert.assert_called_once()
        assert "session" in mock_alert.call_args[0][0]

    def test_counts_actions_and_notifies_only_inserted(self):
        from fintracker.sync.eb_sync import run_eb_sync

        txs = [MagicMock(), MagicMock(), MagicMock()]
        actions = [
            ReconciliationResult(match=None, action="inserted"),
            ReconciliationResult(match=None, action="reconciled"),
            ReconciliationResult(match=None, action="skipped"),
        ]
        with (
            patch(
                "fintracker.sync.eb_sync.fetch_transactions", return_value={"acc1": [{}, {}, {}]}
            ),
            patch("fintracker.sync.eb_sync.fetch_ecb_rates", return_value={}),
            patch("fintracker.sync.eb_sync.normalize", return_value=txs),
            patch("fintracker.sync.eb_sync.connection"),
            patch("fintracker.sync.eb_sync.reconcile_or_insert", side_effect=actions),
            patch("fintracker.sync.eb_sync.notify_transaction") as mock_notify,
            patch("fintracker.sync.eb_sync.send_telegram") as mock_alert,
        ):
            stats = run_eb_sync()

        assert (stats.inserted, stats.reconciled, stats.skipped) == (1, 1, 1)
        mock_notify.assert_called_once()
        mock_alert.assert_not_called()
