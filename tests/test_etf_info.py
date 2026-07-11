"""Session 18: ETF composition reaches the per-ticker prompt (Perfil del ETF).

ETFs used to run on technicals alone — no sector, news or earnings. Now
tickers whose quote_type is ETF (from the tickers table) get their fund
profile (family, expense ratio, top holdings, sector mix) fetched via
yfinance funds_data and rendered as an optional Spanish prompt block;
stocks pay nothing and keep their original prompt.
"""

from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd

import src.main as main_mod
from src.analysis.claude_client import ClaudeClient
from src.analysis.retrospective import sector_exposure
from src.collectors.prices import _build_etf_info
from src.config import Config

OVERVIEW = {"categoryName": None, "family": "Vanguard Group (Ireland) Limited",
            "legalType": "Exchange Traded Fund"}
OPERATIONS = pd.DataFrame(
    {"VWRL.AS": [0.0022, 0.07], "Category Average": [None, None]},
    index=["Annual Report Expense Ratio", "Annual Holdings Turnover"],
)
HOLDINGS = pd.DataFrame(
    {
        "Name": ["NVIDIA Corp", "Apple Inc", "Microsoft Corp",
                 "Amazon.com Inc", "Alphabet Inc Class A", "Meta Platforms Inc"],
        "Holding Percent": [0.047, 0.0427, 0.0317, 0.0247, 0.021, 0.019],
    },
    index=["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META"],
)
SECTORS = {"technology": 0.3251, "financial_services": 0.1531,
           "industrials": 0.1051, "realestate": 0.0179, "energy": 0.0,
           "healthcare": 0.0773, "consumer_cyclical": 0.0919,
           "communication_services": 0.0843, "utilities": 0.0244,
           "consumer_defensive": 0.046, "basic_materials": 0.0376}


def test_build_etf_info_normalizes_all_pieces():
    info = _build_etf_info(OVERVIEW, OPERATIONS, HOLDINGS, SECTORS, "VWRL.AS")
    assert info["family"] == "Vanguard Group (Ireland) Limited"
    assert info["expense_ratio"] == 0.0022
    # Top holdings capped at 5 even when Yahoo serves more.
    assert [h["symbol"] for h in info["top_holdings"]] == ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"]
    assert info["top_holdings"][0] == {"symbol": "NVDA", "name": "NVIDIA Corp", "pct": 0.047}
    # Zero-weight sectors are dropped; the rest keep their fractions.
    assert "energy" not in info["sector_weights"]
    assert info["sector_weights"]["technology"] == 0.3251


def test_build_etf_info_treats_zero_expense_ratio_as_unknown():
    # Yahoo serves 0.0 for many UCITS ETFs where the real figure is unknown.
    ops = pd.DataFrame({"XESC.DE": [0.0]}, index=["Annual Report Expense Ratio"])
    info = _build_etf_info(OVERVIEW, ops, HOLDINGS, SECTORS, "XESC.DE")
    assert info["expense_ratio"] is None


def test_build_etf_info_empty_returns_none():
    assert _build_etf_info({}, None, None, {}, "X") is None
    assert _build_etf_info(None, None, None, None, "X") is None


def _client() -> ClaudeClient:
    cfg = Config(
        db_host="x", db_port=3306, db_user="x", db_pass="x", db_name="x",
        anthropic_api_key="test-key",
    )
    return ClaudeClient(cfg)


def _prompt(ticker_data: dict) -> str:
    params = _client()._ticker_request_params(ticker_data, macro_signals=[])
    return params["messages"][0]["content"]


TICKER = {"id": 1, "symbol": "VWRL.AS", "name": "Vanguard FTSE All-World",
          "sector": None, "phase": "HOLDING"}


def test_prompt_renders_etf_block():
    info = _build_etf_info(OVERVIEW, OPERATIONS, HOLDINGS, SECTORS, "VWRL.AS")
    prompt = _prompt({**TICKER, "technical": {}, "sentiment": {}, "etf_info": info})
    assert "Perfil del ETF" in prompt
    assert "Gestora: Vanguard Group (Ireland) Limited" in prompt
    assert "Ratio de gastos anual: 0.22%" in prompt
    assert "Principales posiciones: NVDA 4.7%, AAPL 4.3%" in prompt
    # Sector mix: top-5 by weight, largest first.
    assert "Distribución sectorial: technology 33%, financial_services 15%" in prompt
    assert "utilities" not in prompt  # below the top-5 cut
    assert "no como una acción individual" in prompt


