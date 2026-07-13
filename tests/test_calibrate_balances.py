from decimal import Decimal
from unittest.mock import MagicMock

import scripts.calibrate_balances as cal  # pyrefly: ignore[missing-import]


def _conn_with_cursor(delta_sum):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (delta_sum,)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_opening_is_eb_balance_minus_known_deltas(monkeypatch):
    monkeypatch.setattr(cal, "fetch_balances", lambda client, uid: Decimal("150.00"))
    monkeypatch.setattr(cal.time, "sleep", lambda s: None)
    conn, cur = _conn_with_cursor(Decimal("-50.00"))

    out = cal.calibrate(conn, MagicMock(), ["acc-1"])

    assert out["acc-1"]["opening"] == Decimal("200.00")  # 150 - (-50)
    # The delta SUM must span ALL rows — a stray is_internal filter would mis-calibrate
    # every opening balance, and the mocked cursor wouldn't catch it. Pin the SQL text.
    select_sql = cur.execute.call_args_list[0].args[0]
    assert (
        select_sql == "SELECT COALESCE(SUM(eur_amount), 0) FROM transactions WHERE account_id = %s"
    )
    assert "is_internal" not in select_sql
    upsert_sql, upsert_params = cur.execute.call_args_list[1].args
    assert "ON CONFLICT (account_uid) DO UPDATE" in upsert_sql
    assert upsert_params == ("acc-1", Decimal("200.00"), Decimal("150.00"))
    assert conn.commit.called


def test_calibrates_every_account_with_delay(monkeypatch):
    calls = []
    monkeypatch.setattr(cal, "fetch_balances", lambda client, uid: Decimal("10.00"))
    monkeypatch.setattr(cal.time, "sleep", lambda s: calls.append(s))
    conn, _cur = _conn_with_cursor(Decimal("0"))

    out = cal.calibrate(conn, MagicMock(), ["a", "b", "c"])

    assert set(out) == {"a", "b", "c"}
    assert calls == [2, 2]  # delay between accounts, not before the first
