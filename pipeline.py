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

    from src.storage.db_insert import ensure_schema, get_connection, insert_transactions

    log.info("Connecting to database ...")
    conn = get_connection(settings.DATABASE_URL)
    ensure_schema(conn)

    if not args.skip_fetch:
        from src.ingestion.fetch_transactions import fetch_transactions
        from src.normalizer.normalize import fetch_ecb_rates, normalize

        log.info("Fetching transactions (last %d days) ...", args.days)
        raw_by_account = fetch_transactions(days_back=args.days)

        if not raw_by_account:
            log.warning(
                "No transactions fetched — check session token and account IDs in config/.env"
            )

        ecb_rates = fetch_ecb_rates()
        all_normalized = []
        for account_id, raw_txs in raw_by_account.items():
            normalized = normalize(raw_txs, account_id, ecb_rates)
            n_internal = sum(1 for t in normalized if t.is_internal)
            log.info(
                "Account %s: %d raw → %d normalized (%d internal)",
                account_id[:8],
                len(raw_txs),
                len(normalized),
                n_internal,
            )
            all_normalized.extend(normalized)

        n = insert_transactions(conn, all_normalized)
        log.info("Stored %d transactions", n)
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
