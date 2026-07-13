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

Everything produced is JSON-safe — the same dict is persisted as the
`prediction_patterns.stats` column (audit trail of what the miner saw).
"""

import json
import logging

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
    """Adds hit_rate_pct to a {correct, incorrect, neutral} count dict."""
    decided = counts["correct"] + counts["incorrect"]
    counts["hit_rate_pct"] = round(100 * counts["correct"] / decided) if decided else None
    return counts


def summarize_features(rows: list[dict], horizon: int = 30) -> dict:
    """Folds graded-outcome feature rows into per-bucket hit-rate aggregates.

    Hit rate = CORRECT / (CORRECT + INCORRECT), NEUTRAL excluded — the same
    definition as every dashboard panel. Buckets whose feature is unknown land
    in "(sin dato)" so the totals stay honest.
    """
    overall = {"correct": 0, "incorrect": 0, "neutral": 0}
    dimensions: dict[str, dict[str, dict]] = {name: {} for name in _DIMENSIONS}

    for row in rows:
        verdict = row["verdict"].lower()
        overall[verdict] += 1
        for name, bucket_fn in _DIMENSIONS.items():
            bucket = bucket_fn(row)
            b = dimensions[name].setdefault(
                bucket, {"correct": 0, "incorrect": 0, "neutral": 0}
            )
            b[verdict] += 1

    for buckets in dimensions.values():
        for counts in buckets.values():
            _tally(counts)

    return {
        "horizon_days": horizon,
        "total_outcomes": len(rows),
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
    whose status is in PROMPT_PATTERN_STATUSES and whose confidence is at least
    PROMPT_PATTERN_MIN_CONFIDENCE, sorted by confidence descending.

    Tolerant of anything malformed — no row, unparseable JSON, non-dict entries
    or missing fields all just shrink the result (worst case []), because a bad
    stored pattern must never cost a recommendation run.
    """
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
        name = p.get("name")
        description = p.get("description")
        if not name or not description:
            continue
        selected.append(
            {"name": name, "description": description, "confidence": confidence}
        )

    selected.sort(key=lambda p: p["confidence"], reverse=True)
    return selected[:PROMPT_PATTERN_MAX]
