"""Wrapper: loads config/.env then starts codex-mcp-server."""

import os
import subprocess
import sys
from pathlib import Path

env_file = Path(__file__).parent.parent / "config" / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

npx = "npx.cmd" if sys.platform == "win32" else "npx"
sys.exit(subprocess.run([npx, "-y", "codex-mcp-server"], env=os.environ).returncode)
