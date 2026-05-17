import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from src.analysis.claude_client import ClaudeClient
from src.analysis.macro import run_macro_analysis
from src.analysis.recommendation import run_ticker_recommendation
from src.analysis.summary import run_daily_summary
from src.collectors.news import fetch_macro_headlines
from src.collectors.prices import fetch_prices_and_indicators
from src.collectors.reddit import extract_ticker_mentions, fetch_reddit_posts, find_trending_unknown
from src.config import load_config
from src.db import get_active_tickers, get_connection, get_known_symbols
from src.persistence.writers import (
    write_daily_summary,
    write_macro_signals,
    write_recommendation,
    write_reddit_mentions,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main(dry_run: bool = False) -> None:
    logger.info(f"Starting stock-recommendations run (dry_run={dry_run})")
    cfg = load_config()

    claude = ClaudeClient(cfg)

    # ── 1. Load active tickers ──────────────────────────────────────────────
    conn = get_connection(cfg)
    try:
        tickers = get_active_tickers(conn)
        known_symbols = get_known_symbols(conn)
    finally:
        conn.close()

    logger.info(f"Active tickers: {[t['symbol'] for t in tickers]}")

    # ── 2. Fetch Reddit posts ───────────────────────────────────────────────
    logger.info("Fetching Reddit posts from /r/stocks...")
    reddit_posts = fetch_reddit_posts(cfg)

    # ── 3. Fetch macro headlines ────────────────────────────────────────────
    logger.info("Fetching macro headlines from RSS feeds...")
    headlines = fetch_macro_headlines()
    logger.info(f"Got {len(headlines)} macro headlines")

    # ── 4. Macro analysis (1 Claude call) ──────────────────────────────────
    logger.info("Running macro analysis with Claude...")
    macro_signals = run_macro_analysis(claude, headlines)

    conn = get_connection(cfg)
    try:
        macro_signal_ids = write_macro_signals(conn, macro_signals, dry_run=dry_run)
    finally:
        conn.close()

    # ── 5. Extract Reddit ticker mentions ───────────────────────────────────
    ticker_mentions = extract_ticker_mentions(reddit_posts, known_symbols)

    # ── 6. Per-ticker analysis ──────────────────────────────────────────────
    all_recommendations = []

    for ticker in tickers:
        symbol = ticker["symbol"]
        logger.info(f"Processing {symbol}...")

        technical = fetch_prices_and_indicators(symbol)
        if not technical:
            logger.warning(f"No technical data for {symbol}, skipping")
            continue

        posts_for_ticker = ticker_mentions.get(symbol, [])
        scores = [p["score"] for p in posts_for_ticker]
        sentiment_summary = {
            "mention_count": len(posts_for_ticker),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "top_posts": [
                {"title": p["title"], "score": p["score"]}
                for p in sorted(posts_for_ticker, key=lambda x: x["score"], reverse=True)[:3]
            ],
        }

        ticker_data = {**ticker, "technical": technical, "sentiment": sentiment_summary}
        recommendation = run_ticker_recommendation(claude, ticker_data, macro_signals)

        action = recommendation.get("action", "?")
        confidence = recommendation.get("confidence", 0)
        logger.info(f"{symbol}: {action} (confidence={confidence:.0%})")

        # Find most relevant macro signal for this ticker's sector
        relevant_macro_id = None
        for i, signal in enumerate(macro_signals):
            if ticker.get("sector") in (signal.get("affected_sectors") or []):
                relevant_macro_id = macro_signal_ids[i]
                break

        conn = get_connection(cfg)
        try:
            write_recommendation(
                conn, ticker["id"], recommendation, technical,
                sentiment_summary, relevant_macro_id, dry_run=dry_run,
            )
            if posts_for_ticker:
                write_reddit_mentions(conn, ticker["id"], posts_for_ticker, dry_run=dry_run)
        finally:
            conn.close()

        all_recommendations.append({"symbol": symbol, **recommendation})

    # ── 7. Write Reddit mentions for posts not matched to any known ticker ──
    mentioned_post_ids = {p["id"] for posts in ticker_mentions.values() for p in posts}
    unmatched_posts = [p for p in reddit_posts if p["id"] not in mentioned_post_ids]
    if unmatched_posts:
        conn = get_connection(cfg)
        try:
            write_reddit_mentions(conn, None, unmatched_posts, dry_run=dry_run)
        finally:
            conn.close()

    # ── 8. Detect trending unknown tickers ──────────────────────────────────
    trending_unknown = find_trending_unknown(reddit_posts, known_symbols)
    if trending_unknown:
        logger.info(
            f"Trending tickers not in watchlist/holdings "
            f"(consider adding): {[t['symbol'] for t in trending_unknown]}"
        )

    # ── 9. Daily summary (1 Claude call) ────────────────────────────────────
    logger.info("Generating daily summary...")
    top_posts = sorted(reddit_posts, key=lambda x: x["score"], reverse=True)[:10]
    analysis_data = {
        "tickers_analyzed": [t["symbol"] for t in tickers],
        "macro_signals": macro_signals,
        "recommendations": all_recommendations,
        "top_reddit_posts": [{"title": p["title"], "score": p["score"]} for p in top_posts],
        "trending_suggestions": trending_unknown,
    }
    summary = run_daily_summary(claude, analysis_data)

    conn = get_connection(cfg)
    try:
        write_daily_summary(conn, summary, len(reddit_posts), dry_run=dry_run)
    finally:
        conn.close()

    logger.info(
        f"Run complete. overall_sentiment={summary.get('overall_sentiment')} "
        f"hot_tickers={summary.get('hot_tickers')}"
    )
    if trending_unknown:
        logger.info(
            f"Trending suggestions for watchlist: "
            f"{[t['symbol'] for t in trending_unknown]}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock Recommendations Runner")
    parser.add_argument("--dry-run", action="store_true", help="Log only — don't write to DB")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
