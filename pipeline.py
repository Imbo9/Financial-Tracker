"""Entry-point shim: Railway cron runs `uv run python pipeline.py` — do not move."""

from fintracker.pipeline import main

if __name__ == "__main__":
    main()
