import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import config.settings as settings
from src.ingestion.fetch_transactions import fetch_transactions
from src.normalizer.normalize import fetch_ecb_rates, normalize
from src.notifications.telegram import notify_transaction
from src.storage.db_insert import get_connection
from src.storage.reconcile import reconcile_or_insert

log = logging.getLogger(__name__)


def run_eb_sync(days_back: int = 2) -> None:
    """Fetch last N days from Enable Banking, reconcile pending rows, insert new ones."""
    log.info("EB sync started (last %d days)", days_back)
    try:
        raw_by_account = fetch_transactions(days_back=days_back)
    except Exception as exc:
        log.error("EB sync fetch failed: %s", exc)
        return

    ecb_rates = fetch_ecb_rates()
    conn = get_connection(settings.DATABASE_URL)
    try:
        inserted_count = reconciled_count = skipped_count = 0
        for account_id, raw_txs in raw_by_account.items():
            normalized = normalize(raw_txs, account_id, ecb_rates)
            for tx in normalized:
                result = reconcile_or_insert(conn, tx)
                if result.action == "inserted":
                    notify_transaction(
                        tx,
                        token=settings.TELEGRAM_TOKEN,
                        chat_id=settings.TELEGRAM_CHAT_ID,
                    )
                    inserted_count += 1
                elif result.action == "reconciled":
                    reconciled_count += 1
                else:
                    skipped_count += 1
    finally:
        conn.close()

    log.info(
        "EB sync done — inserted: %d, reconciled: %d, skipped: %d",
        inserted_count,
        reconciled_count,
        skipped_count,
    )
