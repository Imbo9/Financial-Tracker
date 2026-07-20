from datetime import date, timedelta

from psycopg.rows import dict_row


def by_category(conn, days_back: int, direction: str = "expense") -> list[dict]:
    # Fixed literal, never user input: the route validates direction against income|expense.
    sign_filter = "amount > 0" if direction == "income" else "amount < 0"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT COALESCE(category, 'Uncategorized') AS category,
                       ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total,
                       COUNT(*) AS count
                FROM real_transactions
                WHERE {sign_filter}
                  AND booking_date >= NOW() - (%s * INTERVAL '1 day')
                GROUP BY category
                ORDER BY total DESC""",
            (days_back,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    # numeric columns arrive as Decimal; uncast, pydantic v2 serializes them as JSON strings
    for r in rows:
        r["total"] = float(r["total"])
    grand_total = sum(r["total"] for r in rows) or 1
    for r in rows:
        r["percentage"] = round(r["total"] / grand_total * 100, 1)
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
        r["income"] = float(r["income"])
        r["expenses"] = float(r["expenses"])
        r["net"] = round(r["income"] - r["expenses"], 2)
    return rows


def subcategory_breakdown(conn, category: str | None, days_back: int, direction: str) -> list[dict]:
    """Subcategory split inside one category. `category=None` is the uncategorised bucket.

    Reads real_transactions (internal rows excluded) like by_category — the opposite
    scope from balance_history, which must include them to match EB balances.
    """
    # Both fixed literals, never user input: direction is route-validated, and the
    # category filter shape depends only on whether category is None.
    sign_filter = "amount > 0" if direction == "income" else "amount < 0"
    category_filter = "category IS NULL" if category is None else "category = %s"
    params: list = [] if category is None else [category]
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT COALESCE(subcategory, 'No subcategory') AS subcategory,
                       ROUND(SUM(ABS(eur_amount))::numeric, 2) AS total,
                       COUNT(*) AS count
                FROM real_transactions
                WHERE {sign_filter}
                  AND {category_filter}
                  AND booking_date >= NOW() - (%s * INTERVAL '1 day')
                GROUP BY subcategory
                ORDER BY total DESC""",
            [*params, days_back],
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["total"] = float(r["total"])
    grand_total = sum(r["total"] for r in rows) or 1
    for r in rows:
        r["percentage"] = round(r["total"] / grand_total * 100, 1)
    return rows


def balance_history(conn, months: int = 12) -> list[dict]:
    """Monthly cumulative total balance: openings + running sum of EB-account deltas.

    Internal rows count (they move real money); manual rows (account_id IS NULL) don't,
    mirroring the accounts page scope. Only calibrated accounts (those in the accounts
    table) are summed — same INNER-JOIN scope as accounts.balances, so the last point
    reconciles with net worth and stale post-renewal account_ids are excluded.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT COALESCE(SUM(opening_balance), 0) AS total FROM accounts")
        openings = float(cur.fetchone()["total"])
        cur.execute(
            """SELECT TO_CHAR(DATE_TRUNC('month', booking_date), 'YYYY-MM') AS month,
                      SUM(eur_amount) AS net
               FROM transactions
               WHERE account_id IN (SELECT account_uid FROM accounts)
               GROUP BY 1
               ORDER BY 1"""
        )
        rows = cur.fetchall()

    nets = {r["month"]: float(r["net"]) for r in rows}
    current = date.today().replace(day=1)
    start = current
    for _ in range(months - 1):
        start = (start - timedelta(days=1)).replace(day=1)
    if rows:
        first_year, first_month = map(int, rows[0]["month"].split("-"))
        start = min(start, date(first_year, first_month, 1))

    series: list[dict] = []
    running = openings
    cursor_month = start
    while cursor_month <= current:
        key = cursor_month.strftime("%Y-%m")
        running = round(running + nets.get(key, 0.0), 2)
        series.append({"month": key, "balance": running})
        next_month = cursor_month.month % 12 + 1
        cursor_month = date(cursor_month.year + (cursor_month.month == 12), next_month, 1)
    return series[-months:]
