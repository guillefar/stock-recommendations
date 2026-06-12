# Handoff 04 — 2026-06-12 (session 04)

Continues [HANDOFF_03.md](HANDOFF_03.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](PLAN.md); structural map in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); design spec in [SPEC.md](SPEC.md).

## What session 04 did — Wave 1 (Correctness & unblocking)

All code items of Wave 1, on branch **`fix/wave-1-correctness`** (off `main` @ `241caa5`). **Not yet merged.**

1. **Per-run dedup.** [src/persistence/writers.py](src/persistence/writers.py): `write_recommendation` skips only if the ticker already has a row within `DEDUP_WINDOW_HOURS = 4` (was: same calendar day). Fixes the 2×/day no-op bug; the 17:00 ART run now writes real rows. Same-slot workflow retries are still deduped.
2. **Parse failures are never persisted.** `analyze_ticker` ([src/analysis/claude_client.py](src/analysis/claude_client.py)) returns `None` on unparseable JSON instead of a fake `HOLD/0.5` row; the wrapper in [src/analysis/recommendation.py](src/analysis/recommendation.py) is typed `dict | None` accordingly.
3. **Per-ticker error isolation.** Per-ticker body in [src/main.py](src/main.py) wrapped in try/except → log + count + continue. Missing technicals and `None` recommendations also count as failures. Final log line: `tickers_ok=… tickers_failed=… (failed: […])`. Exits non-zero (SystemExit(1)) only when *every* ticker failed.
4. **`evaluate_outcomes` scheduled.** New step after `src.main` in [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml), with `if: ${{ !cancelled() }}` so grading runs even if the main step fails. It needs `ANTHROPIC_API_KEY` in env only because `load_config()` requires the var; the evaluator never calls Claude.
5. **Fold-in: single DB connection.** main opens one connection for the whole run (was 2+2N opens), with `conn.ping(reconnect=True)` before each write phase since the connection idles during Claude/yfinance calls.

## Validation done

- `python -m src.main --dry-run` — full pass: **63 tickers ok / 0 failed**, no DB writes, summary generated.
- `python -m src.evaluate_outcomes --dry-run` — **693 candidates graded at 7d, 0 at 30d** (see surprise below).
- `tests/test_outcomes.py` — 3/3 pass. pytest was installed **into the local venv only**; adding it to requirements is still Wave 3.

## New finding (corrects HANDOFF_03/PLAN claims)

The "outcomes grade 0 rows" claim was wrong. `price_snapshots` is stale (last row 2026-05-22) but old recommendations **matured against the snapshots that do exist**: the evaluator's first scheduled run will **backfill ~693 outcome rows at the 7d horizon**, all from the old always-HOLD/WATCH prompt era. Expect the digest's hit-rate panels to suddenly populate — dominated by HOLD/WATCH grading semantics (the Wave 3 "grading semantics" decision becomes more urgent once this lands).

## State of play

- **Branch `fix/wave-1-correctness` is pushed but NOT merged to `main`** — the merge is the user's call (or step 1 of the next session if they authorize it in the prompt).
- **No real (non-dry-run) run yet** with the decisive prompt — DB still holds only old WATCH/HOLD rows.
- **Reddit is dark** — `REDDIT_CLIENT_ID/SECRET/USER_AGENT` still missing (user-side task, still open from Wave 1).
- `price_snapshots` still stale for *new* recommendations (last row 2026-05-22); external to this repo.

## Invariants (don't break)

- Never write to `stock-snapshots` tables. Read-only. (Writing to **new tables this repo owns** is fine — see suggestion S1.)
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- Per-session ritual: branch first → confirm task list → batch work → close with docs + numbered handoff (containing the **complete** next prompt, a detailed TODO an older model can follow, and new-functionality/redesign suggestions) → push the branch (never merge to `main` yourself) → show the full next prompt in chat.

## Suggestions — new functionality / redesigns (for discussion, NOT committed work)

Proposals beyond the agreed Waves 2–4. The user picks which (if any) enter the roadmap; record the decision in PLAN.md's decisions log.

- **S1 — In-repo price-snapshot fallback (highest value).** Outcome grading for *new* recommendations is blocked on the external, stale `price_snapshots` collector. Add a migration-003 table owned by this repo (e.g. `price_checks(ticker_id, as_of_date, price)`), write one row per ticker at the end of each run (the price is already fetched in `technical`), and make `evaluate_outcomes` fall back to it when `price_snapshots` has no row in the horizon window. Removes the external dependency without touching the read-only invariant. ~Medium effort.
- **S2 — Track-record feedback loop.** Once `recommendation_outcomes` has rows (it will, after the 693-row backfill), inject each ticker's recent graded history into its prompt ("Tus últimas 5 llamadas en NVDA: 3 CORRECT…"), so the model can self-calibrate confidence. ~Low effort, needs S1 or resumed snapshots to stay fresh.
- **S3 — Tiered model escalation.** Keep Haiku for routine calls; when a HOLDING ticker gets a SELL, or confidence ≥ 0.8, get a second opinion from Sonnet and persist the agreed/Sonnet call (log disagreements). Protects the highest-stakes decisions for cents per run. ~Low-medium effort.
- **S4 — Paper-trading simulation.** Translate BUY/SELL recommendations into a virtual portfolio (fixed position size), track simulated P&L vs a SPY buy-and-hold benchmark on the dashboard. The honest "does this system make money?" metric, beyond per-call hit rates. ~Medium-high effort, best after S1.
- **S5 — Weekly retrospective digest.** On Friday's second run (or Monday's first), one extra Claude call writes a weekly review — calls vs outcomes, action flips, sector exposure — stored alongside the daily summary + a dashboard panel. Complements Wave 4's flip detection. ~Low effort.
- **S6 — Event-driven runs (bigger redesign).** A lightweight hourly workflow that checks intraday moves of holdings (yfinance only, no Claude) and triggers the full pipeline when any holding moves >3–4%. Only worth it if timeliness matters to the user; otherwise skip. ~Medium effort.

