import pytest

from src.evaluate_outcomes import (
    ASSET_CLASS_BAND_SCALE,
    HORIZON_BANDS,
    HORIZONS,
    bands_for,
    grade,
)


def test_buy_rewards_upside():
    assert grade("BUY", 0.05) == "CORRECT"
    assert grade("BUY", -0.05) == "INCORRECT"
    assert grade("BUY", 0.01) == "NEUTRAL"  # inside the band


def test_bearish_actions_reward_downside():
    assert grade("SELL", -0.05) == "CORRECT"
    assert grade("SELL", 0.05) == "INCORRECT"
    assert grade("AVOID", -0.05) == "CORRECT"
    assert grade("AVOID", 0.0) == "NEUTRAL"


def test_watch_is_movement_graded():
    # Worth watching = it moved, in either direction.
    assert grade("WATCH", 0.05) == "CORRECT"
    assert grade("WATCH", -0.05) == "CORRECT"
    assert grade("WATCH", 0.30) == "CORRECT"
    # Flat = the watch wasted attention.
    assert grade("WATCH", 0.01) == "INCORRECT"
    assert grade("WATCH", -0.019) == "INCORRECT"
    assert grade("WATCH", 0.0) == "INCORRECT"
    # In between is noise.
    assert grade("WATCH", 0.03) == "NEUTRAL"
    assert grade("WATCH", -0.04) == "NEUTRAL"


def test_hold_rewards_flat_penalizes_deep_loss():
    assert grade("HOLD", 0.01) == "CORRECT"
    assert grade("HOLD", -0.02) == "CORRECT"
    # Deep loss: the holding deserved a SELL.
    assert grade("HOLD", -0.11) == "INCORRECT"
    assert grade("HOLD", -0.30) == "INCORRECT"
    # Moderate loss and any upside are neutral — upside never penalized.
    assert grade("HOLD", -0.05) == "NEUTRAL"
    assert grade("HOLD", 0.10) == "NEUTRAL"
    assert grade("HOLD", 0.30) == "NEUTRAL"


def test_every_horizon_has_bands():
    assert HORIZONS == (7, 30, 90, 180, 365)
    for h in HORIZONS:
        b = HORIZON_BANDS[h]
        assert 0 < b.neutral < b.watch_move
        assert b.neutral < b.hold_loss


def test_bands_monotonic_across_horizons():
    # Each threshold must widen (or hold) as the horizon grows, so a verdict
    # never gets *easier* at a longer horizon (session 23: 180d slots in).
    ordered = [HORIZON_BANDS[h] for h in HORIZONS]
    for shorter, longer in zip(ordered, ordered[1:]):
        assert shorter.neutral < longer.neutral
        assert shorter.watch_move < longer.watch_move
        assert shorter.hold_loss <= longer.hold_loss


def test_bands_widen_with_horizon():
    # A +3% return is a hit for a weekly BUY but noise for a monthly one.
    assert grade("BUY", 0.03, 7) == "CORRECT"
    assert grade("BUY", 0.03, 30) == "NEUTRAL"
    # +6% in a year is nowhere near a decisive BUY call.
    assert grade("BUY", 0.06, 365) == "NEUTRAL"
    assert grade("BUY", 0.20, 365) == "CORRECT"
    assert grade("BUY", -0.20, 365) == "INCORRECT"


def test_watch_thresholds_scale():
    # ±5% is "it moved" over a week; over 90 days it's flat (wasted attention).
    assert grade("WATCH", 0.05, 7) == "CORRECT"
    assert grade("WATCH", 0.05, 90) == "INCORRECT"
    assert grade("WATCH", 0.10, 90) == "NEUTRAL"
    assert grade("WATCH", 0.16, 90) == "CORRECT"
    # Flat over a year = the watch wasted attention (band is ±15%).
    assert grade("WATCH", 0.10, 365) == "INCORRECT"
    assert grade("WATCH", 0.31, 365) == "CORRECT"


def test_180d_bands():
    # Session 23 (user-approved ±10/21/25): a 6-month BUY must beat +10%.
    assert grade("BUY", 0.09, 180) == "NEUTRAL"
    assert grade("BUY", 0.11, 180) == "CORRECT"
    assert grade("BUY", -0.11, 180) == "INCORRECT"
    # WATCH: it moved = |return| ≥ 21%; flat = inside ±10%.
    assert grade("WATCH", 0.22, 180) == "CORRECT"
    assert grade("WATCH", -0.22, 180) == "CORRECT"
    assert grade("WATCH", 0.15, 180) == "NEUTRAL"
    assert grade("WATCH", 0.05, 180) == "INCORRECT"
    # HOLD: a 6-month slide past −25% deserved a SELL.
    assert grade("HOLD", -0.26, 180) == "INCORRECT"
    assert grade("HOLD", -0.20, 180) == "NEUTRAL"
    assert grade("HOLD", 0.02, 180) == "CORRECT"


