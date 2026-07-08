from psycopg.rows import dict_row


def by_category(conn, days_back: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT COALESCE(category, 'Uncategorized') AS category,
                      ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total,
                      COUNT(*) AS count
               FROM real_transactions
               WHERE amount < 0
                 AND booking_date >= NOW() - (%s * INTERVAL '1 day')
               GROUP BY category
               ORDER BY total DESC""",
            (days_back,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    grand_total = sum(float(r["total"]) for r in rows) or 1
    for r in rows:
        r["percentage"] = round(float(r["total"]) / grand_total * 100, 1)
    return rows


def monthly(conn, months: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT TO_CHAR(DATE_TRUNC('month', booking_date), 'YYYY-MM')
                      AS month,
                      ROUND(
                        SUM(CASE WHEN amount > 0 THEN eur_amount ELSE 0 END)
                        ::numeric,
                        2
                      ) AS income,
                      ROUND(
                        SUM(
                          CASE WHEN amount < 0 THEN ABS(eur_amount) ELSE 0 END
                        )::numeric,
                        2
                      ) AS expenses
               FROM real_transactions
               GROUP BY DATE_TRUNC('month', booking_date)
               ORDER BY DATE_TRUNC('month', booking_date) DESC
               LIMIT %s""",
            (months,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["net"] = round(float(r["income"]) - float(r["expenses"]), 2)
    return rows
