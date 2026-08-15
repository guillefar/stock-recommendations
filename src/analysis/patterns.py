"""Pattern mining over graded outcomes (session 22).

On Friday runs (or --force-patterns), one extra Claude call looks for what the
accurate predictions share. The prompt can't carry ~1,100 raw outcome rows, so
they are folded here into correct-vs-incorrect aggregates per feature bucket
(action, confidence band, RSI band, price-vs-SMA50, 52-week position, volume
ratio, ETF-vs-stock, sector, and — once persisted rows mature — P/E band and
dividend-payer status), plus two crosses where the interesting interactions
live (action × RSI, action × type). Claude also receives its own previous
pattern set (the newest `prediction_patterns` row) so each week it refines,
confirms, revises or retires patterns instead of rediscovering them.

Session 27 adds `excess_return_pp` to every bucket — its mean return minus its
market cohort's (same day, same asset class). A hit rate alone is an absolute
measure, so over a single market regime it mostly measures the regime: the
whole graded corpus came from a −4.80% window, which is why SELL read 100% and
BUY read 2.6% on identical information and the miner CONFIRMED both as skill.
Excess return removes the shared market move, leaving selection. Note it is
direction-blind — a negative excess is skill for SELL/AVOID and failure for
BUY/HOLD — and the mining prompt spells that out.

Session 28 stops trusting the miner to *act* on that figure. Given the corrected
statistics, it cited the excess in every pattern and went on ranking by hit
rate, so `select_patterns_for_prompt` now enforces the threshold itself: a
pattern reaches the ticker prompts only if the bucket it rests on diverged from
its market cohort by at least ±1pp. Session 28 also corrected the cohort itself
— two untyped ETFs had been benchmarked against equities (see src.quote_types),
which alone manufactured the largest positive excess in the set.

Session 29 measured what the loop actually does to production and switched it
off. Across four consecutive runs injecting the *corrected* pattern sets, the
system stopped making actionable calls — BUY+SELL fell to 1–3 of 63 against a
7–17 historical range — while the market it was declining to buy rose 5.7%
(median) over the same fortnight. The next run with no block at all recovered to
9. Injection is now opt-in via PATTERN_INJECTION_ENABLED; mining still runs and
still persists, so the data keeps accumulating for the analysis that has to
happen before it goes back on.

Everything produced is JSON-safe — the same dict is persisted as the
`prediction_patterns.stats` column (audit trail of what the miner saw).
"""

import json
import logging
import math
import os

from src.analysis.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

# Buckets thinner than this many decided calls are still reported (Claude is
# told to distrust them) but a pattern can't rest on them alone.
MIN_DECIDED_FOR_EVIDENCE = 20

# Prompt-injection gate (session 25 — the patterns→prompt feedback loop).
# Only patterns the miner has re-validated against new data (CONFIRMED) or
# refined (REVISED) at high confidence reach the per-ticker prompts. NEW is
# unproven and RETIRED is dead, so neither qualifies — which also means the
# loop stays inert until the first Friday mining run confirms something.
PROMPT_PATTERN_STATUSES = {"CONFIRMED", "REVISED"}
PROMPT_PATTERN_MIN_CONFIDENCE = 0.7
PROMPT_PATTERN_MAX = 3

# The mechanical excess gate (session 28).
#
# Session 27 gave the miner market-relative statistics and asked it, in its own
# working language and immediately beside the data, not to call an action good
# or bad when its excess is near zero. It cited the excess figure in 8 of 8
# patterns and ranked by hit rate anyway: it praised RSI 70+ as reliable at a
# 76% hit rate with an excess of -0.6pp, and called a +10.6pp bucket a
# "colapso catastrófico" for its 0% hit rate. A request in the input is a
# preference; a check on the output is a guarantee. So the threshold is applied
# here, to what the miner returns, rather than asked for in the prompt.
#
# A bucket within ±1pp of its market cohort did what the market did — an extreme
# hit rate on top of that measures the regime, not the system. 1pp is well below
# the effects worth acting on (SELL -9.7pp, BUY -3.3pp, HOLD +1.2pp) and well
# above the noise floor of the buckets that turned out to be artifacts.
PROMPT_PATTERN_MIN_ABS_EXCESS = 1.0

# WATCH is excluded outright, whatever its excess. Every other action asserts a
# direction, so beating or trailing the cohort is evidence about the call.
# WATCH asserts only that a ticker is worth attention, so its excess reports
# which way the bucket happened to drift — bias, not skill. On the live corpus
# WATCH × (otro) reads +10.6pp and would sail through a magnitude test; it is
# the mis-cohorted-ETF artifact of session 28, not a finding.
PROMPT_PATTERN_EXCLUDED_ACTIONS = {"WATCH"}

