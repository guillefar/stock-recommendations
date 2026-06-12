from src.analysis.actions import allowed_actions, coerce_action


def test_allowed_sets_per_phase():
    assert allowed_actions("HOLDING") == ("HOLD", "SELL")
    assert allowed_actions("WATCHLIST") == ("BUY", "WATCH", "AVOID")
    # Unknown / missing phase defaults to the watchlist set (no position assumed).
    assert allowed_actions("") == ("BUY", "WATCH", "AVOID")


def test_in_set_actions_pass_through():
    assert coerce_action("HOLD", "HOLDING") == "HOLD"
    assert coerce_action("SELL", "HOLDING") == "SELL"
    assert coerce_action("BUY", "WATCHLIST") == "BUY"
    assert coerce_action("WATCH", "WATCHLIST") == "WATCH"
    assert coerce_action("AVOID", "WATCHLIST") == "AVOID"


def test_holding_coercions():
    # Non-committal -> HOLD; bearish AVOID -> SELL.
    assert coerce_action("BUY", "HOLDING") == "HOLD"
    assert coerce_action("WATCH", "HOLDING") == "HOLD"
    assert coerce_action("AVOID", "HOLDING") == "SELL"


def test_watchlist_coercions():
    # Sitting on nothing -> WATCH; SELL with no position -> AVOID.
    assert coerce_action("HOLD", "WATCHLIST") == "WATCH"
    assert coerce_action("SELL", "WATCHLIST") == "AVOID"


def test_unknown_action_falls_back_to_phase_neutral():
    assert coerce_action("???", "HOLDING") == "HOLD"
    assert coerce_action("???", "WATCHLIST") == "WATCH"
