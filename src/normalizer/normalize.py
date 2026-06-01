import hashlib
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

log = logging.getLogger(__name__)

# Seven patterns for Revolut-internal moves — stored with is_internal=TRUE,
# excluded from the real_transactions view. Do not add patterns that could
# match real merchant transactions.
INTERNAL_PATTERNS = [
    re.compile(r"^top[\s\-]?up\b", re.IGNORECASE),
    re.compile(r"^exchanged?\s+(from|to)\b", re.IGNORECASE),
    re.compile(r"\bsavings\s+vault\b", re.IGNORECASE),
    re.compile(r"^balance\s+migration\b", re.IGNORECASE),
    re.compile(r"^revolut\s+@", re.IGNORECASE),
    re.compile(r"\b(from|to)\s+vault\b", re.IGNORECASE),
    re.compile(r"^(crypto\s+exchange|crypto\s+purchase|cryptocurrency)\b", re.IGNORECASE),
]

_ecb_cache: dict[str, float] = {}


def fetch_ecb_rates() -> dict[str, float]:
    """Return {currency: rate} where 1 EUR = rate CCY (ECB reference rates)."""
    if _ecb_cache:
        return _ecb_cache
    try:
        url = (
            "https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A"
            "?lastNObservations=1&format=jsondata"
        )
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        series = data["dataSets"][0]["series"]
        dims = data["structure"]["dimensions"]["series"]
        currency_idx = next(i for i, d in enumerate(dims) if d["id"] == "CURRENCY")
        for key, series_data in series.items():
            parts = key.split(":")
            currency = dims[currency_idx]["values"][int(parts[currency_idx])]["id"]
            obs = series_data.get("observations", {})
            if obs:
                rate = float(list(obs.values())[-1][0])
                _ecb_cache[currency] = rate
        log.info("Loaded ECB rates for %d currencies", len(_ecb_cache))
    except Exception as exc:
        log.warning("Failed to fetch ECB rates: %s", exc)
    return _ecb_cache


@dataclass
class NormalizedTransaction:
    dedup_hash: str
    booking_date: str       # YYYY-MM-DDT00:00:00Z
    amount: float           # negative = outflow, positive = inflow
    currency: str
    eur_amount: float
    description: str
    merchant_name: str      # cleaned — only this is sent to the categorizer
    account_id: str
    is_internal: bool
    category: str | None = None
    subcategory: str | None = None
    raw: dict = field(default_factory=dict)


def _dedup_hash(date: str, amount: float, description: str, currency: str) -> str:
    # SHA-256(date[:10] + "|" + abs(amount) + "|" + desc_lower + "|" + currency)
    # NEVER change this formula — it would invalidate all historical hashes.
    payload = f"{date[:10]}|{abs(amount)}|{description.lower()}|{currency}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _to_eur(amount: float, currency: str, rates: dict[str, float]) -> float:
    if currency == "EUR":
        return amount
    rate = rates.get(currency)
    if rate is None:
        log.warning("No ECB rate for %s — storing original amount as eur_amount", currency)
        return amount
    return amount / rate


def _is_internal(description: str) -> bool:
    return any(p.search(description) for p in INTERNAL_PATTERNS)


def _extract_merchant(raw_tx: dict) -> str:
    # Enable Banking uses creditor.name for debits, debtor.name for credits
    indicator = raw_tx.get("credit_debit_indicator", "DBIT")
    if indicator == "DBIT":
        name = (raw_tx.get("creditor") or {}).get("name", "")
    else:
        name = (raw_tx.get("debtor") or {}).get("name", "")
    if not name:
        # remittance_information is an array of strings
        remittance = raw_tx.get("remittance_information", [])
        name = " ".join(remittance) if isinstance(remittance, list) else str(remittance)
    name = re.sub(r"\s+\d{4,}$", "", name)   # strip trailing card/ref numbers
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name or "Unknown"


def _parse_amount(raw_tx: dict) -> float:
    # amount is always a positive string; sign comes from credit_debit_indicator
    amount_data = raw_tx.get("transaction_amount", {})
    amount = abs(float(amount_data.get("amount", 0)))
    if raw_tx.get("credit_debit_indicator", "DBIT") == "DBIT":
        return -amount   # outflow
    return amount        # inflow


def _description(raw_tx: dict) -> str:
    remittance = raw_tx.get("remittance_information", [])
    if isinstance(remittance, list):
        return " | ".join(remittance).strip()
    return str(remittance).strip()


def normalize(
    raw_transactions: list[dict],
    account_id: str,
    ecb_rates: dict[str, float] | None = None,
) -> list[NormalizedTransaction]:
    if ecb_rates is None:
        ecb_rates = fetch_ecb_rates()
    results = []
    for tx in raw_transactions:
        try:
            # Only sync booked transactions (PDNG and INFO are skipped)
            if tx.get("status") not in ("BOOK", None):
                continue
            date_str = tx.get("booking_date", "")
            if not date_str:
                log.warning("Transaction missing booking_date, skipping: %s", tx)
                continue
            currency = (tx.get("transaction_amount") or {}).get("currency", "EUR")
            amount = _parse_amount(tx)
            booking_date = f"{date_str[:10]}T00:00:00Z"
            description = _description(tx)
            merchant = _extract_merchant(tx)
            eur_amount = _to_eur(amount, currency, ecb_rates)
            dedup = _dedup_hash(date_str, amount, description, currency)
            results.append(
                NormalizedTransaction(
                    dedup_hash=dedup,
                    booking_date=booking_date,
                    amount=amount,
                    currency=currency,
                    eur_amount=eur_amount,
                    description=description,
                    merchant_name=merchant,
                    account_id=account_id,
                    is_internal=_is_internal(description),
                    raw=tx,
                )
            )
        except Exception as exc:
            log.warning("Failed to normalize transaction: %s — %s", tx, exc)
    return results
