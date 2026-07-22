from unittest.mock import MagicMock

from fintracker.server.services import accounts, stats, transactions


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
    from datetime import date

    conn, cur = _conn_with_cursor([{"category": "Food", "total": 75.0, "count": 3}])
    stats.by_category(conn, date(2026, 6, 1), date(2026, 6, 30))
    assert "amount < 0" in cur.execute.call_args[0][0]


def test_stats_by_category_income_direction_flips_sign_filter():
    from datetime import date

    conn, cur = _conn_with_cursor([{"category": "Income", "total": 100.0, "count": 1}])
    stats.by_category(conn, date(2026, 6, 1), date(2026, 6, 30), direction="income")
    assert "amount > 0" in cur.execute.call_args[0][0]


def test_stats_by_category_adds_percentage():
    from datetime import date

    conn = _conn_returning(
        [
            {"category": "Food", "total": 75.0, "count": 3},
            {"category": "Travel", "total": 25.0, "count": 1},
        ]
    )
    rows = stats.by_category(conn, date(2026, 6, 1), date(2026, 6, 30))
    assert rows[0]["percentage"] == 75.0
    assert rows[1]["percentage"] == 25.0


def test_accounts_balances_splits_assets_liabilities():
    conn = _conn_returning(
        [
            {
                "account_id": "a",
                "balance": 100.0,
                "display_name": "Main",
                "type": "bank",
                "currency": "EUR",
                "is_manual": False,
                "opening_balance": 90.0,
            },
            {
                "account_id": "b",
                "balance": -40.0,
                "display_name": None,
                "type": "card",
                "currency": "EUR",
                "is_manual": False,
                "opening_balance": 0.0,
            },
        ]
    )
    out = accounts.balances(conn)
    assert out["assets"] == 100.0
    assert out["liabilities"] == 40.0
    assert out["accounts"][0]["display_name"] == "Main"
    assert out["accounts"][0]["type"] == "bank"
    assert out["accounts"][0]["is_manual"] is False


def test_accounts_balances_left_joins_all_registered_accounts():
    conn, cur = _conn_with_cursor([])
    accounts.balances(conn)
    sql = cur.execute.call_args[0][0]
    # LEFT JOIN from accounts: a manual account with zero transactions still shows its
    # opening balance. Scope is driven by the accounts table (stale EB uids aren't in it).
    assert "FROM accounts a" in sql
    assert "LEFT JOIN transactions" in sql
    assert "COALESCE(SUM(t.eur_amount), 0)" in sql
    assert "opening_balance" in sql
    assert "real_transactions" not in sql


def test_balance_history_scopes_to_calibrated_accounts():
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = {"total": 0}
    cur.fetchall.return_value = []
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    stats.balance_history(conn, months=3)

    monthly_sql = cur.execute.call_args_list[1].args[0]
    # Restrict to accounts we have an opening for; a bare `IS NOT NULL` would re-admit
    # stale post-renewal account_ids and desync the series from net worth.
    assert "account_uid FROM accounts" in monthly_sql
    assert "IS NOT NULL" not in monthly_sql


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


def test_list_transactions_uses_date_range_when_both_dates_given():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn,
        page=1,
        page_size=50,
        days_back=30,
        category=None,
        direction=None,
        search=None,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    sql, params = cur.execute.call_args[0]
    assert "< %s::date + INTERVAL '1 day'" in sql
    assert "INTERVAL '1 day')" not in sql or "NOW()" not in sql  # days_back window replaced
    assert date(2026, 6, 1) in params and date(2026, 6, 30) in params


def test_list_transactions_falls_back_to_days_back_without_dates():
    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn,
        page=1,
        page_size=50,
        days_back=30,
        category=None,
        direction=None,
        search=None,
    )
    sql, _ = cur.execute.call_args[0]
    assert "NOW() - (%s * INTERVAL '1 day')" in sql


def test_list_transactions_one_date_alone_falls_back_to_days_back():
    from datetime import date

    # Only date_from, no date_to: the range needs BOTH, so this must cleanly use the
    # days_back window rather than emitting a half-formed range or mis-binding params.
    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn,
        page=1,
        page_size=50,
        days_back=30,
        category=None,
        direction=None,
        search=None,
        date_from=date(2026, 6, 1),
    )
    sql, params = cur.execute.call_args[0]
    assert "NOW() - (%s * INTERVAL '1 day')" in sql
    assert "INTERVAL '1 day'" in sql and "::date" not in sql  # no half-open range emitted
    assert date(2026, 6, 1) not in params  # the stray single date is ignored


