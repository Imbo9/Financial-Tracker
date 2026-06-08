import hashlib
from datetime import datetime


def eb_dedup_hash(date: str, amount: float, description: str, currency: str) -> str:
    # SHA-256(date[:10] + "|" + abs(amount) + "|" + desc_lower + "|" + currency)
    # NEVER change this formula — it would invalidate all historical hashes.
    payload = f"{date[:10]}|{abs(amount)}|{description.lower()}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()


def tasker_dedup_hash(timestamp: datetime, amount: float, currency: str) -> str:
    # Truncate to minute so 14:32:45 and 14:32:00 produce the same hash.
    minute = timestamp.strftime("%Y-%m-%dT%H:%M")
    payload = f"tasker|{minute}|{abs(amount)}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()


def manual_dedup_hash(booking_date: str, amount: float, currency: str) -> str:
    payload = f"manual|{booking_date[:19]}|{abs(amount)}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()
