"""baseline: schema as deployed on Neon (2026-07)"""

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("""
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
""")


def downgrade() -> None:
    raise NotImplementedError("baseline is not reversible")