# The injection kill switch (session 29) — off unless explicitly enabled.
#
# Sessions 26–28 each fixed a real defect in what the loop was learning from,
# and each time the loop found a new way to hurt the product. Session 29 finally
# measured the output rather than the mechanism, over four production runs that
# injected the corrected sets (2026-08-05, 08-07, 08-10, 08-12):
#
#     date        BUY  SELL  decisive        injected set
#     2026-07-31    7     3        10        id=3 (artifact set)
#     2026-08-03    6     1         7        id=3
#     2026-08-05    1     0         1        id=5 (corrected)
#     2026-08-07    2     1         3        id=5
#     2026-08-10    2     0         2        id=6 (corrected)
#     2026-08-12    2     0         2        id=6
#     2026-08-14    6     3         9        NONE — session 28 merged, gate
#                                            failed closed on the fieldless id=6
#
# Historical decisive range: 7–17. Over the collapsed fortnight the median active
# ticker rose 5.69% and 67% of them rose more than 4% — so the system withdrew
# from the market at precisely the wrong moment, because every prompt carried
# "BUY es sistemáticamente fallido: 6% hit rate", a statistic computed entirely
# inside the dead −4.80% May–June window. The calls didn't flip from BUY to
# SELL; both directional buckets drained into WATCH (22 → 28–30). The model was
# not persuaded of a bearish thesis, it was persuaded not to commit.
#
# The last row is the control, and it arrived unplanned: merging session 28 left
# the newest stored set without the schema fields the excess gate requires, so
# Friday 08-14 ran with no block at all — the first time since 2026-07-20 — and
# decisiveness returned to 9 immediately, one run, no other change. Turning the
# loop off is not a precaution against a suspected cause; it is the remedy for a
# measured one.
#
# The excess gate does not save this. The set mined that same Friday (id=7) does
# carry the fields, and "BUY es sistemáticamente fallido" comes back at −2.4pp /
# CONFIRMED 0.93 — clearing ±1.0pp comfortably and ranking second of three. So
# the gate would have re-injected the collapse driver on the very next run. Nor
# would ranking by |excess| help: it ranks that pattern second as well. The
# defect is not which patterns are chosen but that a hit rate mined from one
# regime is fed back as instruction into another.
#
# Mining is deliberately left running: the sets keep landing in
# prediction_patterns for analysis, they just no longer reach a prompt. Turning
# this back on requires evidence that injection improves outcomes, not merely
# that the patterns are true — the sets injected in the table above were the
# most accurate the miner has ever produced.
PATTERN_INJECTION_ENV_VAR = "PATTERN_INJECTION_ENABLED"
_TRUTHY = {"1", "true", "yes", "on"}


def pattern_injection_enabled() -> bool:
    """Whether mined patterns may reach the per-ticker prompts.

    Read at call time rather than import time so the workflow, a test or an
    ad-hoc run can flip it without reimporting the module.
    """
    return os.environ.get(PATTERN_INJECTION_ENV_VAR, "").strip().lower() in _TRUTHY


def _bucket_confidence(v) -> str:
    if v is None:
        return "(sin dato)"
    v = float(v)
    if v < 0.40:
        return "<0.40"
    if v < 0.60:
        return "0.40–0.59"
    if v < 0.80:
        return "0.60–0.79"
    return "0.80+"


def _bucket_rsi(v) -> str:
    if v is None:
        return "(sin dato)"
    if v < 30:
        return "RSI<30 (sobrevendido)"
    if v < 50:
        return "RSI 30–50"
    if v < 70:
        return "RSI 50–70"
    return "RSI 70+ (sobrecomprado)"


def _bucket_sma50(price, sma50) -> str:
    if price is None or sma50 is None:
        return "(sin dato)"
    return "precio > SMA50" if float(price) > float(sma50) else "precio ≤ SMA50"


def _bucket_pos_52w(v) -> str:
    if v is None:
        return "(sin dato)"
    v = float(v)
    if v < 0.33:
        return "tercio inferior 52s"
    if v < 0.66:
        return "tercio medio 52s"
    return "tercio superior 52s"


def _bucket_volume(v) -> str:
    if v is None:
        return "(sin dato)"
    v = float(v)
    if v < 0.8:
        return "volumen bajo (<0.8x)"
    if v <= 1.5:
        return "volumen normal (0.8–1.5x)"
    return "volumen alto (>1.5x)"


def _bucket_type(quote_type) -> str:
    return quote_type if quote_type in ("ETF", "EQUITY") else "(otro)"


def _bucket_sector(row: dict) -> str:
    # Same convention as the retrospective and track-record panel-6: ETFs get
    # their own bucket instead of drowning "(sin sector)".
    if row.get("quote_type") == "ETF":
        return "ETF"
    return row.get("sector") or "(sin sector)"


