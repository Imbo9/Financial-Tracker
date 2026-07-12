"""One-shot 2026-07 taxonomy migration: remap manual rows to the MoneyManager
names, reset every other row so the pipeline re-categorizes with the new prompt.

Run against prod with Railway env:
  railway run --service just-comfort -- uv run python scripts/migrate_taxonomy.py
Then re-categorize:
  railway run --service just-comfort -- uv run python pipeline.py --skip-fetch

Idempotent: every statement matches only rows still carrying legacy labels.
"""

import logging

from fintracker import taxonomy
from fintracker.storage.db import direct_connection

log = logging.getLogger(__name__)

# Legacy AddTransactionModal names → new taxonomy (None = leave uncategorized).
MANUAL_REMAP: dict[str, str | None] = {
    "Transport": "Transit",
    "Career & Professional": "Career & Professional development",
    "Housing": None,
    "Other": None,
}


def migrate(conn) -> dict[str, int]:
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for old, new in MANUAL_REMAP.items():
            cur.execute(
                "UPDATE transactions SET category = %s, subcategory = NULL"
                " WHERE source = 'manual' AND category = %s",
                (new, old),
            )
            counts[f"manual {old} -> {new}"] = cur.rowcount

        valid = [*taxonomy.EXPENSE_CATEGORIES, *taxonomy.INCOME_CATEGORIES]
        cur.execute(
            "UPDATE transactions SET category = NULL, subcategory = NULL"
            " WHERE source = 'manual' AND category IS NOT NULL AND category != ALL(%s)",
            (valid,),
        )
        counts["manual unknown -> NULL"] = cur.rowcount

        cur.execute(
            "UPDATE transactions SET category = NULL, subcategory = NULL WHERE source != 'manual'"
        )
        counts["non-manual reset for re-categorization"] = cur.rowcount

    conn.commit()
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for label, n in migrate(direct_connection()).items():
        log.info("%-45s %5d rows", label, n)
