# Handoff 10 — 2026-07-01 (session 10)

Continues [HANDOFF_09.md](HANDOFF_09.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

> Handoff files live in [`handoffs/`](.). Links to repo-root files use `../`; links to sibling handoffs are bare.

## What session 10 did — merged Wave 3, started Wave 4 (dashboard readability)

Branch **`feat/session-10-wave-4`** (off `main` @ `3de1901`), worktree `.claude/worktrees/session-10-wave-4`. Pushed, **not merged**.

1. **Merged Wave 3 to `main`.** Session 09's `feat/session-09-wave-3` was a clean fast-forward on `main` (`b4af216` → `3de1901`). Verified the diff, ran pytest (14/14) on the branch, then `git merge --ff-only` + pushed `main`. Wave 3 (cost telemetry, pinned deps + CI, README, S15/S16) is now in production.
2. **Post-merge verification (read-only).** One 63-rec batch per weekday (06-23…06-29); `recommendation_outcomes` at **2,181**; live `phase × action` split holds the per-phase enum (zero out-of-set actions); `tests.yml` green on the branch. **Found: the 06-30 scheduled cron failed** at `analyze_macro` with `400 "credit balance too low"` — see caveats. The outcome-eval step (no API) still wrote 63 outcomes that day.
3. **New dashboard [grafana/track_record_dashboard.json](../grafana/track_record_dashboard.json)** (schema v2, 7 panels) — the user's ask: *a clearer view of when predictions were correct, over which periods, and what correct calls share.*
   - **Scorecard header** — 3 `stat` tiles (overall 7d hit rate = 62%, decisiveness = 66%, decided-call sample size) + a markdown "how to read" panel defining CORRECT/NEUTRAL/INCORRECT and the hit-rate denominator.
   - **Hit rate over time (weekly)** `timeseries` — Monday-anchored weekly hit rate for 7d + 30d horizons; the week's decided-call count rides as light bars on a right axis (thin bars = noisy hit rate). The 7d rate slides 69% → 56% across the window.
   - **Hit rate by sector** table — joins `tickers.sector_disp`, ≥10 decided calls: Basic Materials 80% / Industrials 77% / Tech 68% / Financial 48% / Healthcare 38%; big "(unknown)" bucket (ETFs / non-US, no sector metadata) at 54%.
   - **Hit rate by RSI band** table — RSI from `recommendations.technical.$.rsi` at call time: overbought (70+) 69% vs oversold (<30) 56%.
   - Hit rate everywhere = CORRECT ÷ (CORRECT+INCORRECT); all panels default to 7d and respect the time picker.
4. **Docs.** [README.md](../README.md) Grafana section now lists three dashboards; PLAN.md updated (current state, caveats, session-10 Done block, Wave 4 checkbox, decisions log).

## Validation evidence (all offline — no API credits needed)

- **Every embedded `rawSql` re-extracted from the written JSON and run against the live DB** — all 6 queries return sensible rows (scorecard 1 row each, weekly trend 7 weeks, sector 7 rows, RSI 5 bands). The extract-and-run guard caught a real bug mid-build (an ANSI_QUOTES / `only_full_group_by` GROUP BY-by-alias failure), now fixed.
- **JSON parses**; **grid has no overlapping panels** and every panel stays within the 24-col grid.
- **Structural parity** with the working `daily_digest_dashboard.json`: identical top-level + panel-wrapper keys, **integer** panel ids, `variables: []` present.
- **pytest still 14 passed** (unchanged — no Python touched this session).

> ⚠️ **NOT validated: live render in Grafana.** The `stat` and `text` panels were hand-built from canonical Grafana 13.1 shapes because no such panel existed in the repo to copy. The table + timeseries panels are templated off working panels and are low-risk. **Eyeball the scorecard tiles + "how to read" note on first import** and tweak in the UI if a shape is off (then re-export).

## State of play / caveats

- **`feat/session-10-wave-4` pushed, not merged.** Merging is step 1 of session 11. The change is dashboard JSON + docs only — zero pipeline/behavior impact, so it's safe to merge whenever.
- **API credits still exhausted** — the 06-30 cron failed at `analyze_macro` (`400 credit balance too low`). **This is the top real-world item.** Every real run (cron or `--dry-run`) fails at the first Claude call until topped up at the Anthropic Console. Outcome grading is unaffected (uses stored prices only), so `recommendation_outcomes` keeps growing even while recommendation generation fails.
- **Reddit still dark** — `grep -c '^REDDIT_' .env` = 0. https://www.reddit.com/prefs/apps → "script" app; put `REDDIT_CLIENT_ID/SECRET/USER_AGENT` in `.env` AND the three GitHub Actions secrets.
- **Local runs need `env -u ANTHROPIC_API_KEY`** — the shell exports an empty `ANTHROPIC_API_KEY` that shadows `.env` (`load_dotenv` doesn't override). Also: when running an ad-hoc script from the scratchpad, pass an **absolute** path to `load_dotenv('/home/guillo/Git/stock-recommendations/.env')` and set `PYTHONPATH=.` from the worktree. GitHub Actions is unaffected (secrets injected directly).
- Carried: yfinance 404 ERROR lines (cosmetic, S13); the 252 pre-price_checks matured candidates + pre-fix NULL-entry-price ETF recs stay ungradeable (S11 could recover the latter); `price_snapshots` stale since 2026-05-22.

## Invariants (don't break)

- Never write to `stock-snapshots` tables (read-only). Tables this repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- `analyze_ticker` returns `None` on failure — never a fake HOLD.
- Grafana dashboards must be **schema-v2** (`elements`/`layout`), datasource uid `cfadv004ogglcf` (group `mysql`), integer panel ids.
- Per-session ritual: **worktree + branch first** → confirm task list → batch work → close with docs + numbered handoff → push the branch (never merge to `main` yourself unless asked) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## Suggestions (fresh, for discussion; NOT committed work)

- **Dashboard consolidation (the other half of "simplify").** `daily_digest_dashboard.json` and `recommendations_dashboard.json` both carry Daily Market Summary + Macro Signals panels. Now that track-record analytics live on their own dashboard, consider: digest = "today's decisions", recommendations = "live holdings/watchlist", track-record = "is the model any good" — and delete the duplicated panels so each dashboard has one clear job.
- **S17 — feed action flips into the daily-summary prompt** (carried; the dashboard half is done). Compute the run's flips in [src/main.py](../src/main.py) (compare each ticker's new action to its previous stored row) and pass them into `generate_daily_summary` so the summary text names reversals. Needs API credits to validate live.
- **Track-record follow-ups.** (a) The "(unknown)" sector bucket is ~half the sample — a quick win is to also key the sector panel on `industry_disp` or surface how many outcomes lack sector metadata. (b) Add a **hit rate by confidence × horizon** small-multiple, or fold the existing D3 calibration panel into the track-record dashboard so all accuracy views sit together. (c) A **per-ticker leaderboard** (best/worst tickers by hit rate, ≥N calls) would answer "which names does it read well".
- **S18 — more unit tests** (`extract_ticker_mentions` stopwords, `_compute_rsi`/`_pct_change`, dedup window) and **S13 — silence yfinance 404 logs** (`logging.getLogger("yfinance").setLevel(logging.CRITICAL)`). Both free, offline, no credits.
- **S5 — weekly retrospective digest** (carried, Wave 4). Friday run does one extra Claude call summarizing the week; persist + panel. ~1 Haiku call/week.

## Detailed TODO for session 11 (step-by-step; follow in order)

**Step 0 — Orient.** Read [HANDOFF_10.md](HANDOFF_10.md) (this file) and [PLAN.md](../PLAN.md). Session 10 is committed + validated offline (pytest 14; all dashboard SQL runs live). No leftover validation except the live Grafana render (below).

**Step 1 — Merge gate.** Confirm with the user, then merge `feat/session-10-wave-4` to `main` (dashboard JSON + docs only; clean fast-forward expected). Never merge without the user's OK.

**Step 2 — API credits (blocker for any live run).** Remind the user the 06-30 cron failed on `credit balance too low`. Confirm they've topped up before attempting a `--dry-run` or trusting the cron. You can't check the balance via API — ask, or attempt a tiny live call and report if it 400s.

**Step 3 — Import the new dashboard + eyeball it.** Ask the user to import [grafana/track_record_dashboard.json](../grafana/track_record_dashboard.json) (Dashboards → New → Import, pick the MySQL datasource) and confirm the **scorecard stat tiles + "how to read" text panel render** (the only un-live-tested pieces). Fix any shape issues and re-export if needed.

**Step 4 — Workspace.** `git checkout main && git pull`, then `git worktree add .claude/worktrees/session-11-<topic> -b feat/session-11-<topic> main`, and inside it:
```bash
ln -sf /home/guillo/Git/stock-recommendations/.env .env
ln -sf /home/guillo/Git/stock-recommendations/.venv .venv
```
Confirm the task list. Re-check Reddit creds: `grep -c '^REDDIT_' .env`.

**Step 5 — Pick Wave 4 work with the user.** Highest-leverage first:
- **Dashboard consolidation** — dedupe the digest vs recommendations dashboards (finishes the "simplify" ask; offline, no credits).
- **S17 — action flips into the summary prompt** (completes flip detection; needs credits to validate live).
- **Persist trending-unknown tickers** (migration 004 + table).
- **S5 — weekly retrospective digest** (Friday-only extra Claude call + panel).
- Quick wins: **S18** more unit tests, **S13** yfinance log silencing (both offline).

**Step 6 — Validate.** `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`; if the work touches SQL/dashboards, re-run each query against the live DB (extract-and-run, like session 10). Full `--dry-run` only if credits are restored.

**Step 7 — Close out.** Update [PLAN.md](../PLAN.md); write `handoffs/HANDOFF_11.md` (what was done, validation evidence, complete copy-pasteable next prompt, detailed TODO an older model can follow, fresh suggestions); commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_10.md and PLAN.md before doing anything — HANDOFF_10 has the detailed step-by-step TODO for session 11; follow it in order. Context: session 10 merged Wave 3 to main (`3de1901`, clean fast-forward, pytest 14/14) and started Wave 4 with a dashboard-readability slice on branch feat/session-10-wave-4 (off main @ 3de1901, pushed, NOT merged). It added grafana/track_record_dashboard.json — a dedicated model-accuracy dashboard (schema v2, 7 panels): a scorecard header (overall 7d hit rate 62%, decisiveness 66%, decided-call count) + a markdown "how to read" note, a weekly hit-rate trend timeseries by horizon (the "when", with decided-count bars on a right axis; 7d rate slides 69%→56%), and hit rate by sector (Basic Materials 80% … Healthcare 38%, big "(unknown)" ETF bucket) + by RSI band (overbought 69% > oversold 56%) tables (the "what correct calls share"). Hit rate = CORRECT ÷ (CORRECT+INCORRECT), neutral excluded. Validated OFFLINE only: every embedded rawSql re-run against the live DB, JSON parses, no grid overlaps, structural parity with the working dashboard (integer ids, variables:[]). NOT validated: live render in Grafana — the stat/text panels were hand-built from canonical Grafana 13.1 shapes, so eyeball them on first import. THREE real-world flags: (1) API credits are still exhausted — the 06-30 cron FAILED at analyze_macro with 400 "credit balance too low"; confirm with me that I topped up before any real run. (2) Reddit creds still missing. (3) local runs need `env -u ANTHROPIC_API_KEY` (empty shell var shadows .env). First confirm with me that I merged feat/session-10-wave-4 to main, topped up API credits, and imported+eyeballed the new dashboard. Then create the session worktree + branch and confirm the task list. After that, pick Wave 4 work: dashboard consolidation (dedupe the digest vs recommendations dashboards — finishes the "simplify" ask, offline), S17 (feed action flips into the daily-summary prompt — needs credits), persist trending-unknown tickers (migration 004), S5 weekly retrospective, plus quick wins S18 (unit tests) / S13 (silence yfinance 404 logs). Close out per the ritual: update PLAN.md, write handoffs/HANDOFF_11.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push the branch without merging, and print the full next-session prompt in the chat.
