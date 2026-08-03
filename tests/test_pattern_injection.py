"""Session 25 — the patterns→prompt feedback loop.

The newest mined pattern set (prediction_patterns) is gated — status in
{CONFIRMED, REVISED}, confidence ≥ 0.7, top 3 by confidence — and rides into
every per-ticker prompt as a Spanish "patrones históricos" block framed as
weighable biases, never absolute rules. With the gate, the loop ships inert
(the seed row is all-NEW) and self-activates when a Friday mining run first
confirms a pattern. Nothing here may ever cost a run: a bad stored row means
no block, and prompts without patterns stay byte-identical to before.
"""

import json
from datetime import date, datetime
from types import SimpleNamespace

import src.main as main_mod
from src.analysis.claude_client import ClaudeClient, _patterns_block
from src.analysis.patterns import select_patterns_for_prompt
from src.config import Config

TICKER = {"id": 1, "symbol": "AAPL", "name": "Apple", "sector": "Tech", "phase": "WATCHLIST"}

CONFIRMED = {
    "name": "WATCH en ETFs",
    "description": "Las llamadas WATCH sobre ETFs aciertan solo el 14%.",
    "evidence": "WATCH×ETF: 14% (244 decididas).",
    "status": "CONFIRMED",
    "confidence": 0.91,
}
REVISED = {
    "name": "RSI extremo",
    "description": "RSI<30 en WATCHLIST anticipa rebotes.",
    "evidence": "RSI<30: 71% (35 decididas).",
    "status": "REVISED",
    "confidence": 0.75,
}
NEW_HIGH = {
    "name": "Nuevo sin validar",
    "description": "Patrón nuevo de alta confianza.",
    "evidence": "x",
    "status": "NEW",
    "confidence": 0.95,
}
RETIRED = {
    "name": "Retirado",
    "description": "Ya no aplica.",
    "evidence": "x",
    "status": "RETIRED",
    "confidence": 0.9,
}


def _row(patterns: list[dict]) -> dict:
    """A get_latest_patterns row: pymysql returns the JSON column as a string."""
    return {
        "generated_at": datetime(2026, 7, 17, 10, 0),
        "horizon_days": 30,
        "patterns": json.dumps(patterns, ensure_ascii=False),
        "narrative": "n",
    }


def _client() -> ClaudeClient:
    cfg = Config(
        db_host="x", db_port=3306, db_user="x", db_pass="x", db_name="x",
        anthropic_api_key="test-key",
    )
    return ClaudeClient(cfg)


# ── select_patterns_for_prompt (the gate) ────────────────────────────────────

def test_select_returns_empty_without_row():
    assert select_patterns_for_prompt(None) == []


def test_select_gates_status_confirmed_and_revised_only():
    got = select_patterns_for_prompt(_row([CONFIRMED, NEW_HIGH, RETIRED, REVISED]))
    assert [p["name"] for p in got] == ["WATCH en ETFs", "RSI extremo"]


def test_select_gates_confidence_at_070_inclusive():
    low = {**CONFIRMED, "name": "bajo", "confidence": 0.69}
    edge = {**CONFIRMED, "name": "justo", "confidence": 0.7}
    got = select_patterns_for_prompt(_row([low, edge]))
    assert [p["name"] for p in got] == ["justo"]


def test_select_sorts_by_confidence_and_caps_at_three():
    ps = [
        {**CONFIRMED, "name": f"p{i}", "confidence": c}
        for i, c in enumerate([0.72, 0.95, 0.80, 0.88])
    ]
    got = select_patterns_for_prompt(_row(ps))
    assert [p["name"] for p in got] == ["p1", "p3", "p2"]  # 0.95, 0.88, 0.80


def test_select_tolerates_garbage():
    # Unparseable JSON string → [].
    assert select_patterns_for_prompt({"patterns": "{not json"}) == []
    # JSON that isn't a list → [].
    assert select_patterns_for_prompt({"patterns": json.dumps({"a": 1})}) == []
    # Non-dict entries, missing name/description, non-numeric confidence: skipped.
    got = select_patterns_for_prompt(_row([
        "cadena suelta",
        {**CONFIRMED, "name": ""},
        {**CONFIRMED, "description": None},
        {**CONFIRMED, "confidence": "alta"},
        REVISED,
    ]))
    assert [p["name"] for p in got] == ["RSI extremo"]


