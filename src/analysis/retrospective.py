"""S5 weekly retrospective: aggregate the week's evidence for one Claude call.

The prompt can't carry every matured outcome (up to ~300 rows/week), so the
rows are folded into counts + a handful of highlight calls here, in Python.
Everything produced is JSON-safe — the same dict is persisted as the
`weekly_retrospectives.stats` column.
"""

import logging

from src.analysis.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

HIGHLIGHT_COUNT = 5


def summarize_outcomes(rows: list[dict]) -> dict:
    """Folds graded-outcome rows into counts, hit rate, and highlight calls.

    Hit rate = CORRECT / (CORRECT + INCORRECT), NEUTRAL excluded — the same
    definition as every dashboard panel. Highlights are the biggest movers
    among the decided calls (they anchor the narrative better than averages).
    """
    def _shape(row: dict) -> dict:
        return {
            "symbol": row["symbol"],
            "action": row["action"],
            "forward_return": float(row["forward_return"]),
            "verdict": row["verdict"],
            "called_on": str(row["called_on"]),
        }

    correct = [_shape(r) for r in rows if r["verdict"] == "CORRECT"]
    incorrect = [_shape(r) for r in rows if r["verdict"] == "INCORRECT"]
    neutral_count = sum(1 for r in rows if r["verdict"] == "NEUTRAL")
    decided = len(correct) + len(incorrect)

    by_magnitude = lambda r: abs(r["forward_return"])  # noqa: E731
    return {
        "total": len(rows),
        "correct": len(correct),
        "incorrect": len(incorrect),
        "neutral": neutral_count,
        "hit_rate_pct": round(100 * len(correct) / decided) if decided else None,
        "best": sorted(correct, key=by_magnitude, reverse=True)[:HIGHLIGHT_COUNT],
        "worst": sorted(incorrect, key=by_magnitude, reverse=True)[:HIGHLIGHT_COUNT],
    }


def sector_exposure(tickers: list[dict]) -> dict[str, dict[str, int]]:
    """Ticker count per sector, split by phase (HOLDING/WATCHLIST).

    ETFs have no sector of their own (they hold many) — they get their own
    bucket instead of drowning the exposure list in "(sin sector)".
    """
    exposure: dict[str, dict[str, int]] = {}
    for t in tickers:
        phase = t.get("phase") or "WATCHLIST"
        sector = t.get("sector") or (
            "ETF" if t.get("quote_type") == "ETF" else "(sin sector)"
        )
        exposure.setdefault(phase, {})
        exposure[phase][sector] = exposure[phase].get(sector, 0) + 1
    return exposure


def build_retro_data(
    week_start,
    tickers: list[dict],
    outcome_rows: list[dict],
    flip_rows: list[dict],
    horizon: int = 30,
) -> dict:
    """Assembles the JSON-safe payload for the retrospective call + stats column."""
    return {
        "week_start": str(week_start),
        "horizon_days": horizon,
        "outcomes": summarize_outcomes(outcome_rows),
        "flips": [
            {
                "day": str(f["day"]),
                "symbol": f["symbol"],
                "prev_action": f["prev_action"],
                "new_action": f["new_action"],
            }
            for f in flip_rows
        ],
        "sector_exposure": sector_exposure(tickers),
    }


def run_weekly_retrospective(client: ClaudeClient, retro_data: dict) -> dict | None:
    """Generates the week-in-review. None on failure — don't persist."""
    return client.generate_weekly_retrospective(retro_data)
