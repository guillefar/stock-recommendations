import logging
from datetime import date, datetime

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# yfinance logs its own ERROR line (e.g. an HTTP 404 when an ETF has no
# earnings calendar) before our except clauses ever run. Those are cosmetic —
# every failure path here already logs through this module's logger — so the
# library's internal logger (and its children) is silenced outright (S13).
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


def fetch_prices_and_indicators(symbol: str) -> dict:
    """Fetches 1y of OHLCV history and computes all technical indicators."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 2:
            logger.warning(f"No price history for {symbol}")
            return {}

        # Yahoo can emit today's row with NaN Close mid-session (seen on
        # European ETFs); use the last *valid* close so price is never NaN.
        close = hist["Close"].dropna()
        if close.empty:
            logger.warning(f"No valid close prices for {symbol}")
            return {}
        current_price = close.iloc[-1]

        def f(v) -> float | None:
            return round(float(v), 4) if v is not None and not pd.isna(v) else None

        return {
            "price": f(current_price),
            "rsi": f(_compute_rsi(close, 14)),
            "sma20": f(_sma(close, 20)),
            "sma50": f(_sma(close, 50)),
            "sma200": f(_sma(close, 200)),
            "change_1d": f(_pct_change(close, 1)),
            "change_7d": f(_pct_change(close, 5)),   # ~5 trading days
            "change_30d": f(_pct_change(close, 21)),  # ~21 trading days
            "pos_52w": f(_pos_52w(current_price, hist["Low"].min(), hist["High"].max())),
            "high_52w": f(hist["High"].max()),
            "low_52w": f(hist["Low"].min()),
            "volume_ratio": round(float(_volume_ratio(hist["Volume"])), 2),
        }
    except Exception as e:
        logger.error(f"Error fetching prices for {symbol}: {e}")
        return {}


def fetch_ticker_news(symbol: str) -> list[dict]:
    """Fetches recent news headlines for a ticker via yfinance."""
    try:
        news = yf.Ticker(symbol).news or []
        result = []
        for item in news[:10]:
            # yfinance news schema varies by version; handle both shapes
            content = item.get("content", {})
            title = content.get("title") or item.get("title", "")
            url = (content.get("canonicalUrl", {}) or {}).get("url") or item.get("link", "")
            result.append({"title": title, "url": url})
        return result
    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return []


def fetch_next_earnings(symbol: str) -> str | None:
    """Returns the next earnings date as 'YYYY-MM-DD', or None if unknown.

    yfinance's `calendar` schema varies by version (dict with 'Earnings Date'
    in recent ones, DataFrame in older ones) and is empty for ETFs, so this
    degrades to None on anything unexpected.
    """
    try:
        cal = yf.Ticker(symbol).calendar
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date") or []
        elif cal is not None and "Earnings Date" in getattr(cal, "index", []):
            dates = list(cal.loc["Earnings Date"])
        else:
            dates = []
        return _pick_next_earnings(dates, date.today())
    except Exception as e:
        logger.warning(f"Error fetching earnings calendar for {symbol}: {e}")
        return None


def fetch_etf_info(symbol: str) -> dict | None:
    """ETF profile (family, expense ratio, top holdings, sector mix) via yfinance.

    Only called for tickers whose `quote_type` is ETF (from the tickers table).
    Returns None on any fetch error or when Yahoo has no fund data — the prompt
    block is optional enrichment and must never fail the ticker.
    """
    try:
        fd = yf.Ticker(symbol).funds_data
        overview = fd.fund_overview
        try:
            operations = fd.fund_operations
        except Exception:
            operations = None
        return _build_etf_info(
            overview, operations, fd.top_holdings, fd.sector_weightings, symbol
        )
    except Exception as e:
        logger.warning(f"Error fetching ETF info for {symbol}: {e}")
        return None


def _build_etf_info(overview, operations, holdings, sector_weights, symbol: str) -> dict | None:
    """Normalizes yfinance funds_data pieces into the prompt's etf_info shape.

    Yahoo serves an expense ratio of 0.0 for many UCITS ETFs where the real
    figure is unknown — treated as missing rather than shown as 0.00%.
    """
    info = {
        "family": (overview or {}).get("family"),
        "category": (overview or {}).get("categoryName"),
        "expense_ratio": None,
        "top_holdings": [],
        "sector_weights": {},
    }
    try:
        ratio = operations.loc["Annual Report Expense Ratio", symbol]
        info["expense_ratio"] = float(ratio) if ratio and not pd.isna(ratio) else None
    except Exception:
        pass
    if holdings is not None:
        for held_symbol, row in holdings.head(5).iterrows():
            pct = row.get("Holding Percent")
            info["top_holdings"].append({
                "symbol": str(held_symbol),
                "name": row.get("Name") or "",
                "pct": float(pct) if pct is not None and not pd.isna(pct) else None,
            })
    info["sector_weights"] = {
        sector: round(float(weight), 4)
        for sector, weight in (sector_weights or {}).items()
        if weight and float(weight) > 0
    }
    has_content = info["family"] or info["top_holdings"] or info["sector_weights"]
    return info if has_content else None


def _pick_next_earnings(dates: list, today: date) -> str | None:
    """Earliest earnings date at/after today, ISO-formatted; None if none."""
    normalized = []
    for v in dates:
        if isinstance(v, datetime):
            v = v.date()
        elif hasattr(v, "to_pydatetime"):  # pd.Timestamp
            v = v.to_pydatetime().date()
        if isinstance(v, date):
            normalized.append(v)
    upcoming = sorted(d for d in normalized if d >= today)
    return upcoming[0].isoformat() if upcoming else None


def _compute_rsi(prices: pd.Series, period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    # Epsilon, not inf: an all-gain window (loss=0) must yield RSI≈100
    # (overbought), not 0 — inf made rs=0 and inverted the signal.
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else None


def _sma(prices: pd.Series, period: int) -> float | None:
    if len(prices) < period:
        return None
    val = prices.rolling(period).mean().iloc[-1]
    return float(val) if not pd.isna(val) else None


def _pct_change(prices: pd.Series, days: int) -> float | None:
    if len(prices) < days + 1:
        return None
    past = prices.iloc[-(days + 1)]
    now = prices.iloc[-1]
    return float((now / past) - 1) if past != 0 else None


def _pos_52w(price: float, low: float, high: float) -> float:
    rng = high - low
    return (price - low) / rng if rng > 0 else 0.5


def _volume_ratio(volume: pd.Series) -> float:
    today = volume.iloc[-1]
    avg = volume.iloc[-21:].mean()
    return today / avg if avg > 0 else 1.0
