import os

# Set required env vars before any module-level settings import
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://user:changeme@localhost:5432/finance")
