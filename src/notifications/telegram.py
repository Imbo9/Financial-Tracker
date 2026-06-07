import logging
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.transaction import NormalizedTransaction

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"


def build_message(tx: NormalizedTransaction) -> str:
    if tx.amount == 0.0 and tx.merchant_name is None:
        return "⚠️ Notifica Revolut non parsata — controlla raw_text in DB"
    sign = "🔴" if tx.amount < 0 else "🟢"
    if tx.status == "verified":
        sign = "🟢"
    merchant = tx.merchant_name or "?"
    amount_str = f"{abs(tx.amount):.2f} {tx.currency}"
    return f"{sign} {'-' if tx.amount < 0 else '+'}{amount_str} · {merchant} [{tx.status}]"


def send_telegram(text: str, *, token: str, chat_id: str) -> None:
    if not token or not chat_id:
        log.warning("Telegram not configured — skipping notification")
        return
    try:
        resp = httpx.post(
            _API.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("Telegram notification sent")
    except Exception as exc:
        log.warning("Failed to send Telegram notification: %s", exc)


def notify_transaction(tx: NormalizedTransaction, *, token: str, chat_id: str) -> None:
    send_telegram(build_message(tx), token=token, chat_id=chat_id)
