import logging
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from fintracker.settings import settings

log = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        # Single-user app behind one uvicorn worker: a tiny pool is plenty.
        _pool = ConnectionPool(settings.DATABASE_URL, min_size=1, max_size=4, open=True)
        log.info("DB connection pool opened")
    return _pool


@contextmanager
def db_conn() -> Iterator[psycopg.Connection]:
    """Pooled connection; commits on clean exit, rolls back on exception."""
    with get_pool().connection() as conn:
        yield conn


def direct_connection() -> psycopg.Connection:
    """Unpooled connection for batch jobs (pipeline.py)."""
    return psycopg.connect(settings.DATABASE_URL)
