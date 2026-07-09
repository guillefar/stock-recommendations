import logging
from datetime import date, datetime

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


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
