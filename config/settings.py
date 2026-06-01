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

# Anthropic
ANTHROPIC_API_KEY: str = _get("ANTHROPIC_API_KEY")

# Database
DATABASE_URL: str = _get("DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance")

# Pipeline
FETCH_DAYS_BACK: int = int(_get("FETCH_DAYS_BACK", "90"))
LOG_LEVEL: str = _get("LOG_LEVEL", "INFO")
