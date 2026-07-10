import os

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance_test"
)


@pytest.fixture()
def db_conn():
    try:
        conn = psycopg.connect(TEST_DATABASE_URL, autocommit=False)
    except psycopg.OperationalError:
        if os.environ.get("CI"):
            raise  # never silently skip in CI — a green check must mean tests ran
        pytest.skip("Postgres not reachable — start it with: docker compose up db -d")
    # Apply the real schema via Alembic against the test DB
    from alembic import command
    from alembic.config import Config

    from fintracker.settings import settings

    cfg = Config("alembic.ini")
    settings.DATABASE_URL = TEST_DATABASE_URL  # env.py reads settings
    command.upgrade(cfg, "head")

    with conn.cursor() as cur:
        cur.execute("TRUNCATE transactions RESTART IDENTITY")
    conn.commit()
    yield conn
    conn.close()
