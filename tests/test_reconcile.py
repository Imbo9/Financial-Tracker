from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from fintracker.models.transaction import NormalizedTransaction
from fintracker.storage.reconcile import reconcile_or_insert


def _tx(**kwargs) -> NormalizedTransaction:
    # Explicit `Any` values: this dict deliberately mixes str/datetime/float and is later
    # overridden with arbitrary per-test kwargs before being splatted into the pydantic
    # model, so the values can't be narrowed to the model's Literal fields ahead of time.
    defaults: dict[str, Any] = {
        "dedup_hash": "abc123",
        "booking_date": datetime(2026, 6, 7, 10, 0, 0, tzinfo=UTC),
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


# Fresh-insert, pending-match, skip-already-verified and keep-hash-on-collision scenarios
# are exercised for real against Postgres in tests/integration/test_reconcile_pg.py, so the
# fetchone-sequence mocks that used to cover them here were removed (they verified the mock
# was called correctly, not that the SQL was correct).
class TestReconcileOrInsert:
    def test_skipped_when_insert_is_duplicate(self):
        # ON CONFLICT DO NOTHING -> rowcount 0: dedup_hash collides with an existing
        # non-verified row. None of the integration tests hit this branch (they only ever
        # insert fresh hashes), so it stays here as a mock-based test of the idempotence
        # invariant (CLAUDE.md: "re-running is always safe").
        conn = MagicMock()
        cur = MagicMock()
        # Step 1: no pending match; Step 2: not verified; Step 3: insert
        cur.fetchone.side_effect = [None, None]
        cur.rowcount = 0
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = reconcile_or_insert(conn, _tx())
        assert result.action == "skipped"
