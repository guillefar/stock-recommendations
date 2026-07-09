# Handoff 11 — 2026-07-09 (session 11: full code + docs review)

Continues [HANDOFF_10.md](HANDOFF_10.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

> Handoff files live in [`handoffs/`](.). Links to repo-root files use `../`; links to sibling handoffs are bare.

## What session 11 did — review only, zero code changes

Session 11 was a **read-only review of the whole codebase and docs** by a newer model (Claude Fable 5). No branch, no worktree, no edits — the deliverable is this handoff: verified findings (F1–F8), doc-drift list, and a prioritized TODO for session 12. API facts in the findings (Haiku pricing, cache minimums, Batch API discount, structured-output usage) were re-verified against the current Claude API reference — the code's constants are all correct.

**User actions taken after the review (2026-07-09):** ① **API credits topped up** (the 06-30 → 07-08 outage is over — verify the next cron is green); ② **`feat/session-10-wave-4` merged** — `main` is now **`bb5ae86`** (track-record dashboard + docs).

**New user ask (verbatim intent):** *"a more simplified, clear view of the predictions, including a history of the accuracy of the predictions over time."* → task D below. Note the accuracy-history half already exists in [grafana/track_record_dashboard.json](../grafana/track_record_dashboard.json) (weekly hit-rate trend panel) — but it has **never been imported/eyeballed** (carried from HANDOFF_10), so session 12 should start there before building anything new.

## Findings (verified against code, logs, and the live API reference)

### F1 — Production was down 7 runs; grading-gap risk (RESOLVED by top-up, verify)
Every scheduled run **2026-06-30 → 2026-07-08 failed** (confirmed via `gh run list` + `gh run view --log-failed`): `anthropic.BadRequestError: 400 … credit balance is too low`, raised at the first Claude call (`analyze_macro`). Consequence: **zero `price_checks` rows for those 7 weekdays** — the price upsert lives inside `main.py`'s per-ticker loop, which is never reached when step 4 (macro) raises. Math check: a rec generated on day D needs an exit price in [D+7, D+21]; the ~10-day gap is shorter than the 14-day window, so **no recommendation becomes permanently ungradeable provided the cron is green from ~07-09/07-10**. The outcome-eval step (`if: !cancelled()`, no API) kept running throughout.

### F2 — Price recording is coupled to Claude availability (root cause of F1's damage)
`main.py` runs Claude call #1 (macro, [src/main.py:61](../src/main.py#L61)) *before* the per-ticker loop that writes `price_checks`. Any Claude outage (credits, 5xx, rate limit) therefore also kills the day's price collection — exactly the data S1 exists to protect. Per-ticker error isolation (Wave 1) covers everything *except* the two shared Claude calls. **Fix:** wrap `run_macro_analysis` in try/except → degrade to `macro_signals = []` (the prompt already handles "Sin señales macro relevantes"), log the error, continue; likewise wrap `run_daily_summary` so a summary failure doesn't kill the final log/exit path. Keep the existing "exit non-zero if every ticker failed" rule.

### F3 — RSI is inverted for all-gain windows (verified with a repro)
[src/collectors/prices.py:107](../src/collectors/prices.py#L107): `rs = gain / loss.replace(0, float("inf"))`. When a ticker closes higher 14 sessions in a row, `loss = 0` → `rs = 0` → **RSI = 0** (screams "extreme oversold, bullish") when the correct value is **100** (extreme overbought). Repro run this session:

```python
import pandas as pd
from src.collectors.prices import _compute_rsi
_compute_rsi(pd.Series([100.0 + i for i in range(20)]), 14)  # → 0.0, should be ~100
_compute_rsi(pd.Series([100.0 - i for i in range(20)]), 14)  # → 0.0, correct
```

**Fix:** replace the zero loss with a tiny epsilon (`loss.replace(0, 1e-10)`) so `rs → huge` → RSI → ~100. Add unit tests (all-gains ≈ 100, all-losses ≈ 0, mixed sanity) — overlaps with the open S18 item.

### F4 — Unmatched Reddit posts will duplicate forever (dormant until creds arrive)
[src/main.py:149](../src/main.py#L149) writes unmatched posts with `ticker_id = NULL`; `reddit_mentions`' `UNIQUE KEY uq_post_ticker (post_id, ticker_id)` treats every NULL as distinct in MySQL, so `INSERT IGNORE` never dedups them. A hot post that stays on /r/stocks 3 days → 3 rows. **Fix (no migration needed):** in `write_reddit_mentions`, when `ticker_id is None`, pre-SELECT the existing NULL-ticker `post_id`s for the incoming batch and skip those. (Schema alternative: unique key on a `COALESCE(ticker_id, 0)` generated column — heavier, not required.)

### F5 — Failed daily summary is persisted as real data
`generate_daily_summary` ([src/analysis/claude_client.py:335](../src/analysis/claude_client.py#L335)) returns `{"summary": "Error generando resumen.", …}` on refusal/truncation, and `write_daily_summary` **upserts it over that day's row** — contradicting the project's own Wave-1 rule ("never persist parse-failure fallbacks"; `analyze_ticker` already returns `None`). **Fix:** default to `None`, and in `main.py` skip `write_daily_summary` + log when summary is `None` (guard the final log line's `summary.get(...)` too).

### F6 — Summary truncation risk at `max_tokens=1024`
The summary call's input includes all ~63 recommendations with reasoning and must emit 3–5 Spanish markdown paragraphs as JSON. If it hits `max_tokens`, structured output is cut mid-JSON → the F5 fallback. **Fix:** bump to 2048 (cost impact ≈ nothing) and make `_structured_json` log `stop_reason == "max_tokens"` explicitly (it currently surfaces only as a JSON parse error).

### F7 — Workflow hygiene
- [run_recommendations.yml](../.github/workflows/run_recommendations.yml): no `timeout-minutes`, no `concurrency` group. A hung yfinance call could overlap the next day's run (the 4h dedup protects recs, **not** the daily-summary upsert). Add `timeout-minutes: 30` on the job and `concurrency: { group: stock-recs, cancel-in-progress: false }`.
- [tests.yml](../.github/workflows/tests.yml): triggers on `push: branches: ["**"]` **and** `pull_request` → every PR runs the suite twice. Restrict push to `main`.
- `evaluate_outcomes` needlessly requires `ANTHROPIC_API_KEY` (only because `load_config()` demands it). Make the key optional in [src/config.py](../src/config.py) (default `""`), validate it in `ClaudeClient.__init__` instead, then drop the key + comment from the evaluate step's env. Matters because the evaluator is the only step that works during a credit outage.

### F8 — Cost lever (optional): Message Batches API
Verified current: the Batches API gives a **50% discount** and supports structured output on Haiku 4.5. The 63 per-ticker calls are independent and latency-irrelevant (daily cron) — batching would roughly halve the ~$0.147/run cost. At ~$3/month total this is optional; adopt only if a session has slack (poll loop replaces the per-ticker call sequence; keep macro + summary as plain calls since they order-depend).

Small fold-ins when touching the area: `Config.dry_run` is unused; `except (prawcore.PrawcoreException, Exception)` in reddit.py is just `except Exception`; macro-signal→ticker matching is duplicated between [src/main.py:126](../src/main.py#L126) and `analyze_ticker` (existing fold-in item, along with the `get_active_tickers` UNION refactor).

### Doc drift — PROJECT_SUMMARY.md is 3 sessions behind
Fix all of these in one pass (offline):
1. "Cron 2×/day, 11:00 & 17:00 ART / 14:00 & 20:00 UTC" → **once per weekday, 10:00 UTC** (session 08).
2. "writes to four new tables" + the table list → the repo owns **six**: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks` (missing entirely).
3. "`fetch_ticker_news` (currently unused)" → wired into the per-ticker prompt in session 07 (+ `fetch_next_earnings` exists).
4. Conventions: "parser strips markdown fences as a fallback" → all three calls use structured output (`output_config.format`) since S15; `_parse_json` is deleted.
5. Module map: add `src/analysis/actions.py`; Dashboards section: add `track_record_dashboard.json` (README already lists it).

## State of play / caveats

- **`main` = `bb5ae86`** (session 10 merged). No unmerged branches. pytest baseline: 14 passed.
- **API credits topped up 2026-07-09** — but no green scheduled run has been *observed* yet. Session 12 step 1: `gh run list --workflow=run_recommendations.yml --limit 3` and confirm the latest scheduled run succeeded; if the next cron hasn't fired yet, trigger `workflow_dispatch` once.
- **`price_checks` gap 06-30 → top-up date** (F1) — self-healing once the cron is green; no action needed beyond confirming.
- **Track-record dashboard still not imported/eyeballed** (carried from HANDOFF_10) — the `stat`/`text` panels were never live-render-tested.
- **Reddit still dark** — `grep -c '^REDDIT_' .env` = 0 (F4 is dormant until this changes; fix it *before* enabling creds).
- **Local runs need `env -u ANTHROPIC_API_KEY`** — empty shell var shadows `.env` (`load_dotenv` doesn't override). Ad-hoc scratchpad scripts: absolute path to `load_dotenv('/home/guillo/Git/stock-recommendations/.env')` + `PYTHONPATH=.`.
- Carried: yfinance 404 ERROR lines (S13); 252 pre-price_checks matured candidates stay ungradeable; `price_snapshots` stale since 2026-05-22.
- **This handoff was written outside any branch** (review session, no code changes). If it's not committed by the time session 12 starts, commit it from the main checkout (or make it the first commit on the session-12 branch) so the worktree sees it.

## Invariants (don't break)

- Never write to `stock-snapshots` tables (read-only). Tables this repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- `analyze_ticker` returns `None` on failure — never a fake HOLD (F5 extends this rule to the summary).
- Grafana dashboards must be **schema-v2** (`elements`/`layout`), datasource uid `cfadv004ogglcf` (group `mysql`), integer panel ids.
- Per-session ritual: **worktree + branch first** → confirm task list → batch work → close with docs + numbered handoff → push the branch (never merge to `main` yourself unless asked) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## Detailed TODO for session 12 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). If this file is missing from your worktree, it's uncommitted in the main checkout — commit it first. Note PLAN.md's "Current state" predates the session-10 merge and this review; you'll refresh it at close-out.

**Step 1 — Confirm production is green again.** `gh run list --workflow=run_recommendations.yml --limit 3`. If the latest scheduled run after 2026-07-09 succeeded, F1 is closed (say so). If no scheduled run has fired yet, trigger one: `gh workflow run run_recommendations.yml`, wait, check. If it still fails on credits, stop and tell the user.

**Step 2 — Dashboard import gate (carried).** Ask the user to import [grafana/track_record_dashboard.json](../grafana/track_record_dashboard.json) (Dashboards → New → Import, MySQL datasource) and confirm the scorecard `stat` tiles + "how to read" `text` panel render. This also feeds task D — the user should see what already exists before deciding what "simplified view" adds.

**Step 3 — Workspace.** From the main checkout: `git pull`, then
```bash
git worktree add .claude/worktrees/session-12-review-fixes -b feat/session-12-review-fixes main
cd .claude/worktrees/session-12-review-fixes
ln -sf /home/guillo/Git/stock-recommendations/.env .env
ln -sf /home/guillo/Git/stock-recommendations/.venv .venv
```
Confirm the task list with the user (AskUserQuestion). Re-check Reddit creds: `grep -c '^REDDIT_' .env`.

**Step 4 — Task A: pipeline fixes (F2–F6).** All offline-testable except the final dry-run.
1. **F2** [src/main.py](../src/main.py): try/except around `run_macro_analysis` → on failure log + `macro_signals = []` (and `macro_signal_ids = []`; the per-ticker "relevant macro" loop already tolerates empty). Try/except around `run_daily_summary` + its write. Make the final log line robust to `summary is None`.
2. **F3** [src/collectors/prices.py](../src/collectors/prices.py): `loss.replace(0, float("inf"))` → `loss.replace(0, 1e-10)`. Tests in [tests/test_prices.py](../tests/test_prices.py): all-gains ≥ 99, all-losses ≤ 1, a mixed series in (0, 100).
3. **F4** [src/persistence/writers.py](../src/persistence/writers.py): in `write_reddit_mentions`, when `ticker_id is None`, `SELECT post_id FROM reddit_mentions WHERE ticker_id IS NULL AND post_id IN (…)` and skip those posts.
4. **F5** [src/analysis/claude_client.py](../src/analysis/claude_client.py): `generate_daily_summary` → `_structured_json(response, default=None)`; main skips the write + counts it as a (non-fatal) failure in the log.
5. **F6** same file: summary `max_tokens` 1024 → 2048; in `_structured_json`, if `stop_reason == "max_tokens"` log that explicitly before the parse attempt.
6. Fold-ins if touching anyway: drop unused `Config.dry_run`; simplify the reddit except clause.

**Step 5 — Task B: workflow + config hygiene (F7).** `timeout-minutes: 30` + `concurrency` on the recommendations job; `tests.yml` push → `branches: [main]`; `ANTHROPIC_API_KEY` optional in `load_config()` (validate non-empty in `ClaudeClient.__init__`, clear error message), drop key + stale comment from the evaluate step.

**Step 6 — Task C: doc refresh.** Apply the five PROJECT_SUMMARY.md corrections listed above. Sanity-check README against reality while there.

**Step 7 — Task D: simplified predictions view (the new user ask).** Discuss before building (AskUserQuestion): the accuracy-history half already exists (track-record weekly trend). Proposed shape — either a new small **"Predictions" dashboard** or a header section on the digest — containing: (a) **latest call per ticker** table: symbol, phase, action (color-mapped), confidence, entry price, 1-line reasoning, and ideally that ticker's own historical hit rate; (b) the **weekly hit-rate trend** (reuse the track-record query); (c) nothing else. Options to offer the user: new dashboard vs. extend digest vs. extend track-record; and whether to also do the HANDOFF_10 consolidation (dedupe Daily Market Summary + Macro Signals panels between digest and recommendations dashboards) in the same pass. Validate the way session 10 did: extract every `rawSql` from the written JSON and run it against the live DB; schema-v2, integer ids, `variables: []`.

**Step 8 — Validate.** `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q` (expect 14 + new RSI tests). Full `env -u ANTHROPIC_API_KEY .venv/bin/python -m src.main --dry-run` (credits are restored — expect 63 ok / 0 failed and the cost line). For F2, a quick stub test: monkeypatch `run_macro_analysis` to raise and assert the run still processes tickers.

**Step 9 — Close out.** Update [PLAN.md](../PLAN.md) (current state → post-review; mark F-items done; fold remaining review items into the roadmap); write `handoffs/HANDOFF_12.md` (what was done, validation evidence, complete copy-pasteable next prompt, detailed TODO, fresh suggestions); commit; push the branch (no merge unless asked); print the full next prompt in chat.

**Deferred / backlog (don't start unless the user picks them):** S17 action flips into the summary prompt (needs credits, cheap now); persist trending-unknown tickers (migration 004); S5 weekly retrospective; S13 yfinance log silencing; remaining S18 tests (`extract_ticker_mentions` stopwords, dedup window); F8 Batch API (50% cost cut); track-record follow-ups from HANDOFF_10 (sector "(unknown)" bucket, confidence×horizon panel, per-ticker leaderboard — the leaderboard dovetails with task D's per-ticker hit rate).

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_11.md and PLAN.md before doing anything — HANDOFF_11 has the detailed step-by-step TODO for session 12; follow it in order. Context: session 11 was a read-only full-code review (no code changes; main = `bb5ae86` with session 10's track-record dashboard merged). The review found and verified: F1 — every scheduled cron 06-30→07-08 failed with 400 "credit balance too low" at analyze_macro (credits topped up 2026-07-09 — your step 1 is confirming the next run is green via `gh run list`); F2 — price_checks writing is coupled to the macro Claude call, so a Claude outage kills price collection (fix: try/except → empty macro signals, continue); F3 — VERIFIED BUG: `_compute_rsi` returns RSI 0 instead of 100 for a 14-day all-gain window because of `loss.replace(0, inf)` (fix: epsilon; add tests); F4 — unmatched Reddit posts (ticker_id NULL) bypass the UNIQUE key (MySQL NULL semantics) and will duplicate daily once Reddit creds exist (fix: SELECT-guard); F5 — a failed daily summary persists "Error generando resumen." over the day's row (fix: return None, skip write); F6 — summary max_tokens 1024 may truncate (fix: 2048 + explicit max_tokens stop_reason logging); F7 — workflow hygiene (job timeout, concurrency group, tests.yml double-runs on PRs, ANTHROPIC_API_KEY needlessly required by the evaluator); plus a 5-point PROJECT_SUMMARY.md doc-drift list. NEW USER ASK (task D): "a more simplified, clear view of the predictions, including a history of the accuracy of the predictions over time" — the history half already exists in grafana/track_record_dashboard.json (weekly hit-rate trend), which the user has still NOT imported/eyeballed (that's your step 2); discuss the design with AskUserQuestion before building (latest-call-per-ticker table + hit-rate trend; new dashboard vs extend digest; optionally fold in the HANDOFF_10 dashboard consolidation). Real-world flags: Reddit creds still missing (fix F4 before they arrive); local runs need `env -u ANTHROPIC_API_KEY` (empty shell var shadows .env); if HANDOFF_11.md is missing from your worktree it's uncommitted in the main checkout — commit it first. Create the session worktree + branch (`feat/session-12-review-fixes`), confirm the task list with the user, then execute: A) pipeline fixes F2–F6 with tests, B) workflow/config hygiene F7, C) PROJECT_SUMMARY refresh, D) simplified predictions view. Validate: pytest (14 + new), full --dry-run (63 ok expected — credits restored), extract-and-run every dashboard rawSql against the live DB. Close out per the ritual: update PLAN.md, write handoffs/HANDOFF_12.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push the branch without merging, and print the full next-session prompt in the chat.
