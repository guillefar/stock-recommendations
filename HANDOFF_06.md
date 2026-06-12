# Handoff 06 — 2026-06-12 (session 06)

Continues [HANDOFF_05.md](HANDOFF_05.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](PLAN.md); structural map in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); design spec in [SPEC.md](SPEC.md).

## What session 06 did — Wave 1.5 complete

Branch **`feat/session-06-wave-1-5`** (off `main` @ `604e229`), in worktree `.claude/worktrees/session-06-wave-1-5`. Pushed, **not merged** — merging is the user's call and the first gate for next session.

1. **Grading semantics decided + implemented** (user picked from data-grounded options):
   - **WATCH is movement-graded**: CORRECT if |forward_return| ≥ 5% (`WATCH_MOVE_THRESHOLD`), INCORRECT if |forward_return| < 2% (the watch wasted attention), NEUTRAL between.
   - **HOLD has a −10% loss band** (`HOLD_LOSS_BAND`): INCORRECT below −10%, CORRECT if flat (|return| ≤ 2%), NEUTRAL otherwise; upside never penalized.
   - BUY/SELL/AVOID unchanged (directional, ±2% neutral band).
   - `grade()` in [src/evaluate_outcomes.py](src/evaluate_outcomes.py); [tests/test_outcomes.py](tests/test_outcomes.py) rewritten (4 tests).
