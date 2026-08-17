# Handoff 30 — 2026-08-17 (session 30: the switch held, and the scoreboard turned out to have no baseline)

Continues [HANDOFF_29.md](HANDOFF_29.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 30 did

On branch **`feat/session-30-instrument-bands`** (off `main` @ `06af2d9`), worktree `.claude/worktrees/session-30-instrument-bands`. Pushed, **not merged**. **The 5,244-row re-grade is already written to the live DB.**

### 0. The prompt agreed with the repo

`main` @ `06af2d9` with sessions 28 and 29 both merged, exactly as the prompt said. Tally: s19–s21 drifted, s22–s25 clean, s26 drifted twice, **s27–s30 clean**. Keep checking.

One thing to know: **the prompt printed inside HANDOFF_29 is stale** — it was written before session 29 merged itself and still says "not merged, deadline Mon 08-17". The user's actual prompt carried the corrected version. If you are reading a handoff's own printed prompt, prefer the one the user pasted.

The session ran Monday evening, ~19:00 UTC, after the 10:00 UTC production run.

### 1. The kill switch works, and the evidence is triangulated

Monday 08-17 was the first production run carrying it.

| date | BUY | SELL | decisive | AVOID | WATCH | cost | injected |
|---|---|---|---|---|---|---|---|
| 2026-08-12 | 2 | 0 | **2** | 4 | 28 | $0.1386 | id=6 |
| 2026-08-14 | 6 | 3 | **9** | 4 | 24 | $0.1353 | none (gate failed closed) |
| **2026-08-17** | **9** | **3** | **12** | 2 | 23 | **$0.0966** | **none (switch)** |

Three independent confirmations, which matters because any one alone is weak: the run log reads `Pattern injection is disabled`; decisive calls are back inside the 7–17 historical range for a second run; and **the cost fell ~30% at an identical 65 calls**, which is the ~520-token injected block leaving 63 prompts. AVOID never left its normal range, so it was never part of the collapsed pair.

**The CI health check also ran for the first time** and wrote its full table into the run summary, correctly labelling 08-17 as `none (off)`. Its step took 1 second, which looked like a silent no-op — worth checking against the log rather than assuming, since `continue-on-error` hides failures by design. It was real.

### 2. The first 90d outcomes, and why their headline is fake

126 rows. All from recommendations generated **05-17 and 05-18**, and containing **only HOLD and WATCH** — no BUY, SELL or AVOID at all. So "78% at 90d vs 60% at 30d" compares different action mixes. The honest comparison is *the same 126 recommendations at 30d*: **67.3%**. The horizon is worth ~+11pp, and it comes from WATCH crossing its threshold given more time (20 NEUTRAL→CORRECT against 9 NEUTRAL→INCORRECT).

Bands behave: 30d→90d they widen ×1.5 while measured dispersion grows ×1.31, so WATCH gets slightly easier at 90d. Too small and too thin (n=126, two rec dates) to act on. Re-measure when 90d fills.

### 3. The slice: per-instrument grading bands

The class is the wrong unit. Implied scales span **0.087–0.766 within ETFs** (8.8×) against a flat 0.30 and **0.286–2.688 within equities** (9.4×) against a flat 1.00, and the classes overlap so heavily that `SEME.PA`, `ISUN.L`, `CNRG` and `INRG.SW` all move further than `AAPL`. At the edges the yardstick decided the verdict before reading the call:

- **`^STOXX50E`** moves 1.56%/month, needed 10% for a CORRECT WATCH → **0 CORRECT out of 22, ever**.
- **`SPY5.PA`** moves 0.57%/month against a 1.2% "flat" band → **17 free CORRECTs**, 92% hit rate.
- **`MDT` 9.5%, `HWM` 7.7%** — low-volatility *equities* auto-failing on unscaled stock bands.

New [src/instrument_vol.py](../src/instrument_vol.py) pins a measured scale per symbol; `bands_for` resolves **instrument → class → unscaled** in one place. `SOLS` (144 closes) has no estimate and exercises the fallback. Re-derive with [scripts/derive_instrument_scales.py](../scripts/derive_instrument_scales.py).

**The window ending 2026-05-16 is the design, not an implementation detail.** It is the day before the earliest recommendation, so the bands cannot be fitted to the returns they grade. Validated out of sample twice: Spearman **0.90** against observed volatility, and persistence across two disjoint prior years at **R² 0.83, slope 1.18**.

**5,244 outcomes re-graded**, user-approved, simulated first, **verified by reading back — 0 remaining mismatches**. 1,099 rows changed. Movement runs both ways: `^STOXX50E` 0.0→78.1%, `MDT` 9.5→88.9%, `HWM` 7.7→86.2%, but `1GOOGL.MI` 100→63.6%, `AVGO` 76.2→50.0%, `EQQQ.DE` 72.2→47.1%. Cross-instrument spread **27.1pp → 19.1pp**. Headlines now **30d 68.8%, 7d 69.4%, 90d 77.5%**.

### 4. The finding that outlives the slice

The 30d headline rose 60.0% → 68.8%, the **third consecutive re-grade to raise it**. That pattern is what prompted a null-hypothesis backtest: grade *skill-free, randomly generated calls* over a year entirely outside the corpus and see what the scheme returns.

**It returns 63–67%.**

So the headline hit rate — on the scorecard since session 10 — sits within noise of what dice score, and the pre-re-grade 60% was *below* chance. The cause is structural: `HOLD` is CORRECT when the price stays flat, `WATCH` is CORRECT when it moves, and those two carry **89%** of all calls, so nearly any outcome lands on the good side of something. This does **not** show the system lacks skill. It shows the metric cannot answer the question either way.

The same test also **retired this session's own scare**. Mid-session the per-instrument yardstick showed rho −0.197 between volatility and hit rate against the class yardstick's −0.029, which read as a fresh bias and nearly blocked the slice. Under the null the two yardsticks have *different* baselines: **+0.140** for class, **+0.045** for per-instrument. Measured against its own null the new scheme is the *less* biased one, and −0.197 sits 1.3 sd out. The old yardstick's clean-looking −0.029 was two opposite-direction artifacts cancelling.

## Learnings

The arc: s26 — a loop amplifies bad data. s27 — fixing the data doesn't fix the loop. s28 — a fix keyed on a field inherits that field's gaps. s29 — three rounds of accuracy work didn't help; switching it off measured it in one run. **s30 — the yardstick everything was measured against had never been checked against chance.**

1. **Compute what your statistic reads when the finding is false — and do it for the metric you have trusted longest.** The standing instruction has said this for five sessions, and it kept getting applied to *new* numbers. The hit rate was never audited because it was infrastructure. It took a null backtest, which cost one script and no API budget, to find that 89% of calls go to two actions whose CORRECT conditions between them cover almost any outcome. **Audit the denominator of your confidence, not just the latest finding.**
2. **A statistic's null is not always zero, and comparing against zero can invert your conclusion.** The rho scare was real, well-reasoned and wrong: both yardsticks have their own null rho, and the "clean" one was dirtier. Had the session stopped at the first negative result it would have shipped nothing and reported a false problem. **Before rejecting a change because a diagnostic moved, measure what that diagnostic reads under the change with no signal present.**
3. **A correlation is the wrong instrument for an artifact that points both ways.** The class yardstick looked unbiased at rho −0.029 because `^STOXX50E` (calm, scoring 0%) and `SPY5.PA` (calm, scoring 92%) cancelled. Spread caught what correlation hid. **Match the statistic to the shape of the defect you suspect.**
4. **When the fix and the estimate come from the same data, the fix is unfalsifiable.** Per-instrument bands estimated from the graded returns would have flattened every hit rate by construction and looked like a triumph. The pre-corpus window is what makes the result mean anything, and it cost nothing but a date. **The same reasoning forbade shrinkage**: it would have improved the corpus numbers and destroyed the reason to believe them.
5. **Record the hypotheses that failed.** Volatility mean-reversion and a mean-vs-median mismatch both looked compelling and both were wrong (the persistence slope is 1.18; median made the tilt worse at −0.254). The residual tilt is still unexplained. Writing that down is cheaper than the next session re-deriving both.
6. **Three sessions of "the class was the wrong unit" is a pattern, not a coincidence.** s26 keyed on class, s28 found the field had gaps, s30 found the class too coarse. Each fix was correct and each inherited the previous one's granularity assumption. **When a fix is the third in a series against the same defect, question the axis rather than the values on it.**
7. **A one-second step in CI deserves a look at its log.** `continue-on-error` is exactly the setting that turns a broken diagnostic into silence. This one was fine; the habit is what matters.
8. **Elapsed time between sessions is a feature — confirmed again.** Session 29 had to reason about whether 08-14's recovery was a fluke. Session 30 opened after one more production run and simply read the answer.

## Validation evidence

- **pytest: 172 passed** (164 + 8, always `-p no:cacheprovider`). New: instrument scale beats class scale; the two-step fallback (`SOLS` → class, unknown+unknown → unscaled); **byte-identical behaviour when no symbol is passed**, so every pre-session-30 caller is unchanged; the `^STOXX50E` and `SPY5.PA` regressions as named fixtures, so the tests state *why* the file exists; band ordering across horizons for the table's extremes; a plausibility guard on the table (size, range, and that both sides of 1.0 are populated); and `instrument_scale` returning `None` rather than 1.0, which is the distinction session 26's NULL bug turned on.
- **The re-grade**: simulated from stored `forward_return` (1,099 of 5,118 changing, 21.5%), then `--dry-run --regrade` through the real pipeline clean at 5,244 outcomes, then written, then **verified by re-running the simulation against the stored data — 0 rows changing**.
- **Out-of-sample validation of the estimator**: Spearman 0.90 / Pearson 0.84 against observed corpus volatility (n=62, 84% within 2×); persistence R² 0.83, slope 1.18 across 2023-24 → 2024-25.
- **Null backtest**: 8 seeds, skill-free calls, scale from 2023-05→2024-05 graded over 2024-05→2025-05. Hit rate 63–67%; null rho +0.140 (class) vs +0.045 (per instrument).
- **Production verification**: 08-17 run green (63 ok / 0 failed, $0.0966, 65 calls), injection-disabled log line present, health-check step's output read from the downloaded run log.
- **Dashboards**: two how-to-read texts edited surgically (track-record escapes `×`, deep-dive uses literal `×`); **all five JSONs parse**. No rawSql touched.
- **No dry-run of the recommendation pipeline** — no prompt or recommendation code changed. **No migrations. No API spend this session.**

## Invariants (don't break)

All of HANDOFF_29's invariants stand — in particular **pattern injection stays off unless `PATTERN_INJECTION_ENABLED` is truthy**, **re-enabling requires evidence about outcomes**, **mining keeps running**, **`check_run.py` never writes**, and **excess is direction-blind**. New this session:

- **The instrument scale's estimation window must end before the corpus it grades.** This is the whole basis for believing the re-graded numbers. A re-derivation that quietly uses trailing-12-months data overlapping the graded period silently converts the metric into a self-fulfilling one.
- **No shrinkage toward the class scale** unless an *out-of-corpus* persistence estimate justifies it. The measured slope is 1.18; fitting a factor against the corpus is the circularity the window exists to prevent.
- **`instrument_scale` returns `None`, never 1.0, for an unknown symbol.** `None` means "fall back to the class"; 1.0 would assert "as volatile as a typical stock". Conflating them is session 26's NULL bug.
- **The scale is resolved in `bands_for`, not at call sites** — same one-choke-point rule as s28's quote_type overrides and s29's switch.
- **Any change to `INSTRUMENT_BAND_SCALE` changes stored verdicts and needs a `--regrade` with sign-off.** Same rule as `ASSET_CLASS_BAND_SCALE` and `src/quote_types.py`. Never a call-site override, and never one without the other.
- **Do not quote the headline hit rate without its null.** ~65% is what no skill scores. Until the scorecard carries a baseline, the number is decoration.

## State of play / caveats

- **`main` = `06af2d9`** (sessions 28 and 29). **`feat/session-30-instrument-bands` is pushed and not merged.**
- **⚠ THE DATA CHANGE IS ALREADY LIVE AND `main` DOES NOT KNOW.** The re-grade is written; `main`'s grader still scales by class, so the **next `evaluate_outcomes` run on `main` (Wed 2026-08-19 10:00 UTC) will start putting instruments back on class bands**, undoing the re-grade piecemeal — exactly the regression session 29 found between sessions 28 and 29, at ~3 rows/week per affected ticker. Merging is what prevents it. No migrations.
- **The two dashboards need the user**: `track_record_dashboard.json` and `ticker_deep_dive_dashboard.json` how-to-read texts changed this session (and were already owed from session 26). **Edit in place in Grafana; do not re-import the deep-dive** — no `uid` in its JSON, and `predictions_dashboard.json` hardcodes `ma2wqvp` in 3 places for the symbol click-through.
- **Production**: green throughout (08-05 → 08-17, all 63 ok / 0 failed, $0.0966–0.158). Cron `0 10 * * 1,3,5` (12:00 Madrid). **Batch resilience still unexercised.** Cost ~$1.60/month on the **Anthropic API** account, separate from the Claude subscription; an empty balance stops the cron silently. The injection-off runs should bill ~30% less.
- **`prediction_patterns` id=7** (08-14) is newest; a Friday mining run appends regardless of the switch.
- **90d outcomes: 189 rows** after this session's grading (126 before). 180d fills ~2026-11-13, 365d ~2027-05-17.
- **`^STOXX50E`**: grading fixed, **cohort keying not** — `_cohort_key` still benchmarks it against equities, distorting `tipo: (otro)` in the mining aggregates. Inert while injection is off. The prior question stands: should an index be recommended at all?
- Carried: 252 pre-`price_checks` candidates ungradeable; `price_checks` 06-30 → 07-08 gap permanent; deep-dive price history starts 2026-06-12; **Reddit dark** (`grep -c '^REDDIT' .env` = 0, re-checked this session).
- **Local runs**: prefix with `env -u ANTHROPIC_API_KEY` (the shell exports it as an **empty string**, shadowing `.env`). Worktrees have **no `.venv` and no `.env`** — use `/home/guillo/Git/stock-recommendations/.venv/bin/python`, and for scripts either pass an absolute path to `load_dotenv` or `set -a && . /home/guillo/Git/stock-recommendations/.env && set +a` first. **`.env` uses `DB_PASS`, not `DB_PASSWORD`.** `ClaudeClient(cfg)` takes a `Config` from `load_config()`. Ad-hoc DB scripts need `init_command="SET collation_connection = utf8mb4_unicode_ci"`. **`recommendations` has no `symbol` column** — join `tickers` via `ticker_id`; `recommendation_outcomes` *does* carry `ticker_id`. `price_checks` is `(ticker_id, as_of_date, price)`.
- **`pytest` caching lies in worktrees** — always `-p no:cacheprovider`. **`pyyaml`** is missing from the project venv, present in the system `python3`.
- **User timezone: Europe/Madrid.**

## Detailed TODO for session 31 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout: `git pull`, `git log --oneline -3 --decorate`, compare against the prompt — **if they disagree, the repo wins; say so**. `git worktree list`; `git status --short`. **Note today's date**, and note that the machine clock has been correct but sessions have opened days apart.

**Step 1 — The merge gate, and check whether the re-grade has already started rotting.** `feat/session-30-instrument-bands` is pushed, not merged, and the DB is ahead of `main`. Confirm **172 tests pass**, then ask the user to merge. **First measure the damage**: re-run the session-30 simulation logic (compare each stored verdict against what per-instrument bands give) — if rows have drifted back, `main`'s grader has been re-grading them on class bands since 08-19, and the count tells you how long. Report it plainly, merge, then re-grade to repair.

**Step 2 — Read the decisiveness series.** `scripts/check_run.py`, or just open the latest run's GitHub summary page. Two runs above the collapse so far (9, 12). Does it hold across several more? Watch AVOID too.

**Step 3 — The null baseline (the substantive slice; needs the user).** This is the strongest open item and it is squarely the standing instruction's territory. Options in increasing ambition: **(a)** compute the null once, pin it, and draw it as a reference line on the track-record scorecard so every hit rate is read against ~65% — cheap, dashboard-only, no migration; **(b)** report **excess over null** as the headline instead of raw hit rate — changes what the scorecard *means*, so it needs sign-off and a how-to-read rewrite; **(c)** benchmark-relative grading, i.e. grade a call against its instrument's own drift rather than against zero — the principled fix, already on the backlog, and now much better motivated. Note the null backtest harness from this session is in the scratchpad and is ~150 lines; rebuilding it as `scripts/check_null_baseline.py` is a reasonable first move under any option.

**Step 4 — Re-measure the 90d bands** once more data has accumulated (189 rows now, and they will grow every run). The specific question: 30d→90d bands widen ×1.5 while dispersion grows ×1.31, so WATCH may be systematically easier at 90d. Same class of bug as s26 and s28. Not yet actionable.

**Step 5 — Settle `^STOXX50E`'s cohort** (needs the user; the grading half is done). `_cohort_key` still benchmarks an index against equities. Options: (a) exclude index rows from pattern mining, (b) give INDEX its own cohort, (c) drop it from the active set. The prior question is whether an unholdable instrument should be recommended at all. Any of (b)/(c) touching stored verdicts needs a re-grade with sign-off.

**Step 6 — Quarterly hygiene** (not due yet; note the dates): re-derive `INSTRUMENT_BAND_SCALE` with `scripts/derive_instrument_scales.py` — **and if you do, keep the window ending before the corpus, or the numbers stop meaning anything**. `scripts/check_bands.py` still guards the class fallback.

**Step 7 — Pick the next slice with the user** (AskUserQuestion). Suggested order:
1. **Whatever step 3 settles.**
2. **Track decisiveness as a first-class metric** — a digest panel for BUY+SELL per run. Four sessions have now reconstructed it by hand; it is the single most informative number the system produces about itself. Dashboard-only.
3. **Persist the injected set per run** — a JSON column on `run_metrics`. Wanted by five sessions. Migration → sign-off. Cheap to defer while the loop is off, since the answer is constant.
4. **Pattern-evolution panel** (dashboard-only; 7 rows exist).
5. **Scheduled-run watchdog**; portfolio lens dashboard; fundamentals-vs-verdict slice; batched Reddit sentiment (if creds).

**Step 8 — Validate the standard way.** `env -u ANTHROPIC_API_KEY /home/guillo/Git/stock-recommendations/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` (expect **172+**). Full dry-run only if pipeline code changed *and* the effect isn't verifiable more cheaply — sessions 29 and 30 both justifiably skipped it. For miner changes prefer the cheap single mining call (~$0.02) with the DB connection closed first, and **read the output**. Migrations only with sign-off, no `;` in migration comments. Grafana JSONs: surgical text edits, matching each file's unicode convention. Verify every ad-hoc DB write by reading it back. Never `git add -A` blindly — read `git show --stat` before pushing.

**Step 9 — Close out per the ritual.** Update PLAN.md including its Decisions log; write `handoffs/HANDOFF_31.md` (detailed TODO an older model can follow + fresh suggestions + learnings); commit; push; and **print a SHORT next-session prompt in chat** — the user asked for brevity from session 30 onward, because the detail belongs here, not in the prompt.

## Fresh suggestions (beyond the committed backlog)

- **Make `scripts/check_run.py` exit non-zero on a decisiveness collapse** (carried from s29, still undone). It already prints `*** COLLAPSED ***`; a non-zero exit in a `continue-on-error` step surfaces a red X without failing the run. The collapse ran four runs unnoticed.
- **Add the null baseline to `check_run.py` too**, not just the dashboard — a hit rate printed next to "chance scores 65%" is much harder to misread than one printed alone.
- **Report per-action hit rates with their own nulls.** HOLD and WATCH have wildly different chance rates under this scheme; a single null for the headline hides that.
- **Suppress mining dimensions whose non-null share is below a floor** (carried from s28): `_bucket_pe` and `_bucket_dividend` are `(sin dato)` for essentially every 30d row — two of twelve dimensions are noise presented as evidence.
- **Assert the excess invariant in code** (carried from s28): warn when `abs(overall_excess) > 0.05`.
- **Date the corpus in the pattern schema** (carried from s29) — only relevant if the loop ever returns.
- **Retire the daily-era flip baselines** (carried); **retry-once on transient yfinance timeouts** (carried, cheap); **a 180d how-to-read sweep in ~Nov 2026** (carried).

## Prompt for the next session

> Read handoffs/HANDOFF_30.md and PLAN.md before doing anything, then follow HANDOFF_30's step-by-step TODO for session 31 in order. Cross-check the prompt against git log first — if they disagree, the repo wins, say so. Two things are urgent and both are in step 1: `feat/session-30-instrument-bands` is pushed but NOT merged, and session 30's 5,244-row re-grade is ALREADY LIVE in the DB, so `main`'s grader has been putting instruments back on asset-class bands at every run since — measure how many rows drifted before you merge, then re-grade to repair. The headline finding to carry: skill-free random calls score 63–67% under this grading scheme, so the hit rate has never had a baseline, and deciding what replaces it is the session's main slice.
>
> But before the above: some time may have passed. Look at the database and the dashboards first, evaluate how accurate the system has actually been, and adjust parameters, values and code according to what you find — sessions 26 through 30 all proved this instruction pays for itself. The lessons compound: a self-improving loop amplifies a measurement bug (s26); fixing the measurement doesn't fix the loop (s27); a fix keyed on a data field inherits that field's gaps (s28); when successive quality improvements don't improve the outcome, switch the component off and measure (s29); and the metric you have trusted longest is the one nobody has audited (s30). So before trusting any aggregate, compute what it would read if the finding were false — including the aggregates that are infrastructure rather than findings.
