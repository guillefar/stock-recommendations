# Handoff 31 — 2026-08-19 (session 31: the scoreboard got a baseline, and the score went negative)

Continues [HANDOFF_30.md](HANDOFF_30.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 31 did

On branch **`feat/session-31-null-baseline`** (off `main` @ `d12a0cd`), worktree: none — the work was done in the main checkout and branched before commit. Pushed, **not merged**. **No pipeline code, no migrations, no data change beyond the approved repair re-grade.**

### 0. The prompt agreed with the repo

`main` @ `06af2d9`, session 30 pushed and not merged, exactly as the prompt said. Tally: s19–s21 drifted, s22–s25 clean, s26 drifted twice, **s27–s31 clean**. Keep checking.

One wrinkle: **`handoffs/HANDOFF_30.md` existed only on the unmerged branch**, so the file the prompt named was not in the main checkout. Read it with `git show origin/feat/session-30-instrument-bands:handoffs/HANDOFF_30.md`. If a handoff seems missing, check the branch before concluding the prompt is wrong.

The session opened Wednesday evening ~19:30 UTC, two days after session 30 and **after** the 10:00 UTC production run — which is what made the damage measurable rather than hypothetical.

### 1. The merge, and the damage that was smaller than predicted

HANDOFF_30 warned that `main`'s grader would undo the re-grade "piecemeal at ~3 rows/week per affected ticker". **That mechanism was wrong, and checking it before acting on it mattered.**

`_fetch_matured` without `--regrade` carries a `NOT EXISTS` filter on already-graded rows. So the 5,244 re-graded rows were **never at risk** — nothing overwrites them. What actually happened is narrower and different in kind: the 08-19 run graded **63 newly matured 90d rows** on class bands, of which **15 disagreed** with per-instrument bands. All 15 were confirmed to equal exactly what class-band grading produces, which is what identifies the cause rather than assuming it.

The result is a **mixed-semantics corpus** — the bug session 26 spent a session undoing — not an unwinding one. Merged (`d12a0cd`, 172 tests green), then re-graded 5,496 rows with sign-off, then **verified by reading back: 0 mismatches**.

Note the re-grade also wrote **189 newly matured rows** (63 each at 7d/30d/90d) that the 10:00 run had not yet picked up, because their exit-price snapshots land after `evaluate_outcomes` runs in the pipeline order. That is a one-run lag, not a fault, but it means a `--regrade` always writes more rows than the drift count.

### 2. The decisiveness series holds

| date | BUY | SELL | decisive | AVOID | WATCH | cost | injected |
|---|---|---|---|---|---|---|---|
| 2026-08-12 | 2 | 0 | **2** | 4 | 28 | $0.1386 | id=6 |
| 2026-08-14 | 6 | 3 | **9** | 4 | 24 | $0.1353 | none (gate failed closed) |
| 2026-08-17 | 9 | 3 | **12** | 2 | 23 | $0.0966 | none (switch) |
| **2026-08-19** | **4** | **3** | **7** | 2 | 28 | **$0.1020** | **none (switch)** |

Three runs above the collapse, all inside the 7–17 historical range, against 1–3 with the corrected sets injected. AVOID steady at 2–4 throughout. Cost holds ~30% below the injection era. **This question is closed**; keep it on the CI summary rather than re-deriving it by hand.

### 3. The slice: excess over null, and what it exposed

The user chose option (b) — make the scorecard's headline **excess over null** rather than raw hit rate.

**The null is a permutation, not a simulation.** Session 30 generated synthetic skill-free calls over an out-of-corpus year; this shuffles the actions *between real corpus rows* and re-grades. That holds the action mix, the realized returns, the market regime and the per-instrument bands fixed and varies only the association between a call and its outcome — which is the definition of skill. It reproduces session 30's number independently at **65.8%** (30d), 66.5% (7d), 76.1% (90d). Two independent methods agreeing is why the number is safe to pin.

Two shuffles, because they answer different questions:

| shuffle | what it holds fixed | 30d null | observed | excess |
|---|---|---|---|---|
| **global** | action mix only | 65.8% | 68.5% | **+2.7pp** |
| **within-ticker** | + which instrument gets which action | 70.8% | 68.5% | **−2.3pp** |

So the 68.5% decomposes as: **65.8 chance + 5.0pp instrument pairing − 2.3pp timing.** The system's measurable edge is that it puts HOLD on calm instruments and WATCH on movers. That is real, but it is roughly the same information `INSTRUMENT_BAND_SCALE` already encodes — it is not a stock-picking edge, and once you control for it the timing is negative.

**The cleanest result: `WATCH` excess is ~0.0pp under every specification tried** (+0.9 / +0.2 / +0.2 / +0.3), while being **51% of all calls**. Half of everything the system emits carries no information.

### 4. The finding that died, and why that is the important part

Against the global null, `SELL` scored **+27.0pp (+5.1 sd)** and read as the one genuinely skilful action — a headline finding. Against the within-ticker null the identical calls scored **−7.3pp**. **The sign flips with the choice of null.** The system sold names that were falling over the whole window; shuffling *when* it sold them within those same names scores better than what it actually did.

That is session 30's lesson 2 recurring — inside one session, on a statistic built specifically to apply it.

Then the same scrutiny was turned on the new tool. Recommendations are Mon/Wed/Fri and the horizon is 30 days, so consecutive rows for a ticker share **~93% of their forward window**. The ~2,400 rows at 30d carry closer to **~110 independent observations**; a permutation treating them as independent produces a null that is too narrow and inflates every z. The script now ships `--non-overlapping` (keep rows a full horizon apart, resample, and **pool counts rather than average per-draw rates** — averaging ratios is biased when a slice holds ~5 rows), labels the column `sd*`, and its own footer states which numbers survive and which do not.

`BUY` is negative under all three nulls — **−17.7 / −20.2 / −33.6pp** — and is the only per-action sign that never moves. It is recorded as a **hypothesis for session 32, not a finding**, because under non-overlapping sampling it rests on ~12 independent calls.

## Learnings

The arc: s26 — a loop amplifies bad data. s27 — fixing the data doesn't fix the loop. s28 — a fix keyed on a field inherits that field's gaps. s29 — three rounds of accuracy work didn't help; switching it off measured it in one run. s30 — the yardstick everything was measured against had never been checked against chance. **s31 — the tool built to stop numbers being over-read produced an over-read number of its own within the hour.**

1. **When you build an instrument for auditing statistics, audit the instrument first and hardest.** The permutation harness was written to enforce "compute what your statistic reads if the finding is false", and its own first output — SELL at +5.1 sd — was exactly the kind of number it exists to catch. Two further passes were needed (a second null, then an overlap correction) before anything was reportable. **The tool does not inherit the discipline of its purpose.**
2. **Verify the predicted failure mechanism before acting on it, even when the prediction is your own from two days ago.** HANDOFF_30 predicted the re-grade would unwind piecemeal. Measuring first showed the re-graded rows were structurally untouchable and the real exposure was a different, smaller, differently-shaped problem. The remedy happened to be the same, but the count reported to the user, the urgency and the invariant all changed. **A confident mechanism in a handoff is a hypothesis, not a finding — the handoff's author could not run the query.**
3. **A null is a modelling choice, and the choice can carry the whole conclusion.** Global vs within-ticker are both defensible, and they disagree about SELL by 34pp. Neither is "correct" — they answer *does this system have any edge* and *does it have timing edge* respectively. **Report both, name what each holds fixed, and never let a single unlabelled "null" stand in for the concept.**
4. **Independence is the assumption most likely to be silently false in a time series, and permutation tests hide it well.** The permutation is exact under exchangeability, which makes it feel assumption-free; the rows are not exchangeable, and nothing in the output says so. **Before reading a z, ask how many independent observations the corpus actually holds** — here it was 4% of the row count.
5. **Pool counts; do not average ratios.** The first non-overlapping pass averaged each draw's hit rate and produced numbers that were wrong in a direction that flattered the finding. With ~5 rows per action per draw the per-draw rate takes values in {0, 20, 40…}, and averaging those is not the pooled rate.
6. **The metric that is 51% of your output deserves the same scrutiny as the metric that is 4%.** Everyone (five sessions running) has argued about BUY and SELL, which are 8% of calls. `WATCH` is 51%, and its excess is zero under every test. **Scrutiny has been going to the interesting slices rather than the large ones.**
7. **Two independent methods agreeing is worth more than one method with a tight interval.** The permutation null (65.8%) and session 30's out-of-corpus synthetic backtest (63–67%) share no code, no data window and no generative assumption. That agreement is what makes the pinned constant safe to hard-code into a dashboard.
8. **Elapsed time is still a feature — and so is elapsed time of the right size.** Opening *after* the 08-19 run rather than before it turned "the grader may corrupt rows" into "15 rows, here they are". A session opening Tuesday would have had to reason about it.

## Validation evidence

- **pytest: 179 passed** (172 + 7, always `-p no:cacheprovider`). New: the hit-rate definition matches the scorecard's (NEUTRAL excluded); both shuffles preserve the action multiset; the within-ticker shuffle keeps every action on its own ticker and the global shuffle demonstrably does not; **bands resolve from the row's own symbol, pinned by grading one 2% return as CORRECT on `VUSA.AS`, NEUTRAL on `AAPL` and INCORRECT on `IREN`**; determinism for a fixed seed; and a single-row ticker as a fixed point under the within-ticker shuffle.
- **The merge**: `feat/session-30-instrument-bands` → `main` @ `d12a0cd` (`--no-ff`), 172 tests green beforehand, pushed.
- **The repair re-grade**: drift measured first (15 rows, all matching class-band output exactly), then `--dry-run --regrade` clean at 5,496, then written with sign-off, then **verified by re-running the drift measurement — 0 mismatches**, corpus uniformly on per-instrument bands.
- **Null baseline**: 400 permutations, seed 20260819. 65.8% (30d) / 66.5% (7d) / 76.1% (90d), reproducing session 30's independent 63–67%. Non-overlapping mode: ~107 independent rows/draw at 30d.
- **Dashboards**: `track_record_dashboard.json` only — new panel-8, panel-1 rewritten, panel-5 gains a `null (chance)` column and a dashed-red override, how-to-read rewritten. **All five JSONs parse**; top-row grid re-checked as contiguous and summing to 24; **both new rawSql queries executed against the live DB** (panel-1 returns +2.7 / 68.5, panel-5 returns 14 rows with the null column present).
- **`check_run.py`**: run end to end, section 4 renders, exit code **0** (no collapse on the latest run). The non-zero exit is guarded to the latest date so the 08-05 → 08-12 history cannot pin CI red.
- **No API spend. No migrations. No prompt or pipeline code touched**, so no dry-run of the recommendation pipeline was warranted.

## Invariants (don't break)

All of HANDOFF_30's invariants stand — in particular **the instrument scale's estimation window must end before the corpus it grades**, **no shrinkage toward the class scale**, **`instrument_scale` returns `None` not 1.0**, **the scale is resolved in `bands_for` not at call sites**, **any `INSTRUMENT_BAND_SCALE` change needs a `--regrade` with sign-off**, **pattern injection stays off unless `PATTERN_INJECTION_ENABLED` is truthy**, **mining keeps running**, **`check_run.py` never writes**, and **excess is direction-blind**. New this session:

- **Never render a hit rate without its null adjacent to it.** Now enforced in two places (the scorecard's headline tile and `check_run.py` section 4) rather than asserted in prose. ~66% is what dice score.
- **`NULL_BASELINE` in `check_run.py` and the pinned constant in `track_record_dashboard.json` must be re-derived whenever the grading bands or the action mix change.** A stale null silently converts the excess tile back into a hit rate — the exact failure the tile exists to prevent. Both carry a comment saying so; keep them in step with each other.
- **Report both nulls, or name which one you used.** A per-action excess quoted without saying whether instrument selection was held fixed is not interpretable — SELL differs by 34pp between them.
- **`sd` from the permutation is not a p-value** while the corpus contains overlapping forward windows. Use `--non-overlapping` before calling anything significant.
- **`BUY` at −20pp is a hypothesis, not a finding.** Do not act on it — and specifically do not feed it to the miner or the prompt — until it is measured on independent windows. This is precisely the shape of claim (`BUY es sistemáticamente fallido`) that collapsed decisiveness for four runs in sessions 26–29.

## State of play / caveats

- **`main` = `d12a0cd`** (session 30 merged this session). **`feat/session-31-null-baseline` is pushed and not merged.** Its merge gate is light: **no pipeline code, no migrations, no data change**, so nothing drifts while it waits — unlike the last three sessions.
- **The track-record dashboard needs the user.** `track_record_dashboard.json` changed structurally this session (a new panel-8 and a re-laid-out top row), so unlike the session-26/30 text edits this one is **not** a surgical in-place tweak. It has no `uid`, and `predictions_dashboard.json` hardcodes `ma2wqvp` for the deep-dive click-through — **that hardcoding is in the deep-dive's uid, not the track record's**, so re-importing the track-record dashboard is safer than re-importing the deep-dive. Still owed from session 26/30: the `ticker_deep_dive_dashboard.json` how-to-read text (**edit that one in place, never re-import**).
- **Production**: green throughout (08-05 → 08-19, all 63 ok / 0 failed). Cron `0 10 * * 1,3,5` (12:00 Madrid). **Batch resilience still unexercised.** Cost ~$1.60/month on the **Anthropic API** account, separate from the Claude subscription; an empty balance stops the cron silently.
- **Outcomes: 5,496 rows** (2,748 at 7d, 2,433 at 30d, 315 at 90d) all evaluated 2026-08-19 on per-instrument bands. 180d fills ~2026-11-13, 365d ~2027-05-17.
- **`prediction_patterns` id=7** (08-14) is still newest and carries the s28 fields; Friday mining appends regardless of the switch.
- **`^STOXX50E`**: grading fixed (s30), **cohort keying still not** — `_cohort_key` benchmarks it against equities. Inert while injection is off. The prior question stands: should an index be recommended at all?
- Carried: 252 pre-`price_checks` candidates ungradeable; `price_checks` 06-30 → 07-08 gap permanent; deep-dive price history starts 2026-06-12; **Reddit dark**.
- **Local runs**: prefix with `env -u ANTHROPIC_API_KEY` (the shell exports it as an **empty string**, shadowing `.env`). Worktrees have **no `.venv` and no `.env`** — use `/home/guillo/Git/stock-recommendations/.venv/bin/python`, and for scripts either pass an absolute path to `load_dotenv` or `set -a && . /home/guillo/Git/stock-recommendations/.env && set +a` first. **`.env` uses `DB_PASS`, not `DB_PASSWORD`.** Ad-hoc DB scripts need `init_command="SET collation_connection = utf8mb4_unicode_ci"`. **`recommendations` has no `symbol` column** — join `tickers` via `ticker_id`. **`run_metrics` has `run_at` and `estimated_cost_usd`**, not `run_date`/`total_cost_usd`; **`recommendation_outcomes` has `evaluated_at` only** — no `created_at`/`updated_at`.
- **pymysql chokes on `%` in a query when you pass an args tuple** — the track-record panel-5 SQL has `hit %` column aliases, so execute it with no args at all.
- **The Grafana JSONs are schema v2** (`elements` + `layout`, not `panels`). Round-trip with `json.dumps(d, indent=2)` and **no trailing newline** — that reproduces the files byte-identically.
- **`pytest` caching lies in worktrees** — always `-p no:cacheprovider`. **`pyyaml`** is missing from the project venv.
- **User timezone: Europe/Madrid.** A full `--regrade` takes ~2.5 minutes (row-by-row upsert); run it in the background.

## Detailed TODO for session 32 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout: `git pull`, `git log --oneline -3 --decorate`, compare against the prompt — **if they disagree, the repo wins; say so**. `git worktree list`; `git status --short`. **Note today's date.**

**Step 1 — Merge session 31.** Confirm **179 tests pass**, then ask the user to merge. **Unlike the last three sessions there is no urgency and no drift** — no pipeline code, no migrations, the DB is not ahead of `main`. Do not import urgency this session does not have. The only live consequence of the delay is that the scorecard keeps showing the old raw-hit-rate headline.

**Step 2 — Look at production and the null before anything else.** Run `scripts/check_run.py` (section 4 now prints hit rate, null and excess together). Then `scripts/check_null_baseline.py --non-overlapping`. **The specific question: has the excess moved?** More 90d rows have matured, and 90d had the thinnest corpus. If the excess has drifted, ask whether the *null* should have moved too — the action mix changes run to run, and the pinned constants do not.

**Step 3 — Settle the `BUY` hypothesis (the substantive slice; needs the user).** `BUY` is negative under all three nulls (−17.7 / −20.2 / −33.6pp) and is the only per-action sign that never flips, but it rests on ~12 independent calls. It is also, uncomfortably, the same claim that collapsed decisiveness in sessions 26–29 — so **the standard of evidence is high and the consequence of acting early is known and bad**. Concretely: extend the non-overlapping estimate as the corpus grows, and consider whether a block permutation (shuffle contiguous runs of actions, preserving temporal clustering) gives a null with honest error bars. **Do not feed this to the miner or the prompt under any circumstance yet.**

**Step 4 — Benchmark-relative grading** (was option (c) last session; still the principled fix and now better motivated). Grade a call against its instrument's own drift rather than against zero. This would fold the "+5.0pp instrument pairing" term into the yardstick, so the remaining excess would be timing alone and the two nulls would converge. Big slice: it changes every stored verdict, so `--regrade` with sign-off, and the estimation window must end before the corpus (s30's invariant).

**Step 5 — Re-measure the 90d bands** (carried from s30, still not actionable). 30d→90d bands widen ×1.5 while dispersion grows ×1.31, so WATCH may be systematically easier at 90d — the 90d null of **76.1%** vs 30d's 65.8% is consistent with that and is new evidence for it. 315 rows now.

**Step 6 — Settle `^STOXX50E`'s cohort** (carried, needs the user; the grading half is done). `_cohort_key` still benchmarks an index against equities. Options: (a) exclude index rows from mining, (b) give INDEX its own cohort, (c) drop it from the active set. Prior question: should an unholdable instrument be recommended at all?

**Step 7 — Quarterly hygiene** (not due yet): re-derive `INSTRUMENT_BAND_SCALE` with `scripts/derive_instrument_scales.py` — **keep the window ending before the corpus**. `scripts/check_bands.py` guards the class fallback. **If you re-derive, re-derive the null in the same session** — the bands and the null are now coupled.

**Step 8 — Pick the next slice with the user** (AskUserQuestion). Suggested order:
1. **Whatever steps 3/4 settle.**
2. **Track decisiveness as a first-class metric** — a digest panel for BUY+SELL per run. Five sessions have now reconstructed it by hand. Dashboard-only. (`check_run.py` now exits non-zero on a collapse, which covers the alerting half.)
3. **Persist the injected set per run** — a JSON column on `run_metrics`. Wanted by six sessions. Migration → sign-off. Cheap to defer while the loop is off.
4. **Pattern-evolution panel** (dashboard-only; 7 rows exist).
5. **Scheduled-run watchdog**; portfolio lens dashboard; fundamentals-vs-verdict slice; batched Reddit sentiment (if creds).

**Step 9 — Validate the standard way.** `env -u ANTHROPIC_API_KEY /home/guillo/Git/stock-recommendations/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` (expect **179+**). Full dry-run only if pipeline code changed *and* the effect isn't verifiable more cheaply. Migrations only with sign-off, no `;` in migration comments. Grafana JSONs: `json.dumps(d, indent=2)` with no trailing newline; **verify the grid geometry after any layout change** and run new rawSql against the live DB. Verify every ad-hoc DB write by reading it back. Never `git add -A` blindly — read `git show --stat` before pushing.

**Step 10 — Close out per the ritual.** Update PLAN.md including its Decisions log; write `handoffs/HANDOFF_32.md`; commit; push; and **print a SHORT next-session prompt in chat** — the detail belongs here, not in the prompt.

## Fresh suggestions (beyond the committed backlog)

- **Derive the null in CI rather than pinning it.** The constant is now in two files and will go stale silently. A weekly job that recomputes it and fails loudly on a >2pp move would close the invariant properly. Cheap; no API cost.
- **Report per-action excess on the dashboard, with both nulls side by side.** The per-action table currently shows raw hit rates that are not comparable with each other (HOLD's null is ~40%, WATCH's ~79%). It is the most misleading panel left.
- **Count independent observations, not rows, anywhere n is displayed.** The trend panel's "30d decided" bars invite exactly the over-reading this session corrected.
- **Suppress mining dimensions whose non-null share is below a floor** (carried from s28): `_bucket_pe` and `_bucket_dividend` are `(sin dato)` for essentially every 30d row.
- **Assert the excess invariant in code** (carried from s28): warn when `abs(overall_excess) > 0.05`.
- **Date the corpus in the pattern schema** (carried from s29) — only relevant if the loop returns.
- **Retire the daily-era flip baselines** (carried); **retry-once on transient yfinance timeouts** (carried, cheap); **a 180d how-to-read sweep in ~Nov 2026** (carried).

## Prompt for the next session

> Read handoffs/HANDOFF_31.md and PLAN.md before doing anything, then follow HANDOFF_31's TODO for session 32 in order. Cross-check against git log first — if they disagree, the repo wins, say so. `feat/session-31-null-baseline` is pushed and not merged, but there is **no urgency**: no pipeline code, no migrations, no data drift. The finding to carry: the hit rate now has a null (~66%), and against it the system's edge is +2.7pp from instrument selection and **−2.3pp from timing**. `BUY` is negative under every null but rests on ~12 independent calls — treat it as a hypothesis and do not feed it to the prompt or the miner.
>
> But before the above: some time may have passed. Look at the database and the dashboards first, evaluate how accurate the system has actually been, and adjust parameters, values and code according to what you find — sessions 26 through 31 all proved this instruction pays for itself. The lessons compound: a self-improving loop amplifies a measurement bug (s26); fixing the measurement doesn't fix the loop (s27); a fix keyed on a data field inherits that field's gaps (s28); when successive quality improvements don't improve the outcome, switch the component off and measure (s29); the metric you have trusted longest is the one nobody has audited (s30); and the tool you build to audit metrics needs auditing first and hardest (s31). So before trusting any aggregate, compute what it would read if the finding were false — and check how many genuinely independent observations it rests on.
