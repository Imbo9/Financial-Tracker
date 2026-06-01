import logging
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.normalizer.normalize import NormalizedTransaction

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
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tx_booking_date ON transactions (booking_date DESC);
CREATE INDEX IF NOT EXISTS idx_tx_is_internal  ON transactions (is_internal);
CREATE INDEX IF NOT EXISTS idx_tx_category     ON transactions (category);

CREATE OR REPLACE VIEW real_transactions AS
    SELECT * FROM transactions WHERE is_internal = FALSE;
"""

_INSERT = """
INSERT INTO transactions
    (dedup_hash, booking_date, amount, currency, eur_amount,
     description, merchant_name, account_id, is_internal, category, subcategory)
VALUES
    (%(dedup_hash)s, %(booking_date)s, %(amount)s, %(currency)s, %(eur_amount)s,
     %(description)s, %(merchant_name)s, %(account_id)s, %(is_internal)s,
     %(category)s, %(subcategory)s)
ON CONFLICT (dedup_hash) DO NOTHING
"""


def get_connection(database_url: str):
    return psycopg2.connect(database_url)


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_DDL)
    conn.commit()
    log.info("Schema ready")


def insert_transactions(conn, transactions: list[NormalizedTransaction]) -> int:
    if not transactions:
        return 0
    rows = [
        {
            "dedup_hash": t.dedup_hash,
            "booking_date": t.booking_date,
            "amount": t.amount,
            "currency": t.currency,
            "eur_amount": t.eur_amount,
            "description": t.description,
            "merchant_name": t.merchant_name,
            "account_id": t.account_id,
            "is_internal": t.is_internal,
            "category": t.category,
            "subcategory": t.subcategory,
        }
        for t in transactions
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, _INSERT, rows, page_size=200)
    conn.commit()
    log.info("Upserted %d rows (duplicates silently skipped)", len(rows))
    return len(rows)
