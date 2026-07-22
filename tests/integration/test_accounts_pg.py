from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fintracker.server.services import accounts, stats

pytestmark = pytest.mark.integration


def _clean_accounts(conn):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE accounts")
    conn.commit()


def test_manual_account_lifecycle_and_balance(db_conn):
    _clean_accounts(db_conn)
    acc = accounts.create_account(
        db_conn, display_name="Wallet", type="cash", opening_balance=Decimal("200")
    )
    uid = acc["account_id"]
    assert uid.startswith("manual:")

    # Zero-transaction account still appears with its opening balance (LEFT JOIN).
    out = accounts.balances(db_conn)
    mine = next(a for a in out["accounts"] if a["account_id"] == uid)
    assert mine["balance"] == 200.0 and mine["type"] == "cash" and mine["is_manual"] is True

    # A transaction on it moves the balance.
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO transactions
                   (dedup_hash, booking_date, amount, currency, eur_amount, account_id,
                    is_internal, status, source)
               VALUES ('m1', %s, -30, 'EUR', -30, %s, FALSE, 'verified', 'manual')""",
            (datetime(2026, 7, 5, tzinfo=UTC), uid),
        )
    db_conn.commit()
    out = accounts.balances(db_conn)
    assert next(a for a in out["accounts"] if a["account_id"] == uid)["balance"] == 170.0


def test_delete_rules(db_conn):
    _clean_accounts(db_conn)
    acc = accounts.create_account(db_conn, display_name="Wallet", type="cash")
    uid = acc["account_id"]
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO transactions
                   (dedup_hash, booking_date, amount, currency, eur_amount, account_id,
                    is_internal, status, source)
               VALUES ('m2', %s, -5, 'EUR', -5, %s, FALSE, 'verified', 'manual')""",
            (datetime(2026, 7, 6, tzinfo=UTC), uid),
        )
    db_conn.commit()
    assert accounts.delete_account(db_conn, uid) == "has_transactions"

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM transactions WHERE account_id = %s", (uid,))
    db_conn.commit()
    assert accounts.delete_account(db_conn, uid) == "deleted"
    assert accounts.get_account(db_conn, uid) is None


def test_calibrate_does_not_clobber_type_or_name(db_conn, monkeypatch):
    import scripts.calibrate_balances as cal  # pyrefly: ignore[missing-import]

    _clean_accounts(db_conn)
    # A user-typed EB account row already exists.
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO accounts (account_uid, display_name, type, is_manual, opening_balance)
               VALUES ('eb-1', 'My Revolut', 'card', FALSE, 0)"""
        )
    db_conn.commit()

    # Calibrate the EB uid for real: its ON CONFLICT DO UPDATE must touch only
    # opening/eb/calibrated and leave user-set type/display_name intact.
    monkeypatch.setattr(cal, "fetch_balances", lambda client, uid: Decimal("50.00"))
    monkeypatch.setattr(cal.time, "sleep", lambda s: None)
    cal.calibrate(db_conn, object(), ["eb-1"])

    got = accounts.get_account(db_conn, "eb-1")
    assert got["display_name"] == "My Revolut" and got["type"] == "card"
    assert got["opening_balance"] == 50.0  # opening recalibrated (50 - 0 deltas), name/type kept


def test_balance_history_reconciles_with_manual_opening(db_conn):
    _clean_accounts(db_conn)
    accounts.create_account(
        db_conn, display_name="Wallet", type="cash", opening_balance=Decimal("200")
    )
    series = stats.balance_history(db_conn, months=12)
    net_worth = accounts.balances(db_conn)
    total = net_worth["assets"] - net_worth["liabilities"]
    assert round(series[-1]["balance"], 2) == round(total, 2)  # last point == net worth


def test_balance_history_sums_manual_opening_and_same_month_tx(db_conn):
    # A manual account's opening and a transaction that land in the SAME calendar month
    # must be summed by balance_history's outer SUM(net)/GROUP BY, not overwrite each other
    # (the failure mode the Task 6 structural test alone could not catch).
    _clean_accounts(db_conn)
    acc = accounts.create_account(
        db_conn, display_name="Wallet", type="cash", opening_balance=Decimal("200")
    )
    uid = acc["account_id"]
    with db_conn.cursor() as cur:
        cur.execute(
            """INSERT INTO transactions
                   (dedup_hash, booking_date, amount, currency, eur_amount, account_id,
                    is_internal, status, source)
               VALUES ('m-sum', DATE_TRUNC('month', NOW()), -30, 'EUR', -30, %s,
                       FALSE, 'verified', 'manual')""",
            (uid,),
        )
    db_conn.commit()
    series = stats.balance_history(db_conn, months=12)
    net_worth = accounts.balances(db_conn)
    total = net_worth["assets"] - net_worth["liabilities"]
    # opening 200 + same-month net -30 = 170; an overwrite bug would yield 200 or -30.
    assert round(total, 2) == 170.0
    assert round(series[-1]["balance"], 2) == 170.0
