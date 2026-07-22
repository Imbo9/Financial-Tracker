import uuid
from decimal import Decimal

from psycopg.rows import dict_row


def balances(conn) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        # LEFT JOIN from accounts so a registered account with no transactions still
        # shows (opening + 0). transactions (not real_transactions): internal rows count
        # for EB-balance reconciliation. Scope = the accounts table; stale post-renewal
        # EB uids are absent from it and correctly excluded.
        cur.execute(
            """SELECT a.account_uid AS account_id,
                      ROUND((a.opening_balance + COALESCE(SUM(t.eur_amount), 0))::numeric, 2)
                        AS balance,
                      a.display_name, a.type, a.currency, a.is_manual, a.opening_balance
               FROM accounts a
               LEFT JOIN transactions t ON t.account_id = a.account_uid
               GROUP BY a.account_uid, a.opening_balance, a.display_name,
                        a.type, a.currency, a.is_manual
               ORDER BY balance DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
    account_list = [
        {
            "account_id": r["account_id"],
            "balance": float(r["balance"]),
            "display_name": r["display_name"],
            "type": r["type"],
            "currency": r["currency"],
            "is_manual": r["is_manual"],
            "opening_balance": float(r["opening_balance"]),
        }
        for r in rows
    ]
    assets = round(sum(a["balance"] for a in account_list if a["balance"] > 0), 2)
    liabilities = round(abs(sum(a["balance"] for a in account_list if a["balance"] < 0)), 2)
    return {"assets": assets, "liabilities": liabilities, "accounts": account_list}


ACCOUNT_TYPES = frozenset({"cash", "bank", "card", "savings"})

_ACCOUNT_COLS = (
    "account_uid AS account_id, display_name, type, currency, is_manual, opening_balance"
)


def _account_out(row: dict) -> dict:
    row = dict(row)
    row["opening_balance"] = float(row["opening_balance"])
    return row


def get_account(conn, account_uid: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_ACCOUNT_COLS} FROM accounts WHERE account_uid = %s",
            (account_uid,),
        )
        row = cur.fetchone()
    return _account_out(row) if row else None


def create_account(
    conn,
    *,
    display_name: str,
    type: str,
    currency: str = "EUR",
    opening_balance: Decimal = Decimal("0"),
) -> dict:
    account_uid = f"manual:{uuid.uuid4().hex}"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""INSERT INTO accounts
                    (account_uid, display_name, type, currency, is_manual, opening_balance)
                VALUES (%s, %s, %s, %s, TRUE, %s)
                RETURNING {_ACCOUNT_COLS}""",
            (account_uid, display_name, type, currency, opening_balance),
        )
        row = cur.fetchone()
    conn.commit()
    return _account_out(row)


def update_account(
    conn,
    account_uid: str,
    *,
    display_name: str | None = None,
    type: str | None = None,
    opening_balance: Decimal | None = None,
) -> dict | None:
    sets: list[str] = []
    params: list = []
    if display_name is not None:
        sets.append("display_name = %s")
        params.append(display_name)
    if type is not None:
        sets.append("type = %s")
        params.append(type)
    if opening_balance is not None:
        sets.append("opening_balance = %s")
        params.append(opening_balance)
    if not sets:
        return get_account(conn, account_uid)
    params.append(account_uid)
    with conn.cursor(row_factory=dict_row) as cur:
        sql = (
            f"UPDATE accounts SET {', '.join(sets)} WHERE account_uid = %s "
            f"RETURNING {_ACCOUNT_COLS}"
        )
        cur.execute(sql, params)
        row = cur.fetchone()
    conn.commit()
    return _account_out(row) if row else None


def delete_account(conn, account_uid: str) -> str:
    acc = get_account(conn, account_uid)
    if acc is None:
        return "not_found"
    if not acc["is_manual"]:
        return "protected"  # EB accounts are system-managed; they reappear on calibration
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM transactions WHERE account_id = %s LIMIT 1",
            (account_uid,),
        )
        if cur.fetchone() is not None:
            return "has_transactions"
        cur.execute("DELETE FROM accounts WHERE account_uid = %s", (account_uid,))
    conn.commit()
    return "deleted"
