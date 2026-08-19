#!/usr/bin/env python3
"""Re-derive INSTRUMENT_BAND_SCALE (src/instrument_vol.py) from price history.

Session 30. Session 26 scaled the grading bands by asset class; session 30
measured that the class is far too coarse a unit. Within the 63 active tickers
the implied scale spans 0.087–0.766 among ETFs alone (8.8x) against a single
constant of 0.30, and the classes overlap heavily — SEME.PA (ETF) moves further
than 25 of the equities. Grading a thematic solar ETF and VUSA.AS on the same
bands measures the instrument, not the call, which is the artifact session 26
set out to remove.

The scale is each instrument's mean absolute 30-day move relative to the median
equity's, so a scale of 1.0 keeps HORIZON_BANDS meaning exactly what they meant
(they were calibrated to a typical stock) and the median equity lands on 1.0 by
construction.

**The estimation window must end before the corpus it grades.** Bands fitted to
the very returns they score flatten hit rates by construction and peek at the
future, so this defaults to the 12 months ending the day before the earliest
recommendation. Validated at that window: the historical estimate ranks the
instruments against their observed volatility at Spearman 0.90 / Pearson 0.84,
with 84% inside 2x — far tighter than the ~9x spread the class constant imposes.

    python scripts/derive_instrument_scales.py
    python scripts/derive_instrument_scales.py --end 2026-05-16 --months 12

Prints a paste-ready dict. Changing a scale changes stored verdicts, so it
needs a `--regrade` with the user's sign-off — same rule as the class constant
and src/quote_types.py.
"""
import argparse
import os
import statistics as st
import sys
from datetime import date, timedelta

import pymysql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, '.env'))

if 'DB_HOST' not in os.environ:
    # Per-session worktrees carry no .env (it is untracked, by design).
    sys.exit(
        "No DB_* environment found. This script reads ../.env relative to\n"
        "itself, so run it from the main checkout:\n"
        "  /home/guillo/Git/stock-recommendations/.venv/bin/python "
        "/home/guillo/Git/stock-recommendations/scripts/derive_instrument_scales.py"
    )

# The day before the earliest recommendation (2026-05-17). Estimating from
# later data would fit the bands to the returns they grade.
DEFAULT_END = "2026-05-16"

# ~21 trading days ≈ 30 calendar days, matching the 30d grading horizon the
# base bands are calibrated on.
TRADING_DAYS_30D = 21

# Below this many closes the estimate is noise; the instrument falls back to
# its asset-class scale.
MIN_CLOSES = 150


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--end", default=DEFAULT_END,
                    help=f"estimation window end, exclusive (default {DEFAULT_END})")
    ap.add_argument("--months", type=int, default=12,
                    help="window length in months (default 12)")
    args = ap.parse_args()

    end = date.fromisoformat(args.end)
    start = end - timedelta(days=int(args.months * 30.44))

    conn = pymysql.connect(
        host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
        user=os.environ['DB_USER'], password=os.environ['DB_PASS'],
        db=os.environ['DB_NAME'], cursorclass=pymysql.cursors.DictCursor,
        init_command="SET collation_connection = utf8mb4_unicode_ci",
    )
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT t.symbol, t.quote_type
            FROM recommendations r JOIN tickers t ON t.id = r.ticker_id
            ORDER BY t.symbol
        """)
        rows = cur.fetchall()
    conn.close()

    # Correct the two untyped ETFs before they anchor anything (session 28).
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
    from src.quote_types import resolve_quote_type

    universe = {r['symbol']: resolve_quote_type(r['symbol'], r['quote_type'])
                for r in rows}

    import yfinance as yf
    print(f"Estimating from {start} to {end} ({len(universe)} tickers) ...",
          file=sys.stderr)
    closes = yf.download(sorted(universe), start=str(start), end=str(end),
                         progress=False, auto_adjust=True, threads=True)["Close"]

    moves: dict[str, float] = {}
    thin: list[str] = []
    for sym in sorted(universe):
        if sym not in closes.columns:
            thin.append(sym)
            continue
        s = closes[sym].dropna()
        if len(s) < MIN_CLOSES:
            thin.append(sym)
            continue
        fwd = (s.shift(-TRADING_DAYS_30D) / s - 1).dropna().abs()
        if fwd.empty:
            thin.append(sym)
            continue
        moves[sym] = float(fwd.mean())

    equities = [m for sym, m in moves.items() if universe[sym] == "EQUITY"]
    if not equities:
        sys.exit("No equity history — cannot anchor the scale.")
    baseline = st.median(equities)

    print(f"\n# Estimation window {start} -> {end} (exclusive), "
          f"{TRADING_DAYS_30D} trading days ahead.")
    print(f"# Baseline = median equity mean |30d move| = {baseline:.4%} "
          f"(n={len(equities)} equities).")
    print("INSTRUMENT_BAND_SCALE = {")
    for sym in sorted(moves, key=lambda s: moves[s]):
        scale = moves[sym] / baseline
        print(f'    "{sym}": {scale:.2f},'.ljust(30)
              + f"  # {universe[sym] or '(untyped)':<8} mean |30d| {moves[sym]:.2%}")
    print("}")

    if thin:
        print(f"\n# No usable history (< {MIN_CLOSES} closes) — these fall back to")
        print(f"# their asset-class scale: {', '.join(thin)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
