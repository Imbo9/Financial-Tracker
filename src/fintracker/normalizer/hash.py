import hashlib
from datetime import datetime
from decimal import Decimal


def _legacy_amount_repr(amount: float | Decimal) -> str:
    # Historical hashes were computed from Python float repr ("12.5", not "12.50").
    # float() first keeps every stored hash valid after the Decimal migration.
    return str(abs(float(amount)))


def eb_dedup_hash(date: str, amount: float | Decimal, description: str, currency: str) -> str:
    # SHA-256(date[:10] + "|" + abs(amount) + "|" + desc_lower + "|" + currency)
    # NEVER change this formula — it would invalidate all historical hashes.
    payload = f"{date[:10]}|{_legacy_amount_repr(amount)}|{description.lower()}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()


def tasker_dedup_hash(timestamp: datetime, amount: float | Decimal, currency: str) -> str:
    # Truncate to minute so 14:32:45 and 14:32:00 produce the same hash.
    minute = timestamp.strftime("%Y-%m-%dT%H:%M")
    payload = f"tasker|{minute}|{_legacy_amount_repr(amount)}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()


def manual_dedup_hash(booking_date: str, amount: float | Decimal, currency: str) -> str:
    payload = f"manual|{booking_date[:19]}|{_legacy_amount_repr(amount)}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()
