import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.transaction import NormalizedTransaction
from src.storage.reconcile import reconcile_or_insert


def _tx(**kwargs) -> NormalizedTransaction:
    defaults = {
        "dedup_hash": "abc123",
        "booking_date": datetime(2026, 6, 7, 10, 0, 0, tzinfo=timezone.utc),
        "amount": -12.50,
        "currency": "EUR",
        "eur_amount": -12.50,
        "description": "Esselunga",
        "merchant_name": "Esselunga",
        "account_id": "acc1",
        "status": "verified",
        "source": "enable_banking",
    }
    defaults.update(kwargs)
    return NormalizedTransaction(**defaults)


def _mock_conn(fetchone_result=None, rowcount=1):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_result
    cur.rowcount = rowcount
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


class TestReconcileOrInsert:
    def test_skipped_when_already_verified(self):
        conn = MagicMock()
        cur = MagicMock()
        # Step 1: _FIND_PENDING_MATCH → None; Step 2: _CHECK_EXISTING → ("verified",)
        cur.fetchone.side_effect = [None, ("verified",)]
        cur.rowcount = 0
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = reconcile_or_insert(conn, _tx())
        assert result.action == "skipped"
        assert result.match is None

    def test_reconciled_when_pending_match_found(self):
        conn = MagicMock()
        cur = MagicMock()
        # Step 1: _FIND_PENDING_MATCH returns (99, "old_hash") — reconcile immediately
        cur.fetchone.side_effect = [(99, "old_hash")]
        cur.rowcount = 1
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = reconcile_or_insert(conn, _tx())
        assert result.action == "reconciled"
        assert result.match is not None
        assert result.match.pending_id == 99

    def test_inserted_when_no_existing_row(self):
        conn = MagicMock()
        cur = MagicMock()
        # Step 1: _FIND_PENDING_MATCH → None; Step 2: _CHECK_EXISTING → None; Step 3: insert
        cur.fetchone.side_effect = [None, None]
        cur.rowcount = 1
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = reconcile_or_insert(conn, _tx())
        assert result.action == "inserted"

    def test_skipped_when_insert_is_duplicate(self):
        conn = MagicMock()
        cur = MagicMock()
        # Step 1: no pending match; Step 2: not verified; Step 3: ON CONFLICT → rowcount=0
        cur.fetchone.side_effect = [None, None]
        cur.rowcount = 0
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = reconcile_or_insert(conn, _tx())
        assert result.action == "skipped"
