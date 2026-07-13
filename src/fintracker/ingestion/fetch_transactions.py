import logging
import threading
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx
import jwt

from fintracker.settings import settings

log = logging.getLogger(__name__)

BASE_URL = "https://api.enablebanking.com"
_INTER_ACCOUNT_DELAY_SEC = 2  # respect 4 calls/account/24h rate limit

_jwt_cache: tuple[str, int] | None = None
_jwt_lock = threading.Lock()


def _make_jwt() -> str:
    global _jwt_cache
    with _jwt_lock:
        now = int(time.time())
        if _jwt_cache and _jwt_cache[1] > now + 60:
            return _jwt_cache[0]
        if settings.ENABLE_BANKING_PRIVATE_KEY_B64.get_secret_value():
            import base64

            pem = base64.b64decode(
                settings.ENABLE_BANKING_PRIVATE_KEY_B64.get_secret_value()
            ).decode()
        else:
            pem = settings.ENABLE_BANKING_PRIVATE_KEY_PATH.read_text()
        exp = now + 3600
        token = jwt.encode(
            {
                "iss": "enablebanking.com",
                "aud": "api.enablebanking.com",
                "iat": now,
                "exp": exp,
                "app_id": settings.ENABLE_BANKING_APP_ID,
            },
            pem,
            algorithm="RS256",
            headers={"kid": settings.ENABLE_BANKING_APP_ID},
        )
        _jwt_cache = (token, exp)
        return token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_make_jwt()}"}


def _get(client: httpx.Client, path: str, **params) -> Any:
    resp = client.get(f"{BASE_URL}{path}", headers=_headers(), params=params or None)
    resp.raise_for_status()
    return resp.json()


def fetch_balances(client: httpx.Client, account_uid: str) -> Decimal:
    """Current balance for one account; prefers closing-booked (CLBD) per Berlin Group."""
    data = _get(client, f"/accounts/{account_uid}/balances")
    balances = data.get("balances") or []
    if not balances:
        raise ValueError(f"No balances returned for account {account_uid}")
    chosen = next((b for b in balances if b.get("balance_type") == "CLBD"), balances[0])
    amount = chosen["balance_amount"]
    if amount.get("currency") != "EUR":
        log.warning(
            "Account %s balance is in %s — treating as EUR per app convention",
            account_uid[:8],
            amount.get("currency"),
        )
    return Decimal(amount["amount"])


def fetch_accounts() -> list[str]:
    """Return account UIDs — from .env cache or live API call."""
    if settings.ENABLE_BANKING_ACCOUNT_IDS:
        log.info("Using %d cached account IDs from .env", len(settings.ENABLE_BANKING_ACCOUNT_IDS))
        return settings.ENABLE_BANKING_ACCOUNT_IDS
    if not settings.ENABLE_BANKING_SESSION_ID:
        raise OSError("ENABLE_BANKING_SESSION_ID not set — run auth first")
    with httpx.Client(timeout=15) as client:
        data = _get(client, f"/sessions/{settings.ENABLE_BANKING_SESSION_ID}/accounts")
    accounts = [acc["uid"] for acc in data.get("accounts", [])]
    log.info("Discovered %d accounts", len(accounts))
    return accounts


def _fetch_account_transactions(
    client: httpx.Client,
    account_uid: str,
    date_from: date,
    date_to: date,
) -> list[dict]:
    params: dict = {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()}
    all_txs: list[dict] = []
    while True:
        try:
            data = _get(client, f"/accounts/{account_uid}/transactions", **params)
        except (
            httpx.HTTPStatusError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
        ) as exc:
            log.warning("Error fetching transactions for account %s: %s", account_uid[:8], exc)
            break
        all_txs.extend(data.get("transactions", []))
        continuation = data.get("continuation_key")
        if not continuation:
            break
        params["continuation_key"] = continuation
        time.sleep(1)
    log.info("Fetched %d transactions for account %s", len(all_txs), account_uid[:8])
    return all_txs


def fetch_transactions(days_back: int | None = None) -> dict[str, list[dict]]:
    """Return {account_uid: [raw_transaction, ...]} for all accounts."""
    if (
        not settings.ENABLE_BANKING_PRIVATE_KEY_B64.get_secret_value()
        and not settings.ENABLE_BANKING_PRIVATE_KEY_PATH.exists()
    ):
        raise OSError(
            f"Private key not found at {settings.ENABLE_BANKING_PRIVATE_KEY_PATH} — run auth first"
        )
    if days_back is None:
        days_back = settings.FETCH_DAYS_BACK
    date_to = date.today()
    date_from = date_to - timedelta(days=days_back)
    accounts = fetch_accounts()
    if not accounts:
        log.warning("No accounts found — is the session token valid?")
        return {}
    results: dict[str, list[dict]] = {}
    with httpx.Client(timeout=30) as client:
        for i, uid in enumerate(accounts):
            if i > 0:
                time.sleep(_INTER_ACCOUNT_DELAY_SEC)
            results[uid] = _fetch_account_transactions(client, uid, date_from, date_to)
    total = sum(len(v) for v in results.values())
    log.info("Total: %d raw transactions across %d accounts", total, len(results))
    return results
