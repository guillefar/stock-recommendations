"""Session 22: pattern mining — bucketing, aggregation, prompt assembly, wiring."""

import json
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import src.main as main_mod
from src.analysis.claude_client import ClaudeClient
from src.analysis.patterns import (
    _bucket_confidence,
    _bucket_dividend,
    _bucket_pe,
    _bucket_rsi,
    _bucket_sma50,
    build_patterns_data,
    summarize_features,
)

_MINED_JSON = {
    "patterns": [
        {
            "name": "WATCH sobrevendido",
            "description": "Las WATCH con RSI<30 aciertan más.",
            "evidence": "RSI<30: hit rate 71% (25C/10I/5N, 35 decididas) vs 51% global.",
            "status": "NEW",
            "confidence": 0.6,
        }
    ],
    "narrative": "## Patrones\nTexto.",
}


def _row(verdict, action="BUY", confidence="0.60", rsi=45.0, price=10.0, sma50=9.0,
         pos_52w=0.5, volume_ratio=1.0, quote_type="EQUITY", sector="Tech",
         trailing_pe=None, dividend_yield_pct=None):
    return {
        "verdict": verdict, "action": action, "confidence": Decimal(confidence),
        "forward_return": Decimal("0.05"), "symbol": "X", "sector": sector,
        "quote_type": quote_type, "rsi": rsi, "price": price, "sma50": sma50,
        "pos_52w": pos_52w, "volume_ratio": volume_ratio,
        "trailing_pe": trailing_pe, "dividend_yield_pct": dividend_yield_pct,
    }


# ── bucketing ──────────────────────────────────────────────────────────────────

def test_bucket_edges():
    assert _bucket_confidence(Decimal("0.39")) == "<0.40"
    assert _bucket_confidence(Decimal("0.40")) == "0.40–0.59"
    assert _bucket_confidence(Decimal("0.80")) == "0.80+"
    assert _bucket_confidence(None) == "(sin dato)"
    assert _bucket_rsi(29.9) == "RSI<30 (sobrevendido)"
    assert _bucket_rsi(70.0) == "RSI 70+ (sobrecomprado)"
    assert _bucket_rsi(None) == "(sin dato)"
    assert _bucket_sma50(10.0, 9.0) == "precio > SMA50"
    assert _bucket_sma50(9.0, 10.0) == "precio ≤ SMA50"
    assert _bucket_sma50(10.0, None) == "(sin dato)"
    assert _bucket_pe(14.9) == "P/E<15"
    assert _bucket_pe(30.0) == "P/E 30+"
    assert _bucket_pe(None) == "(sin dato)"
    assert _bucket_dividend(3.4) == "paga dividendo"
    assert _bucket_dividend(0.0) == "sin dividendo"
    assert _bucket_dividend(None) == "(sin dato)"


# ── aggregation ────────────────────────────────────────────────────────────────

def test_summarize_features_counts_and_hit_rates():
    rows = [
        _row("CORRECT", action="BUY", rsi=25.0),
        _row("CORRECT", action="BUY", rsi=28.0),
        _row("INCORRECT", action="BUY", rsi=75.0),
        _row("NEUTRAL", action="WATCH", rsi=50.0),
    ]
    s = summarize_features(rows, horizon=30)
    assert s["horizon_days"] == 30
    assert s["total_outcomes"] == 4
    assert s["overall"] == {"correct": 2, "incorrect": 1, "neutral": 1, "hit_rate_pct": 67}
    buy = s["dimensions"]["accion"]["BUY"]
    assert (buy["correct"], buy["incorrect"], buy["hit_rate_pct"]) == (2, 1, 67)
    oversold = s["dimensions"]["rsi"]["RSI<30 (sobrevendido)"]
    assert oversold == {"correct": 2, "incorrect": 0, "neutral": 0, "hit_rate_pct": 100}
    # cross carries the interaction
    assert "BUY × RSI<30 (sobrevendido)" in s["dimensions"]["accion_x_rsi"]
    json.dumps(s)  # JSON-safe for the stats column


def test_summarize_features_etf_bucket_and_missing_data():
    rows = [
        _row("CORRECT", quote_type="ETF", sector=None),
        _row("INCORRECT", quote_type=None, sector=None, rsi=None, trailing_pe=None),
    ]
    s = summarize_features(rows)
    assert s["dimensions"]["sector"]["ETF"]["correct"] == 1
    assert s["dimensions"]["sector"]["(sin sector)"]["incorrect"] == 1
    assert s["dimensions"]["tipo"]["ETF"]["correct"] == 1
    assert s["dimensions"]["tipo"]["(otro)"]["incorrect"] == 1
    assert s["dimensions"]["rsi"]["(sin dato)"]["incorrect"] == 1
    # both rows lack a P/E → they share the "(sin dato)" bucket (1C/1I)
    assert s["dimensions"]["pe"]["(sin dato)"]["hit_rate_pct"] == 50


def test_summarize_features_neutral_only_bucket_has_no_hit_rate():
    s = summarize_features([_row("NEUTRAL")])
    assert s["overall"]["hit_rate_pct"] is None


def test_build_patterns_data_with_and_without_previous():
    stats = summarize_features([_row("CORRECT")])
    fresh = build_patterns_data(stats, None)
    assert fresh["previous_patterns"] is None
    assert fresh["previous_generated_at"] is None
    previous = {
        "generated_at": datetime(2026, 7, 10, 10, 0),
        "patterns": json.dumps([{"name": "p"}]),
    }
    fed = build_patterns_data(stats, previous)
    assert fed["previous_patterns"] == json.dumps([{"name": "p"}])
    assert fed["previous_generated_at"] == "2026-07-10 10:00:00"


