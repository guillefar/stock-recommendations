import json
import logging
from datetime import date, datetime, timedelta, timezone

import pymysql

from src.analysis.claude_client import MODEL

logger = logging.getLogger(__name__)

# A ticker with a recommendation newer than this is a duplicate of the current run
# (protects against same-slot workflow retries) while still allowing the two
# scheduled runs per day to each write their own row.
DEDUP_WINDOW_HOURS = 4


def _utcnow() -> datetime:
    """Naive UTC timestamp (replaces deprecated datetime.utcnow())."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def write_macro_signals(conn: pymysql.Connection, signals: list[dict], dry_run: bool = False) -> list[int]:
    """Inserts macro signals and returns their new IDs (or -1 each in dry-run)."""
    if dry_run:
        logger.info(f"[dry-run] Would insert {len(signals)} macro signals")
        return [-1] * len(signals)

    ids = []
    with conn.cursor() as cur:
        for signal in signals:
            cur.execute(
                """
                INSERT INTO macro_signals
                  (detected_at, theme, affected_sectors, direction, source_headlines, summary)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    _utcnow(),
                    signal.get("theme"),
                    json.dumps(signal.get("affected_sectors", [])),
                    json.dumps(signal.get("direction", {})),
                    json.dumps(signal.get("source_headlines", [])),
                    signal.get("summary"),
                ),
            )
            ids.append(cur.lastrowid)
    logger.info(f"Inserted {len(ids)} macro signals")
    return ids


def write_reddit_mentions(
    conn: pymysql.Connection,
    ticker_id: int | None,
    posts: list[dict],
    dry_run: bool = False,
) -> None:
    """Inserts reddit mentions using INSERT IGNORE for idempotency.

    For unmatched posts (ticker_id=None) the UNIQUE key can't dedup — MySQL
    treats every NULL as distinct — so existing NULL-ticker post_ids are
    pre-selected and skipped instead.
    """
    if dry_run:
        logger.info(f"[dry-run] Would insert {len(posts)} reddit mentions for ticker_id={ticker_id}")
        return

    if ticker_id is None and posts:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(posts))
            cur.execute(
                f"""
                SELECT post_id FROM reddit_mentions
                WHERE ticker_id IS NULL AND post_id IN ({placeholders})
                """,
                [p["id"] for p in posts],
            )
            existing = {row["post_id"] for row in cur.fetchall()}
        if existing:
            posts = [p for p in posts if p["id"] not in existing]
            logger.info(f"Skipping {len(existing)} already-stored unmatched reddit posts")

    with conn.cursor() as cur:
        for post in posts:
            try:
                cur.execute(
                    """
                    INSERT IGNORE INTO reddit_mentions
                      (ticker_id, post_id, post_title, post_url, post_score,
                       post_created_at, sentiment, captured_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)
                    """,
                    (
                        ticker_id,
                        post["id"],
                        (post.get("title") or "")[:500],
                        (post.get("url") or "")[:500],
                        post.get("score", 0),
                        post.get("created_at"),
                        _utcnow(),
                    ),
                )
            except pymysql.err.IntegrityError:
                pass


