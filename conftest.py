import os

os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret-for-pytest!!")  # 32 chars
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance")
