import os

# Set required env vars before any module-level settings import
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret-for-pytest!!")  # 32 chars
os.environ.setdefault("APP_USERNAME", "testuser")
# Pre-computed bcrypt hash of "testpassword" with 4 rounds (for fast tests)
# Generated with bcrypt 5.x: bcrypt.hashpw(b"testpassword", bcrypt.gensalt(rounds=4))
os.environ.setdefault(
    "APP_PASSWORD_HASH", "$2b$04$wz2g1JAQLXiA3lVTx0W5Su2Xj4xXhZzkyjR50YDF4H6.If9ep/2DO"
)
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pytest-tests!!!")  # 35 chars
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("COOKIE_SAMESITE", "lax")
os.environ.setdefault("DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance")
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
