import re
from decimal import Decimal, InvalidOperation

from fintracker.models.tasker import TaskerPayload
from fintracker.models.transaction import NormalizedTransaction
from fintracker.normalizer.hash import tasker_dedup_hash

# Revolut push-notification patterns (IT locale, English text)
# Group names: ccy, amount, merchant (optional)
_AMT = r"\d+(?:[.,]\d+)*"  # matches "0.13" or "1,234.56" without trailing dot

_PATTERNS: list[tuple[str, re.Pattern]] = [
    # "Rosalia sent you EUR0.01. Tap to say thank you 💰"
    (
        "credit",
        re.compile(
            rf"(?P<merchant>.+?)\s+sent you (?P<ccy>[A-Z]{{3}})(?P<amount>{_AMT})",
            re.IGNORECASE,
        ),
    ),
    # "Sent you EUR0.13. Tap to say thank you 💰"  (no sender name)
    ("credit", re.compile(rf"Sent you (?P<ccy>[A-Z]{{3}})(?P<amount>{_AMT})", re.IGNORECASE)),
    # "You paid EUR5.00 at Costa Coffee"
    (
        "debit",
        re.compile(
            rf"You paid (?P<ccy>[A-Z]{{3}})(?P<amount>{_AMT}) at (?P<merchant>.+?)(?:\.|$)",
            re.IGNORECASE,
        ),
    ),
    # "EUR5.00 paid to Costa Coffee"
    (
        "debit",
        re.compile(
            rf"(?P<ccy>[A-Z]{{3}})(?P<amount>{_AMT}) paid to (?P<merchant>.+?)(?:\.|$)",
            re.IGNORECASE,
        ),
    ),
    # "You sent EUR0.01 to Name"
    (
        "debit",
        re.compile(
            rf"You sent (?P<ccy>[A-Z]{{3}})(?P<amount>{_AMT}) to (?P<merchant>.+?)(?:\.|$)",
            re.IGNORECASE,
        ),
    ),
    # "EUR5.00 from Name"  (generic inbound)
    (
        "credit",
        re.compile(
            rf"(?P<ccy>[A-Z]{{3}})(?P<amount>{_AMT}) from (?P<merchant>.+?)(?:\.|$)",
            re.IGNORECASE,
        ),
    ),
]


def _parse_raw_text(raw_text: str) -> tuple[Decimal, str, str | None, str] | None:
    """Return (amount_signed, currency, merchant, direction) or None if no pattern matches."""
    for direction, pat in _PATTERNS:
        m = pat.search(raw_text)
        if m:
            ccy = m.group("ccy").upper()
            raw = m.group("amount")
            # Normalise locale: "1.234,56" (IT) → "1234.56", "1,234.56" (EN) → "1234.56"
            if "," in raw and raw.rindex(",") > raw.rfind("."):
                amt_str = raw.replace(".", "").replace(",", ".")
            else:
                amt_str = raw.replace(",", "")
            try:
                amt = Decimal(amt_str)
            except InvalidOperation:
                continue
            merchant = m.groupdict().get("merchant")
            if merchant:
                merchant = merchant.strip()
            signed = amt if direction == "credit" else -amt
            return signed, ccy, merchant, direction
    return None


def parse_tasker_payload(payload: TaskerPayload) -> NormalizedTransaction:
    """Convert a Tasker push-notification payload into a NormalizedTransaction.

    Amount is always stored as eur_amount too (no FX conversion — Revolut IT
    sends EUR amounts; non-EUR amounts will be reconciled by the EB sync).
    """
    if payload.parse_status == "ok" and payload.amount is not None:
        raw_amount = abs(Decimal(payload.amount))
        amount = -raw_amount if payload.direction == "debit" else raw_amount
        currency = payload.currency or "EUR"
        merchant = payload.merchant
    else:
        # Try server-side parsing of raw_text regardless of parse_status
        parsed = _parse_raw_text(payload.raw_text or "")
        if parsed:
            amount, currency, merchant, _dir = parsed
            merchant = merchant or payload.merchant  # fallback to notification title
        else:
            amount = Decimal("0")
            currency = payload.currency or "EUR"
            merchant = payload.merchant  # notification title from MacroDroid {not_title}

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
