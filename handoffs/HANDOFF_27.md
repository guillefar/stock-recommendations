# Handoff 27 — 2026-08-03 (session 27: market-relative stats for the miner — and the proof that data alone isn't enough)

Continues [HANDOFF_26.md](HANDOFF_26.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 27 did

On branch **`feat/session-27-market-relative`** (off `main` @ `05ccbba`), worktree `.claude/worktrees/session-27-market-relative`. Pushed, **not merged**.

Session 26's pinned follow-up, delivered — and then **falsified as a complete fix by its own validation run**, which is the session's most valuable output.

### 0. The prompt agreed with the repo (first clean session since s25)

HANDOFF_26 said `main` was `c06c89b`; it is **`05ccbba`**, one commit ahead. That commit is HANDOFF_26's own doc close-out, so there is **no code drift**. Session 26 had drifted twice, so this was checked before anything else. Tally: s19–s21 drifted, s22–s25 clean, s26 drifted twice, s27 clean. **Keep checking.**

### 1. Verified `main` and production before building

- **137 tests pass** on `main`.
- **Production is green since the merge**: 07-29, 07-31, 08-03 all succeeded in ~4–5 min. The two 48-minute total failures (07-17, 07-27) both predate the batch fix.
- **Batch resilience remains unexercised** — no batch since the merge has run long enough to hit the deadline, so the harvest path has never fired in production.
- **`ASSET_CLASS_BAND_SCALE` re-derived: 0.306** against the pinned 0.30. Still good; no re-grade needed.
- **Reddit still dark** (`grep -c '^REDDIT' .env` = 0).

### 2. The slice: market-relative statistics

**`summarize_features`** ([src/analysis/patterns.py](../src/analysis/patterns.py)) folds an **`excess_return_pp`** into every bucket — its mean forward return minus its market cohort's, in percentage points. `get_outcome_features` ([src/db.py](../src/db.py)) gained **`DATE(r.generated_at) AS rec_date`** as the cohort key.

**The cohort is `(rec_date, ETF vs non-ETF)`.** Same day because that is the market the calls actually shared. Same asset class because session 26 established the two are not comparable instruments — an ETF judged against a stock-dominated cohort reads its low beta as an absence of skill.

Validated on the **live corpus (2,055 rows, 64 cohorts)** — it reproduces session 26's audit:

| action | hit rate | excess | audit said |
|---|---|---|---|
| SELL | 98% | **−9.7pp** (×EQUITY −11.3pp) | −11.0pp |
| BUY | 6% | **−3.3pp** | −3.0pp |
| HOLD | 55% | **+1.2pp** | +0.9pp |
| WATCH | 64% | **−0.0pp** | +0.3pp |
| AVOID | 73% | −2.3pp | −5.6pp |

Overall excess is **exactly 0.0pp**, as summing deviations from a mean requires — a free correctness check on the whole computation. And the artifact dimension collapses: **`WATCH×ETF` −0.5pp against `WATCH×EQUITY` −0.2pp**, where the raw hit rates still read 60% and 71%.

**Excess is direction-blind, and the live data is what revealed it.** SELL scores −9.7pp — its picks fell harder than their cohort, exactly as the call predicted. That is skill, but it reads as failure to anything assuming positive-is-good. The mining prompt now states the rule explicitly: positive = skill for BUY/HOLD, **negative = skill for SELL/AVOID**, WATCH asserts no direction so its excess only reports bias. Without that clause this fix would have handed the miner a new way to condemn its single most skilful action.

### 3. The validation run — a negative result, and the session's real finding

One live mining call against the corrected stats (**$0.02, wrote nothing**):

**What worked.** 8/8 patterns cite the excess figure. The `WATCH×ETF` artifact that survived into id=5 as a cherry-picked sub-bucket (`0% en subsegmento material`, REVISED 0.82) **is gone** — session 26's predicted self-reference diagnostic resolved. `HOLD×ETF` dropped to REVISED 0.85 citing `+1.1pp` and its own 94%→63% deterioration.

**What didn't.** The **injected top-3 is essentially unchanged**: `SELL genera casi-perfección` (0.93), `BUY es un lastre` (0.92), `HOLD × RSI 70+` (0.90). The miner *cites* excess while still *reasoning* from hit rate:

- **`WATCH × (otro)`** — labelled **"colapso catastrófico: 0% de acierto"** while its own evidence line reads **`exceso +10.6pp`**, the second-highest positive excess in the set. It called the best-performing bucket a catastrophe.
- **`RSI 70+`** — praised as a reliable "patrón de respeto de momentum" at **76% hit rate** with **`exceso −0.6pp`**, directly against the prompt's explicit instruction that an extreme hit rate with ~0 excess is the regime, not skill.
- **`BUY`** — still leads with "6% hit rate, 48 fallos" and "el patrón de mayor riesgo para inversores", while its own evidence shows `BUY×ETF` at **`exceso +0.2pp`** — no deficit at all.

**Conclusion: the slice is necessary but not sufficient. The regime caveat in `_patterns_block` stays.** The fix is a mechanical gate — see the TODO's step 4.

### 4. First evidence on the BUY-suppression watch

A full dry-run (**$0.1239, 63 ok / 0 failed, wrote nothing**) turned out to be the **first time `prediction_patterns` id=5 ever reached a prompt**: Monday 08-03's production run fired at **12:46 UTC** while id=5 was written at **14:14 UTC**, so production still injected the old artifact set id=3. **That makes 07-31 and 08-03 clean pre-correction baselines.**

| run | injected | BUY | WATCH | HOLD | SELL | AVOID | **BUY+SELL** |
|---|---|---|---|---|---|---|---|
| 07-31 | id=3 (artifact) | 7 | 22 | 26 | 3 | 5 | 10 |
| 08-03 prod | id=3 (artifact) | 6 | 22 | 28 | 1 | 6 | 7 |
| **08-03 dry-run** | **id=5 (corrected)** | **3** | 26 | 29 | **0** | 5 | **3** |

Historical ranges across 7 runs: BUY **4–10**, SELL **1–7**, decisive **7–17**. The dry-run came in **below every observed minimum on all three**.

**Note *how* it failed** — this is the part the handoff-26 prediction missed. The injected set says SELL is perfect and BUY fails, so the naive prediction is BUY↓ and SELL↑. Instead **both directional buckets drained into the HOLD/WATCH middle** (50 → 55). The model is not obeying the patterns directionally; being told its own calls fail is making it **decline to commit at all**. The regime caveat doesn't address that — it says "don't infer an action is good or bad in itself", which the model honours by hedging.

Caveats: **n=1**, and the dry-run ran ~4h after production so intraday prices differ; the three BUYs (FIX, VUG, TOYO) are disjoint from production's six, showing real per-ticker variance. **Wed 08-05 is the clean confirmation.**

### 5. `scripts/` — making verification a habit

New directory, two scripts, both runnable from the main checkout:

- **`scripts/check_run.py`** — post-run health in one command: action mix with the pre-correction baselines and the 7–17 decisive range baked in (it prints the verdict), whether Friday's mining actually persisted a row newer than id=5, and the last six `run_metrics` rows flagging any `tickers_ok != 63` (and calling out a *partial* harvest, which is what batch resilience firing looks like).
- **`scripts/check_bands.py`** — re-derives `ASSET_CLASS_BAND_SCALE` from live outcomes and compares against the pinned 0.30 with a ±0.08 tolerance, printing the exact re-grade commands if it drifts. **Currently 0.306.**

Both exit with a clear message rather than a `KeyError` when run from a worktree (which has no `.env`).

### 6. The production bill, measured

From `run_metrics`, not estimated: **Mon/Wed $0.115**, **Friday $0.143** (retro + mining), **≈ $1.60/month ≈ $19/year**. This bills the **Anthropic API account**, which is *separate* from the Claude subscription funding the sessions themselves. The loop's activation on 07-20 raised it ~18% ($0.098 → $0.115) via the ~668-token injected block × 63 prompts. Development sessions cost roughly a month of production each (~$0.15).

## Learnings

Written at the user's request. The through-line: **session 26 learned that a loop amplifies bad data; session 27 learned that fixing the data doesn't fix the loop.**

1. **Correct data does not produce correct conclusions.** The whole slice rested on an assumption worth naming: that the miner reached artifact patterns *because* it only had absolute hit rates. Give it market-relative figures and it should reason better. It didn't. It cited the new number in 8 of 8 patterns and ranked by the old one anyway — calling a +10.6pp bucket a catastrophe and a −0.6pp bucket reliable. **Supplying better evidence is necessary but not sufficient; what a model *attends to* is a separate problem from what it is *shown*.**
2. **When a prompt instruction is load-bearing for safety, encode it as a gate on the output.** The instruction here was explicit, unambiguous, in the model's own working language, and immediately adjacent to the data. It still didn't hold. Session 25 already knew this — the injection gate is code (`status`, `confidence`, top-3), not a request — and session 27 is the same lesson arriving from the other direction. **A request in the input is a preference; a check on the output is a guarantee.** Anything you'd be unwilling to see violated belongs in the second category.
3. **Validate against real data before writing the prose that interprets it.** The direction-blindness trap — SELL's −9.7pp being its *best* evidence, not its worst — was invisible in synthetic tests, where every fixture return was positive. It appeared the moment the implementation ran on the live corpus. Had the prompt been written first from the design, it would have shipped a rule teaching the miner to condemn its most skilful action. **Run the computation on production data before you explain the computation.**
4. **A metric with a known-zero value gives you a free correctness check.** Overall excess must be exactly 0.0pp — deviations from a mean sum to zero. That one assertion validates the cohort keying, the accumulation, and the division in a single line, and it doubles as the anchor that makes "this bucket is just the market" legible to the miner. **Look for the invariant your metric must satisfy; it's usually cheaper than the test you were going to write instead.**
5. **Check the clock on your own evidence.** The dry-run looked like a preview of Wednesday. It was better than that: `prediction_patterns` id=5 was written at 14:14 UTC while Monday's production run fired at 12:46 UTC, so **production had never once injected the corrected set** — which promoted 07-31 and 08-03 from "contaminated" to clean baselines and made the dry-run a genuine first. Two timestamps 88 minutes apart changed the interpretation of the whole comparison. Session 26 learned to check the clock; this is the same lesson paying out again.
6. **Predict the failure mode, not just the failure.** HANDOFF_26 predicted BUY suppression and was right about the magnitude. It was wrong about the mechanism: the model didn't shift from BUY toward SELL, it abandoned *both* directional calls for the HOLD/WATCH middle. The caveat written to prevent the predicted failure ("don't infer an action is good or bad in itself") is actually satisfied by the observed one — hedging honours it. **A mitigation aimed at the wrong mechanism can look compliant while the harm proceeds.**
7. **A negative result from a cheap validation is worth more than the feature it blocks.** One $0.02 call established that the pinned slice — the top backlog item for two sessions, the thing that was supposed to let the regime caveat be removed — does not on its own change what reaches production. Shipping it as "done" and removing the caveat would have been the natural next move and would have been wrong. **Validate the *effect*, not just the mechanism: "8/8 patterns cite the figure" was true and told you almost nothing.**
8. **Ask which account is paying.** The user assumed pipeline runs came out of their Claude subscription; they bill a separate Anthropic API balance. It was worth measuring properly — $0.115/$0.143 per run, ~$1.60/month — because an unnoticed empty balance stops the cron silently, and because knowing the number makes cost-benefit calls on validation runs easy rather than anxious. **Infrastructure that spends money deserves a number, not an impression.**
9. **Cheap habits beat good intentions** (carried from s26 and acted on). Both scripts exist because session 26 wrote "re-derive the 0.30 quarterly" as advice and advice decays. `check_bands.py` turned it into ten seconds; running it immediately confirmed 0.306. Advice in a handoff is a promise the next session may not keep; a script in `scripts/` is one command.
10. **Verify the no-write path too.** The dry-run was confirmed to have written nothing by reading `run_metrics` count, its max `run_at`, the pattern/retro row counts and today's rec count *after* the run. Session 26's lesson was to verify writes by reading them back; the mirror image matters just as much when the whole safety property is "this touched nothing".

## Validation evidence

- **pytest: 146 passed** (137 + 9 new, all in [tests/test_patterns.py](../tests/test_patterns.py), always with `-p no:cacheprovider`): a uniform market move showing as **0.0pp excess despite a 100%/0% hit-rate split** (the exact s26/s27 artifact, as a regression); real selection skill surviving as **±7.5pp**; cohorts scoped per day so opposite markets don't contaminate; ETFs benchmarked against ETFs; `None` excess when no return is usable; JSON-safety for the `stats` column; the prompt rendering excess beside every hit rate; the prompt carrying the weighting instruction; and the prompt carrying the **direction-blindness** rule. Two pre-existing exact-dict assertions were updated for the new key.
- **Live-corpus validation** (2,055 rows, 64 cohorts): reproduces the s26 audit — `SELL×EQUITY` −11.3pp vs −11.0pp, BUY −3.3pp vs −3.0pp, HOLD +1.2pp vs +0.9pp; overall excess exactly **0.0pp**; `WATCH×ETF` −0.5pp vs `WATCH×EQUITY` −0.2pp against raw hit rates of 60%/71%.
- **One real mining call** ($0.02, DB connection closed before the API call so nothing could be written): 8/8 patterns cite excess, `WATCH×ETF` artifact gone, **top-3 unchanged**, three documented instances of hit-rate reasoning overriding the instruction.
- **Full real-API dry-run: 63 ok / 0 failed at $0.1239** (65 calls, Monday so no retro/mining), batch ended in ~4 min. **Wrote nothing** — verified after by reading back `run_metrics` count (11) and max `run_at` (12:50:50, the production run), `prediction_patterns` (4 rows), `weekly_retrospectives` (3), and today's rec count (63, production only).
- **`scripts/check_bands.py` run live**: 7d 0.319, 30d 0.293, mean **0.306** vs pinned 0.30 — within tolerance.
- **No migrations. No dashboard changes.**

## Invariants (don't break)

All of HANDOFF_26's invariants stand. New this session:

- **The market cohort is `(rec_date, ETF vs non-ETF)`.** Changing it changes what "skill" means in every mined pattern. Same day = the shared market; same asset class = s26's finding that the two aren't comparable instruments.
- **Overall `excess_return_pp` must be exactly 0.0.** It is a mathematical identity, not a coincidence — if it drifts, the cohort keying or the accumulation is broken. Test-pinned.
- **Excess is direction-blind.** Positive = skill for BUY/HOLD; **negative = skill for SELL/AVOID**; WATCH asserts no direction. The mining prompt states this and it is test-pinned. **Never "simplify" it to positive-is-good** — on live data that inverts SELL, the system's most skilful action.
- **The `_patterns_block` regime caveat stays until the mechanical excess gate exists.** Session 27 proved the miner cites excess without weighting it, so the market-relative data alone does not make the caveat redundant. HANDOFF_26 said to remove it "when `summarize_features` reports market-relative figures" — **that condition is now met and it is still not sufficient.** Remove it only when a gate *enforces* excess.
- **`_tally` pops `_excess_sum`/`_excess_n`.** It is single-use per bucket by design; calling it twice silently yields `None` excess.
- **Verification scripts live in `scripts/` and read `../.env`.** They are meant to run from the main checkout; worktrees have no `.env` and the scripts exit with an explanatory message rather than a `KeyError`.

## State of play / caveats

- **`main` = `05ccbba`.** `feat/session-27-market-relative` is pushed and **not merged** — pipeline code changed, no migrations, no dashboard changes. **Merging before Fri 08-07 10:00 UTC** puts Friday's production mining on market-relative stats.
- **Still owed by the user: the two dashboard how-to-read edits** (`track_record_dashboard.json`, `ticker_deep_dive_dashboard.json`). **Edit them in place in Grafana — do not re-import the deep-dive.** Its JSON carries no `uid` and `predictions_dashboard.json` hardcodes `ma2wqvp` in 3 places for the symbol click-through; a fresh import mints a new uid and breaks the link that took sessions 19–24 to close.
- **`prediction_patterns` id=5 is still what production injects** (id 4 was deleted in s26; ids run 1,2,3,5). The corrected set has never been re-mined into a stored row — session 27's mining call was read-only.
- **The BUY-suppression signal is n=1** and needs Wed 08-05 to confirm. Baselines: 07-31 BUY=7/decisive=10, 08-03 BUY=6/decisive=7; dry-run BUY=3/SELL=0/decisive=3.
- **Production**: green since the merge; **batch resilience still unexercised**; no Tue/Thu runs; cron `0 10 * * 1,3,5` (12:00 Madrid, 11:00 in winter).
- **Cost**: ~$1.60/month on the **Anthropic API** account (separate from the Claude subscription). Watch for a low-balance email — an empty balance stops the cron.
- Carried: 252 pre-`price_checks` candidates ungradeable; `price_checks` 06-30 → 07-08 gap permanent; 90d/180d/365d fill ~2026-08-15 / 2026-11-13 / 2027-05-17; deep-dive price history starts 2026-06-12; **Reddit dark** (0 as of 2026-08-03).
- **Local runs**: `env -u ANTHROPIC_API_KEY` — the user's shell exports it as an **empty string** (verified `len=0`), which shadows `.env` because dotenv won't override a set var. Worktrees have no `.venv` — use `/home/guillo/Git/stock-recommendations/.venv/bin/python`. Ad-hoc DB scripts need `load_dotenv('/home/guillo/Git/stock-recommendations/.env')` and `init_command="SET collation_connection = utf8mb4_unicode_ci"`. **`ClaudeClient(cfg)` takes a `Config`** — build it with `load_config()` from `src.config` (there is no `Config.from_env()`; this cost a few minutes).
- **`pytest` caching lies in worktrees** — **always** pass `-p no:cacheprovider`.
- **User timezone: Europe/Madrid.**

## Detailed TODO for session 28 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout: `git pull`, `git log --oneline -3 --decorate`, compare against the prompt — **if they disagree, the repo wins; say so** (s19–s21 drifted, s22–s25 didn't, s26 drifted twice, s27 was clean; check every time). `git worktree list`; `git status --short` in the newest worktree. **Note today's date** — steps 2–3 are calendar-gated.

**Step 1 — The merge gate.** `feat/session-27-market-relative` is pushed, not merged. Ask the user. No migrations, no dashboard changes; pipeline code changed so a full dry-run is warranted if anything is added on top. Confirm `146` tests pass first. Also ask whether they made the two dashboard how-to-read edits **in place** (not re-imported — see State of play).

**Step 2 — Run the health check.** From the main checkout:
`/home/guillo/Git/stock-recommendations/.venv/bin/python scripts/check_run.py` (or the worktree path if unmerged). It answers three questions at once. Specifically: **(a) the BUY/decisive verdict** for Wed 08-05 and Fri 08-07 against the 7–17 decisive range — **this is the key check**, since the dry-run scored 3; **(b)** whether Friday's mining persisted a row newer than id=5 (the `max_tokens` 8192 fix); **(c)** `run_metrics` health — 63 ok at ~$0.115/$0.143, and if a batch ever runs long the log should read `canceling and harvesting whatever finished` with a **partial** `tickers_ok`, never 0.

**Step 3 — Interpret the BUY signal.** If Wed/Fri confirm decisive ≤ 6, the hedging effect is real and step 4 becomes urgent. **Note the mechanism**: the model retreats to HOLD/WATCH rather than flipping BUY→SELL, so a fix aimed at "stop trusting SELL" would miss. If decisive recovers to ≥ 7, the dry-run was an artifact of its 4-hour price offset — record that and de-prioritise.

**Step 4 — Build the mechanical excess gate** (the pinned slice; ~40 lines + tests). Add **`excess_return_pp`** (a number) to the pattern **structured-output schema** in `generate_pattern_analysis` ([src/analysis/claude_client.py](../src/analysis/claude_client.py)) so each pattern carries the excess of the bucket it rests on, then extend **`select_patterns_for_prompt`** ([src/analysis/patterns.py](../src/analysis/patterns.py)) to drop any pattern within **±1pp of zero**. On the validated set that correctly blocks `RSI 70+` (−0.6pp) and keeps `SELL` (−9.7pp).
**Settle with the user first**: `WATCH × (otro)` shows **+10.6pp** with a 0% hit rate and would pass a naive magnitude gate — WATCH asserts no direction, so decide between a per-action sign rule (BUY/HOLD require positive, SELL/AVOID require negative, WATCH excluded) or excluding WATCH patterns from the gate entirely. Also decide whether the ±1pp threshold or the gate's existing top-3 cap binds first. Remember the schema validator **rejects `minimum`/`maximum` on numbers** — the range lives in the prompt.
**Once this lands and a Friday confirms it works, the `_patterns_block` regime caveat can finally come out.**

**Step 5 — Check Reddit creds** (`grep -c '^REDDIT' .env`). If >0: GitHub secrets, one real cycle, `reddit_mentions`/`trending_tickers`/panel-14, batched sentiment becomes buildable.

**Step 6 — Pick the next slice with the user** (AskUserQuestion). Suggested order:
1. **The mechanical excess gate** (step 4 — do this first).
2. **Trim the injected pattern block** (~668 tokens/ticker, ~18% of the bill) — render name + a truncated description, or ask the miner for a short `prompt_line` field. Measure with a dry-run cost comparison. Note this pairs naturally with step 4, since both touch the same schema.
3. **Pattern-evolution panel** (dashboard-only; 4 rows exist) — stacked bars of pattern count by status per `generated_at`; would visibly show the s26/s27 CONFIRMED→REVISED churn.
4. **Scheduled-run watchdog** (carried) — a small workflow ~16:00 UTC Mon/Wed/Fri asserting `run_metrics` has a row for today. Give it slack; the real 07-13 lesson was *lateness*, not shedding.
5. **Benchmark-relative + dividend-adjusted grading** (~2026-08-15 when 90d matures) — the principled generalisation of the s26 band work *and* of s27's cohort. Needs design + re-grade sign-off.
6. Portfolio lens dashboard; fundamentals-vs-verdict slice; batched Reddit sentiment (if creds).

**Step 7 — Validate the standard way.** `env -u ANTHROPIC_API_KEY /home/guillo/Git/stock-recommendations/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` (expect **146+**; **always** disable the cache provider). Full dry-run (63 ok / 0 failed) **only if pipeline code changed**. For anything touching the miner, prefer the **cheap single mining call** (~$0.02) over a full dry-run ($0.12) — close the DB connection before the API call so it cannot write, and **read the output patterns**, not just the fact that it returned. Migrations only with sign-off, no `;` in migration comments. No `minimum`/`maximum` on numbers in structured-output schemas. Don't round-trip grafana JSONs — surgical edits, matching each file's unicode convention. New main-harness batch fakes need the 4th `patterns=None` param **and** a `get_latest_patterns` stub **and** `usage_snapshot`/`estimated_cost_usd`/`write_run_metrics`; if a harness makes every ticker fail, wrap `main()` in `pytest.raises(SystemExit)`.

**Step 8 — Close out per the ritual.** Update PLAN.md (including its Decisions log); write `handoffs/HANDOFF_28.md` (complete copy-pasteable next prompt + detailed TODO an older model can follow + fresh suggestions + learnings); commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Fresh suggestions (beyond the committed backlog)

- **Show the miner the realized move distribution per bucket** (carried from s26, now sharper). Session 27 proves the miner under-weights a figure it is merely *given*; the s26 suggestion of pairing each bucket's hit rate with its realized move distribution has the same weakness. Any new evidence column should ship **with a gate**, not just an instruction.
- **Ask the miner for a `skill_claim` field** — a short statement of what the pattern asserts about *skill* (not accuracy), separate from `description`. Cheap to add to the schema, and it forces the distinction the prompt is currently only requesting. Pairs with the excess gate.
- **Track decisiveness as a first-class metric.** `check_run.py` computes BUY+SELL ad hoc; a digest panel would make prompt-induced hedging visible without a script — arguably the single most sensitive indicator of the loop misbehaving, since session 27 showed hedging is how prompt pressure actually manifests.
- **Persist the injected set per run** (carried from s25, now twice-wanted): a JSON column on `run_metrics` recording which patterns the prompts carried. Session 26 had to reconstruct it from workflow logs; session 27 needed the *timestamp* comparison (id=5 at 14:14 vs the run at 12:46) to know what Monday actually injected. Migration → needs sign-off.
- **Re-mine into a stored row after the gate lands.** `prediction_patterns` id=5 is still the artifact-era set; session 27's corrected mining was read-only. A forced re-mine (user-approved, ~$0.02) once the gate exists would put a genuinely clean set into production — and `write_prediction_patterns(conn, result, stats)` takes **result first** (an s26 script reversed them and wrote a 0-pattern row).
- **Loop-effect measurement** (carried, twist compounding): 07-20 → 07-31 is contaminated by artifacts, and 08-05 onward is contaminated by the *uncorrected-weighting* set. The first clean window starts after the excess gate ships.
- **Retire the daily-era flip baselines** (carried); **retry-once on transient yfinance timeouts** (carried, cheap); **a 180d how-to-read sweep in ~Nov 2026** (carried).

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_27.md and PLAN.md before doing anything — HANDOFF_27 has the detailed step-by-step TODO for session 28 (note its Learnings section); follow it in order, and first cross-check this prompt's claims against git log (if they disagree, the repo wins — say so; s19–s21 drifted, s22–s25 didn't, s26 drifted twice, s27 was clean, so check every time). Context: main is at 05ccbba and **feat/session-27-market-relative is pushed but NOT merged** — step 1 is the merge gate. Session 27 delivered session 26's pinned slice — market-relative statistics for the pattern miner — and then its own validation run proved the slice is necessary but NOT sufficient, which is the session's most important output. What shipped: summarize_features in src/analysis/patterns.py now folds an excess_return_pp into every bucket (its mean forward return minus its market cohort's, in percentage points), where a cohort is (rec_date, ETF vs non-ETF) — same day because that is the shared market, same asset class because session 26 established ETFs and stocks are not comparable instruments and an ETF judged against a stock-dominated cohort reads its low beta as an absence of skill; get_outcome_features in src/db.py gained DATE(r.generated_at) AS rec_date as the cohort key. Validated on the live corpus (2,055 rows, 64 cohorts) it reproduces the s26 audit — SELL×EQUITY −11.3pp vs the audit's −11.0pp, BUY −3.3pp vs −3.0pp, HOLD +1.2pp vs +0.9pp — overall excess is exactly 0.0pp (a mathematical identity, test-pinned as a free correctness check), and the artifact dimension collapses: WATCH×ETF −0.5pp against WATCH×EQUITY −0.2pp where the raw hit rates still read 60% and 71%. CRITICAL and easy to get backwards: excess is DIRECTION-BLIND — positive is skill for BUY/HOLD, NEGATIVE is skill for SELL/AVOID (on live data SELL scores −9.7pp and that is its best evidence, not its worst), WATCH asserts no direction so its excess only reports bias; this is stated in the mining prompt and test-pinned, and it was only discovered by running the computation on production data before writing the prose that interprets it. THE NEGATIVE RESULT: one live mining call ($0.02, wrote nothing) showed 8/8 patterns citing the excess figure and the WATCH×ETF artifact finally dying (s26's predicted self-reference diagnostic resolved), BUT the injected top-3 came out essentially unchanged (SELL genera casi-perfección 0.93 / BUY es un lastre 0.92 / HOLD × RSI 70+ 0.90) because the miner cites excess while still RANKING by hit rate — it labelled WATCH × (otro) a "colapso catastrófico" for its 0% hit rate while its own evidence line read exceso +10.6pp (the second-highest positive excess in the set), and praised RSI 70+ as reliable at 76% hit rate with exceso −0.6pp, directly against an explicit instruction. So the _patterns_block regime caveat STAYS — HANDOFF_26 said to remove it once summarize_features reports market-relative figures, that condition is now met and it is still not enough. The fix, and the pinned next slice, is a MECHANICAL GATE: add excess_return_pp to the pattern structured-output schema in generate_pattern_analysis so each pattern carries a machine-readable number, then extend select_patterns_for_prompt to refuse to inject anything within ±1pp of zero (that correctly blocks RSI 70+ at −0.6pp and keeps SELL at −9.7pp) — settle two design questions with the user first: WATCH × (otro) at +10.6pp with a 0% hit rate would pass a naive magnitude gate, so decide between a per-action sign rule (BUY/HOLD positive, SELL/AVOID negative, WATCH excluded) or excluding WATCH from the gate, and decide whether ±1pp or the existing top-3 cap binds first; remember the schema validator rejects minimum/maximum on numbers. Also from session 27: a full dry-run ($0.1239, 63 ok / 0 failed, wrote nothing — verified by reading run_metrics/patterns/retros/rec-counts back afterwards) turned out to be the FIRST time prediction_patterns id=5 ever reached a prompt, because Monday 08-03's production run fired at 12:46 UTC while id=5 was written at 14:14 UTC — so 07-31 (BUY=7, decisive=10) and 08-03 (BUY=6, decisive=7) are clean pre-correction baselines, and the dry-run scored BUY=3 / SELL=0 / decisive=3 against historical ranges of BUY 4–10, SELL 1–7, decisive 7–17, below every observed minimum; note the MECHANISM differs from what HANDOFF_26 predicted — the model did not shift from BUY toward SELL, both directional buckets drained into the HOLD/WATCH middle (50→55), i.e. being told its own calls fail makes it decline to commit at all, which the regime caveat does not address since hedging technically honours it. That signal is n=1 with a ~4h intraday price offset, so Wed 08-05 and Fri 08-07 are the clean confirmation — run scripts/check_run.py (new this session, along with scripts/check_bands.py which re-derives ASSET_CLASS_BAND_SCALE quarterly and currently measures 0.306 against the pinned 0.30). Production is green since the s26 merge (07-29, 07-31, 08-03, ~4–5 min each) with both 48-minute total failures predating the batch fix, but batch resilience is STILL unexercised — no batch has run long enough to trigger the harvest path. The bill was measured from run_metrics: Mon/Wed $0.115, Friday $0.143, ≈$1.60/month on the ANTHROPIC API account, which is separate from the Claude subscription that funds sessions. Still owed by the user: the two dashboard how-to-read edits (track_record and ticker_deep_dive) — these must be edited IN PLACE in Grafana, NOT re-imported, because the deep-dive JSON carries no uid and predictions_dashboard.json hardcodes ma2wqvp in 3 places for its symbol click-through. Reddit still dark (0). Steps: (1) merge gate + confirm 146 tests pass + ask about the dashboard edits; (2) run scripts/check_run.py for Wed 08-05 and Fri 08-07 — the BUY/decisive verdict is the key check, plus whether Friday's mining persisted a row newer than id=5 (the max_tokens 8192 fix) and whether any long batch logged a PARTIAL tickers_ok rather than 0; (3) interpret the BUY signal — if decisive stays ≤6 the hedging is real and the gate is urgent, if it recovers to ≥7 the dry-run was an artifact of its price offset; (4) build the mechanical excess gate; (5) check Reddit creds. Then pick the next slice with the user from HANDOFF_27 step 6. Create the session worktree + branch (feat/session-28-), confirm the task list with the user, batch the work, validate (pytest expect 146+ using the main checkout's .venv — worktrees have none — and ALWAYS pass -p no:cacheprovider; for miner changes prefer the cheap single mining call ~$0.02 over a full $0.12 dry-run, closing the DB connection before the API call so it cannot write, and READ the output patterns rather than trusting that it returned; the user's shell exports ANTHROPIC_API_KEY as an EMPTY STRING which shadows .env, so prefix real-API runs with env -u ANTHROPIC_API_KEY; ClaudeClient(cfg) takes a Config built by load_config() from src.config — there is no Config.from_env(); the outcomes table is recommendation_outcomes with a verdict column and forward_return; write_prediction_patterns takes (conn, result, stats) — result FIRST; verify every ad-hoc DB write by reading it back, and verify no-write paths the same way; rawSql live with SET collation_connection = utf8mb4_unicode_ci, $ticker → quoted CSV, $__timeFilter → literal BETWEEN; migrations only with user sign-off and no semicolons in migration comments; any grading-band change needs a --regrade with sign-off; grafana JSONs have mixed unicode conventions — surgical text edits only; never `git add -A` blindly — read `git show --stat` before pushing), and close out per the ritual: update PLAN.md including its Decisions log, write handoffs/HANDOFF_28.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions + a learnings section, push without merging, and print the full next-session prompt in the chat.
>
> But before the above: some time may have passed since the last session. Take a look at the database and the dashboards first, evaluate how accurate the system has actually been, and adjust the parameters, values and code according to what you find — sessions 26 and 27 both proved this instruction pays for itself. Session 26's lesson was that a self-improving loop will faithfully amplify a measurement bug; session 27's is that **fixing the measurement does not fix the loop** — the miner was given correct market-relative data, cited it in every pattern, and ranked by the old broken number anyway. So before trusting any aggregate, ask whether the measurement could produce that result even if the finding were false; and before trusting any fix, verify its **effect** on what actually reaches production, not just that the mechanism works.
