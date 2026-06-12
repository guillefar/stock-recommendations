"""Grade past recommendations against what the price actually did.

For each matured recommendation, finds the first price at/after a fixed horizon
(from `price_snapshots`, falling back to the in-repo `price_checks` table),
computes the forward return, and assigns a verdict. Results land in
`recommendation_outcomes` (one row per recommendation per horizon).

Run after a few days of price history have accumulated:

    python -m src.evaluate_outcomes            # writes outcomes
    python -m src.evaluate_outcomes --dry-run  # logs only
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from src.config import load_config
from src.db import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Calendar-day horizons at which to grade each recommendation.
HORIZONS = (7, 30)

# Move (in either direction) below which an outcome is "flat" rather than a hit/miss.
NEUTRAL_BAND = 0.02

# How long after a horizon we still accept a snapshot as the exit price. Guards
# against matching a far-future snapshot when price data is sparse.
EXIT_WINDOW_DAYS = 14

# WATCH is movement-graded: a move at least this large (either direction) means
# the ticker was worth watching.
WATCH_MOVE_THRESHOLD = 0.05

# HOLD is wrong only on a deep loss: a drop beyond this band means the holding
# deserved a SELL call instead.
HOLD_LOSS_BAND = 0.10


def grade(action: str, forward_return: float, band: float = NEUTRAL_BAND) -> str:
    """Verdict for a recommendation given its forward return.

    Semantics (decisions log, 2026-06-12 session 06):
    - BUY is bullish, SELL/AVOID bearish, with a ±`band` neutral zone.
    - WATCH is direction-agnostic: CORRECT if |return| ≥ WATCH_MOVE_THRESHOLD,
      INCORRECT if |return| < `band` (the watch wasted attention), else NEUTRAL.
    - HOLD: CORRECT if flat (|return| ≤ `band`), INCORRECT below −HOLD_LOSS_BAND,
      else NEUTRAL. Upside is never penalized.
    Returns 'CORRECT', 'INCORRECT', or 'NEUTRAL'.
    """
    if action == "BUY":
        if forward_return > band:
            return "CORRECT"
        if forward_return < -band:
            return "INCORRECT"
        return "NEUTRAL"
    if action in ("SELL", "AVOID"):
        if forward_return < -band:
            return "CORRECT"
        if forward_return > band:
            return "INCORRECT"
        return "NEUTRAL"
    if action == "WATCH":
        if abs(forward_return) >= WATCH_MOVE_THRESHOLD:
            return "CORRECT"
        if abs(forward_return) < band:
            return "INCORRECT"
        return "NEUTRAL"
    # HOLD
    if forward_return < -HOLD_LOSS_BAND:
        return "INCORRECT"
    return "CORRECT" if abs(forward_return) <= band else "NEUTRAL"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fetch_matured(conn, horizon: int, now: datetime) -> list[dict]:
    """Recommendations matured at this horizon and not yet graded for it.

    Each row carries two exit-price candidates: one from the sibling
    price_snapshots table and one from the in-repo price_checks table
    (daily granularity, so its window is computed on calendar dates).
    The caller prefers price_snapshots when both exist.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              r.id           AS recommendation_id,
              r.ticker_id,
              r.generated_at,
              r.action,
              r.confidence,
              CAST(JSON_EXTRACT(r.technical, '$.price') AS DECIMAL(18,6)) AS entry_price,
              (SELECT ps.price FROM price_snapshots ps
                 WHERE ps.ticker_id = r.ticker_id
                   AND ps.as_of_date >= r.generated_at + INTERVAL %s DAY
                   AND ps.as_of_date <  r.generated_at + INTERVAL %s DAY
                 ORDER BY ps.as_of_date ASC LIMIT 1)      AS exit_price,
              (SELECT ps.as_of_date FROM price_snapshots ps
                 WHERE ps.ticker_id = r.ticker_id
                   AND ps.as_of_date >= r.generated_at + INTERVAL %s DAY
                   AND ps.as_of_date <  r.generated_at + INTERVAL %s DAY
                 ORDER BY ps.as_of_date ASC LIMIT 1)      AS exit_as_of,
              (SELECT pc.price FROM price_checks pc
                 WHERE pc.ticker_id = r.ticker_id
                   AND pc.as_of_date >= DATE(r.generated_at) + INTERVAL %s DAY
                   AND pc.as_of_date <  DATE(r.generated_at) + INTERVAL %s DAY
                 ORDER BY pc.as_of_date ASC LIMIT 1)      AS check_exit_price,
              (SELECT pc.as_of_date FROM price_checks pc
                 WHERE pc.ticker_id = r.ticker_id
                   AND pc.as_of_date >= DATE(r.generated_at) + INTERVAL %s DAY
                   AND pc.as_of_date <  DATE(r.generated_at) + INTERVAL %s DAY
                 ORDER BY pc.as_of_date ASC LIMIT 1)      AS check_exit_as_of
            FROM recommendations r
            WHERE r.generated_at + INTERVAL %s DAY <= %s
              AND NOT EXISTS (
                SELECT 1 FROM recommendation_outcomes o
                WHERE o.recommendation_id = r.id AND o.horizon_days = %s
              )
            """,
            (
                horizon, horizon + EXIT_WINDOW_DAYS,
                horizon, horizon + EXIT_WINDOW_DAYS,
                horizon, horizon + EXIT_WINDOW_DAYS,
                horizon, horizon + EXIT_WINDOW_DAYS,
                horizon, now, horizon,
            ),
        )
        return cur.fetchall()


def _write_outcome(conn, row: dict, horizon: int, fwd: float, verdict: str, now: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO recommendation_outcomes
              (recommendation_id, ticker_id, generated_at, action, confidence,
               horizon_days, entry_price, exit_price, exit_as_of,
               forward_return, verdict, evaluated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              exit_price     = VALUES(exit_price),
              exit_as_of     = VALUES(exit_as_of),
              forward_return = VALUES(forward_return),
              verdict        = VALUES(verdict),
              evaluated_at   = VALUES(evaluated_at)
            """,
            (
                row["recommendation_id"], row["ticker_id"], row["generated_at"],
                row["action"], row["confidence"], horizon,
                row["entry_price"], row["exit_price"], row["exit_as_of"],
                round(fwd, 6), verdict, now,
            ),
        )


