import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.reconciliation import ReconciliationMatch, ReconciliationResult
from src.models.transaction import NormalizedTransaction

log = logging.getLogger(__name__)

_CHECK_EXISTING = "SELECT status FROM transactions WHERE dedup_hash = %s LIMIT 1"

_FIND_PENDING_MATCH = """
SELECT id, dedup_hash
FROM transactions
WHERE status = 'pending'
  AND amount = %s
  AND currency = %s
  AND ABS(EXTRACT(EPOCH FROM (booking_date - %s))) <= 600
LIMIT 1
"""

_UPDATE_TO_VERIFIED = """
UPDATE transactions
SET dedup_hash   = %s,
    status       = 'verified',
    booking_date = %s,
    merchant_name = COALESCE(%s, merchant_name),
    account_id   = COALESCE(%s, account_id),
    source       = %s,
    source_id    = %s
WHERE id = %s
"""

_INSERT = """
INSERT INTO transactions
    (dedup_hash, booking_date, amount, currency, eur_amount,
     description, merchant_name, account_id, is_internal, category, subcategory,
     status, source, source_id)
VALUES
    (%(dedup_hash)s, %(booking_date)s, %(amount)s, %(currency)s, %(eur_amount)s,
     %(description)s, %(merchant_name)s, %(account_id)s, %(is_internal)s,
     %(category)s, %(subcategory)s, %(status)s, %(source)s, %(source_id)s)
ON CONFLICT (dedup_hash) DO NOTHING
"""


def reconcile_or_insert(conn, tx: NormalizedTransaction) -> ReconciliationResult:
    """Process one EB transaction: skip if verified, reconcile if pending match, else insert."""
    with conn.cursor() as cur:
        cur.execute(_CHECK_EXISTING, (tx.dedup_hash,))
        row = cur.fetchone()

    if row is not None:
        if row[0] == "verified":
            return ReconciliationResult(match=None, action="skipped")
        # Row exists as pending — find the pending match by amount/time
        with conn.cursor() as cur:
            cur.execute(_FIND_PENDING_MATCH, (tx.amount, tx.currency, tx.booking_date))
            match_row = cur.fetchone()
        if match_row:
            pending_id, pending_hash = match_row
            with conn.cursor() as cur:
                cur.execute(
                    _UPDATE_TO_VERIFIED,
                    (
                        tx.dedup_hash,
                        tx.booking_date,
                        tx.merchant_name,
                        tx.account_id,
                        tx.source,
                        tx.source_id,
                        pending_id,
                    ),
                )
            conn.commit()
            log.info("Reconciled pending #%d → verified (%s)", pending_id, tx.dedup_hash[:8])
            return ReconciliationResult(
                match=ReconciliationMatch(pending_id=pending_id, pending_dedup_hash=pending_hash),
                action="reconciled",
            )

    # No existing row — insert fresh
    with conn.cursor() as cur:
        cur.execute(_INSERT, tx.model_dump())
        inserted = cur.rowcount > 0
    conn.commit()

    if inserted:
        log.info("Inserted new verified transaction %s", tx.dedup_hash[:8])
        return ReconciliationResult(match=None, action="inserted")
    return ReconciliationResult(match=None, action="skipped")
