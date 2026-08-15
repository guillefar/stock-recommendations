#!/usr/bin/env python3
"""Post-run health check.

Runs as the last step of the production workflow (session 29) and also by hand.
In CI it appends its output to the job summary, so the diagnosis is readable
from a phone on the run's own GitHub page and archived with the run — the point
being that nobody has to be at a particular computer on a particular weekday for
the evidence to survive. Everything here is a read; it never writes.

Three questions:

  1. **Decisiveness.** Is the system still making actionable calls? This is the
     one that matters. Sessions 26–28 each fixed what the feedback loop learned
     from and each time it found a new way to hurt the output; session 29
     measured the output and switched injection off (PATTERN_INJECTION_ENABLED).
     The open question now is whether decisive calls recover with the loop off.
  2. **Mining.** Did Friday's run persist a pattern set, and does it carry the
     session-28 schema fields? Mining still runs with injection off.
  3. **Run health.** 63 ok, cost in range, and whether a long batch ever logged
     a *partial* tickers_ok (batch resilience, merged in s26, still unexercised).

Historical decisive (BUY+SELL) range with the artifact set injected: 7–17.
Injection of the *corrected* sets (id=5 from 08-05, id=6 from 08-10) produced
1, 3, 2, 2 across four consecutive runs — while the median active ticker rose
5.69% over that fortnight. The first run with nothing injected (08-14) returned
to 9. That is why the loop is off.
"""
import os
import sys

import pymysql
from dotenv import load_dotenv

# A local checkout keeps credentials in .env; CI passes them as secrets. Load
# the file when it exists and let the environment win either way.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

_out = []


def say(line=""):
    """Print to stdout and collect for the GitHub job summary."""
    print(line)
    _out.append(line)


try:
    conn = pymysql.connect(
        host=os.environ["DB_HOST"], port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ["DB_USER"], password=os.environ["DB_PASS"],
        db=os.environ["DB_NAME"], cursorclass=pymysql.cursors.DictCursor,
        init_command="SET collation_connection = utf8mb4_unicode_ci",
    )
except KeyError as exc:
    sys.exit(f"check_run: missing database setting {exc}")
cur = conn.cursor()

ACTIONS = ["BUY", "WATCH", "HOLD", "SELL", "AVOID"]
# Runs that injected a pattern set, for reading the decisiveness column against
# the right control. id=3 is the session-26 artifact set; id=5/6 are the
# corrected sets whose injection collapsed decisiveness; from 08-14 the loop is
# off, so anything later is the clean no-injection comparison.
INJECTED = {
    "2026-07-29": "id=3 artifact", "2026-07-31": "id=3 artifact",
    "2026-08-03": "id=3 artifact", "2026-08-05": "id=5 corrected",
    "2026-08-07": "id=5 corrected", "2026-08-10": "id=6 corrected",
    "2026-08-12": "id=6 corrected",
    # 08-14 is the control: session 28 merged on 08-12, so the excess gate met a
    # stored set with no schema fields and failed closed. Decisive went 2 -> 9.
    "2026-08-14": "NONE (control)",
}

say("=" * 78)
say("1. DECISIVENESS  —  is the system still making actionable calls?")
say("=" * 78)
cur.execute("""
    SELECT DATE(generated_at) d, action, COUNT(*) n
    FROM recommendations WHERE generated_at >= '2026-07-29'
    GROUP BY d, action ORDER BY d
""")
days = {}
for r in cur.fetchall():
    days.setdefault(str(r["d"]), {})[r["action"]] = r["n"]

say(f"{'date':12s} {'tot':>4s} " + " ".join(f"{a:>6s}" for a in ACTIONS)
    + f" {'DECIS':>6s}  {'injected':14s} verdict")
for d in sorted(days):
    row = days[d]
    # Decisive = BUY + SELL. The sharper signal: prompt pressure does not flip
    # BUY into SELL, it drains both directional buckets into the HOLD/WATCH
    # middle. Counting BUY alone misses half the effect.
    decisive = row.get("BUY", 0) + row.get("SELL", 0)
    injected = INJECTED.get(d, "none (off)")
    if decisive <= 4:
        verdict = f"*** COLLAPSED ({decisive} vs 7-17) ***"
    elif decisive <= 6:
        verdict = f"*** low: {decisive} vs 7-17 ***"
    else:
        verdict = f"ok — decisive={decisive}"
    say(f"{d:12s} {sum(row.values()):4d} "
        + " ".join(f"{row.get(a, 0):6d}" for a in ACTIONS)
        + f" {decisive:6d}  {injected:14s} {verdict}")

say()
say("Read the DECIS column against the 'injected' column, not against the last")
say("run. Historical range with a set injected: BUY 4-10, SELL 1-7, decisive")
say("7-17. The four runs from 08-05 to 08-12 injected the corrected sets and")
say("produced 1/3/2/2 while the median ticker rose 5.69% — the loop talked the")
say("model out of committing. With injection off, decisive returning to >= 7 is")
say("the confirmation; staying <= 6 means something else is suppressing it and")
say("the loop was wrongly blamed.")

say()
say("=" * 78)
say("2. PATTERN MINING  —  Friday's set, and does it carry the s28 fields?")
say("=" * 78)
cur.execute("""
    SELECT id, generated_at, JSON_LENGTH(patterns) np,
           JSON_CONTAINS_PATH(patterns, 'one', '$[0].excess_return_pp') has_excess,
           JSON_CONTAINS_PATH(patterns, 'one', '$[0].primary_action') has_action
    FROM prediction_patterns ORDER BY id
""")
rows = cur.fetchall()
for r in rows:
    fields = "s28 fields: yes" if (r["has_excess"] and r["has_action"]) else "s28 fields: NO"
    say(f"  id={r['id']:<3d} {r['generated_at']}  patterns={r['np']}  {fields}")
newest = rows[-1]
say()
if not (newest["has_excess"] and newest["has_action"]):
    say(f"  Newest set (id={newest['id']}) predates the session-28 schema. It would")
    say("  fail the excess gate closed if injection were re-enabled — expected for")
    say("  any set mined before the s28 merge (2026-08-12).")
else:
    say(f"  Newest set (id={newest['id']}) carries excess_return_pp + primary_action.")
say("  Mining runs every Friday regardless of whether injection is enabled.")

say()
say("=" * 78)
say("3. RUN HEALTH  —  run_metrics")
say("=" * 78)
cur.execute("""
    SELECT id, run_at, calls, estimated_cost_usd c, tickers_ok ok, tickers_failed f
    FROM run_metrics ORDER BY id DESC LIMIT 6
""")
for r in cur.fetchall():
    flag = "" if r["ok"] == 63 else "   <-- NOT 63 OK"
    partial = "  (PARTIAL HARVEST — batch resilience fired!)" if 0 < r["ok"] < 63 else ""
    say(f"  id={r['id']:<3d} {r['run_at']}  calls={r['calls']:<3d} "
        f"${r['c']}  ok={r['ok']:<3d} failed={r['f']}{flag}{partial}")

conn.close()

# In CI, repeat the whole thing into the run's summary page. Wrapped in a code
# fence so the column alignment survives markdown rendering.
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write("## Post-run health check\n\n```\n" + "\n".join(_out) + "\n```\n")