def write_price_check(
    conn: pymysql.Connection,
    ticker_id: int,
    price: float | None,
    dry_run: bool = False,
) -> None:
    """Upserts today's observed price for a ticker (one row per ticker per day).

    Feeds the in-repo `price_checks` table so outcomes stay gradeable while the
    sibling price_snapshots table is stale. The second run of the day refreshes
    the price.
    """
    if price is None:
        logger.warning(f"No price to record for ticker_id={ticker_id} — skipping price check")
        return
    if dry_run:
        logger.info(f"[dry-run] Would upsert price check for ticker_id={ticker_id}: {price}")
        return

    now = _utcnow()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO price_checks (ticker_id, as_of_date, price, created_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              price      = VALUES(price),
              created_at = VALUES(created_at)
            """,
            (ticker_id, now.date(), price, now),
        )


def write_recommendation(
    conn: pymysql.Connection,
    ticker_id: int,
    recommendation: dict,
    technical: dict,
    sentiment_summary: dict,
    macro_signal_id: int | None,
    dry_run: bool = False,
) -> None:
    """Inserts a recommendation row. Skips if one exists for this ticker within the dedup window."""
    if dry_run:
        logger.info(
            f"[dry-run] Would insert recommendation for ticker_id={ticker_id}: "
            f"{recommendation.get('action')}"
        )
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM recommendations
            WHERE ticker_id = %s AND generated_at >= %s
            """,
            (ticker_id, _utcnow() - timedelta(hours=DEDUP_WINDOW_HOURS)),
        )
        if cur.fetchone()["cnt"] > 0:
            logger.info(
                f"Skipping duplicate recommendation for ticker_id={ticker_id} "
                f"(row within last {DEDUP_WINDOW_HOURS}h)"
            )
            return

        cur.execute(
            """
            INSERT INTO recommendations
              (ticker_id, generated_at, action, confidence, reasoning,
               technical, sentiment, macro_signal_id, model_used)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                ticker_id,
                _utcnow(),
                recommendation.get("action", "HOLD"),
                recommendation.get("confidence"),
                recommendation.get("reasoning"),
                json.dumps(technical),
                json.dumps(sentiment_summary),
                macro_signal_id if macro_signal_id and macro_signal_id > 0 else None,
                MODEL,
            ),
        )


def write_daily_summary(
    conn: pymysql.Connection,
    summary: dict,
    post_count: int,
    dry_run: bool = False,
) -> None:
    """Upserts the daily market summary (one row per calendar date)."""
    if dry_run:
        logger.info(f"[dry-run] Would upsert daily summary: {summary.get('overall_sentiment')}")
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO daily_market_summary
              (summary_date, generated_at, summary, hot_tickers, overall_sentiment, source_post_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              generated_at      = VALUES(generated_at),
              summary           = VALUES(summary),
              hot_tickers       = VALUES(hot_tickers),
              overall_sentiment = VALUES(overall_sentiment),
              source_post_count = VALUES(source_post_count)
            """,
            (
                date.today(),
                _utcnow(),
                summary.get("summary"),
                json.dumps(summary.get("hot_tickers", [])),
                summary.get("overall_sentiment", "NEUTRAL"),
                post_count,
            ),
        )
    logger.info(f"Upserted daily summary: {summary.get('overall_sentiment')}")


def write_weekly_retrospective(
    conn: pymysql.Connection,
    week_start: date,
    retro: dict,
    stats: dict,
    dry_run: bool = False,
) -> None:
    """Upserts the week-in-review (S5; one row per week, keyed on its Monday)."""
    if dry_run:
        logger.info(f"[dry-run] Would upsert weekly retrospective for week {week_start}")
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO weekly_retrospectives
              (week_start, generated_at, retrospective, stats)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              generated_at  = VALUES(generated_at),
              retrospective = VALUES(retrospective),
              stats         = VALUES(stats)
            """,
            (week_start, _utcnow(), retro.get("retrospective"), json.dumps(stats)),
        )
    logger.info(f"Upserted weekly retrospective for week {week_start}")


def write_trending_tickers(
    conn: pymysql.Connection,
    trending: list[dict],
    dry_run: bool = False,
) -> None:
    """Upserts trending-unknown symbols (one row per symbol, Wave 4).

    first_seen sticks; last_seen/mention_count/avg_score reflect the latest run
    and times_seen counts the runs the symbol trended on (once per day at most,
    since the cron is daily).
    """
    if dry_run:
        logger.info(
            f"[dry-run] Would upsert {len(trending)} trending tickers: "
            f"{[t['symbol'] for t in trending]}"
        )
        return

    today = _utcnow().date()
    with conn.cursor() as cur:
        for t in trending:
            cur.execute(
                """
                INSERT INTO trending_tickers
                  (symbol, first_seen, last_seen, times_seen, mention_count, avg_score)
                VALUES (%s, %s, %s, 1, %s, %s)
                ON DUPLICATE KEY UPDATE
                  times_seen    = times_seen + (last_seen <> VALUES(last_seen)),
                  last_seen     = VALUES(last_seen),
                  mention_count = VALUES(mention_count),
                  avg_score     = VALUES(avg_score)
                """,
                (t["symbol"][:10], today, today, t.get("mention_count", 0), t.get("avg_score")),
            )
    logger.info(f"Upserted {len(trending)} trending tickers")
