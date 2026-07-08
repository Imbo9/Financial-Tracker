"""
One-time OAuth flow for Enable Banking.

Prerequisites (do once on the dashboard):
  1. Register an application at https://enablebanking.com
  2. Download the generated RSA private key → save as config/private_key.pem
  3. Set ENABLE_BANKING_APP_ID in config/.env
  4. Add http://localhost:8080/callback to Allowed redirect URLs

Run on the host (not in a container) — needs a browser for the OAuth redirect:
    uv run python src/auth/enable_banking_auth.py

Writes ENABLE_BANKING_SESSION_ID, ENABLE_BANKING_ACCESS_TOKEN, and
ENABLE_BANKING_ACCOUNT_IDS to config/.env when complete (~90 days validity).
"""

import json
import logging
import os
import secrets
import sys
import time
import webbrowser
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import jwt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

BASE_URL = "https://api.enablebanking.com"
CALLBACK_PORT = 8080
REDIRECT_URL = "https://imbo9.github.io/eb-callback/"
SESSION_VALID_DAYS = 90

# Production: Revolut IT uses REVOLUT_REVOGB21 (UK BIC)
# Sandbox: only "Mock ASPSP" is available — set ASPSP_NAME="Mock ASPSP" for testing
ASPSP_NAME = os.environ.get("ASPSP_NAME", "Revolut")
ASPSP_COUNTRY = os.environ.get("ASPSP_COUNTRY", "")
_ASPSP_COUNTRIES = [ASPSP_COUNTRY] if ASPSP_COUNTRY else ["IT", "LT"]


def _make_app_jwt(app_id: str, private_key_pem: str) -> str:
    """Sign a short-lived JWT (PS256) with the app's RSA private key."""
    now = int(time.time())
    payload = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": now,
        "exp": now + 3600,
        "app_id": app_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": app_id})


def _auth_headers(app_id: str, private_key_pem: str) -> dict:
    return {
        "Authorization": f"Bearer {_make_app_jwt(app_id, private_key_pem)}",
        "Content-Type": "application/json",
    }


class _CallbackHandler(BaseHTTPRequestHandler):
    received_code: str | None = None
    received_error: str | None = None
    done: bool = False

    def do_GET(self):
        parsed = urlparse(self.path)
        log.info("Callback received: %s", self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            error = params.get("error", [None])[0]
            if error:
                log.error("Callback error: %s", error)
                _CallbackHandler.received_error = error
                _CallbackHandler.done = True
                self.send_response(400)
                self.end_headers()
                msg = f"<h2>Error: {error}</h2><p>Close this tab and check the terminal.</p>"
                self.wfile.write(msg.encode())
            else:
                _CallbackHandler.received_code = params.get(
                    "code", params.get("access_token", [None])
                )[0]
                _CallbackHandler.done = True
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<h2>Auth complete. You can close this tab.</h2>")
        else:
            # Ignore favicon and other spurious requests
            self.send_response(204)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass  # suppress HTTP access log


def _update_env(updates: dict[str, str], env_path: Path) -> None:
    """Merge key=value pairs into .env, preserving existing entries."""
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
    existing.update(updates)
    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    log.info("Saved to %s: %s", env_path, list(updates.keys()))


def _start_psu_session(
    client: httpx.Client, app_id: str, private_key_pem: str, country: str
) -> str:
    valid_until = (datetime.now(UTC) + timedelta(days=SESSION_VALID_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    resp = client.post(
        f"{BASE_URL}/auth",
        json={
            "access": {"valid_until": valid_until},
            "aspsp": {"name": ASPSP_NAME, "country": country},
            "redirect_url": REDIRECT_URL,
            "psu_type": "personal",
            "state": secrets.token_urlsafe(16),
        },
        headers=_auth_headers(app_id, private_key_pem),
    )
    if not resp.is_success:
        log.error("POST /auth %d — %s", resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()
    url = data.get("url") or data.get("auth_url") or data.get("authorization_url")
    if not url:
        raise ValueError(f"No auth URL in response: {data}")
    return url


def _exchange_code(
    client: httpx.Client, app_id: str, private_key_pem: str, code: str
) -> tuple[str, list[str]]:
    """Exchange auth code → (session_id, [account_uid, ...]). Accounts are in the response."""
    resp = client.post(
        f"{BASE_URL}/sessions",
        json={"code": code},
        headers=_auth_headers(app_id, private_key_pem),
    )
    if not resp.is_success:
        log.error("POST /sessions %d — %s", resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()
    session_id = data.get("session_id") or data.get("id")
    if not session_id:
        raise ValueError(f"No session_id in response: {data}")
    accounts = [acc["uid"] for acc in data.get("accounts", [])]
    return session_id, accounts


def main() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    env_path = root / "config" / ".env"

    from dotenv import load_dotenv

    load_dotenv(env_path)

    app_id = os.getenv("ENABLE_BANKING_APP_ID", "").strip()
    key_path_str = os.getenv("ENABLE_BANKING_PRIVATE_KEY_PATH", "config/private_key.pem").strip()
    key_path = Path(key_path_str) if Path(key_path_str).is_absolute() else root / key_path_str

    if not app_id:
        raise OSError("Set ENABLE_BANKING_APP_ID in config/.env first.")
    if not key_path.exists():
        raise OSError(
            f"Private key not found at {key_path}. "
            "Download it from the Enable Banking dashboard and save it there."
        )

    private_key_pem = key_path.read_text(encoding="utf-8")
    log.info("Loaded private key from %s", key_path)

    auth_url = None
    with httpx.Client(timeout=15) as client:
        for country in _ASPSP_COUNTRIES:
            try:
                log.info("Trying ASPSP country=%s ...", country)
                auth_url = _start_psu_session(client, app_id, private_key_pem, country)
                log.info("Auth URL obtained (country=%s)", country)
                break
            except Exception as exc:
                log.warning("country=%s failed: %s", country, exc)
        if not auth_url:
            raise RuntimeError(
                "All ASPSP countries failed — check APP_ID and private key, then try again."
            )

    _CallbackHandler.received_code = None
    _CallbackHandler.received_error = None
    _CallbackHandler.done = False
    server = HTTPServer(("", CALLBACK_PORT), _CallbackHandler)
    server.timeout = 1
    print(f"\n{'=' * 60}")
    print(f"SESSION URL (torna qui se rimani bloccato):\n{auth_url}")
    print(f"{'=' * 60}\n")
    webbrowser.open(auth_url)
    log.info("Waiting for OAuth callback on localhost:%d  (Ctrl+C to abort) ...", CALLBACK_PORT)
    while not _CallbackHandler.done:
        server.handle_request()

    if _CallbackHandler.received_error:
        raise RuntimeError(f"OAuth error: {_CallbackHandler.received_error}")
    code = _CallbackHandler.received_code
    if not code:
        raise RuntimeError("No auth code received in callback.")

    log.info("Exchanging auth code for session token ...")
    with httpx.Client(timeout=15) as client:
        session_id, account_ids = _exchange_code(client, app_id, private_key_pem, code)
        log.info("Session ID: %s... — %d account(s)", session_id[:8], len(account_ids))

    # The session_id itself serves as the bearer token for data endpoints
    _update_env(
        {
            "ENABLE_BANKING_SESSION_ID": session_id,
            "ENABLE_BANKING_ACCESS_TOKEN": session_id,
            "ENABLE_BANKING_ACCOUNT_IDS": json.dumps(account_ids),
        },
        env_path,
    )
    print(f"\nDone. Session valid ~{SESSION_VALID_DAYS} days. {len(account_ids)} account(s) saved.")


if __name__ == "__main__":
    main()
