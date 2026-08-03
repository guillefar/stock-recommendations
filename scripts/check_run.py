#!/usr/bin/env python3
"""Post-run health check — run after Wed 08-05 and Fri 08-07.

Answers the three session-27 questions in one shot:
  1. Did BUY collapse under the corrected injected pattern set? (id=5 tells
     every prompt "BUY es un lastre: fracaso total" + "SELL genera perfección")
  2. Did Friday's pattern mining actually persist a new row? (max_tokens 3072→8192)
  3. Was the run healthy? (run_metrics: 63 ok, ~$0.11-0.14)

Baselines (both pre-correction — the 08-03 production run fired at 12:46 UTC,
before prediction_patterns id=5 was written at 14:14 UTC, so it still injected
the OLD artifact set id=3):
    07-31  BUY=7   SELL=3   AVOID=5   HOLD=26  WATCH=22
    08-03  BUY=6   SELL=1   AVOID=6   HOLD=28  WATCH=22
"""
import os
import pymysql
from dotenv import load_dotenv

load_dotenv('/home/guillo/Git/stock-recommendations/.env')
conn = pymysql.connect(
    host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
    user=os.environ['DB_USER'], password=os.environ['DB_PASS'],
    db=os.environ['DB_NAME'], cursorclass=pymysql.cursors.DictCursor,
    init_command="SET collation_connection = utf8mb4_unicode_ci",
)
cur = conn.cursor()

BASELINE = {'2026-07-31': 7, '2026-08-03': 6}
ACTIONS = ['BUY', 'WATCH', 'HOLD', 'SELL', 'AVOID']

print("=" * 72)
print("1. ACTION MIX  —  is BUY being suppressed?")
print("=" * 72)
cur.execute("""
    SELECT DATE(generated_at) d, action, COUNT(*) n
    FROM recommendations WHERE generated_at >= '2026-07-29'
    GROUP BY d, action ORDER BY d
""")
days = {}
for r in cur.fetchall():
    days.setdefault(str(r['d']), {})[r['action']] = r['n']

print(f"{'date':12s} {'total':>5s} " + " ".join(f"{a:>6s}" for a in ACTIONS)
      + f" {'DECIS':>6s}   verdict")
for d in sorted(days):
    row = days[d]
    tot = sum(row.values())
    buys = row.get('BUY', 0)
    # Decisive calls = BUY + SELL. This is the sharper signal: the 08-03
    # dry-run showed the corrected set pushes calls out of BOTH directional
    # buckets into the HOLD/WATCH middle, not from BUY toward SELL.
    decisive = row.get('BUY', 0) + row.get('SELL', 0)
    if d in BASELINE:
        verdict = "(pre-correction baseline)"
    elif decisive <= 4:
        verdict = f"*** DECISIVENESS COLLAPSED ({decisive} vs 7-17 range) — caveat failed ***"
    elif decisive <= 6:
        verdict = f"*** SUPPRESSED: {decisive} decisive vs 7-17 historical range ***"
    elif buys <= 3:
        verdict = f"warning: BUY={buys}, below the 4-10 historical range"
    else:
        verdict = f"ok — BUY={buys}, decisive={decisive}"
    print(f"{d:12s} {tot:5d} " + " ".join(f"{row.get(a, 0):6d}" for a in ACTIONS)
          + f" {decisive:6d}   {verdict}")

print()
print("Historical production range (artifact set injected): BUY 4-10, SELL 1-7,")
print("decisive (BUY+SELL) 7-17.  The 2026-08-03 dry-run — the FIRST injection of")
print("the corrected id=5 set — produced BUY=3 SELL=0 decisive=3, below every")
print("observed minimum.  If Wed/Fri confirm this, the market-regime caveat in")
print("_patterns_block is too weak and the market-relative slice is URGENT.")

print()
print("=" * 72)
print("2. PATTERN MINING  —  did Friday's mining persist? (max_tokens fix)")
print("=" * 72)
cur.execute("""
    SELECT id, generated_at, JSON_LENGTH(patterns) np
    FROM prediction_patterns ORDER BY id
""")
rows = cur.fetchall()
for r in rows:
    print(f"  id={r['id']:<3d} {r['generated_at']}  patterns={r['np']}")
newest = rows[-1]
print()
if str(newest['generated_at'])[:10] >= '2026-08-07':
    print(f"  OK — Friday 08-07 mining persisted (id={newest['id']}, "
          f"{newest['np']} patterns). max_tokens fix verified in production.")
else:
    print(f"  Newest set is still id={newest['id']} from {str(newest['generated_at'])[:10]}.")
    print("  After Fri 08-07 there MUST be a newer row. If not, mining failed again —")
    print("  check the workflow log for 'Structured response truncated' / "
          "'No prediction patterns persisted'.")

print()
print("=" * 72)
print("3. RUN HEALTH  —  run_metrics")
print("=" * 72)
cur.execute("""
    SELECT id, run_at, calls, estimated_cost_usd c, tickers_ok ok, tickers_failed f
    FROM run_metrics ORDER BY id DESC LIMIT 6
""")
for r in cur.fetchall():
    flag = "" if r['ok'] == 63 else "   <-- NOT 63 OK"
    partial = "  (PARTIAL HARVEST — batch resilience fired!)" if 0 < r['ok'] < 63 else ""
    print(f"  id={r['id']:<3d} {r['run_at']}  calls={r['calls']:<3d} "
          f"${r['c']}  ok={r['ok']:<3d} failed={r['f']}{flag}{partial}")

conn.close()
