import json
import logging

import anthropic

from fintracker import taxonomy
from fintracker.settings import settings

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 50

_SYSTEM_PROMPT = f"""You are a personal finance categorizer for Revolut transactions in Italy.
Given a JSON array of merchant names, assign each a category and optional subcategory.

Pick ONLY from these categories and subcategories:

{taxonomy.prompt_block()}

Rules:
- The merchant name alone decides: pick the single best fit from either side.
- Use null for subcategory when none fits the merchant.
- If NO category fits (e.g. ATM withdrawals, unrecognizable person-to-person transfers),
  use null for category too.
- Recognizable person-to-person transfers go by purpose: Partner, Family, Gifts or
  Social life when paying out; Reimbursements or Gifts received when money comes in.

Respond ONLY with a JSON array in the same order as the input:
[{{"category": "...", "subcategory": "..."}}, ...]"""


def _categorize_batch(client: anthropic.Anthropic, merchants: list[str]) -> list[dict]:
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": json.dumps(merchants, ensure_ascii=False)}],
        )
        # pyrefly: ignore[missing-attribute]  # no `tools=` param on this call, so the SDK
        # always returns a TextBlock here despite `.content`'s broader declared union type
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            # odd-indexed parts are inside fences; find the JSON array block
            json_blocks = [p.lstrip("json").strip() for p in parts[1::2]]
            raw = next((b for b in json_blocks if b.startswith("[")), json_blocks[0])
        return json.loads(raw)
    except Exception as exc:
        log.warning("Categorization batch failed: %s", exc)
        return [{"category": None, "subcategory": None}] * len(merchants)


def categorize_uncategorized(conn) -> int:
    """Fetch uncategorized real transactions, call Claude, update DB. Returns count updated."""
    if not settings.ANTHROPIC_API_KEY.get_secret_value():
        raise OSError("ANTHROPIC_API_KEY not set in config/.env")

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, merchant_name FROM transactions"
            " WHERE category IS NULL AND is_internal = FALSE"
            " ORDER BY booking_date DESC"
        )
        rows = cur.fetchall()

    if not rows:
        log.info("No uncategorized transactions found")
        return 0

    log.info("Categorizing %d transactions in batches of %d ...", len(rows), BATCH_SIZE)
    total_updated = 0
    n_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        ids = [r[0] for r in batch]
        merchants = [r[1] or "Unknown" for r in batch]
        results = _categorize_batch(client, merchants)

        if len(results) < len(ids):
            log.warning(
                "Batch %d/%d: Claude returned %d results for %d merchants — truncated response?",
                i // BATCH_SIZE + 1,
                n_batches,
                len(results),
                len(ids),
            )
        update_data = [
            (r.get("category"), r.get("subcategory"), row_id)
            for row_id, r in zip(ids, results, strict=False)
            if isinstance(r, dict)
        ]
        if update_data:
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE transactions SET category = %s, subcategory = %s WHERE id = %s",
                    update_data,
                )
            conn.commit()
            total_updated += len(update_data)
        log.info(
            "Batch %d/%d done (%d categorized)", i // BATCH_SIZE + 1, n_batches, len(update_data)
        )

    return total_updated
