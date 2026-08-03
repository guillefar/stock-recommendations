"""Session 28 — asset-class overrides for instruments the source table leaves NULL.

`tickers.quote_type` comes from the read-only stock-snapshots database and is
NULL for VHYL.AS and SPY5.PA, both genuine UCITS ETFs. That NULL quietly
defeated two separate corrections:

- Session 26 scaled grading bands by asset class but read NULL as "unknown →
  use unscaled stock bands", so two ETFs kept being graded as stocks. HOLD is
  CORRECT when flat and these funds are always flat, so 70 of their HOLD rows
  scored a free CORRECT.
- Session 27's market cohort splits on ETF-vs-not, so both were benchmarked
  against equities (mean -8.57%) while returning like ETFs (-1.17%) —
  manufacturing a +10pp "excess" that the miner reported as a headline finding.

The override is applied at the DB read sites so grading, mining cohorts, the
ETF prompt block and the sector bucket all see the corrected class.
"""

from src.analysis.patterns import _cohort_key, summarize_features
from src.evaluate_outcomes import bands_for, grade
from src.quote_types import (
    QUOTE_TYPE_OVERRIDES,
    apply_quote_type_overrides,
    resolve_quote_type,
)


def test_untyped_etfs_resolve_to_etf():
    assert resolve_quote_type("VHYL.AS", None) == "ETF"
    assert resolve_quote_type("SPY5.PA", None) == "ETF"


def test_override_never_contradicts_a_real_source_value():
    # If stock-snapshots ever starts populating the column, the source wins —
    # an override may fill a gap, never overrule a value that exists.
    assert resolve_quote_type("VHYL.AS", "EQUITY") == "EQUITY"
    assert resolve_quote_type("AAPL", "EQUITY") == "EQUITY"


def test_unknown_symbols_stay_unknown():
    # ^STOXX50E is deliberately absent: it is an index, not a holdable
    # instrument, so its verdicts are a different question from a band scale.
    assert resolve_quote_type("^STOXX50E", None) is None
    assert resolve_quote_type("NOPE", None) is None
    assert "^STOXX50E" not in QUOTE_TYPE_OVERRIDES


def test_apply_overrides_across_rows():
    rows = [
        {"symbol": "VHYL.AS", "quote_type": None},
        {"symbol": "AAPL", "quote_type": "EQUITY"},
        {"symbol": "^STOXX50E", "quote_type": "INDEX"},
        {"quote_type": None},  # a query that forgot to select symbol
    ]
    apply_quote_type_overrides(rows)
    assert [r["quote_type"] for r in rows] == ["ETF", "EQUITY", "INDEX", None]


def test_overridden_etf_is_graded_on_etf_bands():
    # The artifact this fixes: a +2% month is flat for a fund that moves 1-2%,
    # so HOLD scored a free CORRECT under stock bands (neutral ±4%). Under ETF
    # bands (±1.2%) the same move is no longer "flat" and grades NEUTRAL.
    assert bands_for(30, "ETF").neutral < bands_for(30, None).neutral
    assert grade("HOLD", 0.02, 30, None) == "CORRECT"
    assert grade("HOLD", 0.02, 30, "ETF") == "NEUTRAL"


def test_overridden_etf_joins_the_etf_cohort():
    # Same day, but the two rows must not benchmark against each other.
    equity = {"rec_date": "2026-06-01", "quote_type": "EQUITY"}
    fund = {"rec_date": "2026-06-01", "quote_type": resolve_quote_type("SPY5.PA", None)}
    assert _cohort_key(equity) != _cohort_key(fund)
    assert _cohort_key(fund) == _cohort_key({"rec_date": "2026-06-01", "quote_type": "ETF"})


def test_miscohorting_a_calm_fund_manufactures_excess():
    """The live artifact, reproduced: the fix removes ~10pp of phantom skill.

    Equities fall 9% on the day while the fund is flat. Cohorted with equities
    the fund looks like a +9pp stock-picking triumph; cohorted with the other
    funds — which is what it is — it shows the ~0pp it earned.
    """
    day = "2026-06-01"
    equities = [
        {"verdict": "CORRECT", "action": "SELL", "rec_date": day,
         "quote_type": "EQUITY", "forward_return": -0.09}
        for _ in range(10)
    ]
    funds = [
        {"verdict": "CORRECT", "action": "WATCH", "rec_date": day,
         "quote_type": "ETF", "forward_return": 0.0}
        for _ in range(4)
    ]

    def watch_excess(rows):
        return summarize_features(rows)["dimensions"]["accion"]["WATCH"]["excess_return_pp"]

    mislabelled = [{**f, "quote_type": None} for f in funds]
    assert watch_excess(equities + mislabelled) > 6.0   # phantom skill
    assert abs(watch_excess(equities + funds)) < 0.1     # the truth
