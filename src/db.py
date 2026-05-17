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
