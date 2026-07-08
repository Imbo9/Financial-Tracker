import argparse
import logging

from fintracker.settings import settings, setup_logging

setup_logging()
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

    from fintracker.storage.db import direct_connection
    from fintracker.storage.db_insert import ensure_schema

    log.info("Connecting to database ...")
    conn = direct_connection()
    ensure_schema(conn)

    if not args.skip_fetch:
        from fintracker.sync.eb_sync import run_eb_sync

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

    if args.skip_categorize:
        log.info("Skipping categorization (--skip-categorize)")
    elif not settings.ANTHROPIC_API_KEY.get_secret_value():
        log.warning("ANTHROPIC_API_KEY not set — skipping categorization")
    else:
        from fintracker.categorizer.categorize import categorize_uncategorized

        log.info("Categorizing with Claude ...")
        n = categorize_uncategorized(conn)
        log.info("Categorized %d transactions", n)

    conn.close()
    log.info("Pipeline complete")


if __name__ == "__main__":
    main()
