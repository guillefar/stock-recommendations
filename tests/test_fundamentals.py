"""Session 20: stock fundamentals reach the per-ticker prompt (Fundamentales).

Stocks used to be judged on technicals + news alone. Now tickers whose
quote_type is EQUITY (from the tickers table) get a lean valuation/
profitability snapshot (P/E, dividend yield, margins, growth, market cap)
fetched via yfinance Ticker.info and rendered as an optional Spanish prompt
block. ETFs keep their funds_data block; the index and untyped tickers get
neither. Yahoo quirks pinned here: Infinity P/E dropped, dividendYield is
already percent units, margins/growth are fractions of 1.
"""

from datetime import date
from types import SimpleNamespace

import src.main as main_mod
from src.analysis.claude_client import ClaudeClient, _human_cap
from src.collectors.prices import _build_fundamentals
from src.config import Config

# Shape observed live for AAPL on 2026-07-11 (values rounded).
INFO_AAPL = {
    "trailingPE": 38.17,
    "forwardPE": 32.82,
    "dividendYield": 0.34,          # percent units: 0.34 means 0.34%
    "profitMargins": 0.2715,        # fraction: 27.15%
    "operatingMargins": 0.3228,
    "revenueGrowth": 0.166,
    "earningsGrowth": 0.218,
    "marketCap": 4631217307648,
    "currency": "USD",
}


def test_build_fundamentals_normalizes_lean_set():
    fund = _build_fundamentals(INFO_AAPL)
    assert fund["trailing_pe"] == 38.17
    assert fund["forward_pe"] == 32.82
    assert fund["dividend_yield_pct"] == 0.34
    assert fund["profit_margin"] == 0.2715
    assert fund["operating_margin"] == 0.3228
    assert fund["revenue_growth"] == 0.166
    assert fund["earnings_growth"] == 0.218
    assert fund["market_cap"] == 4631217307648
    assert fund["currency"] == "USD"


def test_build_fundamentals_drops_non_finite_pe():
    # Seen live on KRKNF: Yahoo serves trailingPE = Infinity near zero earnings.
    fund = _build_fundamentals({**INFO_AAPL, "trailingPE": float("inf")})
    assert fund["trailing_pe"] is None
    assert fund["forward_pe"] == 32.82  # the rest survives


def test_build_fundamentals_ignores_non_numeric_values():
    fund = _build_fundamentals({"trailingPE": "N/A", "marketCap": 100.0})
    assert fund["trailing_pe"] is None
    assert fund["market_cap"] == 100.0


def test_build_fundamentals_empty_returns_none():
    assert _build_fundamentals({}) is None
    # currency alone is not content — every numeric field missing means None.
    assert _build_fundamentals({"currency": "USD", "trailingPE": None}) is None


def _client() -> ClaudeClient:
    cfg = Config(
        db_host="x", db_port=3306, db_user="x", db_pass="x", db_name="x",
        anthropic_api_key="test-key",
    )
    return ClaudeClient(cfg)


def _prompt(ticker_data: dict) -> str:
    params = _client()._ticker_request_params(ticker_data, macro_signals=[])
    return params["messages"][0]["content"]


TICKER = {"id": 1, "symbol": "AAPL", "name": "Apple Inc",
          "sector": "Technology", "phase": "HOLDING"}


def test_prompt_renders_fundamentals_block():
    fund = _build_fundamentals(INFO_AAPL)
    prompt = _prompt({**TICKER, "technical": {}, "sentiment": {}, "fundamentals": fund})
    assert "Fundamentales" in prompt
    assert "P/E: 38.2 (trailing) / 32.8 (forward)" in prompt
    assert "Capitalización: 4.6T USD" in prompt
    assert "Dividend yield: 0.34%" in prompt          # percent units, no ×100
    assert "Margen: neto 27.2%, operativo 32.3%" in prompt
    assert "Crecimiento interanual: ingresos +16.6%, beneficios +21.8%" in prompt
    assert "largo plazo" in prompt