def test_prompt_omits_etf_block_for_stocks():
    prompt = _prompt({**TICKER, "symbol": "AAPL", "technical": {}, "sentiment": {}})
    assert "Perfil del ETF" not in prompt
    prompt = _prompt({**TICKER, "technical": {}, "sentiment": {}, "etf_info": None})
    assert "Perfil del ETF" not in prompt


def test_main_fetches_etf_info_only_for_etfs(monkeypatch):
    """main() calls fetch_etf_info for quote_type ETF and wires it to the batch."""
    batch_items = []
    fetched = []

    etf = {"id": 1, "symbol": "VWRL.AS", "name": "VWRL", "sector": None,
           "quote_type": "ETF", "phase": "HOLDING"}
    stock = {"id": 2, "symbol": "AAPL", "name": "Apple", "sector": "Tech",
             "quote_type": "EQUITY", "phase": "WATCHLIST"}

    def fake_fetch_etf_info(symbol):
        fetched.append(symbol)
        return {"family": "Vanguard", "top_holdings": [], "sector_weights": {}}

    monkeypatch.setattr(main_mod, "_today", lambda: date(2026, 7, 6))  # non-Friday
    monkeypatch.setattr(main_mod, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(
        main_mod, "ClaudeClient", lambda cfg: SimpleNamespace(log_usage=lambda: None)
    )
    monkeypatch.setattr(
        main_mod, "get_connection",
        lambda cfg: SimpleNamespace(ping=lambda **kw: None, close=lambda: None),
    )
    monkeypatch.setattr(main_mod, "get_active_tickers", lambda conn: [etf, stock])
    monkeypatch.setattr(main_mod, "get_known_symbols", lambda conn: {"VWRL.AS", "AAPL"})
    monkeypatch.setattr(main_mod, "get_latest_actions", lambda conn: {})
    monkeypatch.setattr(main_mod, "fetch_reddit_posts", lambda cfg: [])
    monkeypatch.setattr(main_mod, "fetch_macro_headlines", lambda: [])
    monkeypatch.setattr(main_mod, "fetch_prices_and_indicators", lambda s: {"price": 10.0})
    monkeypatch.setattr(main_mod, "fetch_ticker_news", lambda s: [])
    monkeypatch.setattr(main_mod, "fetch_next_earnings", lambda s: None)
    monkeypatch.setattr(main_mod, "fetch_etf_info", fake_fetch_etf_info)
    monkeypatch.setattr(main_mod, "fetch_fundamentals", lambda s: None)
    monkeypatch.setattr(main_mod, "run_macro_analysis", lambda client, headlines: [])

    def fake_batch(client, items, signals):
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
    monkeypatch.setattr(main_mod, "write_daily_summary", lambda *a, **kw: None)

    main_mod.main(dry_run=False)

    assert fetched == ["VWRL.AS"]  # the stock never triggers a fund-data fetch
    by_symbol = {item["symbol"]: item for item in batch_items}
    assert by_symbol["VWRL.AS"]["etf_info"]["family"] == "Vanguard"
    assert by_symbol["AAPL"]["etf_info"] is None


def test_sector_exposure_buckets_etfs():
    tickers = [
        {"phase": "HOLDING", "sector": None, "quote_type": "ETF"},
        {"phase": "HOLDING", "sector": None, "quote_type": "ETF"},
        {"phase": "HOLDING", "sector": "Technology", "quote_type": "EQUITY"},
        {"phase": "WATCHLIST", "sector": None, "quote_type": "INDEX"},
    ]
    exposure = sector_exposure(tickers)
    assert exposure["HOLDING"] == {"ETF": 2, "Technology": 1}
    assert exposure["WATCHLIST"] == {"(sin sector)": 1}
