# Handoff 12 — 2026-07-09 (session 12: review fixes, Batch API, predictions dashboard)

Continues [HANDOFF_11.md](HANDOFF_11.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 12 did

On branch **`feat/session-12-review-fixes`** (off `main` @ `bb5ae86`), worktree `.claude/worktrees/session-12-review-fixes`. Pushed, **not merged**. All of HANDOFF_11's TODO executed, plus the user's new priority (**reduce token usage**) which turned into the Batch API migration.

1. **F1 closed.** The 2026-07-09 scheduled run succeeded end-to-end after the credit top-up (63 recs at 12:26 UTC; verified again live — the latest-calls query returns 63 rows dated today). A redundant `workflow_dispatch` I triggered before noticing was canceled to save credits.
2. **Task A — pipeline fixes F2–F6** ([src/main.py](../src/main.py), [src/analysis/claude_client.py](../src/analysis/claude_client.py), [src/collectors/prices.py](../src/collectors/prices.py), [src/persistence/writers.py](../src/persistence/writers.py)):
   - **F2:** macro analysis and daily summary are each wrapped in try/except; a Claude outage degrades to `macro_signals = []` / `summary = None` and the run continues — `price_checks` are now written before any Claude involvement can fail the ticker.
   - **F3:** `_compute_rsi` uses `loss.replace(0, 1e-10)` (was `inf`) — an all-gain window now yields RSI ≈ 100, not 0.
   - **F4:** `write_reddit_mentions` pre-SELECTs existing NULL-ticker `post_id`s and skips them (MySQL UNIQUE keys treat every NULL as distinct). Done **before** Reddit creds exist, as planned.
   - **F5:** `generate_daily_summary` returns `None` on refusal/truncation/parse failure; main skips the write (never "Error generando resumen." over the day's row) and the final log line tolerates `summary is None`.
   - **F6:** summary `max_tokens` 1024 → 2048; `_structured_json` logs `stop_reason == "max_tokens"` explicitly.
   - Fold-ins: unused `Config.dry_run` dropped; reddit's `except (PrawcoreException, Exception)` → `except Exception` (prawcore import removed).
3. **F8 / token usage — Message Batches API** (the user picked this over prompt trims). `ClaudeClient.analyze_tickers_batch` sends all per-ticker requests as one batch: **50% token discount** on the dominant cost (63 of 65 calls). Key mechanics:
   - `_ticker_request_params` builds the request kwargs; both `analyze_ticker` (kept for ad-hoc/debug) and the batch path share it, so requests are byte-identical.
   - custom_ids are `t<index>` — **ticker symbols cannot be custom_ids** (`XESC.DE`, `RR.L` contain dots; the API allows only `[A-Za-z0-9_-]`).
   - Poll every 30 s, up to 45 min (`BATCH_DEADLINE_SECONDS`), then cancel → every ticker returns `None` → main counts all failed → non-zero exit. The workflow job timeout is 60 min to accommodate.
   - Each succeeded result goes through the same `_structured_json` + `coerce_action` path; usage from each result message is recorded with `batch=True` and priced at 50% in `estimated_cost_usd()` (`batch_input`/`batch_output` counters in the log line).
   - main.py step 6 is now three phases: **6a collect** (yfinance + price_check + sentiment/news/earnings, per-ticker isolation), **6b batch call**, **6c persist** (per-ticker isolation again).
4. **Task B — F7 hygiene.** [run_recommendations.yml](../.github/workflows/run_recommendations.yml): `concurrency: {group: stock-recs, cancel-in-progress: false}` + `timeout-minutes: 60`; evaluate step no longer receives `ANTHROPIC_API_KEY` (`load_config()` defaults it to `""`; `ClaudeClient.__init__` raises a clear error if empty). [tests.yml](../.github/workflows/tests.yml): push trigger `["**"]` → `[main]` (no PR double-runs) + `timeout-minutes: 10`.
5. **Dashboard import fix (user-reported live failure).** The user's import of `track_record_dashboard.json` failed Grafana validation on `timeSettings.weekStart` ("conflicting values"). Fixed by matching the known-good key set: removed `weekStart: ""`, `nowDelay`, `quickRanges` from `timeSettings` **and** the stray `version` key inside `vizConfig.spec` of panels 1–5 (hand-built stat/text/timeseries panels had it; working panels don't).
6. **Task D — [grafana/predictions_dashboard.json](../grafana/predictions_dashboard.json)** (user chose a new standalone dashboard). 3 panels, schema v2, integer ids, `variables: []`:
   - **Latest call per ticker** (table, not time-picker-scoped — always the current run): symbol, phase, action (color-mapped), confidence % (color background), entry price (`technical.$.price`), 200-char reasoning, **ticker hit rate %** (that ticker's own 7d CORRECT÷decided, color background) and **graded calls** (sample size). Ordered BUY/SELL/AVOID → WATCH/HOLD, then confidence.
   - **Hit rate over time (weekly)** — the track-record trend query, verbatim.
   - **How to read** text panel.
7. **Consolidation (HANDOFF_10).** Removed the digest-duplicated *Daily Market Summary* + *Macro Signals* panels from [recommendations_dashboard.json](../grafana/recommendations_dashboard.json) (7 → 5 panels; layout gap closed).
8. **Task C — docs.** PROJECT_SUMMARY: all five drift points fixed, execution flow rewritten for the batch path, six owned tables, dashboards section lists all four. README: four dashboards, tests-trigger wording.

## Validation evidence

- **pytest: 24 passed** (14 baseline + 4 RSI + 4 batch-client-with-stubbed-API + 2 `main()` resilience: macro raising still writes prices+recs; `None` summary is never persisted). Run: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`.
- **All 24 dashboard rawSql queries** re-extracted from the four written JSONs and executed against the live DB (predictions latest-calls: 63 rows; weekly trend: 8 weeks). Note: two `recommendations_dashboard` panels (`s.status = 'HOLDING'` against `v_ticker_status_multi`) throw *Illegal mix of collations* under a default pymysql connection — this is a **harness artifact**, not a dashboard bug; they pass with `SET collation_connection = utf8mb4_unicode_ci` and work in Grafana. Use that init_command when validating from Python.
- **Full `--dry-run` through the real Batch API** (2026-07-09, exit 0): **63 ok / 0 failed**; batch `msgbatch_016Ns7YFG…` submitted 21:17:53, ended 21:20:25 (**~2.5 min**, 63 succeeded / 0 errored); summary MIXED. Cost line: `65 calls — input=13201 output=1536 batch_input=68981 batch_output=11049 (50% rate); estimated cost $0.0830` — vs $0.1471 pre-batch (**−44%**, ≈ $1.7/month at 21 runs).

## Invariants (don't break)

- Never write to `stock-snapshots` tables. This repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes; it still makes real API calls, now ~half price via the batch).
- Spanish in Claude prompts; English elsewhere.
- `analyze_ticker` / batch entries / `generate_daily_summary` return `None` on failure — **never persist placeholders**.
- Grafana dashboards are **schema-v2** (`elements`/`layout`), datasource `{"name": "cfadv004ogglcf"}` group `mysql`, integer panel ids, `variables: []`. **New (learned from a live failure):** `timeSettings` must NOT contain `weekStart`/`nowDelay`/`quickRanges`, and `vizConfig.spec` must NOT contain `version` — copy key sets from a dashboard that has imported successfully.
- Batch custom_ids must be `[A-Za-z0-9_-]` — never raw symbols (dots).
- Per-session ritual: worktree + branch first → confirm task list → batch work → close with docs + numbered handoff → push branch (never merge `main` yourself unless asked) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## State of play / caveats

- **`main` = `bb5ae86`**; this branch is ahead by the session-12 commits. Merge gate: user eyeballs the two new/fixed dashboards + first green scheduled run *from the branch-merged main* (the batch path has run in dry-run, not yet in the production cron).
- **Dashboards to import/eyeball:** `predictions_dashboard.json` (new) and `track_record_dashboard.json` (fixed). If import still fails, capture the exact validator message — that's how the weekStart bug was found.
- **Reddit still dark** (`grep -c '^REDDit_' .env` → check with `^REDDIT_`; 0 as of today). F4 is now fixed ahead of creds arriving.
- **Local runs:** `env -u ANTHROPIC_API_KEY` (empty shell var shadows `.env`). Ad-hoc scripts: `load_dotenv('/home/guillo/Git/stock-recommendations/.env')` + the collation init_command for DB validation.
- **price_checks gap 06-30 → 07-08** — permanent for those dates; self-heals going forward.
- Carried: yfinance 404 ERROR lines (S13, cosmetic); 252 pre-price_checks matured candidates stay ungradeable; `price_snapshots` stale since 2026-05-22.
- **Token-usage levers not taken** (documented for a future session): summary input could send only the first sentence of each reasoning (~−3K in); reasoning cap 2 sentences (output = 5× input price); fewer news/Reddit lines. Combined ≈ another 15–25% off the (already halved) cost. Only worth it opportunistically — total spend is ~$1.7/month after the batch migration.

## Detailed TODO for session 13 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). Workspace ritual: from the main checkout `git pull`, then `git worktree add .claude/worktrees/session-13-<slug> -b feat/session-13-<slug> main`, symlink `.env` and `.venv` into it (`ln -sf /home/guillo/Git/stock-recommendations/.env .env` etc.).

**Step 1 — Merge gate for `feat/session-12-review-fixes`.**
1. Ask the user (AskUserQuestion) whether they imported `predictions_dashboard.json` and the fixed `track_record_dashboard.json` and whether both render. Fix any validator complaints before merging (compare key sets against `daily_digest_dashboard.json`).
2. If approved: `git merge --ff-only feat/session-12-review-fixes` on `main`, push, then watch the next scheduled run (`gh run list --workflow=run_recommendations.yml --limit 3`) — it's the **first production run of the batch path**; check the log for the "Submitted message batch" line, the request_counts line, and the cost line (expect roughly half of $0.147).
3. If the batch misbehaves in production (deadline hit, mass failures), the revert is contained: `run_ticker_recommendations_batch` → loop over `run_ticker_recommendation` (the single-call path still exists and shares the request builder).

**Step 2 — Confirm Reddit creds status.** `grep -c '^REDDIT_' .env`. If the user has added them, verify one real run stores deduped mentions (F4 fix) and unblock the Wave-4 "batched Reddit sentiment" item.

**Step 3 — Pick the next slice with the user.** Ranked suggestions (fresh):
1. **S17 — action flips into the daily-summary prompt** (cheap, high user value: the summary should call out "FSLR flipped HOLD→SELL"). The flip query exists (digest panel-9); feed its rows into `analysis_data` and a "Cambios de recomendación vs ayer:" block in the summary prompt.
2. **Weekly retrospective (S5)** — one extra Haiku call on Fridays; persists a week-in-review; pairs naturally with the predictions dashboard.
3. **Trending-unknown persistence (migration 004)** — so "should I watchlist this?" signals survive.
4. **S18 remainder** — `extract_ticker_mentions` stopword tests, dedup-window test, `_pct_change` fixtures.
5. **Predictions dashboard follow-ups** — per-ticker sparkline of past actions, or a BUY/SELL-only "actionable calls" filter row, if the user wants the simplified view even leaner.
6. **Token trims** (see caveats above) — only if the user re-raises cost.

**Step 4 — Validate whatever you build** the session-12 way: pytest, full `env -u ANTHROPIC_API_KEY .venv/bin/python -m src.main --dry-run` (expect 63 ok / 0 failed; batch poll adds a few minutes), extract-and-run any touched dashboard rawSql with the collation init_command.

**Step 5 — Close out per the ritual.** Update PLAN.md; write `handoffs/HANDOFF_13.md` with a complete copy-pasteable next prompt + a detailed TODO an older model can follow + fresh suggestions; commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_12.md and PLAN.md before doing anything — HANDOFF_12 has the detailed step-by-step TODO for session 13; follow it in order. Context: session 12 (branch feat/session-12-review-fixes, pushed NOT merged, off main = bb5ae86) fixed all of session 11's review findings — F2 macro/summary failures can't kill price collection, F3 RSI epsilon fix, F4 NULL-ticker reddit dedup, F5 no placeholder summaries, F6 summary max_tokens 2048, F7 workflow hygiene (concurrency group, 60-min timeout, evaluator needs no API key, tests.yml main-only) — and migrated the 63 per-ticker calls to the Message Batches API (50% discount, ~$0.15 → ~$0.08/run; custom_ids are t<index> because symbols contain dots; 45-min poll deadline then cancel; single-call analyze_ticker kept as fallback sharing the same request builder). It also shipped grafana/predictions_dashboard.json (task D: latest call per ticker with per-ticker 7d hit rate, weekly trend, how-to-read), fixed the track-record dashboard's Grafana import failure (invalid timeSettings.weekStart/nowDelay/quickRanges + stray vizConfig.spec.version — never emit those keys), removed the digest-duplicated summary/macro panels from recommendations_dashboard.json, and refreshed PROJECT_SUMMARY/README. Validation: pytest 24 passed; all 24 dashboard rawSql queries run against the live DB (use SET collation_connection = utf8mb4_unicode_ci from Python — two v_ticker_status_multi panels false-fail otherwise); full dry-run exercised the real batch path. F1 is closed: production cron is green since the 2026-07-09 credit top-up. Your step 1 is the merge gate: ask the user (AskUserQuestion) if predictions + track-record dashboards imported and render; if yes, ff-only merge the branch to main, push, and verify the first production batch run via gh run list + logs (look for "Submitted message batch" and the cost line). Then check Reddit creds (grep -c '^REDDIT_' .env — still 0 as of 07-09), and pick the next slice with the user: S17 action flips into the summary prompt (recommended, cheap), S5 weekly retrospective, migration 004 trending-unknown persistence, S18 remaining tests, predictions-dashboard follow-ups, or further token trims (summary reasoning truncation, 2-sentence reasoning cap — documented in HANDOFF_12 caveats). Create the session worktree + branch (feat/session-13-<slug>) first, confirm the task list with the user, batch the work, validate (pytest + full dry-run + rawSql extraction), and close out per the ritual: update PLAN.md, write handoffs/HANDOFF_13.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push without merging, and print the full next-session prompt in the chat.