def test_subcategory_breakdown_adds_percentages_and_floats():
    from datetime import date

    conn = _conn_returning(
        [
            {"subcategory": "Fuel", "total": 75.0, "count": 3},
            {"subcategory": "Tolls & Parking", "total": 25.0, "count": 1},
        ]
    )
    out = stats.subcategory_breakdown(
        conn, "Car", date(2026, 6, 1), date(2026, 6, 30), direction="expense"
    )
    assert [r["percentage"] for r in out] == [75.0, 25.0]
    assert all(isinstance(r["total"], float) for r in out)


def test_subcategory_breakdown_uncategorized_uses_is_null():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(
        conn, None, date(2026, 6, 1), date(2026, 6, 30), direction="expense"
    )
    sql = cur.execute.call_args[0][0]
    # 'Uncategorized' is a COALESCE label, not a stored value — a literal
    # comparison would silently return nothing.
    assert "category IS NULL" in sql
    assert "category = %s" not in sql


def test_subcategory_breakdown_named_category_is_parameterised():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(
        conn, "Car", date(2026, 6, 1), date(2026, 6, 30), direction="expense"
    )
    sql, params = cur.execute.call_args[0]
    assert "category = %s" in sql
    assert params[0] == "Car"


def test_subcategory_breakdown_null_subcategory_gets_sentinel_label():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(
        conn, "Car", date(2026, 6, 1), date(2026, 6, 30), direction="expense"
    )
    assert "'No subcategory'" in cur.execute.call_args[0][0]


def test_subcategory_breakdown_income_flips_sign_filter():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(
        conn, "Salary", date(2026, 6, 1), date(2026, 6, 30), direction="income"
    )
    assert "amount > 0" in cur.execute.call_args[0][0]


def test_subcategory_breakdown_empty_does_not_divide_by_zero():
    from datetime import date

    conn = _conn_returning([])
    assert (
        stats.subcategory_breakdown(
            conn, "Car", date(2026, 6, 1), date(2026, 6, 30), direction="expense"
        )
        == []
    )


def test_category_trend_zero_fills_empty_months():
    m2 = _month_shift(2)
    conn = _conn_returning([{"month": m2, "total": 40.0}])

    series = stats.category_trend(conn, "Car", months=3, direction="expense")

    assert [p["month"] for p in series] == [m2, _month_shift(1), _month_shift(0)]
    # flow, not stock: a quiet month is 0.0, never the previous month's value
    assert [p["total"] for p in series] == [40.0, 0.0, 0.0]
    assert all(isinstance(p["total"], float) for p in series)


def test_category_trend_returns_exactly_months_points():
    conn = _conn_returning([])
    series = stats.category_trend(conn, "Car", months=12, direction="expense")
    assert len(series) == 12
    assert series[-1]["month"] == _month_shift(0)
    assert {p["total"] for p in series} == {0.0}


def test_category_trend_named_subcategory_is_parameterised():
    conn, cur = _conn_with_cursor([])
    stats.category_trend(conn, "Car", months=6, direction="expense", subcategory="Fuel")
    sql, params = cur.execute.call_args[0]
    assert "subcategory = %s" in sql
    assert "Fuel" in params


def test_category_trend_sentinel_subcategory_uses_is_null():
    conn, cur = _conn_with_cursor([])
    stats.category_trend(conn, "Car", months=6, direction="expense", subcategory="No subcategory")
    sql, params = cur.execute.call_args[0]
    assert "subcategory IS NULL" in sql
    assert "No subcategory" not in params


def test_category_trend_without_subcategory_adds_no_filter():
    conn, cur = _conn_with_cursor([])
    stats.category_trend(conn, "Car", months=6, direction="expense")
    assert "subcategory" not in cur.execute.call_args[0][0]


def test_category_trend_uses_absolute_amounts():
    conn, cur = _conn_with_cursor([])
    stats.category_trend(conn, "Car", months=6, direction="expense")
    # expenses must trend upward as spending grows, not plunge negative
    assert "ABS(eur_amount)" in cur.execute.call_args[0][0]


def test_list_transactions_named_subcategory_is_parameterised():
    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn,
        page=1,
        page_size=50,
        days_back=30,
        category="Car",
        direction=None,
        search=None,
        subcategory="Fuel",
    )
    sql, params = cur.execute.call_args[0]
    assert "subcategory = %s" in sql
    assert "Fuel" in params


