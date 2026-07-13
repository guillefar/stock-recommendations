"""Session 16 (flip-stability): the ticker prompt carries the standing call.

The model sees its previous action + how long it's been held, and is told a
reversal requires naming material new information — so day-to-day ping-pong
(MU BUY→AVOID→WATCH within days) has to justify itself or stop.
"""

import json
from datetime import date, datetime
from types import SimpleNamespace

import src.main as main_mod
from src.analysis.claude_client import _RECOMMENDATION_SYSTEM, ClaudeClient
from src.config import Config

TICKER = {"id": 1, "symbol": "AAPL", "name": "Apple", "sector": "Tech", "phase": "WATCHLIST"}


def _client() -> ClaudeClient:
    cfg = Config(
        db_host="x", db_port=3306, db_user="x", db_pass="x", db_name="x",
        anthropic_api_key="test-key",
    )
    return ClaudeClient(cfg)


def _prompt(ticker_data: dict) -> str:
    params = _client()._ticker_request_params(ticker_data, macro_signals=[])
    return params["messages"][0]["content"]


def test_prompt_includes_previous_action_and_days_held():
    prompt = _prompt({
        **TICKER, "technical": {}, "sentiment": {},
        "prev_action": "WATCH", "prev_held_days": 5,
    })
    assert "Recomendación vigente: WATCH (mantenida 5 días)" in prompt
    assert "información nueva y material" in prompt
    assert "ruido, no una tesis nueva" in prompt


def test_prompt_singular_day():
    prompt = _prompt({
        **TICKER, "technical": {}, "sentiment": {},
        "prev_action": "HOLD", "prev_held_days": 1,
    })
    assert "Recomendación vigente: HOLD (mantenida 1 día)" in prompt
    assert "1 días" not in prompt


def test_prompt_omits_block_without_previous_action():
    # First-ever run for a ticker: no standing call, no block.
    prompt = _prompt({**TICKER, "technical": {}, "sentiment": {}})
    assert "Recomendación vigente" not in prompt
    assert "mantenida" not in prompt


def test_prompt_handles_missing_held_days():
    # Defensive: an action with no streak start still names the standing call.
    prompt = _prompt({
        **TICKER, "technical": {}, "sentiment": {},
        "prev_action": "BUY", "prev_held_days": None,
    })
    assert "Recomendación vigente: BUY." in prompt
    assert "mantenida" not in prompt


def test_system_prompt_requires_material_information_to_flip():
    assert "información nueva y material" in _RECOMMENDATION_SYSTEM


def test_main_passes_prev_action_and_age_to_batch(monkeypatch):
    """main() wires get_latest_actions into the prepared ticker payloads."""
    batch_items = []

    # Pin a non-Friday (retro path off); held_since 2026-07-01 → 5 days.
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
    monkeypatch.setattr(
        main_mod, "get_latest_actions",
        lambda conn: {1: {"action": "WATCH", "held_since": datetime(2026, 7, 1, 12, 19)}},
    )
    monkeypatch.setattr(main_mod, "get_latest_patterns", lambda conn: None)
    monkeypatch.setattr(main_mod, "fetch_reddit_posts", lambda cfg: [])
    monkeypatch.setattr(main_mod, "fetch_macro_headlines", lambda: [])
    monkeypatch.setattr(main_mod, "fetch_prices_and_indicators", lambda s: {"price": 10.0})
    monkeypatch.setattr(main_mod, "fetch_ticker_news", lambda s: [])
    monkeypatch.setattr(main_mod, "fetch_next_earnings", lambda s: None)
    monkeypatch.setattr(main_mod, "run_macro_analysis", lambda client, headlines: [])

    def fake_batch(client, items, signals, patterns=None):
        batch_items.extend(items)
        return {
            t["symbol"]: {"action": "WATCH", "confidence": 0.5, "reasoning": "r"}
            for t in items
        }

    monkeypatch.setattr(main_mod, "run_ticker_recommendations_batch", fake_batch)
    monkeypatch.setattr(main_mod, "run_daily_summary", lambda client, data: None)
    monkeypatch.setattr(main_mod, "write_price_check", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_macro_signals", lambda conn, s, dry_run=False: [])
    monkeypatch.setattr(main_mod, "write_recommendation", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_reddit_mentions", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_run_metrics", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_daily_summary", lambda *a, **kw: None)

    main_mod.main(dry_run=False)

    assert len(batch_items) == 1
    assert batch_items[0]["prev_action"] == "WATCH"
    assert batch_items[0]["prev_held_days"] == 5
