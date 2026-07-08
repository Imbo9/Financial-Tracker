"""Run once against Neon (or local DB) to add status/source/source_id columns.
Safe to re-run — uses ADD COLUMN IF NOT EXISTS.

Usage:
    uv run python scripts/migrate_schema.py
"""

from fintracker.settings import settings
from fintracker.storage.db_insert import get_connection

_MIGRATION = """
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS status    TEXT DEFAULT 'verified',
    ADD COLUMN IF NOT EXISTS source    TEXT DEFAULT 'enable_banking',
    ADD COLUMN IF NOT EXISTS source_id TEXT;

CREATE INDEX IF NOT EXISTS idx_transactions_pending
    ON transactions (status, booking_date)
    WHERE status = 'pending';
"""


def main() -> None:
    print(f"Connecting to: {settings.DATABASE_URL[:40]}...")
    conn = get_connection(settings.DATABASE_URL)
    with conn.cursor() as cur:
        cur.execute(_MIGRATION)
    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
