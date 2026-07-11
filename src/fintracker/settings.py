import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # UPPERCASE field names keep every call site (`settings.TELEGRAM_TOKEN`) unchanged.
    model_config = SettingsConfigDict(
        env_file=ROOT / "config" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Enable Banking
    ENABLE_BANKING_APP_ID: str = ""
    ENABLE_BANKING_PRIVATE_KEY_PATH: Path = Path("config/private_key.pem")
    ENABLE_BANKING_PRIVATE_KEY_B64: SecretStr = SecretStr("")
    ENABLE_BANKING_SESSION_ID: str = ""
    ENABLE_BANKING_ACCESS_TOKEN: SecretStr = SecretStr("")
    # NoDecode: pydantic-settings otherwise tries to JSON-decode the raw env value
    # *before* our validator runs, which blows up on a blank var (see .env.example's
    # `ENABLE_BANKING_ACCOUNT_IDS=` convention) — the validator below parses it instead.
    ENABLE_BANKING_ACCOUNT_IDS: Annotated[list[str], NoDecode] = []

    # Anthropic — only the categorizer needs it; pipeline skips with a warning if unset
    ANTHROPIC_API_KEY: SecretStr = SecretStr("")

    # Database
    DATABASE_URL: str = "postgresql://user:changeme@localhost:5432/finance"

    # Pipeline
    FETCH_DAYS_BACK: int = 90
    LOG_LEVEL: str = "INFO"

    # Telegram — required by both server and pipeline (sync alerts)
    TELEGRAM_TOKEN: SecretStr
    TELEGRAM_CHAT_ID: str

    # Server-only secrets — validated in validate_server_settings() at create_app(),
    # not at import, so pipeline.py runs without dashboard credentials.
    WEBHOOK_SECRET: SecretStr = SecretStr("")
    APP_USERNAME: str = ""
    APP_PASSWORD_HASH: SecretStr = SecretStr("")
    JWT_SECRET: SecretStr = SecretStr("")

    # Cookies / CORS
    FRONTEND_URL: str = "http://localhost:5173"
    COOKIE_SECURE: bool = True
    # "lax" is safe because the Vercel proxy makes all API calls first-party
    COOKIE_SAMESITE: Literal["lax", "none", "strict"] = "lax"

    @field_validator("ENABLE_BANKING_ACCOUNT_IDS", mode="before")
    @classmethod
    def _parse_account_ids(cls, v: str | list[str] | None) -> list[str]:
        if not v:
            return []
        return json.loads(v) if isinstance(v, str) else v

    @field_validator("ENABLE_BANKING_PRIVATE_KEY_PATH", mode="after")
    @classmethod
    def _resolve_key_path(cls, v: Path) -> Path:
        return v if v.is_absolute() else ROOT / v

    def validate_server_settings(self) -> None:
        missing = [
            key
            for key, val in {
                "WEBHOOK_SECRET": self.WEBHOOK_SECRET.get_secret_value(),
                "APP_USERNAME": self.APP_USERNAME,
                "APP_PASSWORD_HASH": self.APP_PASSWORD_HASH.get_secret_value(),
                "JWT_SECRET": self.JWT_SECRET.get_secret_value(),
            }.items()
            if not val
        ]
        if missing:
            raise OSError(f"Required env vars not set: {', '.join(missing)}")
        if len(self.WEBHOOK_SECRET.get_secret_value()) < 32:
            raise OSError("WEBHOOK_SECRET must be at least 32 characters")
        if len(self.JWT_SECRET.get_secret_value()) < 32:
            raise OSError("JWT_SECRET must be at least 32 characters")


settings = Settings()


def setup_logging() -> None:
    # stdout, not the stderr default: Railway labels every stderr line as error-level
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
