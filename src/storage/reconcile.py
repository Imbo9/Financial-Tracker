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
  AND booking_date::date = %s::date
ORDER BY created_at ASC
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
WHERE id = %s AND status = 'pending'
"""

# Used when the EB dedup_hash already exists in a separate row — keep Tasker's own hash.
_UPDATE_TO_VERIFIED_KEEP_HASH = """
UPDATE transactions
SET status       = 'verified',
    booking_date = %s,
    merchant_name = COALESCE(%s, merchant_name),
    account_id   = COALESCE(%s, account_id),
    source       = %s,
    source_id    = %s
WHERE id = %s AND status = 'pending'
"""

_CHECK_ID_FOR_HASH = "SELECT id FROM transactions WHERE dedup_hash = %s LIMIT 1"

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
    """Process one EB transaction: reconcile pending if match, skip if verified, else insert."""
    # Step 1: check for a pending Tasker row matching amount + currency + same day
    with conn.cursor() as cur:
        cur.execute(_FIND_PENDING_MATCH, (tx.amount, tx.currency, tx.booking_date))
        match_row = cur.fetchone()

    if match_row:
        pending_id, pending_hash = match_row
        # If EB hash already exists as a separate row (e.g. from a prior sync before this fix),
        # keep the Tasker dedup_hash to avoid a UniqueViolation.
        with conn.cursor() as cur:
            cur.execute(_CHECK_ID_FOR_HASH, (tx.dedup_hash,))
            eb_already_exists = cur.fetchone() is not None

        if eb_already_exists:
            with conn.cursor() as cur:
                cur.execute(
                    _UPDATE_TO_VERIFIED_KEEP_HASH,
                    (
                        tx.booking_date,
                        tx.merchant_name,
                        tx.account_id,
                        tx.source,
                        tx.source_id,
                        pending_id,
                    ),
                )
        else:
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

    # Step 2: no pending match — check if already verified
    with conn.cursor() as cur:
        cur.execute(_CHECK_EXISTING, (tx.dedup_hash,))
        row = cur.fetchone()

    if row is not None and row[0] == "verified":
        return ReconciliationResult(match=None, action="skipped")

    # Step 3: not verified, no pending match — insert fresh
    with conn.cursor() as cur:
        cur.execute(_INSERT, tx.model_dump())
        inserted = cur.rowcount > 0
    conn.commit()

    if inserted:
        log.info("Inserted new verified transaction %s", tx.dedup_hash[:8])
        return ReconciliationResult(match=None, action="inserted")
    return ReconciliationResult(match=None, action="skipped")
