from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fintracker.models.transaction import NormalizedTransaction
from fintracker.storage.db_insert import insert_transaction
from fintracker.storage.reconcile import reconcile_or_insert

pytestmark = pytest.mark.integration


def _eb_tx(**kw) -> NormalizedTransaction:
    base = {
        "dedup_hash": "ebhash1",
        "booking_date": datetime(2026, 7, 1, tzinfo=UTC),
        "amount": Decimal("-12.50"),
        "currency": "EUR",
        "eur_amount": Decimal("-12.50"),
        "description": "Esselunga",
        "merchant_name": "Esselunga",
        "account_id": "acc1",
        "status": "verified",
        "source": "enable_banking",
    }
    base.update(kw)
    return NormalizedTransaction(**base)


def _pending_tasker_tx(**kw) -> NormalizedTransaction:
    base = {
        "dedup_hash": "taskerhash1",
        "booking_date": datetime(2026, 7, 1, 14, 32, tzinfo=UTC),
        "amount": Decimal("-12.50"),
        "currency": "EUR",
        "eur_amount": Decimal("-12.50"),
        "description": "You paid EUR12.50 at Esselunga",
        "merchant_name": "Esselunga",
        "status": "pending",
        "source": "tasker",
    }
    base.update(kw)
    return NormalizedTransaction(**base)


def test_inserts_fresh_transaction(db_conn):
    result = reconcile_or_insert(db_conn, _eb_tx())
    assert result.action == "inserted"
    with db_conn.cursor() as cur:
        cur.execute("SELECT status, source FROM transactions WHERE dedup_hash = 'ebhash1'")
        assert cur.fetchone() == ("verified", "enable_banking")


def test_skips_already_verified(db_conn):
    reconcile_or_insert(db_conn, _eb_tx())
    result = reconcile_or_insert(db_conn, _eb_tx())
    assert result.action == "skipped"
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM transactions")
        row = cur.fetchone()
        assert row is not None and row[0] == 1


def test_reconciles_pending_tasker_row(db_conn):
    insert_transaction(db_conn, _pending_tasker_tx())
    result = reconcile_or_insert(db_conn, _eb_tx())
    assert result.action == "reconciled"
    assert result.match is not None
    assert result.match.pending_dedup_hash == "taskerhash1"
    with db_conn.cursor() as cur:
        cur.execute("SELECT status, dedup_hash, source FROM transactions")
        rows = cur.fetchall()
    assert rows == [("verified", "ebhash1", "enable_banking")]


def test_keeps_tasker_hash_when_eb_hash_already_exists(db_conn):
    insert_transaction(db_conn, _eb_tx(dedup_hash="ebhash1", amount=Decimal("-99")))
    insert_transaction(db_conn, _pending_tasker_tx())
    result = reconcile_or_insert(db_conn, _eb_tx())  # ebhash1 already taken by another row
    assert result.action == "reconciled"
    assert result.match is not None
    assert result.match.pending_dedup_hash == "taskerhash1"
    with db_conn.cursor() as cur:
        cur.execute("SELECT dedup_hash FROM transactions WHERE status = 'verified' ORDER BY id")
        hashes = [r[0] for r in cur.fetchall()]
    assert "taskerhash1" in hashes  # pending row kept its own hash (no UniqueViolation)
