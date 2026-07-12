"""S5: weekly retrospective — aggregation, prompt assembly, and main() wiring."""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import src.main as main_mod
from src.analysis.claude_client import ClaudeClient
from src.analysis.retrospective import build_retro_data, sector_exposure, summarize_outcomes

_RETRO_JSON = {"retrospective": "## Semana\nTexto."}


def _row(symbol, action, fwd, verdict, called_on=date(2026, 6, 8)):
    return {
        "symbol": symbol, "action": action, "confidence": Decimal("0.60"),
        "forward_return": Decimal(str(fwd)), "verdict": verdict, "called_on": called_on,
    }


def test_summarize_outcomes_counts_hit_rate_and_highlights():
    rows = [
        _row("AAPL", "BUY", 0.12, "CORRECT"),
        _row("MSFT", "BUY", 0.05, "CORRECT"),
        _row("TSLA", "SELL", 0.20, "INCORRECT"),
        _row("SPY", "HOLD", 0.01, "NEUTRAL"),
    ]
    s = summarize_outcomes(rows)
    assert (s["total"], s["correct"], s["incorrect"], s["neutral"]) == (4, 2, 1, 1)
    assert s["hit_rate_pct"] == 67  # 2 of 3 decided
    assert [c["symbol"] for c in s["best"]] == ["AAPL", "MSFT"]  # biggest mover first
    assert s["worst"][0]["symbol"] == "TSLA"
    # JSON-safe for the stats column (no Decimal/date survives)
    json.dumps(s)


def test_summarize_outcomes_empty_week():
    s = summarize_outcomes([])
    assert s["total"] == 0
    assert s["hit_rate_pct"] is None
    assert s["best"] == [] and s["worst"] == []


def test_sector_exposure_groups_by_phase_and_sector():
    tickers = [
        {"symbol": "AAPL", "sector": "Tech", "phase": "HOLDING"},
        {"symbol": "MSFT", "sector": "Tech", "phase": "HOLDING"},
        {"symbol": "XOM", "sector": "Energy", "phase": "WATCHLIST"},
        {"symbol": "XESC.DE", "sector": None, "phase": "WATCHLIST"},
    ]
    assert sector_exposure(tickers) == {
        "HOLDING": {"Tech": 2},
        "WATCHLIST": {"Energy": 1, "(sin sector)": 1},
    }


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
            content=[SimpleNamespace(type="text", text=json.dumps(_RETRO_JSON))],
        )

    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client


def test_retro_prompt_carries_outcomes_flips_and_exposure():
    captured = {}
    client = _stub_client(captured)
    retro_data = build_retro_data(
        date(2026, 7, 6),
        [{"symbol": "AAPL", "sector": "Tech", "phase": "HOLDING"}],
        [_row("AAPL", "BUY", 0.12, "CORRECT"), _row("TSLA", "SELL", 0.08, "INCORRECT")],
        [{"day": date(2026, 7, 8), "symbol": "MU", "prev_action": "BUY", "new_action": "AVOID"}],
    )
    result = client.generate_weekly_retrospective(retro_data)
    assert result == _RETRO_JSON
    prompt = captured["messages"][0]["content"]
    assert "Retrospectiva de la semana del 2026-07-06" in prompt
    assert "hit rate 50%" in prompt
    assert "- AAPL: BUY del 2026-06-08, retorno +12.0%" in prompt
    assert "- TSLA: SELL del 2026-06-08, retorno +8.0%" in prompt
    assert "- 2026-07-08 MU: BUY → AVOID" in prompt
    assert "- HOLDING: Tech 1" in prompt


def test_retro_prompt_empty_week_says_none():
    captured = {}
    client = _stub_client(captured)
    client.generate_weekly_retrospective(build_retro_data(date(2026, 7, 6), [], [], []))
    prompt = captured["messages"][0]["content"]
    assert "(ninguna)" in prompt  # no best/worst calls
    assert "(ninguno)" in prompt  # no flips
    assert "(sin posiciones)" in prompt


def _run_main(monkeypatch, today, force_retro, retro_result=_RETRO_JSON):
    written = []
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
    monkeypatch.setattr(
        main_mod, "run_weekly_retrospective", lambda client, data: retro_result
    )
    monkeypatch.setattr(main_mod, "write_price_check", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_macro_signals", lambda conn, s, dry_run=False: [])
    monkeypatch.setattr(main_mod, "write_recommendation", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_reddit_mentions", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_run_metrics", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_daily_summary", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_trending_tickers", lambda *a, **kw: None)
    monkeypatch.setattr(
        main_mod, "write_weekly_retrospective",
        lambda conn, week_start, retro, stats, dry_run=False:
            written.append((week_start, retro)),
    )

    main_mod.main(dry_run=False, force_retro=force_retro)
    return written


def test_retro_written_on_friday_keyed_to_monday(monkeypatch):
    written = _run_main(monkeypatch, today=date(2026, 7, 10), force_retro=False)  # a Friday
    assert written == [(date(2026, 7, 6), _RETRO_JSON)]


def test_retro_skipped_off_friday_unless_forced(monkeypatch):
    assert _run_main(monkeypatch, today=date(2026, 7, 8), force_retro=False) == []
    written = _run_main(monkeypatch, today=date(2026, 7, 8), force_retro=True)
    assert written == [(date(2026, 7, 6), _RETRO_JSON)]


def test_failed_retro_is_not_persisted(monkeypatch):
    written = _run_main(
        monkeypatch, today=date(2026, 7, 10), force_retro=False, retro_result=None
    )
    assert written == []
