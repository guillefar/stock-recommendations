# Handoff 13 — 2026-07-09 (session 13: session-12 merge, first production batch run, S17 flips-in-summary)

Continues [HANDOFF_12.md](HANDOFF_12.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 13 did

On branch **`feat/session-13-s17-flips`** (off `main` @ `c6aa78c`), worktree `.claude/worktrees/session-13-s17-flips`. Pushed, **not merged**.

1. **Solved the recurring track-record import failure and merged session 12.** The user's "still failing with weekStart conflicting values" report was **not** a bug in the session-12 fix — they were importing **main's stale working-tree copy** of `track_record_dashboard.json` (which also carried an uncommitted hand-edit shuffling braces; backed up to the session scratchpad, then discarded via `git checkout --`). The branch copy was verified clean: no `weekStart`/`nowDelay`/`quickRanges` in `timeSettings`, and `version` keys only at the **valid** `vizConfig` level (sibling of `spec` — the digest dashboard that imports fine has them there too; only `vizConfig.spec.version` is invalid). The user re-imported from the branch worktree path and **both dashboards render**. The "no UID / can't edit" symptom was explained fallout: schema-v2 JSON carries no `uid` — Grafana assigns one on save, and failed validation blocks saving, leaving an unsaveable preview. ff-merged `feat/session-12-review-fixes` → **`main` @ `c6aa78c`**, pushed (an untracked-but-identical `handoffs/HANDOFF_11.md` had to be removed first so the ff-merge wouldn't refuse).
2. **First production batch run verified** (user chose manual dispatch over waiting for the cron): run `29045521478` — `Submitted message batch msgbatch_01HCYAFkiQVS4zr15gxNhcaB (63 ticker requests)`, ended `63 succeeded, 0 errored`, `tickers_ok=63 tickers_failed=0`, cost line **$0.0836**. Job total 8m11s. Note: this wrote a **second batch of recs for 07-09** (19:47 UTC, >4h after the 12:26 UTC scheduled run, so the dedup window allowed it) — expect a double-rec day in D2/flip panels.
3. **S17 — action flips into the daily-summary prompt** (the user-picked slice):
   - [src/db.py](../src/db.py): new `get_latest_actions(conn) -> dict[ticker_id, action]` — each ticker's most recent stored action (self-join on `MAX(generated_at)`, same semantics as digest panel-9).
   - [src/main.py](../src/main.py): reads `get_latest_actions` **immediately before step 6c** (must happen before this run's rows land, or the query would see them); after each successful `write_recommendation`, appends `{symbol, prev_action, new_action}` when the action changed; logs the flip list; passes `analysis_data["action_flips"]`.
   - [src/analysis/claude_client.py](../src/analysis/claude_client.py) `generate_daily_summary`: renders a `Cambios de recomendación vs la corrida anterior:` block (`- FSLR: HOLD → SELL`, or `(ninguno)` when empty — matching the summary prompt's existing placeholder convention) and the `summary` field instruction now ends with "Si hubo cambios de recomendación, destácalos explícitamente (qué cambió y por qué es relevante)."
   - Flip semantics decision (PLAN decisions log): flip = persisted action vs immediately-preceding stored rec; first-ever rec ≠ flip; dedup-skipped recs still report their flip (in-memory comparison) — harmless, per-day summary upsert.
4. **Docs.** PLAN.md (current state, In progress, session-13 Done section, Wave 4 flip item now `[x]`, decisions-log entry); PROJECT_SUMMARY execution-flow steps 6c and 9 mention the flips.

## Validation evidence

- **pytest: 28 passed** (24 baseline + 4 new in [tests/test_summary_flips.py](../tests/test_summary_flips.py): prompt contains the flips block with real arrows; "(ninguno)" fallback; `main()` reports a flip on change; no flip on unchanged action or first run). `tests/test_main_resilience.py` now stubs `get_latest_actions`. Run: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`.
- **`get_latest_actions` against the live DB:** 63 rows (HOLD 25 / WATCH 25 / AVOID 5 / SELL 4 / BUY 4).
- **Full `--dry-run` through the real batch API** (2026-07-09 22:06, exit 0): **63 ok / 0 failed**, **8 real flips** detected and fed to the summary (RGTI HOLD→SELL, POET SELL→HOLD, AAPL WATCH→BUY, APLD WATCH→AVOID, ^STOXX50E BUY→WATCH, SPY BUY→WATCH, SOLS WATCH→AVOID, GEV WATCH→BUY), summary BULLISH, cost **$0.0871** (the flips block + call-out instruction add ~a cent).
- No dashboard JSON touched this session (no rawSql re-validation needed).

## Invariants (don't break)

- Never write to `stock-snapshots` tables. This repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes; real API calls at ~half price via the batch).
- Spanish in Claude prompts; English elsewhere.
- Ticker/batch/summary calls return `None` on failure — **never persist placeholders**.
- Grafana dashboards are **schema-v2** (`elements`/`layout`), datasource `{"name": "cfadv004ogglcf"}` group `mysql`, integer panel ids, `variables: []`. `timeSettings` must NOT contain `weekStart`/`nowDelay`/`quickRanges`; `version` is valid at `vizConfig` level but NOT inside `vizConfig.spec`. **When the user reports an import failure, first check WHICH file copy they imported** (worktree vs main) — that cost us a session-12→13 round trip.
- `get_latest_actions` must be read **before** step 6c persists — moving it later silently kills flip detection (it would compare a run against itself).
- Batch custom_ids must be `[A-Za-z0-9_-]` — never raw symbols (dots).
- Per-session ritual: worktree + branch first → confirm task list → batch work → close with docs + numbered handoff → push branch (never merge `main` yourself unless asked) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## State of play / caveats

- **`main` = `c6aa78c`** (session 12 merged, in production). This branch adds S17 only. Merge gate: user eyeballs a daily summary generated *with* flips (the next production run after merging) and confirms the Spanish reads well.
- **Production is green on the batch path** (verified run `29045521478`, $0.0836). Cost telemetry baseline: ~$0.083–0.087/run ≈ **$1.8/month** at 21 weekday runs.
- **2026-07-09 has two rec batches** (12:26 scheduled + 19:47 manual verification) — D2/flip panels will show a doubled day; one-off, self-explaining.
- **Reddit still dark** (`grep -c '^REDDIT_' .env` = 0). F4 dedup fix is already in production ahead of creds.
- **Local runs:** `env -u ANTHROPIC_API_KEY` (empty shell var shadows `.env`). Ad-hoc DB scripts: `load_dotenv('/home/guillo/Git/stock-recommendations/.env')`; add `SET collation_connection = utf8mb4_unicode_ci` when validating dashboard rawSql from Python (two `v_ticker_status_multi` panels false-fail otherwise).
- Carried: yfinance 404 ERROR lines (S13, cosmetic); 252 pre-price_checks matured candidates ungradeable; `price_snapshots` stale since 2026-05-22; price_checks gap 06-30→07-08 permanent.
- **Token levers still on the table** (HANDOFF_12): summary input truncation (first sentence of each reasoning, ~−3K in), 2-sentence reasoning cap (output = 5× input price), fewer news/Reddit lines → another 15–25% off; only worth it opportunistically at ~$1.8/month.

## Detailed TODO for session 14 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout: `git pull`, then `git worktree add .claude/worktrees/session-14-<slug> -b feat/session-14-<slug> main`, and inside it `ln -sf /home/guillo/Git/stock-recommendations/.env .env && ln -sf /home/guillo/Git/stock-recommendations/.venv .venv`.

**Step 1 — Merge gate for `feat/session-13-s17-flips`.**
1. Ask the user (AskUserQuestion) whether to merge S17. There is no dashboard to eyeball this time; the branch is small and fully tested, so the gate is light — offer "merge now" as the recommended option.
2. If approved: from the main checkout `git merge --ff-only feat/session-13-s17-flips && git push`.
3. After the next scheduled run (10:00 UTC weekdays), check the log (`gh run list --workflow=run_recommendations.yml --limit 3`, then `gh run view <id> --log | grep -i "flips\|Would upsert\|upserted"`) for the "Action flips vs previous run:" line, and have the user read that day's summary in the digest dashboard — it should explicitly mention any flips.

**Step 2 — Confirm Reddit creds status.** `grep -c '^REDDIT_' .env`. If >0: add the three secrets to GitHub Actions too, run one real cycle, verify `reddit_mentions` rows are deduped (F4), then unblock Wave-4 "batched Reddit sentiment".

**Step 3 — Pick the next slice with the user** (AskUserQuestion). Ranked suggestions (fresh):
1. **S5 — weekly retrospective** (the biggest remaining Wave-4 item): on Friday runs, one extra Haiku call summarizing the week — calls vs outcomes (join `recommendation_outcomes` for the week), flips, sector exposure; persist (needs a table or a `daily_market_summary` variant row) + a digest panel. Design the storage with the user first.
2. **Migration 004 — trending-unknown persistence**: table `trending_tickers` (symbol, first_seen, last_seen, mention_count, score); upsert from `find_trending_unknown`; small dashboard table "candidates to watchlist".
3. **S18 remainder** — tests for `extract_ticker_mentions` stopwords (`IT`, `GO`, `BE`), the 4h dedup window, `_pct_change`/`_compute_rsi` edge fixtures.
4. **S13** — silence the cosmetic yfinance 404 ERROR lines (logging filter on `yfinance` logger).
5. **Token trims** (HANDOFF_12 caveats) — only if the user re-raises cost.

**Step 4 — Validate** the session-13 way: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`, full `env -u ANTHROPIC_API_KEY .venv/bin/python -m src.main --dry-run` (expect 63 ok / 0 failed; batch adds ~3–6 min), extract-and-run any touched dashboard rawSql with the collation init_command, apply any new migration to the DB only after user sign-off.

**Step 5 — Close out per the ritual.** Update PLAN.md; write `handoffs/HANDOFF_14.md` with a complete copy-pasteable next prompt + a detailed TODO an older model can follow + fresh suggestions; commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_13.md and PLAN.md before doing anything — HANDOFF_13 has the detailed step-by-step TODO for session 14; follow it in order. Context: main is at c6aa78c (session 12 merged: batch API in production, verified run 29045521478 at $0.0836/run; predictions + track-record dashboards both render — the earlier import failures were the user importing main's stale working-tree copy instead of the fixed branch file). Session 13 (branch feat/session-13-s17-flips, pushed NOT merged, off main = c6aa78c) delivered S17: src/db.py get_latest_actions reads each ticker's previous stored action BEFORE step 6c persists (order matters — later would compare the run against itself), main.py collects {symbol, prev_action, new_action} flips for persisted recs and passes analysis_data["action_flips"], and generate_daily_summary renders a "Cambios de recomendación vs la corrida anterior:" block ("(ninguno)" when empty) plus an instruction to highlight changes explicitly. Validation: pytest 28 passed; get_latest_actions returns 63 rows live; full dry-run 63 ok / 0 failed with 8 real flips fed to the summary (e.g. RGTI HOLD→SELL, AAPL WATCH→BUY), cost $0.0871. Your step 1 is the light merge gate: ask the user (AskUserQuestion) to merge S17 (recommended — no dashboard to eyeball, fully tested); if yes, ff-only merge to main, push, and after the next 10:00 UTC scheduled run check the log for the "Action flips vs previous run:" line and have the user read the day's summary. Then check Reddit creds (grep -c '^REDDIT_' .env — still 0 as of 07-09), and pick the next slice with the user: S5 weekly retrospective (recommended — design storage with the user first), migration 004 trending-unknown persistence, S18 remaining tests, S13 yfinance-404 silencing, or token trims (HANDOFF_12 caveats). Create the session worktree + branch (feat/session-14-<slug>) first, confirm the task list with the user, batch the work, validate (pytest + full dry-run + rawSql extraction with SET collation_connection = utf8mb4_unicode_ci), and close out per the ritual: update PLAN.md, write handoffs/HANDOFF_14.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push without merging, and print the full next-session prompt in the chat.
