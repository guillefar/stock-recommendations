# Handoff 15 — 2026-07-11 (session 15: S14 merge + S5 retrospective + Wave-4 close)

Continues [HANDOFF_14.md](HANDOFF_14.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 15 did

On branch **`feat/session-15-s5-retro`** (off `main` @ `4240120`), worktree `.claude/worktrees/session-15-s5-retro`. **Merged 2026-07-11** → `main` @ `b30eb88` (user-requested, same session).

1. **Verified S17 in production** (HANDOFF_14 step 1): scheduled run `29092211473` (2026-07-10 12:19 UTC) logged `Action flips vs previous run:` with 11 flips and the stored Spanish summary explicitly narrated them ("Se registraron 11 cambios de recomendación importantes… SOLS WATCH→BUY… MU BUY→AVOID…"). 63 ok / 0 failed, cost $0.0845.
2. **Merged session 14** (`feat/session-14-long-term` ff → `main` @ `4240120`, pushed) after the user imported all three dashboards from the session-14 worktree path and approved the 30d panels.
3. **S5 — weekly retrospective** (user chose the dedicated-table design): migration **005 `weekly_retrospectives`** (**applied to the DB**) — one row per week keyed on its Monday, upsert; `retrospective` TEXT + `stats` JSON. On Friday runs (`_RETRO_WEEKDAY` in [src/main.py](../src/main.py)) or with `--force-retro`, step 10 makes one extra Haiku call: [src/db.py](../src/db.py) `get_week_outcomes` (30d outcomes whose **`generated_at`+30d fell due in the last 7 days** — deliberately not `evaluated_at`, which re-grades rewrite) + `get_week_flips` (panel-9 semantics), aggregated by [src/analysis/retrospective.py](../src/analysis/retrospective.py) (counts, hit rate, top-5 movers each way, sector exposure by phase — never raw rows, so the prompt is bounded), rendered by `generate_weekly_retrospective` ([src/analysis/claude_client.py](../src/analysis/claude_client.py), structured output `{retrospective}`), persisted by `write_weekly_retrospective`. Failure → `None`, nothing persisted, run survives. Digest **panel-12** shows the latest week.
4. **Flip-stability watch**: digest **panel-13 "Action flips per run"** — flips-per-day bars (same join as panel-9). Motivation: 11 flips on 07-10, **18 in this session's dry-run**, many reversing the previous day's (MU BUY→AVOID→WATCH, SPY BUY→WATCH ping-pong) — the reoriented prompt has **not** settled yet.
5. **Trending-unknown persistence**: migration **004 `trending_tickers`** (**applied to the DB**) — one row per symbol, `first_seen` sticks, `times_seen` increments only when `last_seen` changes (same-day retries don't double-count); `write_trending_tickers` wired into main step 8; digest **panel-14**. Empty until Reddit creds exist.
6. **S18 tests**: [tests/test_reddit_mentions.py](../tests/test_reddit_mentions.py) (bare `IT`/`GO`/`BE` stopworded but `$IT` counts; trending needs >3 mentions at score>100), [tests/test_writers_dedup.py](../tests/test_writers_dedup.py) (4h window skip/write/dry-run), `_pct_change` fixtures in [tests/test_prices.py](../tests/test_prices.py). Existing main-harness tests now pin a non-Friday `_today()` so the retro path is deterministic.
7. **S13**: `logging.getLogger("yfinance").setLevel(logging.CRITICAL)` in [src/collectors/prices.py](../src/collectors/prices.py) — a full real run now emits **zero** yfinance 404 lines (was ~21).
8. **Docs**: PLAN (current state, session-15 Done, 3 decisions, roadmap checkboxes), PROJECT_SUMMARY (8 owned tables, retrospective module, step 10), README (migrations 001→005, `--force-retro`, digest description).

## Validation evidence

- **pytest: 55 passed** (34 baseline + 21 new). Run: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`.
- **Full `--dry-run --force-retro` through the real APIs** (2026-07-11 ~03:16 UTC, exit 0): **63 ok / 0 failed**, summary MIXED, retrospective generated and dry-run-upserted for week 2026-07-06, 66 calls, cost **$0.1058** (the retro adds ~1¢ and only fires Fridays). Zero yfinance 404 lines.
- **All 27 dashboard rawSql queries** (4 dashboards) green against the live DB (collation init_command; `$__timeFilter(x)` → `x >= '2026-05-01'`). Panels 12/14 return 0 rows legitimately (tables empty until the first production Friday run / Reddit creds).
- **Ad-hoc real retrospective printed for review** (no writes): week 2026-07-06 → 252 matured 30d calls, 93 C / 89 I / 70 N, hit 51%, 40 flips. The Spanish output is genuinely useful — it identified the HOLD-on-deteriorating-holdings failure mode (AMPX 4× HOLD at −36..−41%) and called the 07-09/07-10 flip churn "ruido, no tesis".
- **Migrations 004 + 005 applied**: `DESCRIBE` verified both tables.

## Invariants (don't break)

- Never write to `stock-snapshots` tables. This repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`, `trending_tickers`, `weekly_retrospectives`.
- Keep `--dry-run` working (no DB writes; real API calls). `--force-retro` exists for off-Friday retro testing.
- Spanish in Claude prompts; English elsewhere. Claude calls return `None` on failure — **never persist placeholders** (retro included).
- **Long-term orientation (user, 2026-07-10)**: 30d is the headline horizon; 7d diagnostic only; prompts demand a ≥1-month thesis. The retrospective is framed on matured **30d** outcomes.
- **Retro "matured this week" = `generated_at + 30d` in the last 7 days**, never `evaluated_at` (re-grades rewrite it and would flood a week).
- **Grading bands are per-horizon** (`HORIZON_BANDS`); changing them = user decision + re-grade, never silent.
- Grafana dashboards are **schema-v2**; edit programmatically (parse → assert → dump); `timeSettings` must NOT contain `weekStart`/`nowDelay`/`quickRanges`; no `version` inside `vizConfig.spec`. On import failures, first ask WHICH file copy was imported (worktree vs stale main).
- `get_latest_actions` read **before** step 6c persists (S17). Batch custom_ids must be `[A-Za-z0-9_-]`.
- `trending_tickers.times_seen` increment relies on the `times_seen` assignment appearing **before** `last_seen` in the ON DUPLICATE KEY UPDATE clause (MySQL evaluates left→right).
- Per-session ritual: worktree + branch first → confirm task list → batch work → docs + numbered handoff → push branch (never merge `main` yourself unless asked) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## State of play / caveats

- **`main` = `b30eb88`** (sessions 14 + 15 both merged 2026-07-11; the Mon 2026-07-13 run is the first production run carrying the long-term prompt *and* the session-15 features). Dashboards on main are current — the worktree-vs-main import trap is moot until the next unmerged branch.
- **Flip volume is NOT settling yet**: 11 flips (07-10 production) → 18 (07-11 dry-run), with visible ping-pong (MU, SPY, VWRL.AS, SOLS reversing within a day). Panel-13 makes this visible; the ad-hoc retro flagged it too. If it stays ≥10 after ~a week of production runs, the "no cambies de opinión por ruido" instruction needs reinforcement — that's the top follow-up candidate.
- **First real retrospective row lands Friday 2026-07-17** (merge already done). Panel-12 is empty until then; panel-14 empty until Reddit creds.
- **Reddit still dark** (`grep -c '^REDDIT_' .env` = 0, checked 2026-07-11).
- **Wave 4 is now closed except batched Reddit sentiment** (creds-gated). Remaining backlog: token trims (HANDOFF_12), fold-in cleanups (PLAN), S6 event-driven runs (deferred).
- Carried: 252 pre-price_checks matured candidates ungradeable; `price_snapshots` stale since 2026-05-22; price_checks gap 06-30→07-08 permanent; 90d/365d series fill from ~2026-08-15/2027-05-17.
- **Local runs:** `env -u ANTHROPIC_API_KEY` (empty shell var shadows `.env`). Ad-hoc DB scripts: `load_dotenv('/home/guillo/Git/stock-recommendations/.env')`, env var is `DB_PASS` (not `DB_PASSWORD`), add `SET collation_connection = utf8mb4_unicode_ci` as init_command when validating dashboard rawSql.

## Detailed TODO for session 16 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout: `git pull`, then `git worktree add .claude/worktrees/session-16-<slug> -b feat/session-16-<slug> main`, and inside it `ln -sf /home/guillo/Git/stock-recommendations/.env .env && ln -sf /home/guillo/Git/stock-recommendations/.venv .venv`.

**Step 1 — Digest dashboard import (merge already done 2026-07-11 → `main` @ `b30eb88`).** If the user hasn't yet, they import `grafana/daily_digest_dashboard.json` (main's copy is current) and eyeball the three new panels: panel-12 "Retrospectiva semanal (S5, 30d)" (legitimately empty until 07-17), panel-13 "Action flips per run" (bars: ~8 on 07-08, ~11+ on 07-09/07-10), panel-14 "Trending tickers not in watchlist" (legitimately empty until Reddit creds). Any render problem is a fix-forward item now.

**Step 2 — Verify the S14 long-term prompt in production.** The first post-S14-merge scheduled run is Monday 2026-07-13 ~10:00 UTC. `gh run list --workflow=run_recommendations.yml --limit 3`; on it check the cost line (~$0.10) and the flip count in the `Action flips vs previous run:` log line; skim the day's summary tone (long-term framing). Record the flip count — it's the panel-13 data point that decides the flip-stability question.

**Step 3 — First production retrospective (only if it's Friday 2026-07-17 or later).** After Friday's run: `gh run view <id> --log | grep -i retrospective` should show "Generating weekly retrospective..." + the upsert log line; `SELECT week_start, LEFT(retrospective, 200) FROM weekly_retrospectives` should have the week's row; the user reads panel-12.

**Step 4 — Check Reddit creds** (`grep -c '^REDDIT_' .env`). If >0: add the three GitHub Actions secrets, run one real cycle, verify `reddit_mentions` + `trending_tickers` fill and panel-14 renders; then batched Reddit sentiment (the last Wave-4 item) becomes buildable.

**Step 5 — Pick the next slice with the user** (AskUserQuestion). Ranked suggestions (fresh):
1. **Flip-stability reinforcement** (recommended if panel-13 stays ≥10 after a few post-merge runs): strengthen the anti-noise wording in `_RECOMMENDATION_SYSTEM`/the ticker prompt — e.g. explicitly pass the ticker's previous action + how many days it's held, and instruct that a reversal within N days requires naming the material new information. Validate with 2–3 consecutive dry-runs watching the flip count. (The 07-11 ad-hoc retrospective literally recommends this.)
2. **Token trims** (HANDOFF_12 backlog, user declared cost a priority): send only the first sentence of each reasoning to the summary prompt (~−3K tokens/run), cap reasoning at 2 sentences (output is 5× input), fewer news lines.
3. **Batched Reddit sentiment** — only if step 4 found creds.
4. **Fold-ins**: `get_active_tickers` UNION refactor, macro→ticker matching prefers non-NEUTRAL signals.
5. **S6 — event-driven runs** (deferred since session 05; revisit only if the user asks).

**Step 6 — Validate** the standard way: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q` (expect 55+); full `env -u ANTHROPIC_API_KEY .venv/bin/python -m src.main --dry-run` (63 ok / 0 failed, ~$0.10; add `--force-retro` if the retro path was touched); re-extract and run any touched dashboard rawSql with the collation init_command; migrations only with user sign-off.

**Step 7 — Close out per the ritual.** Update PLAN.md; write `handoffs/HANDOFF_16.md` with a complete copy-pasteable next prompt + a detailed TODO an older model can follow + fresh suggestions; commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_15.md and PLAN.md before doing anything — HANDOFF_15 has the detailed step-by-step TODO for session 16; follow it in order. Context: main is at b30eb88 — sessions 14 (long-term reorientation) AND 15 were both merged 2026-07-11, so the Mon 2026-07-13 run is the first production run carrying the long-term prompt plus session 15's features. Session 15 closed Wave 4 except Reddit-gated sentiment: S5 weekly retrospective (migration 005 weekly_retrospectives APPLIED to the DB; Friday runs or --force-retro make one extra Haiku call reviewing the week's matured-30d outcomes/flips/sector exposure — maturity = generated_at+30d in the last 7 days, never evaluated_at; digest panel-12, first real row expected Fri 2026-07-17), flip-stability panel-13 (flips per run — 11 on 07-10 production, 18 in the 07-11 dry-run with visible ping-pong: NOT settling yet), migration 004 trending_tickers (APPLIED; upsert per symbol, digest panel-14, empty until Reddit creds), S18 tests (reddit stopwords, 4h dedup window, _pct_change) and S13 (yfinance logger silenced — zero 404 lines in a real run). Validation: pytest 55 passed; dry-run --force-retro 63 ok / 0 failed at $0.1058 with the retro generated; all 27 dashboard rawSql green live; an ad-hoc real retrospective (252 matured calls, 51% hit) correctly diagnosed the HOLD-on-deteriorating-holdings failure mode and the flip churn. Steps: confirm the user imported the digest dashboard (main's copy is current; panels 12/14 legitimately empty); verify the Mon 07-13 production run (cost ~$0.10, flip count from the "Action flips vs previous run:" log line — it decides the flip-stability question); verify the first production Friday retrospective (07-17: log line + weekly_retrospectives row + panel-12, user reads it); check Reddit creds (grep -c '^REDDIT_' .env — still 0 as of 07-11). Then pick the next slice with the user: flip-stability prompt reinforcement (recommended if panel-13 stays ≥10 — pass the previous action + days held into the ticker prompt and require naming material new information for a reversal), token trims (HANDOFF_12), batched Reddit sentiment (only if creds), or fold-in cleanups. Create the session worktree + branch (feat/session-16-<slug>) first, confirm the task list with the user, batch the work, validate (pytest + full dry-run + rawSql extraction with SET collation_connection = utf8mb4_unicode_ci), and close out per the ritual: update PLAN.md, write handoffs/HANDOFF_16.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push without merging, and print the full next-session prompt in the chat.