2. **Backfill re-graded** (authorized destructive step): all 693 `recommendation_outcomes` rows deleted, evaluator re-run → 693 rows again. **Verdicts: 113 C / 326 I / 254 N → 335 C / 155 I / 203 N** (WATCH 250/81/104, HOLD 84/74/99, AVOID 1 C). Matched the predicted distribution exactly.
3. **S1 landed.** [migrations/003_create_price_checks.sql](migrations/003_create_price_checks.sql) **applied to the DB**; `write_price_check` upsert in [src/persistence/writers.py](src/persistence/writers.py) (dry-run-safe, warns + skips on NULL price); called in [src/main.py](src/main.py) right after the technical fetch (price lands even if the rec later fails); `_fetch_matured` carries a `price_checks` exit candidate (calendar-day window — it's a DATE column) and the loop prefers `price_snapshots`, falling back to `price_checks`.
4. **Bonus fix — NaN closes (important).** 21/63 tickers (all European ETFs: XESC.DE, VUSA.AS, SPY5.PA, …) had `technical.price = None` because yfinance emits today's row with a NaN Close mid-session. That means Claude saw `price: None` for them and their recommendations stored **NULL entry prices** (ungradeable). [src/collectors/prices.py](src/collectors/prices.py) now drops NaN closes before taking the last. Validated by re-fetching exactly those 21 tickers: 21/21 got prices.
5. **D1+D2 digest panels** in [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json), schema v2: panel-9 "Same-day run disagreements (D1)" (self-join table, action-colored columns) and panel-10 "Action mix over time (D2)" (stacked-bar timeseries, per-action colors). Both queries validated against the live DB. D1 is legitimately **empty today** — no day has two disagreeing runs yet.

## Validation evidence

- pytest: **4/4 pass**.
- `src.main --dry-run`: 63 ok / 0 failed, no writes (price-check writes log `[dry-run]`).
- One real `src.main`: exit 0, 63 ok; recommendation inserts dedup-skipped (within 4h of the cron run — expected); price_checks upserted.
- `evaluate_outcomes --dry-run` after the changes: clean; 252 matured candidates remain ungradeable (no exit price in either table — see caveats).
- `price_checks` end-of-session: **63 rows today, one per active ticker**.
- Re-grade before/after: 326→155 INCORRECT, 113→335 CORRECT, 254→203 NEUTRAL.

## State of play / caveats

- **`feat/session-06-wave-1-5` pushed, not merged.** The GitHub cron runs `main`, so **no `price_checks` accumulate from the cron until the user merges.** Merging is step 1 of next session.
- New recommendations become gradeable at 7d once `price_checks` spans the horizon — i.e. ~7 days **after the merge**.
- The 252 ungradeable matured candidates (recs ~2026-05-29 → 2026-06-05) will mostly stay ungradeable forever: no exit price exists in any table for their horizon window. Accept the gap.
- Pre-fix recs of the 21 European ETFs have NULL entry prices → also permanently ungradeable (unless backfilled, see S11).
- **Reddit is still dark** — `.env` has none of `REDDIT_CLIENT_ID/SECRET/USER_AGENT` (checked this session). https://www.reddit.com/prefs/apps, "script" app; also add the three GitHub Actions secrets.
- The user's Code OSS client renders replies collapsed to one line (content is intact when selected). Client-side issue; keep all substance in final messages / AskUserQuestion dialogs regardless.

## Invariants (don't break)

- Never write to `stock-snapshots` tables (read-only). Tables this repo owns: `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- Grafana dashboards must be **schema-v2** (`elements`/`layout`) — classic schema fails import on the user's Grafana 13.1.x.
- Per-session ritual: **worktree + branch first** → confirm task list → batch work → close with docs + numbered handoff (complete next prompt, detailed TODO an older model can follow, fresh suggestions) → push the branch (never merge to `main` yourself) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs — put any explanation they must read inside the question text/options or in the final message, never in mid-turn text.

## Suggestions (fresh, for discussion; NOT committed work)

- **S11 — Backfill NULL entry prices (low effort, recovers data).** ~21 European-ETF recs per old run are permanently ungradeable only because `technical.price` is NULL. A one-off script could fetch each rec's historical close (yfinance `history`) for `DATE(generated_at)` and patch `technical.$.price`. Recovers hundreds of gradeable rows cheaply.
- **S12 — price_checks gap-fill (low effort, resilience).** If the cron fails for a few days, exit prices vanish for those horizons again. A small step in `evaluate_outcomes` (or main) could fetch missing daily closes for the last N days from yfinance history and upsert them into `price_checks` — making grading robust to outages.
- **S7 — prompt/model provenance columns** (carried from HANDOFF_05, still good: makes prompt changes A/B-queryable).
- **S8 — per-run daily summaries** (carried: the per-day upsert still loses the morning run's sentiment; pairs with D1).
- **D3 is now unblocked**: the confidence-calibration panel (Wave 4) was sequenced after the semantics fix — that fix is in. Natural next dashboard work.

## Detailed TODO for session 07 (step-by-step; follow in order)

**Step 0 — Orient.** Read [HANDOFF_06.md](HANDOFF_06.md) (this file) and [PLAN.md](PLAN.md) completely. Session 07 scope: **post-merge verification + D3 panel + start Wave 2** (ticker news + earnings awareness).

**Step 1 — Merge gate.** Ask the user to confirm `feat/session-06-wave-1-5` is merged to `main` (or to merge it now — never merge yourself). If it isn't, stop and resolve that first; everything downstream depends on the cron running the new code.

**Step 2 — Workspace.** From the main checkout: `git checkout main && git pull`. Create the session worktree + branch (`git worktree add .claude/worktrees/session-07-<topic> -b feat/session-07-<topic> main`), then inside it:
```bash
ln -s /home/guillo/Git/stock-recommendations/.env .env
ln -s /home/guillo/Git/stock-recommendations/.venv .venv
```
Confirm the session task list with the user (explanations inside the AskUserQuestion, not mid-turn prose). Also re-check Reddit creds: `grep -c '^REDDIT_' .env` (0 as of session 06).

**Step 3 — Post-merge verification (read-only).** Check the cron has run the new code since the merge: `SELECT as_of_date, COUNT(*) FROM price_checks GROUP BY as_of_date ORDER BY as_of_date DESC LIMIT 5` (expect ~63/day on weekdays after the merge date) and `SELECT COUNT(*) FROM recommendation_outcomes` (will exceed 693 once post-merge recs mature at 7d). If the cron hasn't fired yet, note it and continue.

**Step 4 — D3: confidence-calibration panel.** In [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json) (schema v2 only; copy panel-9/panel-10 structure): hit-rate by confidence band. Validate first against the DB, e.g.:
```sql
SELECT CASE WHEN confidence >= 0.8 THEN '0.8+'
            WHEN confidence >= 0.6 THEN '0.6–0.79'
            ELSE '0.4–0.59' END AS band,
       action, COUNT(*) AS n,
       ROUND(100 * SUM(verdict = 'CORRECT') / COUNT(*), 1) AS hit_rate
FROM recommendation_outcomes
GROUP BY band, action ORDER BY band, action;
```
Add it as panel-11 (id 11) + a GridLayoutItem at the bottom (next free y is 72).

**Step 5 — Wave 2 item 1: ticker news in the prompt.** `fetch_ticker_news` exists at [src/collectors/prices.py](src/collectors/prices.py) but is never called. In [src/main.py](src/main.py), fetch top ~5 headlines per ticker and pass them into `run_ticker_recommendation` → include a "Noticias recientes:" block in the per-ticker prompt ([src/analysis/claude_client.py](src/analysis/claude_client.py) / recommendation.py — prompts in Spanish). Degrade gracefully (empty list → omit the block).

**Step 6 — Wave 2 item 2: earnings awareness.** Fetch the next earnings date via yfinance (`Ticker.calendar` — guard with try/except, schema varies) and add "Próximo earnings: …" to the ticker prompt when known.

**Step 7 — Validate.** `.venv/bin/python -m pytest tests/ -q`; `.venv/bin/python -m src.main --dry-run` full pass (63 ok expected; prompts changed, so spot-check a few logged actions look sane). No real run needed unless the user wants one (the cron now covers real runs).

**Step 8 — Close out.** Update PLAN.md (check off Wave 2 items done, refresh Current state, decisions log if any). Write HANDOFF_07.md: what was done, validation evidence, complete copy-pasteable next prompt, detailed TODO, fresh suggestions. Commit, push the branch (no merge), print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read HANDOFF_06.md and PLAN.md before doing anything — HANDOFF_06 contains the detailed step-by-step TODO for this session (session 07); follow it in order. Context: session 06 completed Wave 1.5 on branch feat/session-06-wave-1-5 (pushed, NOT merged): new grading semantics (WATCH movement-graded ≥5%/<2%, HOLD −10% band) implemented and the 693 outcomes re-graded to 335 CORRECT / 155 INCORRECT / 203 NEUTRAL; S1 price_checks landed (migration applied, 63/63 tickers covered on 2026-06-12) plus a NaN-close fix for 21 European ETFs; D1+D2 digest panels added. First confirm with me that I merged feat/session-06-wave-1-5 to main — the cron writes no price_checks until then. Then create the session worktree + branch and confirm the task list with me. Session 07 scope: verify post-merge cron output (price_checks per day, outcomes count), add the D3 confidence-calibration panel to the digest (schema v2, validate the SQL against the DB first), then start Wave 2: wire fetch_ticker_news into the per-ticker prompt (top ~5 headlines, Spanish prompt block, graceful when empty) and add next-earnings-date awareness via yfinance. Validate with pytest and a full --dry-run; no real run needed (cron covers it). Also check whether I added the Reddit credentials yet. Close out per the ritual: update PLAN.md, write HANDOFF_07.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push the branch without merging, and print the full next-session prompt in the chat.
