import json
import logging
from datetime import date, datetime, timezone

import pymysql

from src.analysis.claude_client import MODEL

logger = logging.getLogger(__name__)


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
    """Inserts reddit mentions using INSERT IGNORE for idempotency."""
    if dry_run:
        logger.info(f"[dry-run] Would insert {len(posts)} reddit mentions for ticker_id={ticker_id}")
        return

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


def write_recommendation(
    conn: pymysql.Connection,
    ticker_id: int,
    recommendation: dict,
    technical: dict,
    sentiment_summary: dict,
    macro_signal_id: int | None,
    dry_run: bool = False,
) -> None:
    """Inserts a recommendation row. Skips if one already exists for this ticker today."""
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
            WHERE ticker_id = %s AND DATE(generated_at) = %s
            """,
            (ticker_id, date.today()),
        )
        if cur.fetchone()["cnt"] > 0:
            logger.info(f"Skipping duplicate recommendation for ticker_id={ticker_id} (already exists today)")
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
