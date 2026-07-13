import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

from src.analysis.claude_client import ClaudeClient
from src.analysis.macro import run_macro_analysis
from src.analysis.patterns import (
    build_patterns_data,
    run_pattern_analysis,
    select_patterns_for_prompt,
    summarize_features,
)
from src.analysis.recommendation import run_ticker_recommendations_batch
from src.analysis.retrospective import build_retro_data, run_weekly_retrospective
from src.analysis.summary import run_daily_summary
from src.collectors.news import fetch_macro_headlines
from src.collectors.prices import (
    fetch_etf_info,
    fetch_fundamentals,
    fetch_next_earnings,
    fetch_prices_and_indicators,
    fetch_ticker_news,
)
from src.collectors.reddit import extract_ticker_mentions, fetch_reddit_posts, find_trending_unknown
from src.config import load_config
from src.db import (
    get_active_tickers,
    get_connection,
    get_known_symbols,
    get_latest_actions,
    get_latest_patterns,
    get_outcome_features,
    get_week_flips,
    get_week_outcomes,
)
from src.persistence.writers import (
    write_daily_summary,
    write_macro_signals,
    write_prediction_patterns,
    write_price_check,
    write_recommendation,
    write_reddit_mentions,
    write_run_metrics,
    write_trending_tickers,
    write_weekly_retrospective,
)

# The weekly retrospective (S5) fires on the last cron run of the trading week.
_RETRO_WEEKDAY = 4  # Friday

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _today() -> date:
    return date.today()


def _pick_macro_signal_id(sector, macro_signals: list[dict], macro_signal_ids: list) -> int | None:
    """Most relevant macro signal for a ticker's sector (stored as its link).

    Prefers a signal whose direction for the sector is POSITIVE/NEGATIVE — a
    NEUTRAL mention shouldn't shadow a signal that actually moves the sector.
    Falls back to the first sector match when none is directional.
    """
    fallback = None
    for i, signal in enumerate(macro_signals):
        if sector in (signal.get("affected_sectors") or []):
            if (signal.get("direction") or {}).get(sector) in ("POSITIVE", "NEGATIVE"):
                return macro_signal_ids[i]
            if fallback is None:
                fallback = macro_signal_ids[i]
    return fallback


