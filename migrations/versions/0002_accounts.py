"""accounts: per-account opening balances for absolute balance math (spec 2026-07-13)"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS accounts (
    account_uid     TEXT PRIMARY KEY,
    display_name    TEXT,
    opening_balance NUMERIC     NOT NULL DEFAULT 0,
    eb_balance      NUMERIC,
    calibrated_at   TIMESTAMPTZ
);
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accounts;")
