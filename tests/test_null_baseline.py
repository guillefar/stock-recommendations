"""Tests for the null-baseline harness (scripts/check_null_baseline.py).

Session 31. The point of the harness is that the headline hit rate is only
readable against what a skill-free call scores, so the properties that make the
permutation a *valid* null are the ones worth pinning: it must destroy the
association between call and outcome while preserving everything that is not
skill (the action mix, the returns, the per-instrument bands). A permutation
that quietly changed the mix would produce a null that looks like a finding.
"""
import collections
import importlib.util
import os
import random

import pytest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "check_null_baseline.py")


def _load():
    """Import the script by path — scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location("check_null_baseline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nb = pytest.importorskip("pymysql") and _load()


def _rows():
    # Two tickers with deliberately different volatility, so a permutation that
    # moved an action onto the wrong instrument's bands would change the grade.
    return [
        {"horizon_days": 30, "action": "WATCH", "forward_return": 0.05,
         "verdict": "CORRECT", "symbol": "AAPL", "quote_type": "EQUITY"},
        {"horizon_days": 30, "action": "HOLD", "forward_return": 0.01,
         "verdict": "CORRECT", "symbol": "AAPL", "quote_type": "EQUITY"},
        {"horizon_days": 30, "action": "BUY", "forward_return": -0.08,
         "verdict": "INCORRECT", "symbol": "AAPL", "quote_type": "EQUITY"},
        {"horizon_days": 30, "action": "SELL", "forward_return": 0.02,
         "verdict": "INCORRECT", "symbol": "VUSA.AS", "quote_type": "ETF"},
        {"horizon_days": 30, "action": "WATCH", "forward_return": 0.00,
         "verdict": "INCORRECT", "symbol": "VUSA.AS", "quote_type": "ETF"},
        {"horizon_days": 30, "action": "HOLD", "forward_return": 0.003,
         "verdict": "CORRECT", "symbol": "VUSA.AS", "quote_type": "ETF"},
    ]


def test_hit_rate_excludes_neutral():
    # Must match the scorecard's definition exactly, or the null is not
    # comparable with the number it is meant to calibrate.
    assert nb.hit_rate(["CORRECT", "INCORRECT"]) == 50.0
    assert nb.hit_rate(["CORRECT", "NEUTRAL", "NEUTRAL"]) == 100.0
    assert nb.hit_rate(["NEUTRAL"]) is None
    assert nb.hit_rate([]) is None


def test_permutation_preserves_the_action_mix():
    # The mix is a property of how the system talks, not of whether it is
    # right. A null that changed it would be measuring the wrong thing.
    rows = _rows()
    before = collections.Counter(r["action"] for r in rows)
    for within in (False, True):
        out = nb.permute(rows, random.Random(1), within)
        assert collections.Counter(a for a, _ in out) == before


def test_within_ticker_permutation_keeps_actions_on_their_own_ticker():
    # This is what separates "SELLs the right names" from "SELLs at the right
    # moments": instrument selection must be held fixed.
    rows = _rows()
    per_symbol = collections.defaultdict(collections.Counter)
    for r in rows:
        per_symbol[r["symbol"]][r["action"]] += 1
    out = nb.permute(rows, random.Random(7), within_ticker=True)
    got = collections.defaultdict(collections.Counter)
    for (action, _), r in zip(out, rows):
        got[r["symbol"]][action] += 1
    assert got == per_symbol


def test_global_permutation_does_move_actions_between_tickers():
    # The counterpart of the test above — if the global shuffle also kept
    # actions on their own ticker the two nulls would be the same number and
    # the decomposition would be silently meaningless.
    rows = _rows() * 6
    moved = False
    for seed in range(20):
        out = nb.permute(rows, random.Random(seed), within_ticker=False)
        if any(a != r["action"] for (a, _), r in zip(out, rows)):
            moved = True
            break
    assert moved


def test_permutation_grades_on_the_rows_own_instrument_bands():
    # The band travels with the row, never with the action. The same 2% move is
    # a CORRECT WATCH on VUSA.AS (scale 0.13, watch_move 1.3%) and an INCORRECT
    # one on IREN (scale 1.91, neutral band 7.6%) — all three verdicts are
    # reachable from one return, so if permute() resolved the band by anything
    # other than the row's own symbol this test moves.
    def verdict_for(symbol, quote_type):
        row = {"horizon_days": 30, "action": "WATCH", "forward_return": 0.02,
               "verdict": "CORRECT", "symbol": symbol, "quote_type": quote_type}
        (_, v), = nb.permute([row], random.Random(0), within_ticker=False)
        return v

    assert verdict_for("VUSA.AS", "ETF") == "CORRECT"      # 2% clears 1.3%
    assert verdict_for("AAPL", "EQUITY") == "NEUTRAL"      # inside 1.3%–3.2%
    assert verdict_for("IREN", "EQUITY") == "INCORRECT"    # inside a 7.6% band


def test_permutation_is_deterministic_for_a_seed():
    # The pinned null on the dashboard has to be reproducible, or "65.8" is
    # just a number someone once saw.
    rows = _rows()
    a = nb.permute(rows, random.Random(42), False)
    b = nb.permute(rows, random.Random(42), False)
    assert a == b


def test_single_row_ticker_is_a_fixed_point_under_within_ticker_shuffle():
    # A ticker with one row cannot be shuffled, so its verdict must survive
    # untouched — otherwise the within-ticker null would drift toward the
    # global one as the corpus thins.
    rows = _rows()[:1]
    (action, verdict), = nb.permute(rows, random.Random(3), within_ticker=True)
    assert action == rows[0]["action"]
    assert verdict == rows[0]["verdict"]
