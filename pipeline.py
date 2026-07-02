import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config.settings as settings

settings.setup_logging()
log = logging.getLogger("pipeline")


def main() -> None:
    parser = argparse.ArgumentParser(description="Revolut → Postgres finance pipeline")
    parser.add_argument(
        "--days",
        type=int,
        default=settings.FETCH_DAYS_BACK,
        help="Days of history to fetch (default: %(default)s)",
    )
    parser.add_argument("--skip-fetch", action="store_true", help="Skip Enable Banking fetch")
    parser.add_argument("--skip-categorize", action="store_true", help="Skip Claude categorization")
    args = parser.parse_args()

    from src.storage.db_insert import ensure_schema, get_connection

    log.info("Connecting to database ...")
    conn = get_connection(settings.DATABASE_URL)
    ensure_schema(conn)

    if not args.skip_fetch:
        from src.sync.eb_sync import run_eb_sync

        log.info("Syncing transactions (last %d days) ...", args.days)
        stats = run_eb_sync(days_back=args.days)
        log.info(
            "Stored %d new, reconciled %d, skipped %d",
            stats.inserted,
            stats.reconciled,
            stats.skipped,
        )
    else:
        log.info("Skipping fetch (--skip-fetch)")

    if not args.skip_categorize:
        from src.categorizer.categorize import categorize_uncategorized

        log.info("Categorizing with Claude ...")
        n = categorize_uncategorized(conn)
        log.info("Categorized %d transactions", n)
    else:
        log.info("Skipping categorization (--skip-categorize)")

    conn.close()
    log.info("Pipeline complete")


if __name__ == "__main__":
    main()
