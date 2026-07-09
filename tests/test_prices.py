from datetime import date, datetime

import pandas as pd

from src.collectors.prices import _compute_rsi, _pick_next_earnings

TODAY = date(2026, 6, 12)


def test_picks_earliest_future_date():
    dates = [date(2026, 7, 30), date(2026, 7, 28)]
    assert _pick_next_earnings(dates, TODAY) == "2026-07-28"


def test_today_counts_as_upcoming():
    assert _pick_next_earnings([date(2026, 6, 12)], TODAY) == "2026-06-12"


def test_stale_calendar_returns_none():
    # Only past dates (yfinance sometimes serves the last report) → unknown.
    assert _pick_next_earnings([date(2026, 5, 1)], TODAY) is None
    assert _pick_next_earnings([], TODAY) is None


def test_normalizes_datetime_and_timestamp():
    dates = [datetime(2026, 8, 3, 16, 0), pd.Timestamp("2026-07-15")]
    assert _pick_next_earnings(dates, TODAY) == "2026-07-15"


def test_ignores_non_date_values():
    assert _pick_next_earnings(["garbage", None, 42], TODAY) is None


def test_rsi_all_gains_is_overbought():
    # 20 consecutive up-closes: loss=0 must give RSI≈100, not 0 (the F3 bug).
    prices = pd.Series([100.0 + i for i in range(20)])
    assert _compute_rsi(prices, 14) >= 99


def test_rsi_all_losses_is_oversold():
    prices = pd.Series([100.0 - i for i in range(20)])
    assert _compute_rsi(prices, 14) <= 1


def test_rsi_mixed_series_in_open_interval():
    prices = pd.Series([100.0, 101.0, 99.5, 102.0, 100.5, 103.0, 101.5, 104.0,
                        102.5, 105.0, 103.5, 106.0, 104.5, 107.0, 105.5, 108.0])
    rsi = _compute_rsi(prices, 14)
    assert 0 < rsi < 100


def test_rsi_too_short_series_returns_none():
    assert _compute_rsi(pd.Series([100.0, 101.0]), 14) is None
