# Handoff 14 — 2026-07-10 (session 14: S17 merge + long-term reorientation)

Continues [HANDOFF_13.md](HANDOFF_13.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 14 did

On branch **`feat/session-14-long-term`** (off `main` @ `f28053f`), worktree `.claude/worktrees/session-14-long-term`. Pushed, **not merged**.

1. **Merged S17** (`feat/session-13-s17-flips` ff → `main` @ `f28053f`, pushed). The production verification (the "Action flips vs previous run:" log line + the flips call-out in the day's Spanish summary) is still pending — the next 10:00 UTC scheduled run is the first one carrying S17.
2. **The user declared their long-term orientation** (now also in auto-memory as `predictions-long-term-orientation`): positions are held for months/years; predictions must target ≥1 month, 1 year, and long term — not week-to-week trading. Everything below implements that (all options confirmed via AskUserQuestion).
3. **Per-horizon grading** ([src/evaluate_outcomes.py](../src/evaluate_outcomes.py)): `Bands` dataclass + `HORIZON_BANDS` = {7: ±2%/5%/10%, 30: ±4%/10%/15%, 90: ±7%/15%/20%, 365: ±15%/30%/30%} (neutral/WATCH-move/HOLD-loss; ~√time scaling — user choice over flat bands). `grade(action, fwd, horizon)` looks bands up by horizon; `HORIZONS` is derived from the table, so 90d/365d grading is live (first matured ≈ 2026-08-15 / 2027-05-17; earliest rec is 2026-05-17).
4. **30d re-grade executed** (user-authorized): `DELETE … WHERE horizon_days = 30` (1,134 rows) + real evaluator run re-wrote all 1,134 → **382 C / 363 I / 389 N, 30d hit rate 51%** (was 470/270/394 = 64% under the too-easy ±2% band). 7d rows untouched (1,803).
5. **Prompt reorientation** ([src/analysis/claude_client.py](../src/analysis/claude_client.py)): `_RECOMMENDATION_SYSTEM` now frames a long-term investor (months/years, don't flip on short-term noise); the per-ticker prompt gets a "Horizonte de inversión: mínimo un mes…" block (short-term indicators = entry timing only; a weekly move doesn't invalidate a months-long thesis); HOLDING→SELL requires *long-term-thesis* deterioration; WATCHLIST→BUY is an entry "para una posición de varios meses"; `reasoning` must cite "la tesis al horizonte de 1+ mes"; the daily summary is addressed to a long-term investor.
6. **Dashboards re-defaulted to 30d**:
   - `track_record_dashboard.json`: the 3 scorecard tiles + sector + RSI tables retitled "(30d)" and repinned `horizon_days=30`; the weekly trend now plots 30d (green, headline), 7d (super-light-green, timing diagnostic), 90d (blue) and 365d (purple) hit % + "30d decided" bars on the right axis; how-to-read rewritten (bands widen with horizon, maturity dates).
   - `predictions_dashboard.json`: per-ticker hit rate subquery → 30d; same new trend query; how-to-read updated + horizon note.
   - `daily_digest_dashboard.json`: panel-11 (confidence calibration) pinned to 30d — it previously **mixed all horizons in one aggregate** (pre-existing wart, worse with 4 horizons). Panels 6/7 group by horizon and need no change.
7. **Repaired the user's hand-edit of `track_record_dashboard.json`** (was uncommitted on main, backed up to the session scratchpad): their intent — `version` keys at the `vizConfig` level (sibling of `spec`; valid, the digest has them there) — was right, but the manual brace edits pushed panels 2–7 **out of `elements` to the document top level** (Grafana would render only panel-1). Rebuilt from the committed copy + `"version": "13.2.0-28852654685"` on panels 1–5 (6–7 keep their existing 13.1.0 value). Main's working tree was reset to the committed copy; **the repaired file lives on this branch — the user must import from the session-14 worktree path** (or after merge).
8. **Docs**: PLAN (current state, In progress, session-14 Done, 3 decisions-log entries), PROJECT_SUMMARY (outcomes table line), README (track-record description).

## Validation evidence

- **pytest: 34 passed** (28 baseline + 6 new: `test_outcomes.py` per-horizon band tests, `test_prompt_horizon.py` system/ticker-prompt long-term framing). Run: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`.
- **Full `--dry-run` through the real batch API** (2026-07-10 ~02:03 UTC, exit 0): **63 ok / 0 failed**, summary MIXED, cost **$0.0991** (the horizon block adds ~1¢/run vs $0.0871). 11 flips detected vs the previous stored run — the first run under the new prompt re-decides everything, expect flip volume to settle.
- **All 21 dashboard rawSql queries** (4 dashboards) ran green against the live DB via the scratchpad harness (`SET collation_connection = utf8mb4_unicode_ci` as init_command; `$__timeFilter(x)` → `x >= '2026-05-01'`). Spot values: 30d hit 64% pre-re-grade / decisiveness 65% / 740 decided in the May-window; sector table 7 rows, RSI 5 rows at 30d.
- **Post-re-grade DB state**: 7d = 1,803 rows (703/483/617, 59%); 30d = 1,134 rows (382/363/389, **51%**); 90d/365d = 0 (nothing matured — correct).

## Invariants (don't break)

- Never write to `stock-snapshots` tables. This repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes; real API calls at ~half price via the batch).
- Spanish in Claude prompts; English elsewhere.
- Ticker/batch/summary calls return `None` on failure — **never persist placeholders**.
- **Long-term orientation (user, 2026-07-10)**: 30d is the headline horizon; 7d is a diagnostic only; prompts demand a ≥1-month thesis. Don't reintroduce 7d-first framing in new panels or prompts.
- **Grading bands are per-horizon** (`HORIZON_BANDS`); changing them re-defines verdicts — user decision + re-grade required, never silent.
- Grafana dashboards are **schema-v2** (`elements`/`layout`), datasource `{"name": "cfadv004ogglcf"}` group `mysql`, integer panel ids, `variables: []`. `timeSettings` must NOT contain `weekStart`/`nowDelay`/`quickRanges`; `version` is valid at `vizConfig` level but NOT inside `vizConfig.spec`. Repair dashboards programmatically (parse → assert → dump), never by manual brace edits. When the user reports an import failure, **first check WHICH file copy they imported** (worktree vs main).
- `get_latest_actions` must be read **before** step 6c persists (S17 flip detection).
- Batch custom_ids must be `[A-Za-z0-9_-]` — never raw symbols (dots).
- Per-session ritual: worktree + branch first → confirm task list → batch work → close with docs + numbered handoff → push branch (never merge `main` yourself unless asked) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## State of play / caveats

- **`main` = `f28053f`** (S17 in production). This branch adds the long-term reorientation. Merge gate: user imports the three touched dashboards **from this branch/worktree** (track-record also carries their repaired hand-edit — the copy on main renders only panel-1 in spirit; the working-tree stale-copy trap already cost sessions 12→13 a round trip) and eyeballs the 30d panels; plus the first post-merge production run.
- **Expect elevated flips right after merge**: the reoriented prompt re-decides every ticker (11 flips in the dry-run). One noisy day is expected; if flip volume stays high after a few runs, the "don't flip on weekly noise" instruction may need reinforcement — check digest panel-9 trend.
- **The 30d headline is now 51%**, not 64% — that's the band change, not a regression. Weekly-trend history redraws under the new verdicts too.
- **90d/365d panels/series render empty until maturity** (≈ 2026-08-15 / 2027-05-17). Not a bug.
- **price_checks horizon reach**: 365d grading needs a price ~a year after each rec; the table only accumulates from 2026-06-12, so 1y outcomes for the earliest recs (2026-05-17…06-11) depend on `price_snapshots` or stay ungradeable — same known-gap class as before.
- **Reddit still dark** (`grep -c '^REDDIT_' .env` = 0 as of 07-10).
- **Local runs:** `env -u ANTHROPIC_API_KEY` (empty shell var shadows `.env`). Ad-hoc DB scripts: `load_dotenv('/home/guillo/Git/stock-recommendations/.env')`; add `SET collation_connection = utf8mb4_unicode_ci` when validating dashboard rawSql from Python.
- Carried: yfinance 404 ERROR lines (S13, cosmetic); 252 pre-price_checks matured candidates ungradeable; `price_snapshots` stale since 2026-05-22; price_checks gap 06-30→07-08 permanent; token levers (HANDOFF_12) still optional.

## Detailed TODO for session 15 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout: `git pull`, then `git worktree add .claude/worktrees/session-15-<slug> -b feat/session-15-<slug> main`, and inside it `ln -sf /home/guillo/Git/stock-recommendations/.env .env && ln -sf /home/guillo/Git/stock-recommendations/.venv .venv`.

**Step 1 — Verify S17 in production** (it merged before the reorientation, so any post-07-10 scheduled run carries it). `gh run list --workflow=run_recommendations.yml --limit 3`; on the latest run `gh run view <id> --log | grep -i "Action flips"`. Have the user read that day's summary in the digest dashboard — it should call the flips out explicitly. If no flips occurred that day, "(ninguno)" + no call-out is correct behavior.

**Step 2 — Merge gate for `feat/session-14-long-term`** (AskUserQuestion). The user must import all three touched dashboards **from the session-14 worktree path** (`.claude/worktrees/session-14-long-term/grafana/…`) — stress this, the stale-main-copy trap is real — and eyeball: (a) track-record tiles say "(30d)" and show ~51% / ~65% / ~740-ish (time-range dependent), (b) the trend chart shows the 30d + 7d series (90d/365d legitimately absent), (c) predictions table's per-ticker hit rate populated, (d) digest panel-11 titled "(D3, 30d)". If approved: `git merge --ff-only feat/session-14-long-term && git push` from the main checkout. After the next scheduled run, confirm cost (~$0.10) and skim the summary's long-term tone.

**Step 3 — Check Reddit creds** (`grep -c '^REDDIT_' .env`). If >0: add the three secrets to GitHub Actions, run one real cycle, verify `reddit_mentions` dedup, unblock Wave-4 batched Reddit sentiment.

**Step 4 — Pick the next slice with the user** (AskUserQuestion). Ranked suggestions (fresh, long-term lens):
1. **S5 — weekly retrospective** (recommended; biggest remaining Wave-4 item, now naturally long-term): on Friday runs, one extra Haiku call reviews the week's calls vs 30d outcomes, flips, and sector exposure. **Design storage with the user first** (new table vs a `daily_market_summary` variant row) before writing code; add a digest panel.
2. **Flip-stability watch**: if production shows sustained high flip volume under the new prompt, add a small "flips per run" stat/trend panel and consider reinforcing the no-noise-flips instruction. Cheap, directly protects the long-term story.
3. **Migration 004 — trending-unknown persistence**: table `trending_tickers` (symbol, first_seen, last_seen, mention_count, score); upsert from `find_trending_unknown`; "candidates to watchlist" table panel. (Only useful once Reddit creds exist — otherwise it stays empty.)
4. **S18 remainder** — tests for `extract_ticker_mentions` stopwords (`IT`, `GO`, `BE`), the 4h dedup window, `_pct_change` fixtures.
5. **S13** — silence the cosmetic yfinance 404 ERROR lines (logging filter on the `yfinance` logger).

**Step 5 — Validate** the standard way: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`; full `env -u ANTHROPIC_API_KEY .venv/bin/python -m src.main --dry-run` (expect 63 ok / 0 failed, ~$0.10, batch adds ~3–6 min); extract-and-run any touched dashboard rawSql with the collation init_command; apply any new migration to the DB only after user sign-off.

**Step 6 — Close out per the ritual.** Update PLAN.md; write `handoffs/HANDOFF_15.md` with a complete copy-pasteable next prompt + a detailed TODO an older model can follow + fresh suggestions; commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_14.md and PLAN.md before doing anything — HANDOFF_14 has the detailed step-by-step TODO for session 15; follow it in order. Context: main is at f28053f (S17 merged 2026-07-10: action flips now feed the daily-summary prompt; production verification of the flips log line + summary call-out is still pending — do it in step 1). Session 14 (branch feat/session-14-long-term, pushed NOT merged, off main = f28053f) reoriented everything to the user's long-term horizon (they hold for months/years): evaluate_outcomes now grades at 7d/30d/90d/365d with per-horizon bands that widen ~√time (HORIZON_BANDS; 30d = ±4%/10%/15%), the 1,134 historical 30d outcomes were re-graded under the new bands (30d hit rate is now an honest 51%, was an inflated 64%), the recommendation prompts demand a ≥1-month investment thesis (short-term indicators are entry timing only), and all dashboards headline 30d (7d demoted to a trend-chart diagnostic; 90d/365d series fill in from ~2026-08-15/2027-05-17). The user's hand-edit of track_record_dashboard.json was repaired into the branch (version keys at vizConfig level; their brace edits had pushed panels 2–7 out of elements). Validation: pytest 34 passed; dry-run 63 ok / 0 failed at $0.0991 with 11 flips (first run under the new prompt — expect it to settle); all 21 dashboard rawSql queries green live. Your step 2 is the merge gate: the user must import the three touched dashboards FROM THE SESSION-14 WORKTREE PATH (.claude/worktrees/session-14-long-term/grafana/ — the stale-main-copy trap cost sessions 12→13 a round trip) and eyeball the 30d panels, then ff-only merge + push if approved. Then check Reddit creds (grep -c '^REDDIT_' .env — still 0 as of 07-10) and pick the next slice with the user: S5 weekly retrospective (recommended — design storage with the user first, frame it on 30d outcomes), flip-stability watch, migration 004 trending-unknown persistence, S18 remaining tests, or S13 yfinance-404 silencing. Create the session worktree + branch (feat/session-15-<slug>) first, confirm the task list with the user, batch the work, validate (pytest + full dry-run + rawSql extraction with SET collation_connection = utf8mb4_unicode_ci), and close out per the ritual: update PLAN.md, write handoffs/HANDOFF_15.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push without merging, and print the full next-session prompt in the chat.
