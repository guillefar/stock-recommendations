from src.evaluate_outcomes import grade


def test_bullish_actions_reward_upside():
    assert grade("BUY", 0.05) == "CORRECT"
    assert grade("BUY", -0.05) == "INCORRECT"
    assert grade("WATCH", 0.05) == "CORRECT"
    assert grade("BUY", 0.01) == "NEUTRAL"  # inside the band


def test_bearish_actions_reward_downside():
    assert grade("SELL", -0.05) == "CORRECT"
    assert grade("SELL", 0.05) == "INCORRECT"
    assert grade("AVOID", -0.05) == "CORRECT"
    assert grade("AVOID", 0.0) == "NEUTRAL"


def test_hold_rewards_flat_never_penalizes():
    assert grade("HOLD", 0.01) == "CORRECT"
    assert grade("HOLD", 0.10) == "NEUTRAL"
    assert grade("HOLD", -0.10) == "NEUTRAL"