def test_select_accepts_already_parsed_list():
    got = select_patterns_for_prompt({"patterns": [CONFIRMED]})
    assert [p["name"] for p in got] == ["WATCH en ETFs"]


# ── _patterns_block (the render) ─────────────────────────────────────────────

def test_block_empty_when_no_patterns():
    assert _patterns_block(None) == ""
    assert _patterns_block([]) == ""


def test_block_renders_name_description_and_framing():
    block = _patterns_block([CONFIRMED, REVISED])
    assert "Patrones históricos del propio sistema" in block
    assert "- WATCH en ETFs: Las llamadas WATCH sobre ETFs aciertan solo el 14%." in block
    assert "- RSI extremo: RSI<30 en WATCHLIST anticipa rebotes." in block
    assert "no reglas absolutas" in block


def test_block_carries_the_market_regime_caveat():
    # Session 26: the mined hit rates are NOT market-adjusted, so per-action
    # base rates are mechanically biased by market direction — the whole graded
    # corpus is a -4.80% window, which is why SELL reads ~100% and BUY ~6%.
    # Without this caveat the loop injects "never BUY / always SELL" as if it
    # were skill. Remove it only once summarize_features reports market-relative
    # figures (the pinned next slice).
    block = _patterns_block([CONFIRMED])
    assert "no están ajustados" in block.replace("NO están", "no están")
    assert "mayoritariamente bajista" in block
    assert "SELL y AVOID" in block and "BUY falla" in block


# ── _ticker_request_params (prompt inclusion / byte-identical omission) ──────

def test_prompt_carries_patterns_block():
    td = {**TICKER, "technical": {}, "sentiment": {}}
    params = _client()._ticker_request_params(td, [], [CONFIRMED])
    msg = params["messages"][0]["content"]
    assert "Patrones históricos del propio sistema" in msg
    assert "WATCH en ETFs" in msg


def test_prompt_unchanged_without_patterns():
    td = {**TICKER, "technical": {}, "sentiment": {}}
    client = _client()
    legacy = client._ticker_request_params(td, [])
    for empty in (None, []):
        assert client._ticker_request_params(td, [], empty) == legacy
    assert "Patrones históricos" not in legacy["messages"][0]["content"]


# ── main() wiring ────────────────────────────────────────────────────────────

def _run_main(monkeypatch, latest_patterns_fn):
    """Minimal main() harness; returns the patterns arg the batch received."""
    received = {}

    monkeypatch.setattr(main_mod, "_today", lambda: date(2026, 7, 20))  # Monday
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
    monkeypatch.setattr(main_mod, "get_latest_patterns", latest_patterns_fn)
    monkeypatch.setattr(main_mod, "fetch_reddit_posts", lambda cfg: [])
    monkeypatch.setattr(main_mod, "fetch_macro_headlines", lambda: [])
    monkeypatch.setattr(main_mod, "fetch_prices_and_indicators", lambda s: {"price": 10.0})
    monkeypatch.setattr(main_mod, "fetch_ticker_news", lambda s: [])
    monkeypatch.setattr(main_mod, "fetch_next_earnings", lambda s: None)
    monkeypatch.setattr(main_mod, "run_macro_analysis", lambda client, headlines: [])

    def fake_batch(client, items, signals, patterns=None):
        received["patterns"] = patterns
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
    return received


def test_main_passes_gated_patterns_to_batch(monkeypatch):
    got = _run_main(monkeypatch, lambda conn: _row([CONFIRMED, NEW_HIGH]))
    assert [p["name"] for p in got["patterns"]] == ["WATCH en ETFs"]


def test_main_survives_pattern_read_failure(monkeypatch):
    def boom(conn):
        raise RuntimeError("db down")
    got = _run_main(monkeypatch, boom)
    assert got["patterns"] == []  # run completed, block simply absent