def main(dry_run: bool = False) -> None:
    logger.info(f"Evaluating recommendation outcomes (dry_run={dry_run})")
    cfg = load_config()
    now = _now()
    conn = get_connection(cfg)
    try:
        total = 0
        for horizon in HORIZONS:
            rows = _fetch_matured(conn, horizon, now)
            graded = 0
            for row in rows:
                if row["exit_price"] is None and row["check_exit_price"] is not None:
                    # price_snapshots has no row in the window — fall back to
                    # the in-repo price_checks observation.
                    row["exit_price"] = row["check_exit_price"]
                    row["exit_as_of"] = row["check_exit_as_of"]
                entry, exit_ = row["entry_price"], row["exit_price"]
                if entry is None or exit_ is None or entry == 0:
                    continue  # missing entry price or no matured price in either table
                fwd = float(exit_) / float(entry) - 1.0
                verdict = grade(row["action"], fwd)
                graded += 1
                if dry_run:
                    logger.info(
                        f"[dry-run] rec={row['recommendation_id']} {row['action']} "
                        f"h={horizon}d return={fwd:+.2%} -> {verdict}"
                    )
                else:
                    _write_outcome(conn, row, horizon, fwd, verdict, now)
            logger.info(f"Horizon {horizon}d: graded {graded} of {len(rows)} matured candidates")
            total += graded
        logger.info(f"Done. {total} outcomes {'evaluated' if dry_run else 'written'}.")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grade past recommendations against realized prices")
    parser.add_argument("--dry-run", action="store_true", help="Log only — don't write to DB")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
