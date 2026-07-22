"""accounts: type/is_manual/currency/created_at for the manual-account registry (SP-1)"""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS type        TEXT        NOT NULL DEFAULT 'bank',
    ADD COLUMN IF NOT EXISTS is_manual   BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS currency    CHAR(3)     NOT NULL DEFAULT 'EUR',
    ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE accounts
    DROP COLUMN IF EXISTS type,
    DROP COLUMN IF EXISTS is_manual,
    DROP COLUMN IF EXISTS currency,
    DROP COLUMN IF EXISTS created_at;
""")
