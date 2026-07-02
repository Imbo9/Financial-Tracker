import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.transaction import NormalizedTransaction

log = logging.getLogger(__name__)

_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS transactions (
    id            SERIAL PRIMARY KEY,
    dedup_hash    TEXT        NOT NULL UNIQUE,
    booking_date  TIMESTAMPTZ NOT NULL,
    amount        NUMERIC     NOT NULL,
    currency      CHAR(3)     NOT NULL,
    eur_amount    NUMERIC     NOT NULL,
    description   TEXT,
    merchant_name TEXT,
    account_id    TEXT,
    is_internal   BOOL        NOT NULL DEFAULT FALSE,
    category      TEXT,
    subcategory   TEXT,
    embedding     vector(1536),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status        TEXT        NOT NULL DEFAULT 'verified',
    source        TEXT        NOT NULL DEFAULT 'enable_banking',
    source_id     TEXT
);

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS status    TEXT NOT NULL DEFAULT 'verified';
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS source    TEXT NOT NULL DEFAULT 'enable_banking';
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS source_id TEXT;

CREATE INDEX IF NOT EXISTS idx_transactions_pending
    ON transactions (status, booking_date)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_tx_booking_date ON transactions (booking_date DESC);
CREATE INDEX IF NOT EXISTS idx_tx_is_internal  ON transactions (is_internal);
CREATE INDEX IF NOT EXISTS idx_tx_category     ON transactions (category);

CREATE OR REPLACE VIEW real_transactions AS
    SELECT * FROM transactions WHERE is_internal = FALSE;
"""

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


def get_connection(database_url: str):
    return psycopg2.connect(database_url)


@contextmanager
def connection(database_url: str):
    """Context-managed psycopg2 connection — closes on exit."""
    conn = get_connection(database_url)
    try:
        yield conn
    finally:
        conn.close()


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_DDL)
    conn.commit()
    log.info("Schema ready")


def insert_transactions(conn, transactions: list[NormalizedTransaction]) -> int:
    if not transactions:
        return 0
    rows = [t.model_dump() for t in transactions]
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, INSERT_SQL, rows, page_size=200)
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
