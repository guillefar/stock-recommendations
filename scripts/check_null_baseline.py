#!/usr/bin/env python3
"""What the hit rate reads when the calls carry no skill.

Session 31. The headline hit rate has been on the scorecard since session 10 and
had never been compared against anything. Session 30's out-of-corpus backtest
found that skill-free calls score **63-67%** under this grading scheme, which put
the 68.8% headline inside noise of chance and the pre-re-grade 60.0% *below* it.
The cause is structural, not a bug: `HOLD` is CORRECT when the price stays flat
and `WATCH` is CORRECT when it moves, and those two actions carry ~89% of all
calls, so nearly any outcome lands on the good side of something.

This script pins that baseline so no hit rate is ever read bare again.

The null used here is a **permutation**: take the real corpus rows — real
tickers, real dates, real forward returns — and shuffle only the *actions*
between them, then re-grade. That destroys the association between the call and
what the price did, which is exactly what "skill" means, while preserving the
things that are not skill and would otherwise contaminate the comparison:

  * the action mix (51% WATCH / 38% HOLD is a property of how the system talks,
    not of whether it is right),
  * the distribution of realized returns,
  * the market regime over the corpus window,
  * the per-instrument bands, which travel with the row rather than the action.

That last point is why the permutation had to wait for session 30: before
per-instrument bands, shuffling an action onto a different instrument changed
the yardstick as well as the call, and the null would have measured both.

Two shuffles, because they answer different questions:

  global        actions shuffled across every row at a horizon. Excess over
                this null is total skill, *including* deciding which instruments
                to be decisive about.
  within-ticker actions shuffled only among rows of the same ticker. Excess over
                this null is timing skill alone — it holds instrument selection
                fixed, so a system that merely learned which tickers are calm
                scores zero against it.

Per-action nulls are reported too: HOLD and WATCH have wildly different chance
rates, and a single headline null hides that.

    python scripts/check_null_baseline.py
    python scripts/check_null_baseline.py --iterations 2000 --horizon 30

Read-only — like `check_run.py`, this never writes to the database.
"""
import argparse
import collections
import os
import random
import statistics as st
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
        "/home/guillo/Git/stock-recommendations/scripts/check_null_baseline.py"
    )

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from src.evaluate_outcomes import grade  # noqa: E402
from src.quote_types import apply_quote_type_overrides  # noqa: E402

# Enough that the null's own standard error (~0.2pp at these corpus sizes) is
# small against the effect being judged; still runs in seconds.
DEFAULT_ITERATIONS = 1000

# Fixed so the pinned number in the scorecard is reproducible. The spread across
# seeds is reported, so this is a convenience, not a thumb on the scale.
DEFAULT_SEED = 20260819


def hit_rate(verdicts: list[str]) -> float | None:
    """CORRECT as a share of decided calls. NEUTRAL is not a wrong answer.

    Matches the scorecard's definition — the whole point is to produce a number
    comparable to the one on the dashboard.
    """
    decided = [v for v in verdicts if v != "NEUTRAL"]
    return 100.0 * sum(v == "CORRECT" for v in decided) / len(decided) if decided else None


