import psycopg2.extras


def balances(conn) -> dict:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT account_id, ROUND(SUM(eur_amount)::numeric, 2) AS balance
               FROM real_transactions
               WHERE account_id IS NOT NULL
               GROUP BY account_id
               ORDER BY balance DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
    accounts = [{"account_id": r["account_id"], "balance": float(r["balance"])} for r in rows]
    assets = round(sum(a["balance"] for a in accounts if a["balance"] > 0), 2)
    liabilities = round(abs(sum(a["balance"] for a in accounts if a["balance"] < 0)), 2)
    return {"assets": assets, "liabilities": liabilities, "accounts": accounts}
