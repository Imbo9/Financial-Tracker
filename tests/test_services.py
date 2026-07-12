from unittest.mock import MagicMock

from fintracker.server.services import accounts, stats


def _conn_with_cursor(rows):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = rows
    cur.fetchone.return_value = {"total": len(rows)}
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def _conn_returning(rows):
    conn, _ = _conn_with_cursor(rows)
    return conn


def test_stats_by_category_defaults_to_expense_filter():
    conn, cur = _conn_with_cursor([{"category": "Food", "total": 75.0, "count": 3}])
    stats.by_category(conn, days_back=30)
    assert "amount < 0" in cur.execute.call_args[0][0]


def test_stats_by_category_income_direction_flips_sign_filter():
    conn, cur = _conn_with_cursor([{"category": "Income", "total": 100.0, "count": 1}])
    stats.by_category(conn, days_back=30, direction="income")
    assert "amount > 0" in cur.execute.call_args[0][0]


def test_stats_by_category_adds_percentage():
    conn = _conn_returning(
        [
            {"category": "Food", "total": 75.0, "count": 3},
            {"category": "Travel", "total": 25.0, "count": 1},
        ]
    )
    rows = stats.by_category(conn, days_back=30)
    assert rows[0]["percentage"] == 75.0
    assert rows[1]["percentage"] == 25.0


def test_accounts_balances_splits_assets_liabilities():
    conn = _conn_returning(
        [
            {"account_id": "a", "balance": 100.0},
            {"account_id": "b", "balance": -40.0},
        ]
    )
    out = accounts.balances(conn)
    assert out["assets"] == 100.0
    assert out["liabilities"] == 40.0
