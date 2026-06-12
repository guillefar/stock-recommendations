# Handoff 08 — 2026-06-12 (session 08)

Continues [HANDOFF_07.md](HANDOFF_07.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

> **Handoff files now live in [`handoffs/`](.).** Links to repo-root files (code, PLAN, etc.) use `../`; links to sibling handoffs are bare.

## What session 08 did — Wave 2 finished + cron + handoffs folder

Branch **`feat/session-08-wave-2-finish`** (off `main` @ `cc1319f`), in worktree `.claude/worktrees/session-08-wave-2-finish`. Pushed, **not merged** — merging is the user's call and the first gate for session 09.

1. **Merge gate cleared.** Git confirmed session 07's `feat/session-07-d3-wave-2` was fast-forwarded onto `main`/`origin/main` (`cc1319f`) before this session — so news/earnings reach production prompts now.
2. **Cron verification (read-only).** `price_checks`: 63 rows for 2026-06-12 (the only day so far — today). `recommendations`: still one batch/weekday at ~13–14h UTC (the 14:00 cron); **no 20:00-UTC batch has ever materialized** (today's would fire later, but the schedule is being replaced). `recommendation_outcomes`: 693, unchanged (06-12 recs mature ~06-19). D1 (panel-9) still empty. Side finding that grounded item 3: over 14 days, **40 HOLDING recs returned WATCH** (would coerce → HOLD), 8 returned SELL; the WATCHLIST side was clean (339 WATCH / 1 AVOID, zero out-of-set).
3. **Cron → once/weekday at 12:00 CEST (10:00 UTC)** in [.github/workflows/run_recommendations.yml](../.github/workflows/run_recommendations.yml) (user decision; replaced the two `0 14`/`0 20` lines). DST caveat documented inline: GitHub cron is UTC and ignores DST, so during CET winter it fires at 11:00 local. This **reverses the earlier two-runs/day decision** — D1 stays permanently empty; the 4h per-run dedup window is kept as a guard against workflow retries.
4. **Wave 2 item 3 — action set constrained per phase.** New pure module [src/analysis/actions.py](../src/analysis/actions.py): `allowed_actions(phase)` + `coerce_action(action, phase)` with the explicit mapping (HOLDING: BUY→HOLD, WATCH→HOLD, AVOID→SELL; WATCHLIST: HOLD→WATCH, SELL→AVOID; unknown → phase neutral), every coercion logged via `logger.warning`. `analyze_ticker` states the phase's allowed set in the prompt wording **and** pins it via the JSON-schema `enum`, then applies `coerce_action` as a defensive backstop. New [tests/test_actions.py](../tests/test_actions.py) — 5 tests.
5. **Wave 2 item 4 — structured JSON output.** `analyze_ticker` in [src/analysis/claude_client.py](../src/analysis/claude_client.py) now passes `output_config={"format": {"type": "json_schema", "schema": …}}` (the `/claude-api`-recommended mechanism; supported on Haiku 4.5) and parses via a new `_structured_json` helper — no ```-fence stripping, still returns `None` on `stop_reason == "refusal"` / empty / truncated content so the caller skips persistence (no fake HOLD). `_parse_json` is retained for the macro + summary calls (looser/array schemas — converting those is a follow-up, S15 below).
6. **`cache_control` no-op removed** from all three Claude calls. Haiku 4.5's minimum cacheable prefix is **4096 tokens** (`/claude-api` → prompt-caching); the `_MACRO_SYSTEM` / `_RECOMMENDATION_SYSTEM` / `_SUMMARY_SYSTEM` prompts are a few hundred chars, so the ephemeral marker never cached. System prompts are now plain strings.
7. **Handoff files moved** to [`handoffs/`](.) and intra-repo links updated (PLAN.md pointers + this file).

## Validation evidence

- **pytest: 14 passed** (4 outcomes + 5 prices + 5 actions).
- **Full `python -m src.main --dry-run`: 63 ok / 0 failed**, exit 0, all writes logged `[dry-run]` (no DB writes). The structured-output path (`output_config.format`) was exercised against the real API (HTTP 200s).
- **0 coercion warnings / no out-of-set actions** — the schema `enum` held, so `coerce_action` never had to fire. Action mix this run: **8 BUY / 2 SELL / 27 HOLD / 25 WATCH / 1 AVOID** (= 63). Holdings (HOLD 27 + SELL 2 = 29) returned **zero WATCH** — exactly the item-3 fix (previously ~14% of holdings came back WATCH) — and BUY now appears decisively (was 0 in the prior live data).
- SDK: `anthropic==0.102.0`; `messages.create` accepts `output_config`.
- Cron-verification SQL ran against the live DB (numbers above).
- Committed as `78a2487` and pushed.

> Note: validation was briefly blocked mid-session by a sandbox command-approval outage ("Error: Stream closed" on `python`/`pytest`/`git commit`); it recovered and everything above was run for real before commit.

## State of play / caveats

- **`feat/session-08-wave-2-finish` committed (`78a2487`) + pushed, not merged.** Merging is step 1 of session 09. The cron change only takes effect on `main`.
- **Validation passed** (see above) — items 3 + 4 are verified against the real API. If `output_config.format` ever errors on a model change, the fallback is forced tool-use (`tool_choice={"type":"tool","name":...}` with the same schema as `input_schema`).
- **D1 (panel-9) is now permanently empty** by the single-cron decision. Consider removing panel-9 or repurposing it (e.g. day-over-day action flips) in a future dashboard pass.
- **Reddit still dark** — `grep -c '^REDDIT_' .env` = 0. https://www.reddit.com/prefs/apps → "script" app; put `REDDIT_CLIENT_ID/SECRET/USER_AGENT` in `.env` AND the three GitHub Actions secrets.
- Carried: yfinance's internal 404 ERROR lines on ETF calendar lookups (cosmetic, S13); the 252 pre-price_checks matured candidates + pre-fix NULL-entry-price ETF recs stay ungradeable (S11 could recover the latter).

## Invariants (don't break)

- Never write to `stock-snapshots` tables (read-only). Tables this repo owns: `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- `analyze_ticker` returns `None` on failure — never a fake HOLD.
- Grafana dashboards must be **schema-v2** (`elements`/`layout`).
- Per-session ritual: **worktree + branch first** → confirm task list → batch work → close with docs + numbered handoff → push the branch (never merge to `main` yourself) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## Suggestions (fresh, for discussion; NOT committed work)

- **S15 — convert macro + summary to structured output too.** `analyze_macro` (array of 0–5 theme objects) and `generate_daily_summary` (fixed object: summary/hot_tickers/overall_sentiment enum) still use `_parse_json` string-stripping. Summary is a clean fixed-schema win; macro needs an array-of-objects schema (`source_headlines`/`affected_sectors` arrays). Would let `_parse_json` be deleted entirely.
- **S16 — drop or repurpose D1 (panel-9).** With one run/day it can never populate. Replace with a day-over-day "action flips" table (the Wave 4 flip-detection idea) so the panel earns its space.
- **S7 — prompt/model provenance columns (carried, now more valuable).** Session 08 changed the prompt *and* the parse path; without a prompt-version column, pre/post hit-rate comparisons are confounded. A `prompt_version` (or hash) + `model_used` already-exists column would let outcomes be sliced by prompt era.
- **S14 — persist the news shown to the model (carried).** Reasoning can cite headlines but they aren't stored; fold `news` titles into the `sentiment` JSON or a new column in `write_recommendation`.
- **S13 — silence yfinance's internal 404 ERROR lines (carried, trivial).** `logging.getLogger("yfinance").setLevel(logging.CRITICAL)` around the calendar call.
- **S11 — backfill NULL entry prices (carried).** One-off script to patch old European-ETF recs from historical closes; recovers hundreds of gradeable rows.

## Detailed TODO for session 09 (step-by-step; follow in order)

**Step 0 — Orient.** Read [HANDOFF_08.md](HANDOFF_08.md) (this file) and [PLAN.md](../PLAN.md). Session 08 is committed (`78a2487`) and validated (pytest 14, dry-run 63/0, 0 coercions) — no leftover validation to run. Session 09 scope: post-merge cron verification, then start Wave 3.

**Step 1 — Merge gate.** Ask the user to confirm `feat/session-08-wave-2-finish` is merged to `main` (or to merge it now — never merge yourself). Until merged, the cron change and Wave 2 items 3–4 don't reach production.

**Step 2 — Workspace.** `git checkout main && git pull`, then `git worktree add .claude/worktrees/session-09-<topic> -b feat/session-09-<topic> main`, and inside it:
```bash
ln -s /home/guillo/Git/stock-recommendations/.env .env
ln -s /home/guillo/Git/stock-recommendations/.venv .venv
```
Confirm the session task list with the user. Re-check Reddit creds: `grep -c '^REDDIT_' .env`.

**Step 3 — Post-merge + cron verification (read-only).** After the merge, confirm the new single cron fired:
```sql
SELECT DATE(generated_at) d, HOUR(generated_at) h, COUNT(*) FROM recommendations
  WHERE generated_at >= '2026-06-15' GROUP BY d,h ORDER BY d DESC, h;   -- expect ONE bucket/weekday at ~10 UTC
SELECT as_of_date, COUNT(*) FROM price_checks GROUP BY as_of_date ORDER BY as_of_date DESC LIMIT 7;  -- ~63/weekday
SELECT COUNT(*) FROM recommendation_outcomes;   -- should grow past 693 once 2026-06-12+ recs mature (~06-19)
SELECT CASE WHEN h.ticker_id IS NOT NULL THEN 'HOLDING' ELSE 'WATCHLIST' END phase, r.action, COUNT(*)
  FROM recommendations r LEFT JOIN holdings h ON h.ticker_id=r.ticker_id AND h.quantity>0
  WHERE r.generated_at >= '2026-06-15' GROUP BY phase, r.action;  -- confirm NO HOLDING WATCH/BUY/AVOID rows post-merge
```
The last query is the real-world check that item 3 worked: post-merge there should be **zero** out-of-set actions (the enum prevents them). Also check whether outcomes finally grew and whether the GH Actions run history shows the single 10:00-UTC run succeeding.

**Step 4 — Start Wave 3 (observability & hygiene).** Pick with the user. Highest-leverage first:
- **Cost telemetry:** accumulate `response.usage` (input/output/cache tokens) across the 2+N Claude calls; log totals + estimated USD at run end. (Now that `cache_control` is gone, this also confirms there's no caching to miss.)
- **Pin `requirements.txt`** (yfinance breaks compat often) and **add `pytest` to a dev-requirements file + a CI test step** in the workflow.
- **README.md** at repo root pointing at SPEC / PROJECT_SUMMARY / PLAN / `handoffs/`, plus Grafana import notes.
- Consider **S15** (structured output for macro + summary) and **S16** (drop/repurpose D1) as quick wins.

**Step 5 — Validate.** `.venv/bin/python -m pytest tests/ -q`; full `.venv/bin/python -m src.main --dry-run`. No real run needed (cron covers it).

**Step 6 — Close out.** Update [PLAN.md](../PLAN.md); write `handoffs/HANDOFF_09.md` (what was done, validation evidence, complete copy-pasteable next prompt, detailed TODO an older model can follow, fresh suggestions); commit; push the branch (no merge); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_08.md and PLAN.md before doing anything — HANDOFF_08 has the detailed step-by-step TODO for session 09; follow it in order. Context: session 08 finished Wave 2 on branch feat/session-08-wave-2-finish (committed 78a2487, pushed, NOT merged; validated: pytest 14 passed, dry-run 63 ok / 0 failed, 0 coercions / no out-of-set actions) — action set is now constrained per phase (HOLDING→{HOLD,SELL}, WATCHLIST→{BUY,WATCH,AVOID}) via a JSON-schema enum plus a logged coerce_action backstop in src/analysis/actions.py (+ tests/test_actions.py), and analyze_ticker switched to structured output (output_config.format, json_schema) instead of _parse_json string-stripping, returning None on refusal/truncation; the no-op cache_control was removed from all three Claude calls (Haiku min cacheable = 4096 tokens). The recommendations cron was changed to once/weekday at 12:00 CEST (10:00 UTC), reversing the two-runs/day decision (so D1/panel-9 stays empty). Handoff files were moved to handoffs/. First confirm with me that I merged feat/session-08-wave-2-finish to main (the cron change + Wave 2 items 3–4 only reach production once merged). Then create the session worktree + branch and confirm the task list. After that: post-merge cron verification (single 10:00-UTC batch/weekday, zero out-of-set HOLDING actions, whether outcomes grew past 693), then start Wave 3 (cost telemetry, pin requirements.txt + add pytest/CI step, README at repo root pointing at handoffs/, and consider S15 structured-output for macro+summary / S16 drop-or-repurpose D1). Also check whether I added the Reddit credentials yet. Close out per the ritual: update PLAN.md, write handoffs/HANDOFF_09.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push the branch without merging, and print the full next-session prompt in the chat.