def test_hold_loss_band_scales():
    # −12% is a graded miss at 7d but inside the 30d band (−15%).
    assert grade("HOLD", -0.12, 7) == "INCORRECT"
    assert grade("HOLD", -0.12, 30) == "NEUTRAL"
    assert grade("HOLD", -0.16, 30) == "INCORRECT"
    assert grade("HOLD", -0.25, 365) == "NEUTRAL"
    assert grade("HOLD", -0.31, 365) == "INCORRECT"


# ── Session 26: per-asset-class band scaling ──────────────────────────────────
# The base bands are single-stock volatility bands. ETFs move ~0.30x as far
# (measured mean-absolute 30d move 4.29% vs 14.67%; 2.70% vs 8.52% at 7d), so
# grading them on stock bands measured the instrument, not the call.


def test_unknown_asset_class_keeps_base_bands():
    # The index and the untyped tickers must grade exactly as before — this is
    # what keeps every pre-session-26 expectation above valid.
    for h in HORIZONS:
        assert bands_for(h) == HORIZON_BANDS[h]
        assert bands_for(h, None) == HORIZON_BANDS[h]
        assert bands_for(h, "EQUITY") == HORIZON_BANDS[h]


def test_etf_bands_are_scaled_and_case_insensitive():
    b = bands_for(30, "ETF")
    assert b.neutral == pytest.approx(0.012)
    assert b.watch_move == pytest.approx(0.030)
    assert b.hold_loss == pytest.approx(0.045)
    assert bands_for(30, "etf") == b


def test_etf_scaling_preserves_monotonicity_across_horizons():
    # A uniform scale can't break the √time ordering, but assert it: a verdict
    # must never get easier at a longer horizon for ETFs either.
    ordered = [bands_for(h, "ETF") for h in HORIZONS]
    for shorter, longer in zip(ordered, ordered[1:]):
        assert shorter.neutral < longer.neutral
        assert shorter.watch_move < longer.watch_move
        assert shorter.hold_loss <= longer.hold_loss


def test_etf_bands_stay_ordered_within_each_horizon():
    for h in HORIZONS:
        b = bands_for(h, "ETF")
        assert 0 < b.neutral < b.watch_move
        assert b.neutral < b.hold_loss


def test_watch_on_etf_is_no_longer_structurally_doomed():
    # The bug this fixes: a 2.6% monthly move is a *typical* ETF month, and the
    # old bands scored it flatly INCORRECT (below the 4% neutral band) while
    # demanding an all-but-unreachable 10% for a CORRECT. Under ETF bands the
    # median ETF month lands mid-scale instead of auto-failing, and a decent
    # 4% month is a genuine hit.
    assert grade("WATCH", 0.026, 30) == "INCORRECT"          # old behaviour
    assert grade("WATCH", 0.026, 30, "ETF") == "NEUTRAL"     # 1.2% <= 2.6% < 3.0%
    assert grade("WATCH", 0.04, 30, "ETF") == "CORRECT"      # 4.0% >= 3.0%
    assert grade("WATCH", 0.04, 30) == "NEUTRAL"             # old behaviour
    # And a genuinely flat ETF month is still a wasted watch.
    assert grade("WATCH", 0.005, 30, "ETF") == "INCORRECT"


def test_hold_on_etf_is_no_longer_a_free_win():
    # HOLD scored 94.5% on ETFs only because HOLD is CORRECT when flat and ETFs
    # are flat. A 2% ETF month is now a move, not a hit.
    assert grade("HOLD", 0.02, 30) == "CORRECT"              # old behaviour
    assert grade("HOLD", 0.02, 30, "ETF") == "NEUTRAL"
    assert grade("HOLD", 0.01, 30, "ETF") == "CORRECT"
    # An ETF sliding 5% in a month is a real loss at ETF scale (band −4.5%).
    assert grade("HOLD", -0.05, 30, "ETF") == "INCORRECT"
    assert grade("HOLD", -0.05, 30) == "NEUTRAL"


def test_directional_calls_scale_too():
    # BUY/SELL/AVOID pivot on the neutral band, which also scales.
    assert grade("BUY", 0.02, 30, "ETF") == "CORRECT"
    assert grade("BUY", 0.02, 30) == "NEUTRAL"
    assert grade("SELL", -0.02, 30, "ETF") == "CORRECT"
    assert grade("AVOID", -0.02, 30) == "NEUTRAL"
    assert grade("BUY", 0.005, 30, "ETF") == "NEUTRAL"


def test_scale_factor_is_the_measured_ratio():
    # Guard the constant: it is an empirical ETF/stock volatility ratio
    # (0.317 at 7d, 0.292 at 30d), not a knob to nudge.
    assert ASSET_CLASS_BAND_SCALE == {"ETF": 0.30}