## Detailed TODO for the next session (step-by-step; follow in order)

**Step 0 — Orient.** Read [HANDOFF_04.md](HANDOFF_04.md) (this file) and [PLAN.md](PLAN.md) completely before editing anything.

**Step 1 — Merge Wave 1 (only with the user's authorization, which the prompt below grants).**
```bash
git checkout main && git pull
git merge --ff-only fix/wave-1-correctness
git push
```
If `--ff-only` fails, stop and show the user the divergence instead of forcing anything.

**Step 2 — Branch for this session.** `git checkout -b <type>/session-05-<topic>` off the updated `main`. Then write the session task list and **confirm it with the user before executing**.

**Step 3 — Check Reddit credentials.** Run `grep -E '^REDDIT_(CLIENT_ID|CLIENT_SECRET|USER_AGENT)=.+' .env`. If all three are present, verify the collector works:
```bash
.venv/bin/python -c "from dotenv import load_dotenv; load_dotenv(); from src.config import load_config; from src.collectors.reddit import fetch_reddit_posts; print(len(fetch_reddit_posts(load_config())), 'posts')"
```
Expect a non-zero post count. If creds are missing, remind the user (https://www.reddit.com/prefs/apps, "script" app; also add the three GitHub Actions secrets) and continue — the run works without Reddit.

**Step 4 — First real (non-dry-run) execution.**
```bash
.venv/bin/python -m src.main          # NO --dry-run; this writes to the DB on purpose
echo "exit code: $?"
.venv/bin/python -m src.evaluate_outcomes
```
Expect: `tickers_ok=~63 tickers_failed=0` in the final log line, and the evaluator writing ~693 outcomes at 7d.

**Step 5 — Sanity-check the DB.** Use the repo's own connection (creds come from `.env`):
```bash
.venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv()
from src.config import load_config; from src.db import get_connection
conn = get_connection(load_config()); cur = conn.cursor()
cur.execute(\"SELECT action, COUNT(*) c FROM recommendations WHERE generated_at >= CURDATE() GROUP BY action\"); print('today:', cur.fetchall())
cur.execute(\"SELECT COUNT(*) c FROM recommendation_outcomes\"); print('outcomes:', cur.fetchone())
cur.execute(\"SELECT summary_date, overall_sentiment FROM daily_market_summary ORDER BY summary_date DESC LIMIT 1\"); print('summary:', cur.fetchone())
conn.close()"
```
Expect: one recommendation row per ticker for today (actions should now include some non-WATCH/HOLD), ~693 outcome rows, today's summary row.

**Step 6 — Verify the 4h dedup.** Run `.venv/bin/python -m src.main` a second time (within 4h of step 4). Expect every ticker to log `Skipping duplicate recommendation … (row within last 4h)` and the today-count from step 5 to be unchanged. (This burns one set of Claude calls — acceptable, it's the verification of the Wave 1 fix.)

**Step 7 — Roadmap discussion.** Show the user the S1–S6 suggestions above and ask which to adopt; record decisions in PLAN.md (decisions log + roadmap).

**Step 8 — If time remains: start Wave 2 item 1** (wire `fetch_ticker_news` from [src/collectors/prices.py](src/collectors/prices.py#L43) into the per-ticker prompt, top ~5 headlines) — only after re-confirming with the user.

**Step 9 — Close out.** Update PLAN.md (check off "first real execution", and "Reddit creds" if done; refresh Current state). Write HANDOFF_05.md including: what was done, validation evidence, a **complete copy-pasteable next-session prompt**, a **detailed step-by-step TODO like this one**, and a **fresh suggestions section**. Commit, **push the session branch** (do not merge), and **print the full next-session prompt in the chat reply**.

## Prompt for the next session (copy-paste exactly)

> Read HANDOFF_04.md and PLAN.md before doing anything — HANDOFF_04 contains the detailed step-by-step TODO for this session; follow it in order. Context you need: Wave 1 (correctness fixes: 4h per-run dedup, no parse-failure persistence, per-ticker error isolation, scheduled evaluate_outcomes, single DB connection) is implemented and validated on branch `fix/wave-1-correctness`, which is pushed but not merged. I authorize the fast-forward merge of `fix/wave-1-correctness` into `main` as step 1. Then: create a session branch, confirm the task list with me, check whether I added the Reddit credentials, do the FIRST REAL (non-dry-run) execution of `python -m src.main` and `python -m src.evaluate_outcomes`, sanity-check the DB with the queries in HANDOFF_04 (expect ~693 backfilled 7d outcomes), and verify the 4h dedup with a second run. Then walk me through the S1–S6 suggestions in HANDOFF_04 and ask which I want in the roadmap. If time remains, start Wave 2 item 1 (wire fetch_ticker_news into the ticker prompt). Close out per the ritual: update PLAN.md, write HANDOFF_05.md with the complete next prompt + a detailed TODO that older LLM models can follow + new functionality/redesign suggestions, push the branch without merging, and print the full next-session prompt in the chat.
