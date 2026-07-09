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
    """Returns tickers from active holdings (quantity > 0) and active watchlist entries."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT
                t.id, t.symbol, t.name, t.sector, t.industry,
                t.currency, t.long_business_summary,
                CASE WHEN h.ticker_id IS NOT NULL THEN 'HOLDING' ELSE 'WATCHLIST' END AS phase
            FROM tickers t
            LEFT JOIN holdings h ON h.ticker_id = t.id AND h.quantity > 0
            LEFT JOIN watchlist w ON w.ticker_id = t.id AND w.active = 1
            WHERE h.ticker_id IS NOT NULL OR w.ticker_id IS NOT NULL
        """)
        return cur.fetchall()


def get_known_symbols(conn: pymysql.Connection) -> set[str]:
    """Returns all known ticker symbols from the tickers table."""
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM tickers")
        return {row["symbol"] for row in cur.fetchall()}


def get_latest_actions(conn: pymysql.Connection) -> dict[int, str]:
    """Most recent stored action per ticker — the previous run's view.

    Must be read before this run's recommendations are written, so a flip
    means "changed vs the immediately-preceding run" (same semantics as the
    digest dashboard's action-flips panel).
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.ticker_id, r.action
            FROM recommendations r
            JOIN (
                SELECT ticker_id, MAX(generated_at) AS latest_at
                FROM recommendations
                GROUP BY ticker_id
            ) m ON m.ticker_id = r.ticker_id AND m.latest_at = r.generated_at
        """)
        return {row["ticker_id"]: row["action"] for row in cur.fetchall()}
