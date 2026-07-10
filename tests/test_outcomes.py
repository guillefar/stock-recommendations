from src.evaluate_outcomes import HORIZON_BANDS, HORIZONS, grade


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
    assert HORIZONS == (7, 30, 90, 365)
    for h in HORIZONS:
        b = HORIZON_BANDS[h]
        assert 0 < b.neutral < b.watch_move
        assert b.neutral < b.hold_loss


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


def test_hold_loss_band_scales():
    # −12% is a graded miss at 7d but inside the 30d band (−15%).
    assert grade("HOLD", -0.12, 7) == "INCORRECT"
    assert grade("HOLD", -0.12, 30) == "NEUTRAL"
    assert grade("HOLD", -0.16, 30) == "INCORRECT"
    assert grade("HOLD", -0.25, 365) == "NEUTRAL"
    assert grade("HOLD", -0.31, 365) == "INCORRECT"
