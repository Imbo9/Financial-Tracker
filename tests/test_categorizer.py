from fintracker import taxonomy
from fintracker.categorizer.categorize import _SYSTEM_PROMPT


def test_prompt_contains_every_taxonomy_category():
    for cat in (*taxonomy.EXPENSE_CATEGORIES, *taxonomy.INCOME_CATEGORIES):
        assert f"- {cat}" in _SYSTEM_PROMPT


def test_prompt_dropped_the_old_hardcoded_taxonomy():
    assert "Food & Dining" not in _SYSTEM_PROMPT
    assert "ATM/Cash" not in _SYSTEM_PROMPT


def test_prompt_keeps_null_fallback_and_json_contract():
    assert "null" in _SYSTEM_PROMPT
    assert '[{"category": "...", "subcategory": "..."}, ...]' in _SYSTEM_PROMPT