# ── prompt assembly ────────────────────────────────────────────────────────────

def _stub_client(captured):
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
            content=[SimpleNamespace(type="text", text=json.dumps(_MINED_JSON))],
        )

    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client


def test_patterns_prompt_carries_aggregates_and_previous_set():
    captured = {}
    client = _stub_client(captured)
    stats = summarize_features(
        [_row("CORRECT", action="BUY", rsi=25.0), _row("INCORRECT", action="SELL", rsi=75.0)]
    )
    previous = {"generated_at": datetime(2026, 7, 10), "patterns": [{"name": "viejo patrón"}]}
    result = client.generate_pattern_analysis(build_patterns_data(stats, previous))
    assert result == _MINED_JSON
    prompt = captured["messages"][0]["content"]
    assert "horizonte de 30 días" in prompt
    assert "1C/1I/0N — hit rate 50%" in prompt
    assert "BUY: hit rate 100% (1C/0I/0N, 1 decididas)" in prompt
    assert "BUY × RSI<30 (sobrevendido)" in prompt
    assert "viejo patrón" in prompt
    # schema constrains the pattern lifecycle
    schema = captured["output_config"]["format"]["schema"]
    statuses = schema["properties"]["patterns"]["items"]["properties"]["status"]["enum"]
    assert statuses == ["NEW", "CONFIRMED", "REVISED", "RETIRED"]


def test_patterns_prompt_first_run_says_no_previous():
    captured = {}
    client = _stub_client(captured)
    client.generate_pattern_analysis(
        build_patterns_data(summarize_features([_row("CORRECT")]), None)
    )
    prompt = captured["messages"][0]["content"]
    assert "primera ejecución del minado de patrones" in prompt


# ── main() wiring ──────────────────────────────────────────────────────────────

def _run_main(monkeypatch, today, force_patterns=False, feature_rows=None,
              mined=_MINED_JSON):
    written = []
    if feature_rows is None:
        feature_rows = [_row("CORRECT")]
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
    monkeypatch.setattr(main_mod, "_today", lambda: today)
    monkeypatch.setattr(
        main_mod, "get_active_tickers",
        lambda conn: [{"id": 1, "symbol": "AAPL", "name": "Apple", "sector": "Tech",
                       "phase": "WATCHLIST"}],
    )
    monkeypatch.setattr(main_mod, "get_known_symbols", lambda conn: {"AAPL"})
    monkeypatch.setattr(main_mod, "get_latest_actions", lambda conn: {})
    monkeypatch.setattr(main_mod, "get_week_outcomes", lambda conn, now, horizon=30: [])
    monkeypatch.setattr(main_mod, "get_week_flips", lambda conn, now: [])
    monkeypatch.setattr(main_mod, "get_outcome_features",
                        lambda conn, horizon=30: feature_rows)
    monkeypatch.setattr(main_mod, "get_latest_patterns", lambda conn: None)
    monkeypatch.setattr(main_mod, "fetch_reddit_posts", lambda cfg: [])
    monkeypatch.setattr(main_mod, "fetch_macro_headlines", lambda: [])
    monkeypatch.setattr(main_mod, "fetch_prices_and_indicators", lambda s: {"price": 10.0})
    monkeypatch.setattr(main_mod, "fetch_ticker_news", lambda s: [])
    monkeypatch.setattr(main_mod, "fetch_next_earnings", lambda s: None)
    monkeypatch.setattr(main_mod, "run_macro_analysis", lambda client, headlines: [])
    monkeypatch.setattr(
        main_mod, "run_ticker_recommendations_batch",
        lambda client, items, signals: {
            t["symbol"]: {"action": "WATCH", "confidence": 0.5, "reasoning": "r"}
            for t in items
        },
    )
    monkeypatch.setattr(main_mod, "run_daily_summary", lambda client, data: None)
    monkeypatch.setattr(main_mod, "run_weekly_retrospective", lambda client, data: None)
    monkeypatch.setattr(main_mod, "run_pattern_analysis", lambda client, data: mined)
    monkeypatch.setattr(main_mod, "write_price_check", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_macro_signals", lambda conn, s, dry_run=False: [])
    monkeypatch.setattr(main_mod, "write_recommendation", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_reddit_mentions", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_run_metrics", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_daily_summary", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_trending_tickers", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_weekly_retrospective", lambda *a, **kw: None)
    monkeypatch.setattr(
        main_mod, "write_prediction_patterns",
        lambda conn, result, stats, horizon=30, dry_run=False:
            written.append((result, stats, horizon)),
    )

    main_mod.main(dry_run=False, force_patterns=force_patterns)
    return written


def test_patterns_written_on_friday(monkeypatch):
    written = _run_main(monkeypatch, today=date(2026, 7, 17))  # a Friday
    assert len(written) == 1
    result, stats, horizon = written[0]
    assert result == _MINED_JSON
    assert horizon == 30
    assert stats["total_outcomes"] == 1  # the stats fed to the miner are persisted


def test_patterns_skipped_off_friday_unless_forced(monkeypatch):
    assert _run_main(monkeypatch, today=date(2026, 7, 15)) == []  # a Wednesday
    written = _run_main(monkeypatch, today=date(2026, 7, 15), force_patterns=True)
    assert len(written) == 1


def test_failed_mining_is_not_persisted(monkeypatch):
    written = _run_main(monkeypatch, today=date(2026, 7, 17), mined=None)
    assert written == []


def test_no_graded_outcomes_skips_mining(monkeypatch):
    written = _run_main(monkeypatch, today=date(2026, 7, 17), feature_rows=[])
    assert written == []
