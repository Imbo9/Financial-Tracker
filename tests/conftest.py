import os

# Set required env vars before any module-level settings import
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret-for-pytest!!")  # 32 chars
os.environ.setdefault(
    "API_SECRET", "test-api-secret-for-pytest-tests!!"
)  # 32 chars — removed later
os.environ.setdefault("APP_USERNAME", "testuser")
# Pre-computed bcrypt hash of "testpassword" with 4 rounds (for fast tests)
os.environ.setdefault(
    "APP_PASSWORD_HASH", "$2b$04$WFgyB8N3viqNM4HN8jZjd.MXFyHiVWFrZX5YVCqQEBrY4SxYiVhLK"
)
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pytest-tests!!!")  # 35 chars
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("COOKIE_SAMESITE", "lax")
os.environ.setdefault("DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance")
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