def test_list_transactions_sentinel_subcategory_uses_is_null():
    conn, cur = _conn_with_cursor([])
    transactions.list_transactions(
        conn,
        page=1,
        page_size=50,
        days_back=30,
        category="Car",
        direction=None,
        search=None,
        subcategory="No subcategory",
    )
    sql, params = cur.execute.call_args[0]
    assert "subcategory IS NULL" in sql
    assert "No subcategory" not in params


def test_by_category_binds_both_dates_and_is_inclusive_to_date_to():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    stats.by_category(conn, date(2026, 6, 1), date(2026, 6, 30), direction="expense")
    sql, params = cur.execute.call_args[0]
    assert "booking_date >= %s" in sql
    assert "< %s::date + INTERVAL '1 day'" in sql  # half-open upper bound => date_to inclusive
    assert "days_back" not in sql.lower()
    assert params == (date(2026, 6, 1), date(2026, 6, 30))


def test_subcategory_breakdown_binds_date_range():
    from datetime import date

    conn, cur = _conn_with_cursor([])
    stats.subcategory_breakdown(
        conn, "Car", date(2026, 6, 1), date(2026, 6, 30), direction="expense"
    )
    sql, params = cur.execute.call_args[0]
    assert "booking_date >= %s" in sql
    assert "< %s::date + INTERVAL '1 day'" in sql
    assert "days_back" not in sql.lower()
    # category param first, then the two dates
    assert params == ["Car", date(2026, 6, 1), date(2026, 6, 30)]


def _dict_cursor_conn(fetchone_seq):
    """A conn whose dict_row cursor returns the given fetchone values in order."""
    from unittest.mock import MagicMock

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = list(fetchone_seq)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_account_types_are_the_single_source():
    assert frozenset({"cash", "bank", "card", "savings"}) == accounts.ACCOUNT_TYPES


def test_create_account_namespaces_uid_and_marks_manual():
    row = {
        "account_id": "manual:x",
        "display_name": "Wallet",
        "type": "cash",
        "currency": "EUR",
        "is_manual": True,
        "opening_balance": 200.0,
    }
    conn, cur = _dict_cursor_conn([row])
    from decimal import Decimal

    out = accounts.create_account(
        conn, display_name="Wallet", type="cash", opening_balance=Decimal("200")
    )
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO accounts" in sql and "TRUE" in sql  # is_manual literal TRUE
    assert params[0].startswith("manual:")
    assert out["opening_balance"] == 200.0 and isinstance(out["opening_balance"], float)


def test_get_account_returns_none_when_absent():
    conn, _ = _dict_cursor_conn([None])
    assert accounts.get_account(conn, "manual:nope") is None


def test_update_account_only_sets_provided_fields():
    row = {
        "account_id": "manual:x",
        "display_name": "Cash",
        "type": "cash",
        "currency": "EUR",
        "is_manual": True,
        "opening_balance": 0.0,
    }
    conn, cur = _dict_cursor_conn([row])
    accounts.update_account(conn, "manual:x", display_name="Cash")
    sql, params = cur.execute.call_args[0]
    assert "display_name = %s" in sql
    assert "type = %s" not in sql and "opening_balance = %s" not in sql
    assert params == ["Cash", "manual:x"]


def test_delete_account_blocks_non_manual():
    conn, _ = _dict_cursor_conn(
        [
            {
                "account_id": "eb1",
                "display_name": "Revolut",
                "type": "bank",
                "currency": "EUR",
                "is_manual": False,
                "opening_balance": 10.0,
            },
        ]
    )
    assert accounts.delete_account(conn, "eb1") == "protected"


def test_delete_account_blocks_when_transactions_exist():
    conn, _ = _dict_cursor_conn(
        [
            {
                "account_id": "manual:x",
                "display_name": "Cash",
                "type": "cash",
                "currency": "EUR",
                "is_manual": True,
                "opening_balance": 0.0,
            },  # get_account
            (1,),  # the "SELECT 1 FROM transactions" probe finds a row
        ]
    )
    assert accounts.delete_account(conn, "manual:x") == "has_transactions"


def test_delete_account_deletes_empty_manual():
    conn, cur = _dict_cursor_conn(
        [
            {
                "account_id": "manual:x",
                "display_name": "Cash",
                "type": "cash",
                "currency": "EUR",
                "is_manual": True,
                "opening_balance": 0.0,
            },  # get_account
            None,  # no transactions
        ]
    )
    assert accounts.delete_account(conn, "manual:x") == "deleted"
    assert any("DELETE FROM accounts" in c.args[0] for c in cur.execute.call_args_list)
