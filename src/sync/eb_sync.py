import logging
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import config.settings as settings  # noqa: E402
from src.ingestion.fetch_transactions import fetch_transactions  # noqa: E402
from src.normalizer.normalize import fetch_ecb_rates, normalize  # noqa: E402
from src.notifications.telegram import notify_transaction, send_telegram  # noqa: E402
from src.storage.db_insert import connection  # noqa: E402
from src.storage.reconcile import reconcile_or_insert  # noqa: E402

log = logging.getLogger(__name__)


@dataclass
class SyncStats:
    inserted: int = 0
    reconciled: int = 0
    skipped: int = 0


def _alert(text: str) -> None:
    send_telegram(text, token=settings.TELEGRAM_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID)


def run_eb_sync(days_back: int = 2) -> SyncStats:
    """Fetch last N days from Enable Banking, reconcile pending rows, insert new ones.

    Used by both the Railway cron (via pipeline.py) and POST /sync.
    """
    log.info("EB sync started (last %d days)", days_back)
    stats = SyncStats()

    try:
        raw_by_account = fetch_transactions(days_back=days_back)
    except Exception as exc:
        log.error("EB sync fetch failed: %s", exc)
        _alert("⚠️ EB sync failed — check Railway logs")
        return stats

    if not raw_by_account:
        log.error("EB sync returned no accounts — session likely expired")
        _alert(
            "⚠️ EB sync returned no accounts — session likely expired. "
            "Renew: uv run python src/auth/enable_banking_auth.py"
        )
        return stats

    ecb_rates = fetch_ecb_rates()
    with connection(settings.DATABASE_URL) as conn:
        for account_id, raw_txs in raw_by_account.items():
            for tx in normalize(raw_txs, account_id, ecb_rates):
                result = reconcile_or_insert(conn, tx)
                if result.action == "inserted":
                    notify_transaction(
                        tx, token=settings.TELEGRAM_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID
                    )
                    stats.inserted += 1
                elif result.action == "reconciled":
                    stats.reconciled += 1
                else:
                    stats.skipped += 1

    log.info(
        "EB sync done — inserted: %d, reconciled: %d, skipped: %d",
        stats.inserted,
        stats.reconciled,
        stats.skipped,
    )
    return stats