def test_prompt_omits_fundamentals_block_when_unknown():
    prompt = _prompt({**TICKER, "technical": {}, "sentiment": {}})
    assert "Fundamentales" not in prompt
    prompt = _prompt({**TICKER, "technical": {}, "sentiment": {}, "fundamentals": None})
    assert "Fundamentales" not in prompt


def test_prompt_partial_fundamentals_skips_missing_lines():
    fund = _build_fundamentals({"trailingPE": 20.0, "currency": "EUR"})
    prompt = _prompt({**TICKER, "technical": {}, "sentiment": {}, "fundamentals": fund})
    assert "P/E: 20.0 (trailing)" in prompt
    assert "Dividend yield" not in prompt
    assert "Capitalización" not in prompt
    assert "Margen" not in prompt


def test_human_cap_scales():
    assert _human_cap(4631217307648) == "4.6T"
    assert _human_cap(909695778816) == "909.7B"
    assert _human_cap(258449648) == "258.4M"
    assert _human_cap(950000) == "950000"


def test_main_fetches_fundamentals_only_for_equities(monkeypatch):
    """main() calls fetch_fundamentals for quote_type EQUITY only and wires it
    to the batch — ETFs, the index and untyped tickers never trigger it."""
    batch_items = []
    fetched = []

    stock = {"id": 1, "symbol": "AAPL", "name": "Apple", "sector": "Tech",
             "quote_type": "EQUITY", "phase": "HOLDING"}
    etf = {"id": 2, "symbol": "VWRL.AS", "name": "VWRL", "sector": None,
           "quote_type": "ETF", "phase": "HOLDING"}
    index = {"id": 3, "symbol": "^STOXX50E", "name": "Euro Stoxx 50", "sector": None,
             "quote_type": "INDEX", "phase": "WATCHLIST"}
    untyped = {"id": 4, "symbol": "SPY5.PA", "name": "SPDR S&P 500", "sector": None,
               "quote_type": None, "phase": "WATCHLIST"}
    tickers = [stock, etf, index, untyped]

    def fake_fetch_fundamentals(symbol):
        fetched.append(symbol)
        return {"trailing_pe": 38.2, "currency": "USD"}

    monkeypatch.setattr(main_mod, "_today", lambda: date(2026, 7, 6))  # non-Friday
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
    monkeypatch.setattr(main_mod, "get_active_tickers", lambda conn: tickers)
    monkeypatch.setattr(main_mod, "get_known_symbols",
                        lambda conn: {t["symbol"] for t in tickers})
    monkeypatch.setattr(main_mod, "get_latest_actions", lambda conn: {})
    monkeypatch.setattr(main_mod, "get_latest_patterns", lambda conn: None)
    monkeypatch.setattr(main_mod, "fetch_reddit_posts", lambda cfg: [])
    monkeypatch.setattr(main_mod, "fetch_macro_headlines", lambda: [])
    monkeypatch.setattr(main_mod, "fetch_prices_and_indicators", lambda s: {"price": 10.0})
    monkeypatch.setattr(main_mod, "fetch_ticker_news", lambda s: [])
    monkeypatch.setattr(main_mod, "fetch_next_earnings", lambda s: None)
    monkeypatch.setattr(main_mod, "fetch_etf_info", lambda s: None)
    monkeypatch.setattr(main_mod, "fetch_fundamentals", fake_fetch_fundamentals)
    monkeypatch.setattr(main_mod, "run_macro_analysis", lambda client, headlines: [])

    def fake_batch(client, items, signals, patterns=None):
        batch_items.extend(items)
        return {
            t["symbol"]: {"action": "HOLD" if t["phase"] == "HOLDING" else "WATCH",
                          "confidence": 0.5, "reasoning": "r"}
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

    assert fetched == ["AAPL"]  # ETF / index / untyped never trigger the fetch
    by_symbol = {item["symbol"]: item for item in batch_items}
    assert by_symbol["AAPL"]["fundamentals"]["trailing_pe"] == 38.2
    assert by_symbol["VWRL.AS"]["fundamentals"] is None
    assert by_symbol["^STOXX50E"]["fundamentals"] is None
    assert by_symbol["SPY5.PA"]["fundamentals"] is None
