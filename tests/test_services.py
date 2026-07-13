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


def _month_shift(back: int) -> str:
    from datetime import date

    d = date.today().replace(day=1)
    for _ in range(back):
        d = (d - __import__("datetime").timedelta(days=1)).replace(day=1)
    return d.strftime("%Y-%m")


def _conn_for_history(openings_total, monthly_rows):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = {"total": openings_total}
    cur.fetchall.return_value = monthly_rows
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
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
            {"account_id": "a", "balance": 100.0, "display_name": "Main"},
            {"account_id": "b", "balance": -40.0, "display_name": None},
        ]
    )
    out = accounts.balances(conn)
    assert out["assets"] == 100.0
    assert out["liabilities"] == 40.0
    assert out["accounts"][0]["display_name"] == "Main"


def test_accounts_balances_joins_openings():
    conn, cur = _conn_with_cursor([])
    accounts.balances(conn)
    sql = cur.execute.call_args[0][0]
    assert "LEFT JOIN accounts" in sql
    assert "opening_balance" in sql
    assert "real_transactions" not in sql
    assert "FROM transactions" in sql


def test_balance_history_accumulates_on_openings_with_carry_forward():
    m2, m0 = _month_shift(2), _month_shift(0)
    conn = _conn_for_history(100.0, [{"month": m2, "net": 10.0}, {"month": m0, "net": -5.0}])

    series = stats.balance_history(conn, months=3)

    assert [p["month"] for p in series] == [m2, _month_shift(1), m0]
    assert [p["balance"] for p in series] == [110.0, 110.0, 105.0]  # gap month carries forward
    assert all(isinstance(p["balance"], float) for p in series)


def test_balance_history_without_transactions_is_flat_openings():
    conn = _conn_for_history(250.0, [])

    series = stats.balance_history(conn, months=4)

    assert len(series) == 4
    assert {p["balance"] for p in series} == {250.0}
    assert series[-1]["month"] == _month_shift(0)


def test_balance_history_slices_window_but_keeps_older_accumulation():
    m3 = _month_shift(3)
    conn = _conn_for_history(0.0, [{"month": m3, "net": 40.0}])

    series = stats.balance_history(conn, months=2)

    assert len(series) == 2
    assert series[0]["month"] == _month_shift(1)
    assert series[0]["balance"] == 40.0  # older net accumulated before the window
