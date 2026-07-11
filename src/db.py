from datetime import datetime

import pymysql
import pymysql.cursors

from src.config import Config


def get_connection(cfg: Config) -> pymysql.Connection:
    return pymysql.connect(
        host=cfg.db_host,
        port=cfg.db_port,
        user=cfg.db_user,
        password=cfg.db_pass,
        database=cfg.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def get_active_tickers(conn: pymysql.Connection) -> list[dict]:
    """Returns tickers from active holdings (quantity > 0) and active watchlist entries.

    A ticker that is both held and watchlisted comes back once, as HOLDING
    (the watchlist arm excludes held tickers).
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT
                t.id, t.symbol, t.name, t.sector, t.industry, t.quote_type,
                t.currency, t.long_business_summary, 'HOLDING' AS phase
            FROM tickers t
            JOIN holdings h ON h.ticker_id = t.id AND h.quantity > 0
            UNION
            SELECT DISTINCT
                t.id, t.symbol, t.name, t.sector, t.industry, t.quote_type,
                t.currency, t.long_business_summary, 'WATCHLIST' AS phase
            FROM tickers t
            JOIN watchlist w ON w.ticker_id = t.id AND w.active = 1
            LEFT JOIN holdings h ON h.ticker_id = t.id AND h.quantity > 0
            WHERE h.ticker_id IS NULL
        """)
        return cur.fetchall()


def get_known_symbols(conn: pymysql.Connection) -> set[str]:
    """Returns all known ticker symbols from the tickers table."""
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM tickers")
        return {row["symbol"] for row in cur.fetchall()}


def get_latest_actions(conn: pymysql.Connection) -> dict[int, dict]:
    """Most recent stored action per ticker — the previous run's view.

    Returns {ticker_id: {"action": str, "held_since": datetime}} where
    `held_since` is the start of the current consecutive streak of that action
    (the first run after the ticker last held a *different* action) — it feeds
    the "mantenida N días" line in the ticker prompt (flip-stability).

    Must be read before this run's recommendations are written, so a flip
    means "changed vs the immediately-preceding run" (same semantics as the
    digest dashboard's action-flips panel).
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.ticker_id, r.action,
                (SELECT MIN(r2.generated_at)
                 FROM recommendations r2
                 WHERE r2.ticker_id = r.ticker_id
                   AND r2.generated_at > COALESCE(
                       (SELECT MAX(r3.generated_at)
                        FROM recommendations r3
                        WHERE r3.ticker_id = r.ticker_id
                          AND r3.action <> r.action),
                       '1970-01-01')
                ) AS held_since
            FROM recommendations r
            JOIN (
                SELECT ticker_id, MAX(generated_at) AS latest_at
                FROM recommendations
                GROUP BY ticker_id
            ) m ON m.ticker_id = r.ticker_id AND m.latest_at = r.generated_at
        """)
        return {
            row["ticker_id"]: {"action": row["action"], "held_since": row["held_since"]}
            for row in cur.fetchall()
        }


def get_week_outcomes(
    conn: pymysql.Connection, now: datetime, horizon: int = 30
) -> list[dict]:
    """Graded outcomes whose horizon fell due in the 7 days before `now` (S5).

    Maturity is `generated_at + horizon`, not `evaluated_at` — a backfill or
    re-grade rewrites evaluated_at for old rows and would flood the first
    retrospective after it.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              t.symbol, o.action, o.confidence, o.forward_return, o.verdict,
              DATE(o.generated_at) AS called_on
            FROM recommendation_outcomes o
            JOIN tickers t ON t.id = o.ticker_id
            WHERE o.horizon_days = %s
              AND o.generated_at + INTERVAL %s DAY >  %s - INTERVAL 7 DAY
              AND o.generated_at + INTERVAL %s DAY <= %s
            ORDER BY o.forward_return DESC
            """,
            (horizon, horizon, now, horizon, now),
        )
        return cur.fetchall()


def get_week_flips(conn: pymysql.Connection, now: datetime) -> list[dict]:
    """Action flips in the 7 days before `now` (S5).

    Same flip semantics as the digest's panel-9: this recommendation's action
    vs the ticker's immediately-preceding stored recommendation.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              DATE(r2.generated_at) AS day,
              t.symbol,
              r1.action AS prev_action,
              r2.action AS new_action
            FROM recommendations r2
            JOIN recommendations r1
              ON r1.ticker_id = r2.ticker_id
             AND r1.generated_at = (
               SELECT MAX(r3.generated_at) FROM recommendations r3
               WHERE r3.ticker_id = r2.ticker_id AND r3.generated_at < r2.generated_at
             )
             AND r1.action <> r2.action
            JOIN tickers t ON t.id = r2.ticker_id
            WHERE r2.generated_at > %s - INTERVAL 7 DAY
              AND r2.generated_at <= %s
            ORDER BY r2.generated_at, t.symbol
            """,
            (now, now),
        )
        return cur.fetchall()
