# Handoff 19 — 2026-07-11 (session 19: session-18 merge + ticker deep-dive dashboard)

Continues [HANDOFF_18.md](HANDOFF_18.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 19 did

On branch **`feat/session-19-ticker-dashboard`** (off `main` @ `4f8f5ad`), worktree `.claude/worktrees/session-19-ticker-dashboard`. Pushed, **not merged**.

Session start: **merged session 18** (`feat/session-18-etf-info` ff → `main` @ `4f8f5ad`, pushed, user-approved). Session ran on **Saturday 07-11**, so HANDOFF_18 steps 2–3 (Mon 07-13 run verification, Fri 07-17 retro) were impossible by the calendar and carry to session 20. Reddit creds still 0.

The slice (user ask: "a new dashboard, similar to track_record, but that allows to select specific stocks to see how the predictions went for them"):

1. **New [grafana/ticker_deep_dive_dashboard.json](../grafana/ticker_deep_dive_dashboard.json)** (schema v2, 8 panels) — the repo's **first dashboard with a template variable**.
2. **`$ticker` multi-select QueryVariable**: `SELECT DISTINCT t.symbol FROM tickers t JOIN recommendations r ON r.ticker_id = t.id ORDER BY t.symbol` (63 symbols live), include-All (default), `allowCustomValue: false`. Every data panel filters `t.symbol IN ($ticker)` — Grafana's MySQL datasource expands the multi-value as quoted CSV. The variable spec was written against Grafana's canonical v2 schema (`QueryVariableKind` in grafana/grafana `packages/grafana-schema/src/schema/dashboard/v2beta1/types.spec.gen.ts`) because no repo dashboard had one to copy; required keys `name/current/hide/refresh/skipUrlSync/query/regex/sort/options/multi/includeAll/allowCustomValue` are all present (`current` = All, `refresh: onDashboardLoad`, `sort: disabled` — the SQL already orders).
3. **Panels**: scorecard row — *Hit rate (30d)* / *Decided calls (30d)* / *Calls in range* stats + a how-to-read markdown (small-sample warning; price history starts 2026-06-12; avg return is direction-blind); *Price history* timeseries from `price_checks` using mysql **`format: time_series`** (`time_sec` / `metric` / `value` — one series per symbol; also new to this repo, every other timeseries panel is wide-format `table`); *Hit rate by horizon* table (7/30/90/365d × total/C/I/N/hit-rate %/avg return %); *30d verdicts by week* stacked bars (verdict-colored, Monday-anchored, keyed to the week the call was made); *Call history* table (newest first: generated_at, symbol, action color-mapped like predictions panel-1, confidence color-bg, entry price from `technical.$.price`, 30d verdict color-mapped + 30d return %, 200-char reasoning; empty verdict = not matured / no exit price).
4. **README** dashboard list updated (five dashboards; deep-dive noted as the one variable-dropdown exception).

## Validation evidence

- **All 9 rawSql green against the live DB** (collation init_command; `$__timeFilter` → BETWEEN, `$ticker` → quoted CSV) under two scenarios: multi (`'AAPL','XESC.DE','SPY'`: hit rate 28, decided 40, 108 calls, 42 price rows, 2 horizon rows, 5 weekly rows, 108 history rows) and single-with-no-data (`'NVDA'`: NULL/0 rows everywhere, **no errors** — empty selections degrade gracefully). Variable query: 63 symbols.
- **Structural checks**: JSON parses; top-level keys identical to the known-good `track_record_dashboard.json`; grid overlap-free within 24 columns; every layout item references an existing element.
- **pytest: 75 passed** (unchanged — dashboard-only change, no pipeline code, so no paid dry-run; same rule as session 10's dashboard slice).
- **Not done**: live render in Grafana — the QueryVariable and the `time_series` format are both firsts for this repo, built from canonical shapes but never eyeballed. First-import review is the session-20 merge gate.

## Invariants (don't break)

All of HANDOFF_18's invariants stand (never write to stock-snapshots tables; `--dry-run` = no writes, real API; Spanish prompts; no persisted placeholders; 30d headline horizon; `get_latest_actions` before step 6a; ETF fetch only for `quote_type == "ETF"`; `_build_etf_info` → None when unknown; panel-6 ETF bucket keys on `t.quote_type`; schema-v2 dashboard rules; batch custom_ids `[A-Za-z0-9_-]`; worktree-per-session ritual; user only sees the final message). New this session:

- **The deep-dive `$ticker` variable must keep `multi: true` + `includeAll: true`** and panels must filter with `IN ($ticker)` (never `= $ticker`) or multi-select breaks.
- **The price-history panel is `format: "time_series"`** (`time_sec/metric/value`); don't "normalize" it to the wide-table pattern of the other timeseries panels — per-symbol series need the metric column.
- **Only the deep-dive dashboard has a variable**; the other four navigate by time picker only (README documents the exception).

## State of play / caveats

- **`main` = `4f8f5ad` (session 18 merged, pushed)**; session 19 is on `feat/session-19-ticker-dashboard`, pushed, **awaiting user merge + first Grafana import**.
- **Dashboard imports the user owes themselves**: `ticker_deep_dive_dashboard.json` (new, after merge), `track_record_dashboard.json` from main (s18 changed panel-6 rawSql), and predictions + track-record from the s17 description changes if never re-imported.
- **The Mon 2026-07-13 run** is the first with s16+s17+s18 all live: expect 63 ok, cost ≈ **$0.097** (s18 dry-run figure), and a flip count to compare against 11 (07-10). The Mon→Fri flip trend is the production verdict on session 16; **flip-stability round 2** only if flips stay ≥10 with same-day reversals.
- **First real retrospective row lands Friday 2026-07-17** (log line + `weekly_retrospectives` row + digest panel-12).
- **ETF hit rate 37% (486 outcomes) is the s18 baseline**; first ETF-informed calls mature ~mid-August 2026. Watch the ETF row in track-record panel-6.
- **Reddit still dark** (`grep -c '^REDDIT_' .env` = 0, 2026-07-11). Batched Reddit sentiment stays gated.
- **Committed backlog** (user-selected 2026-07-11, PLAN roadmap): fundamentals in prompts, benchmark-relative grading, dividend-adjusted returns, lower run frequency. Grading changes need explicit user sign-off + re-grade (session-14 rule). Also available: per-run cost telemetry in the DB, portfolio lens dashboard, flip-stability round 2 (only if the week says so).
- Carried: 252 pre-price_checks matured candidates ungradeable; `price_snapshots` stale since 2026-05-22; price_checks gap 06-30→07-08 permanent; 90d/365d series fill from ~2026-08-15 / 2027-05-17; price history in the new dashboard starts 2026-06-12 (price_checks epoch) and has the 06-30→07-08 hole.
- **Local runs:** `env -u ANTHROPIC_API_KEY` (empty shell var shadows `.env`). Ad-hoc DB scripts: `load_dotenv('/home/guillo/Git/stock-recommendations/.env')`, env var is `DB_PASS`, add `SET collation_connection = utf8mb4_unicode_ci` as init_command when validating dashboard rawSql.
- **User timezone: Europe/Madrid.**

## Detailed TODO for session 20 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout (`/home/guillo/Git/stock-recommendations`): `git pull`, then `git log --oneline -3` and compare against the prompt you were given — **if they disagree, the repo wins; say so to the user before doing anything**. `git worktree list`; check the newest worktree's `status --short` for interrupted work.

**Step 1 — Merge gate for session 19.** The gate is a **render check, not just approval**: ask the user (AskUserQuestion) to (a) import `grafana/ticker_deep_dive_dashboard.json` (from the worktree `.claude/worktrees/session-19-ticker-dashboard/grafana/` or after merge from `main`) and (b) confirm the Ticker dropdown populates (~63 symbols), All + multi-select work, and all 8 panels render (pick one ticker, e.g. AAPL, and eyeball the call-history table). If the import validator rejects it, the variable block is the prime suspect — compare against `QueryVariableKind` in grafana/grafana `types.spec.gen.ts` (v2beta1) and fix field-by-field. On approval: `git checkout main && git merge --ff-only feat/session-19-ticker-dashboard && git push`. Remind the user to also re-import **track_record** from main (s18 panel-6) if they haven't.

**Step 2 — Verify the week's production runs (Mon 07-13 onward).** `gh run list --workflow=run_recommendations.yml --limit 5`; per scheduled run check: 63 ok / 0 failed; cost line ≈ $0.097 (s16+s17+s18 all live — s18's dry-run figure); the `Action flips vs previous run:` count vs 11 on 07-10. Record counts in PLAN. Settling = low single digits without same-day reversals; if flips stay ≥10, flip-stability round 2 becomes a candidate slice.

**Step 3 — First production retrospective (on/after Friday 2026-07-17).** After Friday's run: the log shows the retrospective generation + upsert lines; `SELECT week_start, LEFT(retrospective, 200) FROM weekly_retrospectives;` has the week's row; the user reads digest panel-12. Note whether its flip commentary matches step 2's counts.

**Step 4 — Check Reddit creds** (`grep -c '^REDDIT_' .env`). If >0: add the three GitHub Actions secrets, run one real cycle, verify `reddit_mentions` + `trending_tickers` fill and digest panel-14 renders; batched Reddit sentiment becomes buildable.

**Step 5 — Pick the next slice with the user** (AskUserQuestion). Suggested order unchanged from HANDOFF_18:
1. **Fundamentals in the per-ticker prompt** (stocks): P/E, dividend yield, margins, revenue growth via yfinance `Ticker.info` (probe field availability first — European tickers are patchy). Same optional-block pattern as news/earnings/ETF. Self-contained, no grading impact.
2. **Lower run frequency** (daily → 2–3×/week): cron-line change; ask the user for the cadence; keep a Friday run for the retro. Cuts the API bill proportionally.
3. **Benchmark-relative + dividend-adjusted grading at 90d/365d**: needs user decisions (benchmark choice, re-grade or not — session-14 rule) and total-return data; best started once 90d outcomes near maturity (~2026-08-15). Do the two together.
4. Others if asked: per-run cost telemetry in the DB, portfolio lens dashboard, flip-stability round 2 (only if step 2 says so).

**Step 6 — Validate** the standard way: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q` (expect 75+); full `env -u ANTHROPIC_API_KEY .venv/bin/python -m src.main --dry-run` if pipeline code changed (63 ok / 0 failed; `--force-retro` if the retro path was touched); re-extract and run any touched dashboard rawSql with the collation init_command (substitute `$ticker` with a quoted CSV for deep-dive queries); migrations only with user sign-off.

**Step 7 — Close out per the ritual.** Update PLAN.md; write `handoffs/HANDOFF_20.md` with a complete copy-pasteable next prompt + a detailed TODO an older model can follow + fresh suggestions; commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Fresh suggestions (beyond the committed backlog)

- **Annotate calls on the deep-dive price chart**: Grafana annotation queries can mark BUY/SELL calls on the price timeseries (one annotation query on `recommendations` filtered to `$ticker`); makes "did the call precede the move?" visible at a glance. Cheap follow-up now that the variable exists.
- **Deep-dive link-through**: add a data link from the predictions dashboard's per-ticker table to the deep-dive with `var-ticker=${__data.fields.symbol}` — one click from "latest call" to "how has this ticker graded historically".
- **Per-run cost telemetry in the DB** (old suggestion, still cheap): persist the run's token/cost line into a table so cost trends become dashboardable instead of log-archaeology.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_19.md and PLAN.md before doing anything — HANDOFF_19 has the detailed step-by-step TODO for session 20; follow it in order, and first cross-check this prompt's claims against git log (if they disagree, the repo wins — say so). Context: main is at 4f8f5ad (session 18 ETF awareness merged + pushed 2026-07-11). Session 19 (Saturday 2026-07-11, branch feat/session-19-ticker-dashboard, pushed NOT merged) delivered the ticker deep-dive dashboard the user asked for: new grafana/ticker_deep_dive_dashboard.json (schema v2, 8 panels) with the repo's first template variable — a multi-select $ticker QueryVariable (63 symbols, include-All) scoping every panel: 30d hit-rate/decided/calls-in-range stats + how-to-read, price history from price_checks (mysql time_series format, one series per symbol), hit-rate-by-horizon table, 30d-verdicts-by-week stacked bars, and a full call-history table with each call's 30d grade. All 9 rawSql validated live (multi + empty-selection scenarios, collation init_command); pytest 75 passed; dashboard-only change so no dry-run; NOT yet rendered in Grafana — first import is the merge gate. HANDOFF_18's production checks were impossible on Saturday and carry over. Steps: (1) merge gate — user imports ticker_deep_dive_dashboard.json (from the s19 worktree or main after merge) and confirms the Ticker dropdown + all 8 panels render, then ff-merge session 19 to main and push; if Grafana's validator rejects it, debug the variable block against QueryVariableKind in grafana/grafana types.spec.gen.ts (v2beta1); also remind the user to re-import track_record from main (s18 changed panel-6). (2) verify the week's production runs (Mon 07-13 onward: 63 ok, cost ≈$0.097, flip trend vs 11 on 07-10 — the verdict on session 16; round 2 only if flips stay ≥10 with reversals); (3) on/after Fri 07-17 verify the first production weekly retrospective (log line + weekly_retrospectives row + digest panel-12); (4) check Reddit creds (grep -c '^REDDIT_' .env — 0 as of 07-11). Then pick the next slice with the user from HANDOFF_19 step 5 (suggested order: fundamentals-in-prompt, lower run frequency, benchmark-relative + dividend-adjusted grading once 90d outcomes near maturity ~08-15; also available: per-run cost telemetry, portfolio lens, deep-dive price-chart call annotations, predictions→deep-dive data link, batched Reddit sentiment if creds). Create the session worktree + branch (feat/session-20-<slug>) once the slice is known, confirm the task list with the user, batch the work, validate (pytest expect 75+, full dry-run 63 ok if pipeline code changed, rawSql with SET collation_connection = utf8mb4_unicode_ci if dashboards touched — substitute $ticker with quoted CSV on deep-dive queries, migrations only with user sign-off), and close out per the ritual: update PLAN.md, write handoffs/HANDOFF_20.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push without merging, and print the full next-session prompt in the chat.
