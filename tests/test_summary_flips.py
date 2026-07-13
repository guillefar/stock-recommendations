"""S17: action flips vs the previous run reach the daily-summary prompt."""

import json
from types import SimpleNamespace

import src.main as main_mod
from src.analysis.claude_client import ClaudeClient

TICKER = {"id": 1, "symbol": "AAPL", "name": "Apple", "sector": "Tech", "phase": "WATCHLIST"}

_SUMMARY_JSON = {"summary": "ok", "hot_tickers": [], "overall_sentiment": "NEUTRAL"}


def _stub_client(captured):
    """A ClaudeClient whose API layer records kwargs and returns a valid summary."""
    client = ClaudeClient.__new__(ClaudeClient)
    client._usage = {
        "calls": 0, "input": 0, "output": 0,
        "batch_input": 0, "batch_output": 0,
        "cache_write": 0, "cache_read": 0,
    }

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(_SUMMARY_JSON))],
        )

    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client


def test_summary_prompt_includes_flips_block():
    captured = {}
    client = _stub_client(captured)
    result = client.generate_daily_summary({
        "tickers_analyzed": ["FSLR", "AAPL"],
        "recommendations": [],
        "action_flips": [
            {"symbol": "FSLR", "prev_action": "HOLD", "new_action": "SELL"},
            {"symbol": "AAPL", "prev_action": "WATCH", "new_action": "BUY"},
        ],
    })
    assert result == _SUMMARY_JSON
    prompt = captured["messages"][0]["content"]
    assert "Cambios de recomendación vs la corrida anterior:" in prompt
    assert "- FSLR: HOLD → SELL" in prompt
    assert "- AAPL: WATCH → BUY" in prompt


def test_summary_prompt_without_flips_says_none():
    captured = {}
    client = _stub_client(captured)
    client.generate_daily_summary({"tickers_analyzed": ["AAPL"], "recommendations": []})
    prompt = captured["messages"][0]["content"]
    assert "Cambios de recomendación vs la corrida anterior:\n(ninguno)" in prompt


def _run_main(monkeypatch, previous_actions, captured):
    from datetime import date

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
    monkeypatch.setattr(main_mod, "get_latest_actions", lambda conn: previous_actions)
    monkeypatch.setattr(main_mod, "get_latest_patterns", lambda conn: None)
    monkeypatch.setattr(main_mod, "fetch_reddit_posts", lambda cfg: [])
    monkeypatch.setattr(main_mod, "fetch_macro_headlines", lambda: [])
    monkeypatch.setattr(main_mod, "fetch_prices_and_indicators", lambda s: {"price": 10.0})
    monkeypatch.setattr(main_mod, "fetch_ticker_news", lambda s: [])
    monkeypatch.setattr(main_mod, "fetch_next_earnings", lambda s: None)
    monkeypatch.setattr(main_mod, "run_macro_analysis", lambda client, headlines: [])
    monkeypatch.setattr(
        main_mod, "run_ticker_recommendations_batch",
        lambda client, items, signals, patterns=None: {
            t["symbol"]: {"action": "WATCH", "confidence": 0.5, "reasoning": "r"}
            for t in items
        },
    )

    def fake_summary(client, data):
        captured.update(data)
        return None

    monkeypatch.setattr(main_mod, "run_daily_summary", fake_summary)
    monkeypatch.setattr(main_mod, "write_price_check", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_macro_signals", lambda conn, s, dry_run=False: [])
    monkeypatch.setattr(main_mod, "write_recommendation", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_reddit_mentions", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_run_metrics", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_daily_summary", lambda *a, **kw: None)

    main_mod.main(dry_run=False)


def test_main_reports_flip_when_action_changed(monkeypatch):
    from datetime import datetime

    captured = {}
    _run_main(
        monkeypatch,
        previous_actions={1: {"action": "BUY", "held_since": datetime(2026, 7, 1, 10, 0)}},
        captured=captured,
    )
    assert captured["action_flips"] == [
        {"symbol": "AAPL", "prev_action": "BUY", "new_action": "WATCH"}
    ]


def test_main_no_flip_when_action_unchanged_or_first_run(monkeypatch):
    from datetime import datetime

    captured = {}
    _run_main(
        monkeypatch,
        previous_actions={1: {"action": "WATCH", "held_since": datetime(2026, 7, 1, 10, 0)}},
        captured=captured,
    )
    assert captured["action_flips"] == []

    captured = {}
    _run_main(monkeypatch, previous_actions={}, captured=captured)
    assert captured["action_flips"] == []
