import pytest
from pydantic import SecretStr

from fintracker.settings import settings


class TestValidateServerSettings:
    def test_passes_with_full_test_env(self):
        settings.validate_server_settings()

    def test_reports_missing_vars_by_name(self, monkeypatch):
        monkeypatch.setattr(settings, "JWT_SECRET", SecretStr(""))
        monkeypatch.setattr(settings, "APP_USERNAME", "")
        with pytest.raises(EnvironmentError, match="APP_USERNAME, JWT_SECRET"):
            settings.validate_server_settings()

    def test_rejects_short_webhook_secret(self, monkeypatch):
        monkeypatch.setattr(settings, "WEBHOOK_SECRET", SecretStr("short"))
        with pytest.raises(EnvironmentError, match="WEBHOOK_SECRET"):
            settings.validate_server_settings()

    def test_rejects_short_jwt_secret(self, monkeypatch):
        monkeypatch.setattr(settings, "JWT_SECRET", SecretStr("short"))
        with pytest.raises(EnvironmentError, match="JWT_SECRET"):
            settings.validate_server_settings()