def _bucket_pe(v) -> str:
    if v is None:
        return "(sin dato)"
    v = float(v)
    if v < 15:
        return "P/E<15"
    if v < 30:
        return "P/E 15–30"
    return "P/E 30+"


def _bucket_dividend(v) -> str:
    if v is None:
        return "(sin dato)"
    return "paga dividendo" if float(v) > 0 else "sin dividendo"


# dimension name -> callable(row) -> bucket label
_DIMENSIONS = {
    "accion": lambda r: r["action"],
    "confianza": lambda r: _bucket_confidence(r.get("confidence")),
    "rsi": lambda r: _bucket_rsi(r.get("rsi")),
    "precio_vs_sma50": lambda r: _bucket_sma50(r.get("price"), r.get("sma50")),
    "posicion_52w": lambda r: _bucket_pos_52w(r.get("pos_52w")),
    "volumen": lambda r: _bucket_volume(r.get("volume_ratio")),
    "tipo": lambda r: _bucket_type(r.get("quote_type")),
    "sector": _bucket_sector,
    "pe": lambda r: _bucket_pe(r.get("trailing_pe")),
    "dividendo": lambda r: _bucket_dividend(r.get("dividend_yield_pct")),
    # Crosses: where single-dimension views hide the signal.
    "accion_x_rsi": lambda r: f"{r['action']} × {_bucket_rsi(r.get('rsi'))}",
    "accion_x_tipo": lambda r: f"{r['action']} × {_bucket_type(r.get('quote_type'))}",
}


def _tally(counts: dict) -> dict:
    """Adds hit_rate_pct and excess_return_pp to a bucket's running counts.

    `excess_return_pp` is the bucket's mean excess return in percentage points
    versus its market cohort (see `_cohort_key`) — the market-relative figure.
    None when no row in the bucket had a usable return.
    """
    decided = counts["correct"] + counts["incorrect"]
    counts["hit_rate_pct"] = round(100 * counts["correct"] / decided) if decided else None
    n = counts.pop("_excess_n", 0)
    total = counts.pop("_excess_sum", 0.0)
    counts["excess_return_pp"] = round(100 * total / n, 1) if n else None
    return counts


def _cohort_key(row: dict) -> tuple:
    """The market cohort a call is judged against: same day, same asset class.

    Session 27. Every graded 30d outcome in the corpus came from a single
    −4.80% window, which alone made SELL read 100% and BUY read 2.6% — the
    miner then CONFIRMED both as skill. Subtracting the cohort's mean forward
    return strips the shared market move out, so what's left is selection.

    Asset class is part of the key because session 26 established ETFs and
    stocks are not comparable instruments (an ETF's median 30d move is 2.62%
    against a stock's 10.70%). Judging an ETF call against a stock-dominated
    cohort would read its low beta as an absence of skill.
    """
    return (row.get("rec_date"), "ETF" if row.get("quote_type") == "ETF" else "NO-ETF")


def _cohort_means(rows: list[dict]) -> dict:
    """Mean forward return per cohort — the benchmark each call is measured on.

    Every call counts toward its cohort's mean, NEUTRAL included: the cohort is
    meant to represent the market that day, not the decided calls only.
    """
    sums: dict[tuple, list] = {}
    for row in rows:
        ret = row.get("forward_return")
        if ret is None:
            continue
        acc = sums.setdefault(_cohort_key(row), [0.0, 0])
        acc[0] += float(ret)
        acc[1] += 1
    return {key: total / n for key, (total, n) in sums.items() if n}


def summarize_features(rows: list[dict], horizon: int = 30) -> dict:
    """Folds graded-outcome feature rows into per-bucket hit-rate aggregates.

    Hit rate = CORRECT / (CORRECT + INCORRECT), NEUTRAL excluded — the same
    definition as every dashboard panel. Buckets whose feature is unknown land
    in "(sin dato)" so the totals stay honest.

    Each bucket also carries `excess_return_pp` (session 27): its mean return
    minus its market cohort's, in percentage points. Hit rate answers "how
    often was this call right", which in a one-directional market mostly
    measures the market; excess return answers "did this call beat the calls
    that shared its market", which is the part attributable to the system.
    """
    overall = {"correct": 0, "incorrect": 0, "neutral": 0,
               "_excess_sum": 0.0, "_excess_n": 0}
    dimensions: dict[str, dict[str, dict]] = {name: {} for name in _DIMENSIONS}
    cohorts = _cohort_means(rows)

    for row in rows:
        verdict = row["verdict"].lower()
        overall[verdict] += 1
        ret = row.get("forward_return")
        cohort_mean = cohorts.get(_cohort_key(row))
        excess = None if ret is None or cohort_mean is None else float(ret) - cohort_mean
        if excess is not None:
            overall["_excess_sum"] += excess
            overall["_excess_n"] += 1
        for name, bucket_fn in _DIMENSIONS.items():
            bucket = bucket_fn(row)
            b = dimensions[name].setdefault(
                bucket,
                {"correct": 0, "incorrect": 0, "neutral": 0,
                 "_excess_sum": 0.0, "_excess_n": 0},
            )
            b[verdict] += 1
            if excess is not None:
                b["_excess_sum"] += excess
                b["_excess_n"] += 1

    for buckets in dimensions.values():
        for counts in buckets.values():
            _tally(counts)

    return {
        "horizon_days": horizon,
        "total_outcomes": len(rows),
        "cohort_count": len(cohorts),
        "overall": _tally(overall),
        "dimensions": dimensions,
    }


