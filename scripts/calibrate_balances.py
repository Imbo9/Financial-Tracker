"""One-shot balance calibration: opening = EB current balance - sum of known deltas.

Includes is_internal rows on purpose - top-ups/vault moves change the real balance.
Run with prod env:
  railway run --service just-comfort -- uv run python scripts/calibrate_balances.py
Re-runnable anytime: it refreshes opening_balance/eb_balance/calibrated_at per account.
"""

import logging
import time

import httpx

from fintracker.ingestion.fetch_transactions import fetch_balances
from fintracker.settings import settings
from fintracker.storage.db import direct_connection

log = logging.getLogger(__name__)

_INTER_ACCOUNT_DELAY_SEC = 2


def calibrate(conn, client: httpx.Client, account_uids: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for i, uid in enumerate(account_uids):
        if i:
            time.sleep(_INTER_ACCOUNT_DELAY_SEC)
        eb_balance = fetch_balances(client, uid)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(eur_amount), 0) FROM transactions WHERE account_id = %s",
                (uid,),
            )
            delta_sum = cur.fetchone()[0]
            opening = eb_balance - delta_sum
            cur.execute(
                "INSERT INTO accounts (account_uid, opening_balance, eb_balance, calibrated_at)"
                " VALUES (%s, %s, %s, NOW())"
                " ON CONFLICT (account_uid) DO UPDATE SET"
                " opening_balance = EXCLUDED.opening_balance,"
                " eb_balance = EXCLUDED.eb_balance,"
                " calibrated_at = EXCLUDED.calibrated_at",
                (uid, opening, eb_balance),
            )
        conn.commit()
        results[uid] = {"eb_balance": eb_balance, "delta_sum": delta_sum, "opening": opening}
        log.info("%s: eb=%s deltas=%s opening=%s", uid[:8], eb_balance, delta_sum, opening)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with httpx.Client(timeout=30) as http_client:
        calibrate(direct_connection(), http_client, settings.ENABLE_BANKING_ACCOUNT_IDS)