def main(dry_run: bool = False, force_retro: bool = False, force_patterns: bool = False) -> None:
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

        # Previous actions must be read before this run's rows land, so a flip
        # is "vs the immediately-preceding run" (S17 — surfaced in the summary).
        # Read before 6a so each ticker prompt can carry its previous action +
        # how long it's been held (flip-stability reinforcement, session 16).
        conn.ping(reconnect=True)
        previous_actions = get_latest_actions(conn)

        # Patterns→prompt feedback loop (session 25): the newest mined pattern
        # set — gated to CONFIRMED/REVISED at confidence ≥ 0.7, top 3 — rides
        # into every ticker prompt. Fail-soft: any problem here just means the
        # prompts carry no patterns block; it never costs the run.
        prompt_patterns: list[dict] = []
        try:
            conn.ping(reconnect=True)
            prompt_patterns = select_patterns_for_prompt(get_latest_patterns(conn))
            if prompt_patterns:
                logger.info(
                    f"Injecting {len(prompt_patterns)} mined pattern(s) into ticker "
                    "prompts: " + ", ".join(p["name"] for p in prompt_patterns)
                )
            else:
                logger.info(
                    "No confirmed high-confidence patterns to inject into ticker prompts"
                )
        except Exception:
            logger.exception(
                "Pattern injection read failed — ticker prompts carry no patterns block"
            )
            prompt_patterns = []

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

                # These collectors degrade to empty/None on error — news,
                # earnings, ETF profile and fundamentals enrich the prompt but
                # never fail the ticker. The ETF fetch only runs for actual
                # ETFs and the fundamentals fetch only for actual equities
                # (quote_type from the tickers table) — indices and untyped
                # tickers pay nothing and get neither block.
                news = fetch_ticker_news(symbol)[:3]
                next_earnings = fetch_next_earnings(symbol)
                etf_info = (
                    fetch_etf_info(symbol)
                    if ticker.get("quote_type") == "ETF" else None
                )
                fundamentals = (
                    fetch_fundamentals(symbol)
                    if ticker.get("quote_type") == "EQUITY" else None
                )

                prev = previous_actions.get(ticker["id"])
                prepared.append({
                    **ticker,
                    "technical": technical,
                    "sentiment": sentiment_summary,
                    "news": news,
                    "next_earnings": next_earnings,
                    "etf_info": etf_info,
                    "fundamentals": fundamentals,
                    "prev_action": prev["action"] if prev else None,
                    "prev_held_days": (
                        (_today() - prev["held_since"].date()).days
                        if prev and prev.get("held_since") else None
                    ),
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
                    claude, prepared, macro_signals, prompt_patterns
                )
            except Exception:
                logger.exception("Batch recommendation call failed — no recommendations this run")

        # ── 6c. Persist recommendations ───────────────────────────────────────
        action_flips = []

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

                relevant_macro_id = _pick_macro_signal_id(
                    ticker_data.get("sector"), macro_signals, macro_signal_ids
                )

                conn.ping(reconnect=True)
                write_recommendation(
                    conn, ticker_data["id"], recommendation, ticker_data["technical"],
                    ticker_data["sentiment"], relevant_macro_id,
                    fundamentals=ticker_data.get("fundamentals"), dry_run=dry_run,
                )
                posts_for_ticker = ticker_mentions.get(symbol, [])
                if posts_for_ticker:
                    write_reddit_mentions(conn, ticker_data["id"], posts_for_ticker, dry_run=dry_run)

                all_recommendations.append({"symbol": symbol, **recommendation})

                prev = previous_actions.get(ticker_data["id"])
                if prev and prev["action"] != action:
                    action_flips.append(
                        {"symbol": symbol, "prev_action": prev["action"], "new_action": action}
                    )
            except Exception:
                logger.exception(f"{symbol}: persistence failed — continuing with remaining tickers")
                failed_symbols.append(symbol)

        # ── 7. Write Reddit mentions for posts not matched to any known ticker ──
        mentioned_post_ids = {p["id"] for posts in ticker_mentions.values() for p in posts}
        unmatched_posts = [p for p in reddit_posts if p["id"] not in mentioned_post_ids]
        if unmatched_posts:
            conn.ping(reconnect=True)
            write_reddit_mentions(conn, None, unmatched_posts, dry_run=dry_run)

        # ── 8. Detect + persist trending unknown tickers ─────────────────────
        trending_unknown = find_trending_unknown(reddit_posts, known_symbols)
        if trending_unknown:
            logger.info(
                f"Trending tickers not in watchlist/holdings "
                f"(consider adding): {[t['symbol'] for t in trending_unknown]}"
            )
            conn.ping(reconnect=True)
            write_trending_tickers(conn, trending_unknown, dry_run=dry_run)

        # ── 9. Daily summary (1 Claude call) ─────────────────────────────────
        logger.info("Generating daily summary...")
        if action_flips:
            logger.info(
                f"Action flips vs previous run: "
                f"{[(f['symbol'], f['prev_action'], f['new_action']) for f in action_flips]}"
            )
        top_posts = sorted(reddit_posts, key=lambda x: x["score"], reverse=True)[:10]
        analysis_data = {
            "tickers_analyzed": [t["symbol"] for t in tickers],
            "macro_signals": macro_signals,
            "recommendations": all_recommendations,
            "action_flips": action_flips,
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

        # ── 10. Weekly retrospective (S5 — Fridays, 1 extra Claude call) ─────
        # Reviews the week for a long-term investor: which calls' 30d horizon
        # matured this week and how they graded, the week's flips, and current
        # sector exposure. A failure here must not kill the run.
        today = _today()
        if force_retro or today.weekday() == _RETRO_WEEKDAY:
            logger.info("Generating weekly retrospective...")
            week_start = today - timedelta(days=today.weekday())
            retro = None
            try:
                conn.ping(reconnect=True)
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                retro_data = build_retro_data(
                    week_start,
                    tickers,
                    get_week_outcomes(conn, now, horizon=30),
                    get_week_flips(conn, now),
                )
                retro = run_weekly_retrospective(claude, retro_data)
            except Exception:
                logger.exception("Weekly retrospective failed")
            if retro is not None:
                conn.ping(reconnect=True)
                write_weekly_retrospective(conn, week_start, retro, retro_data, dry_run=dry_run)
            else:
                logger.error(f"No weekly retrospective persisted for week {week_start}")

        # ── 11. Pattern mining (session 22 — Fridays, 1 extra Claude call) ───
        # What do the accurate predictions share? Aggregates every graded 30d
        # outcome into per-bucket hit rates, feeds them + the previous pattern
        # set to Claude, and appends the refined set. Never kills the run.
        if force_patterns or today.weekday() == _RETRO_WEEKDAY:
            logger.info("Mining prediction patterns...")
            mined = None
            stats = None
            try:
                conn.ping(reconnect=True)
                feature_rows = get_outcome_features(conn, horizon=30)
                if not feature_rows:
                    logger.info("No graded outcomes yet — skipping pattern mining")
                else:
                    stats = summarize_features(feature_rows, horizon=30)
                    previous = get_latest_patterns(conn)
                    mined = run_pattern_analysis(
                        claude, build_patterns_data(stats, previous)
                    )
            except Exception:
                logger.exception("Pattern mining failed")
            if mined is not None:
                logger.info(
                    "Patterns: "
                    f"{[(p['name'], p['status']) for p in mined.get('patterns', [])]}"
                )
                conn.ping(reconnect=True)
                write_prediction_patterns(conn, mined, stats, horizon=30, dry_run=dry_run)
            elif stats is not None:
                logger.error("No prediction patterns persisted this run")

        # ── 12. Run metrics (session 24 — cost telemetry to the DB) ─────────
        # Persists the run's accumulated Claude usage + cost + ok/failed
        # counts. Runs last so every call (macro, batch, summary, Friday
        # retro/patterns) is counted. A failure here must not kill the run.
        try:
            conn.ping(reconnect=True)
            write_run_metrics(
                conn,
                claude.usage_snapshot(),
                claude.estimated_cost_usd(),
                tickers_ok=len(all_recommendations),
                tickers_failed=len(failed_symbols),
                dry_run=dry_run,
            )
        except Exception:
            logger.exception("Writing run metrics failed")
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
    parser.add_argument(
        "--force-retro", action="store_true",
        help="Generate the weekly retrospective regardless of weekday",
    )
    parser.add_argument(
        "--force-patterns", action="store_true",
        help="Run the prediction-pattern mining regardless of weekday",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run, force_retro=args.force_retro, force_patterns=args.force_patterns)