def build_patterns_data(stats: dict, previous: dict | None) -> dict:
    """Assembles the payload for the mining call (stats + previous patterns)."""
    return {
        "stats": stats,
        "previous_patterns": (previous or {}).get("patterns"),
        "previous_generated_at": (
            str(previous["generated_at"]) if previous else None
        ),
    }


def run_pattern_analysis(client: ClaudeClient, patterns_data: dict) -> dict | None:
    """Mines/refines the pattern set. None on failure — don't persist."""
    return client.generate_pattern_analysis(patterns_data)


def select_patterns_for_prompt(latest: dict | None) -> list[dict]:
    """Gates the newest stored pattern set for per-ticker prompt injection.

    Takes the raw `get_latest_patterns` row (the `patterns` column arrives from
    pymysql as a JSON string) and returns at most PROMPT_PATTERN_MAX patterns
    that clear every gate, sorted by confidence descending:

    - `status` in PROMPT_PATTERN_STATUSES — re-validated against new data.
    - `confidence` at least PROMPT_PATTERN_MIN_CONFIDENCE.
    - `primary_action` not in PROMPT_PATTERN_EXCLUDED_ACTIONS.
    - `|excess_return_pp|` at least PROMPT_PATTERN_MIN_ABS_EXCESS — the pattern
      rests on a bucket that actually diverged from its market cohort.

    The filters run before the PROMPT_PATTERN_MAX cap, so the cap selects among
    patterns that already qualify rather than reserving slots for ones that
    don't: three eligible patterns are injected whether or not five were mined.

    Tolerant of anything malformed — no row, unparseable JSON, non-dict entries
    or missing fields all just shrink the result (worst case []), because a bad
    stored pattern must never cost a recommendation run. The excess and action
    gates **fail closed**: a pattern missing either field is dropped rather than
    waved through. Pattern sets mined before session 28 carry neither field, so
    they stop being injected the moment this ships — which is the intent. Every
    stored set predates both the session-26 re-grade and the session-28
    quote_type fix, and injecting a known-contaminated set into 63 prompts is
    the exact failure this gate exists to stop. Injection resumes on the first
    Friday mining run after deploy.

    Session 29 put a switch in front of all of it: unless
    PATTERN_INJECTION_ENABLED is set, this returns [] before reading anything.
    The gates below stay exactly as they were, so re-enabling restores the
    session-28 behaviour rather than an untested path.
    """
    if not pattern_injection_enabled():
        logger.info(
            "Pattern injection is disabled (%s unset) — ticker prompts carry no "
            "patterns block. Mining still runs and still persists.",
            PATTERN_INJECTION_ENV_VAR,
        )
        return []
    if not latest:
        return []
    raw = latest.get("patterns")
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("Stored patterns JSON is unparseable — no prompt injection")
            return []
    if not isinstance(raw, list):
        return []

    selected = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        if p.get("status") not in PROMPT_PATTERN_STATUSES:
            continue
        try:
            confidence = float(p.get("confidence"))
        except (TypeError, ValueError):
            continue
        if confidence < PROMPT_PATTERN_MIN_CONFIDENCE:
            continue
        action = p.get("primary_action")
        if not isinstance(action, str) or action.upper() in PROMPT_PATTERN_EXCLUDED_ACTIONS:
            continue
        try:
            excess = float(p.get("excess_return_pp"))
        except (TypeError, ValueError):
            continue
        # json.loads accepts the NaN/Infinity literals, and NaN fails every
        # comparison — including the one below, which would let it through.
        if not math.isfinite(excess):
            continue
        if abs(excess) < PROMPT_PATTERN_MIN_ABS_EXCESS:
            logger.info(
                "Pattern %r not injected: excess %+.1fpp is within ±%.1fpp of its "
                "market cohort (hit rate alone is the regime, not skill)",
                p.get("name"), excess, PROMPT_PATTERN_MIN_ABS_EXCESS,
            )
            continue
        name = p.get("name")
        description = p.get("description")
        if not name or not description:
            continue
        selected.append(
            {"name": name, "description": description, "confidence": confidence}
        )

    selected.sort(key=lambda p: p["confidence"], reverse=True)
    return selected[:PROMPT_PATTERN_MAX]
