import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "config" / ".env")


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Required env var not set: {key}")
    return val


# Enable Banking
ENABLE_BANKING_APP_ID: str = _get("ENABLE_BANKING_APP_ID")
# Path to RSA private key PEM — relative paths are resolved from project root
_raw_key_path = _get("ENABLE_BANKING_PRIVATE_KEY_PATH", "config/private_key.pem")
ENABLE_BANKING_PRIVATE_KEY_PATH: Path = (
    Path(_raw_key_path) if Path(_raw_key_path).is_absolute() else ROOT / _raw_key_path
)
ENABLE_BANKING_SESSION_ID: str = _get("ENABLE_BANKING_SESSION_ID")
ENABLE_BANKING_ACCESS_TOKEN: str = _get("ENABLE_BANKING_ACCESS_TOKEN")
ENABLE_BANKING_ACCOUNT_IDS: list[str] = json.loads(_get("ENABLE_BANKING_ACCOUNT_IDS") or "[]")

# Anthropic — only needed by the categorizer pipeline, not the server
ANTHROPIC_API_KEY: str = _get("ANTHROPIC_API_KEY")

# Database
DATABASE_URL: str = _get("DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance")

# Pipeline
FETCH_DAYS_BACK: int = int(_get("FETCH_DAYS_BACK", "90"))
LOG_LEVEL: str = _get("LOG_LEVEL", "INFO")

# Telegram — needed by both the server and the pipeline (sync alerts)
TELEGRAM_TOKEN: str = _require("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID: str = _require("TELEGRAM_CHAT_ID")

# Server-only secrets — validated by validate_server_settings() at server startup,
# so pipeline.py (local runs and sync-cron) doesn't need dashboard credentials.
WEBHOOK_SECRET: str = _get("WEBHOOK_SECRET")
APP_USERNAME: str = _get("APP_USERNAME")
APP_PASSWORD_HASH: str = _get("APP_PASSWORD_HASH")
JWT_SECRET: str = _get("JWT_SECRET")


def validate_server_settings() -> None:
    missing = [
        key
        for key, val in {
            "WEBHOOK_SECRET": WEBHOOK_SECRET,
            "APP_USERNAME": APP_USERNAME,
            "APP_PASSWORD_HASH": APP_PASSWORD_HASH,
            "JWT_SECRET": JWT_SECRET,
        }.items()
        if not val
    ]
    if missing:
        raise EnvironmentError(f"Required env vars not set: {', '.join(missing)}")
    if len(WEBHOOK_SECRET) < 32:
        raise EnvironmentError("WEBHOOK_SECRET must be at least 32 characters")
    if len(JWT_SECRET) < 32:
        raise EnvironmentError("JWT_SECRET must be at least 32 characters")


# Cookie settings — override per environment
FRONTEND_URL: str = _get("FRONTEND_URL", "http://localhost:5173")
COOKIE_SECURE: bool = _get("COOKIE_SECURE", "true").lower() == "true"
# "lax" is safe because the Vercel proxy makes all API calls first-party
COOKIE_SAMESITE: str = _get("COOKIE_SAMESITE", "lax")

# Enable Banking — base64 private key for cloud deployments (overrides file path)
ENABLE_BANKING_PRIVATE_KEY_B64: str = _get("ENABLE_BANKING_PRIVATE_KEY_B64")


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