def fetch(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.horizon_days, o.action, o.forward_return, o.verdict,
                   o.generated_at, t.symbol, t.quote_type
            FROM recommendation_outcomes o
            JOIN tickers t ON t.id = o.ticker_id
            WHERE o.forward_return IS NOT NULL
        """)
        return apply_quote_type_overrides(cur.fetchall())


def permute(rows: list[dict], rng: random.Random,
            within_ticker: bool) -> list[tuple[str, str]]:
    """Re-grade the corpus with the actions shuffled between rows.

    Returns (shuffled action, resulting verdict) pairs, so a caller can bucket
    by the action a verdict was actually graded under.
    """
    if within_ticker:
        groups: dict[str, list[int]] = collections.defaultdict(list)
        for i, r in enumerate(rows):
            groups[r["symbol"]].append(i)
        actions = [r["action"] for r in rows]
        for idx in groups.values():
            pool = [actions[i] for i in idx]
            rng.shuffle(pool)
            for i, a in zip(idx, pool):
                actions[i] = a
    else:
        actions = [r["action"] for r in rows]
        rng.shuffle(actions)
    return [
        (a, grade(a, float(r["forward_return"]), r["horizon_days"],
                  r["quote_type"], r["symbol"]))
        for a, r in zip(actions, rows)
    ]


# Below this many decided calls the null's own spread swamps any excess, and
# the line is noise dressed as a finding (90d AVOID had n=1 and a null sd of 49).
MIN_DECIDED = 25

OVERLAP_CAVEAT = """\
* The `sd` figures are NOT a significance test, and the honest reading of this
  whole table depends on knowing why.

  Recommendations are generated Mon/Wed/Fri, so two consecutive 30d outcomes for
  one ticker share ~93% of their forward window. A permutation treats those rows
  as independent, so the null distribution comes out too narrow and every z is
  inflated — at 30d the ~2,400 rows carry closer to ~110 independent
  observations. Run --non-overlapping to see the corrected picture: it keeps
  only rows at least one horizon apart within each ticker, resamples, and pools.

  What survives every specification tried in session 31 (both shuffles,
  overlapping and not):

    WATCH  excess ~0.0pp everywhere. It is 51% of all calls and carries no
           information at all — the strongest and least ambiguous result here.
    overall excess <= 0 against the within-ticker null. The +2.7pp the headline
           shows against the global null is instrument selection, not timing.

  What does NOT survive: the per-action BUY/SELL/AVOID excesses. SELL reads
  +27pp against the global null and -7pp against the within-ticker one — the
  sign flips with the choice of null, which is session 30's lesson 2 recurring.
  Under non-overlapping sampling those slices rest on ~5-12 independent calls.
  Treat them as hypotheses, not findings."""


def summarize(name: str, samples: list[float], observed: float | None,
              n_decided: int | None = None) -> None:
    mean, sd = st.mean(samples), (st.stdev(samples) if len(samples) > 1 else 0.0)
    line = f"  {name:<20} null {mean:5.1f}%  (sd {sd:.2f})"
    if observed is not None:
        excess = observed - mean
        # Distance from the null in the null's own sd. Reported because the
        # sign and rough size are informative, but NOT as a significance test:
        # see OVERLAP_CAVEAT — the rows are not independent, so this is an
        # upper bound on confidence, not a p-value.
        z = excess / sd if sd else float("nan")
        line += (f"   observed {observed:5.1f}%  excess {excess:+6.1f}pp"
                 f"  ({z:+.1f} sd*)")
    if n_decided is not None:
        line += f"  n={n_decided}"
        if n_decided < MIN_DECIDED:
            line += "  [too thin to read]"
    print(line)


def nonoverlapping_report(hrows: list[dict], horizon: int, rng: random.Random,
                          draws: int) -> None:
    """Excess re-measured on rows that don't share a forward window.

    Each draw keeps, per ticker, a chain of rows at least `horizon` days apart
    starting from a random offset — so the kept rows have disjoint return
    windows and are genuinely independent. Counts are **pooled** across draws
    rather than averaging each draw's rate: a per-action slice holds only a
    handful of rows per draw, and averaging ratios that coarse is biased.
    """
    by_sym: dict[str, list[dict]] = collections.defaultdict(list)
    for r in hrows:
        by_sym[r["symbol"]].append(r)
    for v in by_sym.values():
        v.sort(key=lambda r: r["generated_at"])

    obs: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    nul: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])

    def acc(d, action, verdict):
        if verdict == "CORRECT":
            d[action][0] += 1
        elif verdict == "INCORRECT":
            d[action][1] += 1

    kept_total = 0
    for _ in range(draws):
        for sym, v in by_sym.items():
            start = rng.randrange(len(v))
            chain, last = [], None
            for r in sorted(v[start:] + v[:start],
                            key=lambda r: r["generated_at"]):
                if last is None or (r["generated_at"] - last).days >= horizon:
                    chain.append(r)
                    last = r["generated_at"]
            kept_total += len(chain)
            for r in chain:
                acc(obs, r["action"], r["verdict"])
                acc(obs, "overall", r["verdict"])
            # within-ticker null on the same independent chain
            acts = [r["action"] for r in chain]
            rng.shuffle(acts)
            for a, r in zip(acts, chain):
                g = grade(a, float(r["forward_return"]), horizon,
                          r["quote_type"], r["symbol"])
                acc(nul, a, g)
                acc(nul, "overall", g)

    def rate(pair):
        c, i = pair
        return 100.0 * c / (c + i) if c + i else None

    print(f"  -- non-overlapping ({draws} draws, ~{kept_total / draws:.0f} "
          f"independent rows each) --")
    for a in sorted(obs, key=lambda x: (x != "overall", -sum(obs[x]))):
        o, n = rate(obs[a]), rate(nul[a])
        if o is None or n is None:
            continue
        per_draw = sum(obs[a]) / draws
        line = (f"    {a:<18} null {n:5.1f}%   observed {o:5.1f}%  "
                f"excess {o - n:+6.1f}pp   ~{per_draw:.0f} independent/draw")
        if per_draw < 15 and a != "overall":
            line += "  [hypothesis only]"
        print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS,
                    help=f"permutations per null (default {DEFAULT_ITERATIONS})")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help=f"RNG seed (default {DEFAULT_SEED})")
    ap.add_argument("--horizon", type=int, action="append",
                    help="restrict to a horizon (repeatable; default all)")
    ap.add_argument("--non-overlapping", action="store_true",
                    help="also re-measure on rows with disjoint return windows "
                         "(the honest correction for overlap — see the footer)")
    args = ap.parse_args()

    conn = pymysql.connect(
        host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
        user=os.environ['DB_USER'], password=os.environ['DB_PASS'],
        db=os.environ['DB_NAME'], cursorclass=pymysql.cursors.DictCursor,
        init_command="SET collation_connection = utf8mb4_unicode_ci",
    )
    try:
        rows = fetch(conn)
    finally:
        conn.close()

    by_h: dict[int, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_h[r["horizon_days"]].append(r)
    horizons = sorted(args.horizon) if args.horizon else sorted(by_h)

    print(f"Null baseline for the hit rate — {args.iterations} permutations, "
          f"seed {args.seed}.")
    print("A hit rate is only readable against this. See the module docstring.\n")

    for h in horizons:
        hrows = by_h.get(h, [])
        if not hrows:
            print(f"{h}d: no graded rows.\n")
            continue
        observed = hit_rate([r["verdict"] for r in hrows])
        print(f"{h}d  ({len(hrows)} rows, {len({r['symbol'] for r in hrows})} tickers)")

        decided_all = sum(r["verdict"] != "NEUTRAL" for r in hrows)
        for label, within in (("global", False), ("within-ticker", True)):
            rng = random.Random(args.seed)
            overall = [hit_rate([v for _, v in permute(hrows, rng, within)]) or 0.0
                       for _ in range(args.iterations)]
            summarize(label, overall, observed, decided_all)

        # Per-action nulls, under both shuffles. The global one asks what an
        # action scores landing on an unrelated outcome; the within-ticker one
        # additionally holds instrument selection fixed, so it separates "the
        # system SELLs the right names" from "it SELLs at the right moments".
        obs_by_action: dict[str, list[str]] = collections.defaultdict(list)
        for r in hrows:
            obs_by_action[r["action"]].append(r["verdict"])

        for label, within in (("global", False), ("within-ticker", True)):
            rng = random.Random(args.seed)
            per_action: dict[str, list[float]] = collections.defaultdict(list)
            for _ in range(args.iterations):
                bucket: dict[str, list[str]] = collections.defaultdict(list)
                for a, v in permute(hrows, rng, within):
                    bucket[a].append(v)
                for a, vs in bucket.items():
                    hr = hit_rate(vs)
                    if hr is not None:
                        per_action[a].append(hr)
            print(f"  -- per action, {label} shuffle --")
            for a in sorted(per_action, key=lambda x: -len(obs_by_action[x])):
                decided = sum(v != "NEUTRAL" for v in obs_by_action[a])
                summarize(f"  {a}", per_action[a], hit_rate(obs_by_action[a]),
                          decided)

        if args.non_overlapping:
            nonoverlapping_report(hrows, h, random.Random(args.seed),
                                  max(50, args.iterations // 4))
        print()

    print("Reading this: excess is the number that means something. A hit rate")
    print("at or below its null is decoration — under this scheme HOLD scores")
    print("well by standing still and WATCH by anything moving, so ~65% is what")
    print("dice return. Never quote a hit rate without the excess beside it.")
    print()
    print(OVERLAP_CAVEAT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
