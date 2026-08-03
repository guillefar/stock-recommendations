#!/usr/bin/env python3
"""Re-derive ASSET_CLASS_BAND_SCALE from live outcomes. Run quarterly.

Session 26 set `ASSET_CLASS_BAND_SCALE = {"ETF": 0.30}` in
src/evaluate_outcomes.py — the measured ratio of ETF to stock mean absolute
forward return, which was stable across horizons (0.317 at 7d, 0.292 at 30d).
It is an empirical volatility ratio measured in one regime, not a tuning knob:
a volatility-compressed or -expanded market moves it.

This prints the current ratio so the check is a 10-second habit rather than a
research project. If it has drifted materially from 0.30, the fix is a code
change to the constant plus a full `--regrade` with user sign-off — never a
call-site override, and never one without the other (mixed semantics in the
corpus is exactly the bug session 26 spent a session undoing).

    python scripts/check_bands.py
"""
import os
import sys

import pymysql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), os.pardir, '.env'))

if 'DB_HOST' not in os.environ:
    # Per-session worktrees carry no .env (it is untracked, by design).
    sys.exit(
        "No DB_* environment found. This script reads ../.env relative to\n"
        "itself, so run it from the main checkout:\n"
        "  /home/guillo/Git/stock-recommendations/.venv/bin/python "
        "/home/guillo/Git/stock-recommendations/scripts/check_bands.py"
    )

PINNED = 0.30
# Drift beyond this is worth acting on; inside it, the noise is larger than
# the correction would be.
TOLERANCE = 0.08

conn = pymysql.connect(
    host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
    user=os.environ['DB_USER'], password=os.environ['DB_PASS'],
    db=os.environ['DB_NAME'], cursorclass=pymysql.cursors.DictCursor,
    init_command="SET collation_connection = utf8mb4_unicode_ci",
)
cur = conn.cursor()

cur.execute("""
    SELECT o.horizon_days h,
           CASE WHEN t.quote_type = 'ETF' THEN 'ETF' ELSE 'STOCK' END cls,
           AVG(ABS(o.forward_return)) mean_abs,
           COUNT(*) n
    FROM recommendation_outcomes o
    JOIN tickers t ON t.id = o.ticker_id
    WHERE o.forward_return IS NOT NULL
    GROUP BY h, cls
    ORDER BY h
""")

by_h = {}
for r in cur.fetchall():
    by_h.setdefault(r['h'], {})[r['cls']] = (float(r['mean_abs']), r['n'])

print(f"ETF / STOCK mean absolute forward return   (pinned constant: {PINNED})")
print(f"{'horizon':>8s} {'ETF':>9s} {'STOCK':>9s} {'ratio':>8s}   samples")
ratios = []
for h in sorted(by_h):
    row = by_h[h]
    if 'ETF' not in row or 'STOCK' not in row:
        continue
    etf, n_etf = row['ETF']
    stock, n_stock = row['STOCK']
    if not stock:
        continue
    ratio = etf / stock
    ratios.append(ratio)
    print(f"{h:>7d}d {etf:>8.2%} {stock:>8.2%} {ratio:>8.3f}   "
          f"ETF n={n_etf}, STOCK n={n_stock}")

if not ratios:
    print("\nNo horizon has both classes graded yet — nothing to check.")
    raise SystemExit(0)

mean_ratio = sum(ratios) / len(ratios)
drift = abs(mean_ratio - PINNED)
print(f"\nmean ratio across horizons: {mean_ratio:.3f}  (pinned {PINNED}, "
      f"drift {drift:+.3f})")
if drift > TOLERANCE:
    print(f"\n*** DRIFTED beyond ±{TOLERANCE} ***")
    print("    Update ASSET_CLASS_BAND_SCALE in src/evaluate_outcomes.py, update")
    print("    the test pinning it, then re-grade WITH USER SIGN-OFF:")
    print("      python -m src.evaluate_outcomes --regrade --dry-run   # inspect first")
    print("      python -m src.evaluate_outcomes --regrade")
else:
    print(f"OK — within ±{TOLERANCE} of the pinned constant. No action needed.")

conn.close()
