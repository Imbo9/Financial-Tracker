import json
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

# Telegram
TELEGRAM_TOKEN: str = _require("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID: str = _require("TELEGRAM_CHAT_ID")

# Webhook
WEBHOOK_SECRET: str = _require("WEBHOOK_SECRET")
if len(WEBHOOK_SECRET) < 32:
    raise EnvironmentError("WEBHOOK_SECRET must be at least 32 characters")

# API authentication — separate from WEBHOOK_SECRET (HMAC signing key)
# Set API_SECRET in Railway env; use this value for VITE_API_TOKEN in the frontend.
API_SECRET: str = _require("API_SECRET")
if len(API_SECRET) < 32:
    raise EnvironmentError("API_SECRET must be at least 32 characters")

# Enable Banking — base64 private key for cloud deployments (overrides file path)
ENABLE_BANKING_PRIVATE_KEY_B64: str = _get("ENABLE_BANKING_PRIVATE_KEY_B64")
