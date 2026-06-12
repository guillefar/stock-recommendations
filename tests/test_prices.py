from datetime import date, datetime

import pandas as pd

from src.collectors.prices import _pick_next_earnings

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
