import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.models.tasker import TaskerPayload
from src.models.transaction import NormalizedTransaction
from src.normalizer.hash import tasker_dedup_hash


def parse_tasker_payload(payload: TaskerPayload) -> NormalizedTransaction:
    """Convert a Tasker push-notification payload into a NormalizedTransaction.

    Amount is always stored as eur_amount too (no FX conversion — Revolut IT
    sends EUR amounts; non-EUR amounts will be reconciled by the EB sync).
    """
    if payload.parse_status == "failed" or payload.amount is None:
        amount = 0.0
        currency = payload.currency or "EUR"
        merchant = None
    else:
        raw_amount = abs(float(payload.amount))
        amount = -raw_amount if payload.direction == "debit" else raw_amount
        currency = payload.currency or "EUR"
        merchant = payload.merchant

    dedup = tasker_dedup_hash(payload.device_timestamp, abs(amount), currency)

    return NormalizedTransaction(
        dedup_hash=dedup,
        booking_date=payload.device_timestamp,
        amount=amount,
        currency=currency,
        eur_amount=amount,  # same as amount; EB sync will correct on reconciliation
        description=payload.raw_text,
        merchant_name=merchant,
        account_id=None,
        is_internal=False,
        status="pending",
        source="tasker",
        source_id=None,
    )
