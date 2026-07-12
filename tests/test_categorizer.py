from unittest.mock import MagicMock

from fintracker import taxonomy
from fintracker.categorizer import categorize as categorize_mod
from fintracker.categorizer.categorize import _SYSTEM_PROMPT, categorize_uncategorized


def test_prompt_contains_every_taxonomy_category():
    for cat in (*taxonomy.EXPENSE_CATEGORIES, *taxonomy.INCOME_CATEGORIES):
        assert f"- {cat}" in _SYSTEM_PROMPT


def test_prompt_dropped_the_old_hardcoded_taxonomy():
    assert "Food & Dining" not in _SYSTEM_PROMPT
    assert "ATM/Cash" not in _SYSTEM_PROMPT


def test_prompt_keeps_null_fallback_and_json_contract():
    assert "null" in _SYSTEM_PROMPT
    assert '[{"category": "...", "subcategory": "..."}, ...]' in _SYSTEM_PROMPT


def _conn_with_rows(rows):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


# One row per required-behavior bullet: valid pair, foreign subcategory, unknown
# category, orphan subcategory (no category), and a legitimate "no fit" (None/None).
_FAKE_ROWS = [
    (1, "Esso"),
    (2, "Auchan"),
    (3, "Unknown merchant"),
    (4, "Mystery"),
    (5, "ATM Withdrawal"),
]

_FAKE_RESULTS = [
    {"category": "Car", "subcategory": "Fuel"},  # valid pair -> kept as-is
    {"category": "Car", "subcategory": "Supermarket"},  # foreign subcategory -> sub dropped
    {"category": "Food & Dining", "subcategory": "Restaurant"},  # unknown category -> both dropped
    {"category": None, "subcategory": "Fuel"},  # orphan subcategory -> both dropped
    {"category": None, "subcategory": None},  # legitimate "no fit" -> stays None
]


def _patch_categorizer(monkeypatch):
    monkeypatch.setattr(
        categorize_mod, "_categorize_batch", lambda client, merchants: _FAKE_RESULTS
    )
    monkeypatch.setattr(categorize_mod.anthropic, "Anthropic", MagicMock())


def test_categorize_uncategorized_sanitizes_claude_output_against_taxonomy(monkeypatch):
    conn, cur = _conn_with_rows(_FAKE_ROWS)
    _patch_categorizer(monkeypatch)

    updated = categorize_uncategorized(conn)

    assert updated == 5
    assert cur.executemany.call_args[0][1] == [
        ("Car", "Fuel", 1),
        ("Car", None, 2),
        (None, None, 3),
        (None, None, 4),
        (None, None, 5),
    ]


def test_categorize_uncategorized_warns_on_foreign_subcategory_and_unknown_category(
    monkeypatch, caplog
):
    conn, _cur = _conn_with_rows(_FAKE_ROWS)
    _patch_categorizer(monkeypatch)

    with caplog.at_level("WARNING"):
        categorize_uncategorized(conn)

    assert "Supermarket" in caplog.text
    assert "Food & Dining" in caplog.text
