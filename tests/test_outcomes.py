from src.evaluate_outcomes import grade


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
