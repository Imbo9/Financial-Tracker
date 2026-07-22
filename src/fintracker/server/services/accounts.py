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
