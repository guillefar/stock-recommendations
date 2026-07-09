import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from src.analysis.claude_client import ClaudeClient
from src.analysis.macro import run_macro_analysis
from src.analysis.recommendation import run_ticker_recommendations_batch
from src.analysis.summary import run_daily_summary
from src.collectors.news import fetch_macro_headlines
from src.collectors.prices import fetch_next_earnings, fetch_prices_and_indicators, fetch_ticker_news
from src.collectors.reddit import extract_ticker_mentions, fetch_reddit_posts, find_trending_unknown
from src.config import load_config
from src.db import get_active_tickers, get_connection, get_known_symbols
from src.persistence.writers import (
    write_daily_summary,
    write_macro_signals,
    write_price_check,
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

    # One connection for the whole run; ping(reconnect=True) before each write
    # phase in case it idled out during the Claude/yfinance calls.
    conn = get_connection(cfg)
    try:
        # ── 1. Load active tickers ──────────────────────────────────────────
        tickers = get_active_tickers(conn)
        known_symbols = get_known_symbols(conn)

        logger.info(f"Active tickers: {[t['symbol'] for t in tickers]}")

        # ── 2. Fetch Reddit posts ───────────────────────────────────────────
        logger.info("Fetching Reddit posts from /r/stocks...")
        reddit_posts = fetch_reddit_posts(cfg)

        # ── 3. Fetch macro headlines ────────────────────────────────────────
        logger.info("Fetching macro headlines from RSS feeds...")
        headlines = fetch_macro_headlines()
        logger.info(f"Got {len(headlines)} macro headlines")

        # ── 4. Macro analysis (1 Claude call) ───────────────────────────────
        # A Claude failure here must not kill the run: the per-ticker loop is
        # what records price_checks, and the prompt already handles "no macro".
        logger.info("Running macro analysis with Claude...")
        try:
            macro_signals = run_macro_analysis(claude, headlines)
        except Exception:
            logger.exception("Macro analysis failed — continuing without macro signals")
            macro_signals = []

        macro_signal_ids = []
        if macro_signals:
            conn.ping(reconnect=True)
            macro_signal_ids = write_macro_signals(conn, macro_signals, dry_run=dry_run)

        # ── 5. Extract Reddit ticker mentions ────────────────────────────────
        ticker_mentions = extract_ticker_mentions(reddit_posts, known_symbols)

        # ── 6a. Per-ticker data collection ───────────────────────────────────
        # Failures are isolated per ticker: log, count, and move on, so one bad
        # ticker can't abort the unattended run. The price check is written here
        # (before any Claude involvement) so a Claude outage can't lose prices.
        prepared = []
        all_recommendations = []
        failed_symbols = []

        for ticker in tickers:
            symbol = ticker["symbol"]
            logger.info(f"Collecting data for {symbol}...")

            try:
                technical = fetch_prices_and_indicators(symbol)
                if not technical:
                    logger.warning(f"No technical data for {symbol}, skipping")
                    failed_symbols.append(symbol)
                    continue

                # Record today's price even if the recommendation later fails —
                # it's what keeps outcomes gradeable (price_snapshots is stale).
                conn.ping(reconnect=True)
                write_price_check(conn, ticker["id"], technical.get("price"), dry_run=dry_run)

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

                # Both collectors degrade to empty/None on error — news and
                # earnings enrich the prompt but never fail the ticker.
                news = fetch_ticker_news(symbol)[:5]
                next_earnings = fetch_next_earnings(symbol)

                prepared.append({
                    **ticker,
                    "technical": technical,
                    "sentiment": sentiment_summary,
                    "news": news,
                    "next_earnings": next_earnings,
                })
            except Exception:
                logger.exception(f"{symbol}: data collection failed — continuing with remaining tickers")
                failed_symbols.append(symbol)

        # ── 6b. Recommendations via the Message Batches API (50% cost) ───────
        recommendations_by_symbol: dict[str, dict | None] = {}
        if prepared:
            logger.info(f"Requesting recommendations for {len(prepared)} tickers via batch...")
            try:
                recommendations_by_symbol = run_ticker_recommendations_batch(
                    claude, prepared, macro_signals
                )
            except Exception:
                logger.exception("Batch recommendation call failed — no recommendations this run")

        # ── 6c. Persist recommendations ───────────────────────────────────────
        for ticker_data in prepared:
            symbol = ticker_data["symbol"]
            try:
                recommendation = recommendations_by_symbol.get(symbol)
                if recommendation is None:
                    logger.error(f"{symbol}: no usable Claude response — nothing persisted")
                    failed_symbols.append(symbol)
                    continue

                action = recommendation.get("action", "?")
                confidence = recommendation.get("confidence", 0)
                logger.info(f"{symbol}: {action} (confidence={confidence:.0%})")

                # Find most relevant macro signal for this ticker's sector
                relevant_macro_id = None
                for i, signal in enumerate(macro_signals):
                    if ticker_data.get("sector") in (signal.get("affected_sectors") or []):
                        relevant_macro_id = macro_signal_ids[i]
                        break

                conn.ping(reconnect=True)
                write_recommendation(
                    conn, ticker_data["id"], recommendation, ticker_data["technical"],
                    ticker_data["sentiment"], relevant_macro_id, dry_run=dry_run,
                )
                posts_for_ticker = ticker_mentions.get(symbol, [])
                if posts_for_ticker:
                    write_reddit_mentions(conn, ticker_data["id"], posts_for_ticker, dry_run=dry_run)

                all_recommendations.append({"symbol": symbol, **recommendation})
            except Exception:
                logger.exception(f"{symbol}: persistence failed — continuing with remaining tickers")
                failed_symbols.append(symbol)

        # ── 7. Write Reddit mentions for posts not matched to any known ticker ──
        mentioned_post_ids = {p["id"] for posts in ticker_mentions.values() for p in posts}
        unmatched_posts = [p for p in reddit_posts if p["id"] not in mentioned_post_ids]
        if unmatched_posts:
            conn.ping(reconnect=True)
            write_reddit_mentions(conn, None, unmatched_posts, dry_run=dry_run)

        # ── 8. Detect trending unknown tickers ───────────────────────────────
        trending_unknown = find_trending_unknown(reddit_posts, known_symbols)
        if trending_unknown:
            logger.info(
                f"Trending tickers not in watchlist/holdings "
                f"(consider adding): {[t['symbol'] for t in trending_unknown]}"
            )

        # ── 9. Daily summary (1 Claude call) ─────────────────────────────────
        logger.info("Generating daily summary...")
        top_posts = sorted(reddit_posts, key=lambda x: x["score"], reverse=True)[:10]
        analysis_data = {
            "tickers_analyzed": [t["symbol"] for t in tickers],
            "macro_signals": macro_signals,
            "recommendations": all_recommendations,
            "top_reddit_posts": [{"title": p["title"], "score": p["score"]} for p in top_posts],
            "trending_suggestions": trending_unknown,
        }
        # A failed summary is never persisted (no "Error generando resumen."
        # placeholder overwriting the day's row) and never kills the run.
        try:
            summary = run_daily_summary(claude, analysis_data)
        except Exception:
            logger.exception("Daily summary generation failed")
            summary = None

        if summary is not None:
            conn.ping(reconnect=True)
            write_daily_summary(conn, summary, len(reddit_posts), dry_run=dry_run)
        else:
            logger.error("No daily summary persisted for today")
    finally:
        conn.close()

    logger.info(
        f"Run complete. tickers_ok={len(all_recommendations)} "
        f"tickers_failed={len(failed_symbols)}"
        f"{f' (failed: {failed_symbols})' if failed_symbols else ''} "
        f"overall_sentiment={summary.get('overall_sentiment') if summary else 'N/A'} "
        f"hot_tickers={summary.get('hot_tickers') if summary else 'N/A'}"
    )
    claude.log_usage()
    if trending_unknown:
        logger.info(
            f"Trending suggestions for watchlist: "
            f"{[t['symbol'] for t in trending_unknown]}"
        )

    if tickers and not all_recommendations:
        logger.error("Every ticker failed this run — exiting non-zero")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock Recommendations Runner")
    parser.add_argument("--dry-run", action="store_true", help="Log only — don't write to DB")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
