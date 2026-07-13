from psycopg.rows import dict_row


def balances(conn) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        # transactions (not real_transactions): internal rows included for EB-balance calibration.
        cur.execute(
            """SELECT t.account_id,
                      ROUND((COALESCE(a.opening_balance, 0) + SUM(t.eur_amount))::numeric, 2)
                          AS balance,
                      a.display_name
               FROM transactions t
               LEFT JOIN accounts a ON a.account_uid = t.account_id
               WHERE t.account_id IS NOT NULL
               GROUP BY t.account_id, a.opening_balance, a.display_name
               ORDER BY balance DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
    accounts = [
        {
            "account_id": r["account_id"],
            "balance": float(r["balance"]),
            "display_name": r["display_name"],
        }
        for r in rows
    ]
    assets = round(sum(a["balance"] for a in accounts if a["balance"] > 0), 2)
    liabilities = round(abs(sum(a["balance"] for a in accounts if a["balance"] < 0)), 2)
    return {"assets": assets, "liabilities": liabilities, "accounts": accounts}
