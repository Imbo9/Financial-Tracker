import logging

from fintracker.models.transaction import NormalizedTransaction

log = logging.getLogger(__name__)

INSERT_SQL = """
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


def insert_transactions(conn, transactions: list[NormalizedTransaction]) -> int:
    if not transactions:
        return 0
    rows = [t.model_dump() for t in transactions]
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
    conn.commit()
    log.info("Upserted %d rows (duplicates silently skipped)", len(rows))
    return len(rows)


def insert_transaction(conn, tx: NormalizedTransaction) -> bool:
    """Insert one transaction. Returns True if inserted, False if duplicate."""
    with conn.cursor() as cur:
        cur.execute(INSERT_SQL, tx.model_dump())
        inserted = cur.rowcount > 0
    conn.commit()
    return inserted
