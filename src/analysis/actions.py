"""Phase-constrained action sets and coercion.

Each position phase admits only a subset of the five actions:

  HOLDING   -> {HOLD, SELL}          (we own it: keep it or exit)
  WATCHLIST -> {BUY, WATCH, AVOID}   (no position: enter, keep watching, or pass)

Structured output already pins the model to the phase's set via a JSON-schema
``enum`` (see ``analyze_ticker``), so out-of-set actions should not occur in
normal operation. ``coerce_action`` is the defensive backstop for the paths
where the enum can't help — a future non-structured call site, a refusal, or a
schema change — mapping any stray action to the nearest valid one and logging it.
"""

import logging

logger = logging.getLogger(__name__)

HOLDING_ACTIONS = ("HOLD", "SELL")
WATCHLIST_ACTIONS = ("BUY", "WATCH", "AVOID")

# Explicit nearest-valid mapping for out-of-set actions, per phase. A holding
# that comes back BUY/WATCH is the model being non-committal -> HOLD; AVOID on a
# holding is a bearish call -> SELL. On the watchlist, HOLD (sitting on nothing)
# -> WATCH; SELL with no position -> AVOID.
_HOLDING_COERCE = {"BUY": "HOLD", "WATCH": "HOLD", "AVOID": "SELL"}
_WATCHLIST_COERCE = {"HOLD": "WATCH", "SELL": "AVOID"}

# Neutral fall-back per phase, used only for actions in neither known set.
_NEUTRAL = {"HOLDING": "HOLD", "WATCHLIST": "WATCH"}


def allowed_actions(phase: str) -> tuple[str, ...]:
    """The actions permitted for a phase. Anything but ``HOLDING`` is treated as
    a watchlist position (no holding assumed)."""
    return HOLDING_ACTIONS if phase == "HOLDING" else WATCHLIST_ACTIONS


def coerce_action(action: str, phase: str) -> str:
    """Return ``action`` if valid for ``phase``; otherwise the nearest valid
    action per the explicit mapping (unknown actions fall back to the phase's
    neutral). Every coercion is logged with both values."""
    allowed = allowed_actions(phase)
    if action in allowed:
        return action
    mapping = _HOLDING_COERCE if phase == "HOLDING" else _WATCHLIST_COERCE
    coerced = mapping.get(action) or _NEUTRAL.get(phase, "WATCH")
    logger.warning(
        "Coerced out-of-set action %r -> %r for phase %s", action, coerced, phase
    )
    return coerced
