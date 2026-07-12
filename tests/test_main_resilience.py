"""F2/F5 wiring: a Claude failure in macro or summary must not kill the run
or persist placeholder data — tickers still process and prices still land."""

from types import SimpleNamespace

import src.main as main_mod

TICKER = {"id": 1, "symbol": "AAPL", "name": "Apple", "sector": "Tech", "phase": "WATCHLIST"}


def _run_main(monkeypatch, macro_raises: bool, summary_result):
    from datetime import date

    calls = {"price_checks": [], "recommendations": [], "summaries": []}

    # Pin a non-Friday so the S5 retrospective path stays out of these tests.
    monkeypatch.setattr(main_mod, "_today", lambda: date(2026, 7, 6))
    monkeypatch.setattr(main_mod, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(
        main_mod, "ClaudeClient",
        lambda cfg: SimpleNamespace(
            log_usage=lambda: None,
            usage_snapshot=lambda: {"calls": 0, "input": 0, "output": 0,
                                    "batch_input": 0, "batch_output": 0,
                                    "cache_write": 0, "cache_read": 0},
            estimated_cost_usd=lambda: 0.0,
        )
    )
    monkeypatch.setattr(
        main_mod, "get_connection",
        lambda cfg: SimpleNamespace(ping=lambda **kw: None, close=lambda: None),
    )
    monkeypatch.setattr(main_mod, "get_active_tickers", lambda conn: [TICKER])
    monkeypatch.setattr(main_mod, "get_known_symbols", lambda conn: {"AAPL"})
    monkeypatch.setattr(main_mod, "get_latest_actions", lambda conn: {})
    monkeypatch.setattr(main_mod, "fetch_reddit_posts", lambda cfg: [])
    monkeypatch.setattr(main_mod, "fetch_macro_headlines", lambda: [{"title": "x"}])
    monkeypatch.setattr(main_mod, "fetch_prices_and_indicators", lambda s: {"price": 10.0})
    monkeypatch.setattr(main_mod, "fetch_ticker_news", lambda s: [])
    monkeypatch.setattr(main_mod, "fetch_next_earnings", lambda s: None)

    def fake_macro(client, headlines):
        if macro_raises:
            raise RuntimeError("Claude is down")
        return []

    monkeypatch.setattr(main_mod, "run_macro_analysis", fake_macro)
    monkeypatch.setattr(
        main_mod, "run_ticker_recommendations_batch",
        lambda client, items, signals: {
            t["symbol"]: {"action": "WATCH", "confidence": 0.5, "reasoning": "r"}
            for t in items
        },
    )
    monkeypatch.setattr(main_mod, "run_daily_summary", lambda client, data: summary_result)

    monkeypatch.setattr(
        main_mod, "write_price_check",
        lambda conn, tid, price, dry_run=False: calls["price_checks"].append(tid),
    )
    monkeypatch.setattr(main_mod, "write_macro_signals", lambda conn, s, dry_run=False: [])
    monkeypatch.setattr(
        main_mod, "write_recommendation",
        lambda conn, tid, rec, tech, sent, macro_id, fundamentals=None, dry_run=False:
            calls["recommendations"].append(rec["action"]),
    )
    monkeypatch.setattr(main_mod, "write_reddit_mentions", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_run_metrics", lambda *a, **kw: None)
    monkeypatch.setattr(
        main_mod, "write_daily_summary",
        lambda conn, summary, count, dry_run=False: calls["summaries"].append(summary),
    )

    main_mod.main(dry_run=False)
    return calls


def test_macro_failure_does_not_kill_price_or_recommendation_flow(monkeypatch):
    calls = _run_main(monkeypatch, macro_raises=True, summary_result={
        "summary": "ok", "hot_tickers": [], "overall_sentiment": "NEUTRAL",
    })
    assert calls["price_checks"] == [1]
    assert calls["recommendations"] == ["WATCH"]
    assert len(calls["summaries"]) == 1


def test_failed_summary_is_not_persisted(monkeypatch):
    calls = _run_main(monkeypatch, macro_raises=False, summary_result=None)
    assert calls["recommendations"] == ["WATCH"]
    assert calls["summaries"] == []  # F5: never upsert a placeholder
