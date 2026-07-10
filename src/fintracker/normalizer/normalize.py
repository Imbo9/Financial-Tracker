import logging
import re
import time
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from fintracker.models.transaction import NormalizedTransaction
from fintracker.normalizer.hash import eb_dedup_hash

log = logging.getLogger(__name__)

INTERNAL_PATTERNS = [
    re.compile(r"^top[\s\-]?up\b", re.IGNORECASE),
    re.compile(r"^exchanged?\s+(from|to)\b", re.IGNORECASE),
    re.compile(r"\bsavings\s+vault\b", re.IGNORECASE),
    re.compile(r"^balance\s+migration\b", re.IGNORECASE),
    re.compile(r"^revolut\s+@", re.IGNORECASE),
    re.compile(r"\b(from|to)\s+vault\b", re.IGNORECASE),
    re.compile(r"^(crypto\s+exchange|crypto\s+purchase|cryptocurrency)\b", re.IGNORECASE),
]

_ECB_TTL_SECONDS = 12 * 3600  # ECB reference rates update once per day (~16:00 CET)
_ecb_cache: dict[str, float] = {}
_ecb_fetched_at: float = 0.0


def fetch_ecb_rates() -> dict[str, float]:
    """Return {currency: rate} where 1 EUR = rate CCY (ECB reference rates)."""
    global _ecb_fetched_at
    if _ecb_cache and time.monotonic() - _ecb_fetched_at < _ECB_TTL_SECONDS:
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
        fresh: dict[str, float] = {}
        for key, series_data in series.items():
            parts = key.split(":")
            currency = dims[currency_idx]["values"][int(parts[currency_idx])]["id"]
            obs = series_data.get("observations", {})
            if obs:
                raw_value = list(obs.values())[-1][0]
                if raw_value is None:
                    continue
                fresh[currency] = float(raw_value)
        _ecb_cache.clear()
        _ecb_cache.update(fresh)
        _ecb_fetched_at = time.monotonic()
        log.info("Loaded ECB rates for %d currencies", len(_ecb_cache))
    except Exception as exc:
        log.warning("Failed to fetch ECB rates: %s", exc)  # stale cache (if any) still returned
    return _ecb_cache


def _to_eur(amount: Decimal, currency: str, rates: dict[str, float]) -> Decimal:
    if currency == "EUR":
        return amount
    rate = rates.get(currency)
    if rate is None:
        log.error("No ECB rate for %s — storing original amount as eur_amount", currency)
        return amount
    return amount / Decimal(str(rate))


def _is_internal(description: str) -> bool:
    return any(p.search(description) for p in INTERNAL_PATTERNS)


def _extract_merchant(raw_tx: dict) -> str:
    indicator = raw_tx.get("credit_debit_indicator", "DBIT")
    if indicator == "DBIT":
        name = (raw_tx.get("creditor") or {}).get("name", "")
    else:
        name = (raw_tx.get("debtor") or {}).get("name", "")
    if not name:
        remittance = raw_tx.get("remittance_information", [])
        name = " ".join(remittance) if isinstance(remittance, list) else str(remittance)
    name = re.sub(r"\s+\d{4,}$", "", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name or "Unknown"


def _parse_amount(raw_tx: dict) -> Decimal:
    amount_data = raw_tx.get("transaction_amount", {})
    amount = abs(Decimal(str(amount_data.get("amount", "0"))))
    if raw_tx.get("credit_debit_indicator", "DBIT") == "DBIT":
        return -amount
    return amount


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
            if tx.get("status") not in ("BOOK", None):
                continue
            date_str = tx.get("booking_date", "")
            if not date_str:
                log.warning(
                    "Transaction missing booking_date, skipping: amount=%s ccy=%s",
                    (tx.get("transaction_amount") or {}).get("amount"),
                    (tx.get("transaction_amount") or {}).get("currency"),
                )
                continue
            currency = (tx.get("transaction_amount") or {}).get("currency", "EUR")
            amount = _parse_amount(tx)
            booking_date = datetime(
                int(date_str[:4]),
                int(date_str[5:7]),
                int(date_str[8:10]),
                tzinfo=UTC,
            )
            description = _description(tx)
            merchant = _extract_merchant(tx)
            eur_amount = _to_eur(amount, currency, ecb_rates)
            dedup = eb_dedup_hash(date_str, amount, description, currency)
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
                    status="verified",
                    source="enable_banking",
                )
            )
        except Exception as exc:
            log.warning(
                "Failed to normalize transaction: amount=%s ccy=%s — %s",
                (tx.get("transaction_amount") or {}).get("amount"),
                (tx.get("transaction_amount") or {}).get("currency"),
                exc,
            )
    return results
