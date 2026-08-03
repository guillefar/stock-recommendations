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

# Fixtures carry the session-28 fields (`excess_return_pp`, `primary_action`)
# because the gate now requires them — a set mined before session 28 has
# neither and is correctly rejected wholesale (see the fail-closed tests below).
CONFIRMED = {
    "name": "SELL anticipa caídas reales",
    "description": "Las llamadas SELL caen bastante más que su cohorte de mercado.",
    "evidence": "SELL: 98% (58 decididas), exceso -9.7pp.",
    "status": "CONFIRMED",
    "confidence": 0.91,
    "excess_return_pp": -9.7,
    "primary_action": "SELL",
}
REVISED = {
    "name": "RSI extremo",
    "description": "RSI<30 en WATCHLIST anticipa rebotes.",
    "evidence": "RSI<30: 71% (35 decididas), exceso +4.2pp.",
    "status": "REVISED",
    "confidence": 0.75,
    "excess_return_pp": 4.2,
    "primary_action": "NONE",
}
NEW_HIGH = {
    "name": "Nuevo sin validar",
    "description": "Patrón nuevo de alta confianza.",
    "evidence": "x",
    "status": "NEW",
    "confidence": 0.95,
    "excess_return_pp": -6.0,
    "primary_action": "BUY",
}
RETIRED = {
    "name": "Retirado",
    "description": "Ya no aplica.",
    "evidence": "x",
    "status": "RETIRED",
    "confidence": 0.9,
    "excess_return_pp": 5.0,
    "primary_action": "HOLD",
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
    assert [p["name"] for p in got] == ["SELL anticipa caídas reales", "RSI extremo"]


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
    assert [p["name"] for p in got] == ["SELL anticipa caídas reales"]


# ── _patterns_block (the render) ─────────────────────────────────────────────

def test_block_empty_when_no_patterns():
    assert _patterns_block(None) == ""
    assert _patterns_block([]) == ""


def test_block_renders_name_description_and_framing():
    block = _patterns_block([CONFIRMED, REVISED])
    assert "Patrones históricos del propio sistema" in block
    assert "- SELL anticipa caídas reales: Las llamadas SELL caen bastante más que su cohorte de mercado." in block
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
    assert "SELL anticipa caídas reales" in msg


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
    assert [p["name"] for p in got["patterns"]] == ["SELL anticipa caídas reales"]


def test_main_survives_pattern_read_failure(monkeypatch):
    def boom(conn):
        raise RuntimeError("db down")
    got = _run_main(monkeypatch, boom)
    assert got["patterns"] == []  # run completed, block simply absent


# ── the mechanical excess gate (session 28) ──────────────────────────────────
#
# Session 27 gave the miner market-relative statistics and asked it in the
# prompt to weigh them. It cited the excess figure in 8 of 8 patterns and went
# on ranking by hit rate: it praised RSI 70+ as reliable at 76% with an excess
# of -0.6pp, and called a +10.6pp bucket a "colapso catastrófico" because its
# hit rate was 0%. These tests pin the check that replaced the request.

def test_select_drops_patterns_whose_bucket_matched_the_market():
    # The live RSI 70+ case: a 76% hit rate on top of a -0.6pp excess is the
    # market regime showing through, not skill, and it must not be injected.
    regime = {**CONFIRMED, "name": "RSI 70+ es fiable",
              "excess_return_pp": -0.6, "primary_action": "HOLD"}
    assert select_patterns_for_prompt(_row([regime])) == []


def test_select_keeps_excess_at_exactly_one_point():
    # ±1.0pp is inclusive — the gate drops what is *within* the band.
    for excess in (1.0, -1.0):
        p = {**CONFIRMED, "name": "justo", "excess_return_pp": excess}
        assert [q["name"] for q in select_patterns_for_prompt(_row([p]))] == ["justo"]


def test_select_keeps_large_negative_excess():
    # Excess is direction-blind: SELL's -9.7pp is its best evidence, not its
    # worst. A gate that tested `excess > 1` instead of `abs(excess) > 1` would
    # silently drop the system's single most skilful action.
    got = select_patterns_for_prompt(_row([CONFIRMED]))
    assert [p["name"] for p in got] == ["SELL anticipa caídas reales"]


def test_select_excludes_watch_patterns_whatever_the_excess():
    # WATCH × (otro) reads +10.6pp on the live corpus — the second-largest
    # positive excess in the set, and a pure mis-cohorting artifact (session 28,
    # src.quote_types). WATCH asserts no direction, so its excess is bias rather
    # than skill and no magnitude of it earns injection.
    watch = {**CONFIRMED, "name": "WATCH × otro", "primary_action": "WATCH",
             "excess_return_pp": 10.6}
    assert select_patterns_for_prompt(_row([watch])) == []


def test_select_fails_closed_on_pre_session_28_sets():
    # Every stored prediction_patterns row (ids 1,2,3,5) predates these fields.
    # Dropping them is intended: each rests on a corpus graded before the
    # session-26 re-grade and the session-28 quote_type fix, so injecting one
    # would push known-contaminated guidance into all 63 prompts. Injection
    # resumes on the first Friday mining run after deploy.
    legacy = {k: v for k, v in CONFIRMED.items()
              if k not in ("excess_return_pp", "primary_action")}
    assert select_patterns_for_prompt(_row([legacy])) == []


def test_select_rejects_unusable_gate_fields():
    cases = [
        {**CONFIRMED, "excess_return_pp": None},
        {**CONFIRMED, "excess_return_pp": "mucho"},
        # json.loads accepts the bare NaN literal, and NaN fails every
        # comparison — including `abs(x) < 1.0`, which would let it through.
        {**CONFIRMED, "excess_return_pp": float("nan")},
        {**CONFIRMED, "primary_action": None},
        {**CONFIRMED, "primary_action": 3},
    ]
    for bad in cases:
        assert select_patterns_for_prompt({"patterns": [bad]}) == [], bad


def test_excess_gate_runs_before_the_top_three_cap():
    # The cap must select among patterns that already qualify, not reserve
    # slots for ones the gate rejects. Here the two highest-confidence patterns
    # are regime artifacts; all three survivors should still be injected.
    ps = [
        {**CONFIRMED, "name": "regimen-a", "confidence": 0.99, "excess_return_pp": 0.2},
        {**CONFIRMED, "name": "regimen-b", "confidence": 0.98, "excess_return_pp": -0.9},
        {**CONFIRMED, "name": "real-a", "confidence": 0.90, "excess_return_pp": -9.7},
        {**CONFIRMED, "name": "real-b", "confidence": 0.85, "excess_return_pp": 3.1},
        {**CONFIRMED, "name": "real-c", "confidence": 0.80, "excess_return_pp": -2.4},
        {**CONFIRMED, "name": "real-d", "confidence": 0.75, "excess_return_pp": 5.0},
    ]
    got = select_patterns_for_prompt(_row(ps))
    assert [p["name"] for p in got] == ["real-a", "real-b", "real-c"]
