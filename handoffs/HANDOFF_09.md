# Handoff 09 — 2026-06-29 (session 09)

Continues [HANDOFF_08.md](HANDOFF_08.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

> Handoff files live in [`handoffs/`](.). Links to repo-root files use `../`; links to sibling handoffs are bare.

## What session 09 did — Wave 3 complete + post-merge verification

Branch **`feat/session-09-wave-3`** (off `main` @ `b4af216`), in worktree `.claude/worktrees/session-09-wave-3`. Pushed, **not merged** — merging is the user's call and the first gate for session 10.

1. **Merge gate cleared.** `main` is at `b4af216` (session 08's Wave 2 work) — the single `0 10` UTC cron and [src/analysis/actions.py](../src/analysis/actions.py) are in production. Session 08's `feat/session-08-wave-2-finish` was merged before this session.
2. **Post-merge cron verification (read-only).** Since 2026-06-15 exactly **one batch of 63 fires per weekday** (06-15…06-19, 06-22…06-26, 06-29 — no weekend runs, no second daily batch; GitHub's scheduling lag puts the `0 10` cron at ~12–15h UTC, consistent with prior sessions). `price_checks`: 63/weekday. `recommendation_outcomes`: **693 → 2,118** (the 06-12+ recs matured ~06-19 as predicted). Live `phase × action` since 06-15: HOLDING = {HOLD 265, SELL 54}, WATCHLIST = {BUY 67, WATCH 278, AVOID 29} — **zero out-of-set actions**, so the item-3 enum holds in production.
3. **Wave 3 item — cost telemetry.** [src/analysis/claude_client.py](../src/analysis/claude_client.py): `ClaudeClient` accumulates `response.usage` across all three call types via `_record_usage(response)` (called right after each `messages.create`), with `estimated_cost_usd()` (Haiku 4.5 list pricing in `_PRICE_PER_MTOK`) and `log_usage()`. [src/main.py](../src/main.py) calls `claude.log_usage()` at run end. A real dry-run logged **65 calls, 83.6K in / 12.7K out, cache_write=cache_read=0, $0.1471**.
4. **Wave 3 item — pinned deps + CI.** [requirements.txt](../requirements.txt) pinned to installed versions (`anthropic==0.102.0`, `yfinance==1.3.0`, `feedparser==6.0.12`, `praw==7.8.2`, `pandas==3.0.3`, `PyMySQL==1.1.3`, `python-dotenv==1.2.2`); new [requirements-dev.txt](../requirements-dev.txt) (`-r requirements.txt` + `pytest==9.0.3`); new [.github/workflows/tests.yml](../.github/workflows/tests.yml) runs `pytest tests/ -q` on every push + PR (and `workflow_dispatch`).
5. **Wave 3 item — root README.** [README.md](../README.md): docs map (SPEC/PROJECT_SUMMARY/PLAN/handoffs), local run/test commands, env vars, both workflows, migrations, Grafana import notes (schema v2, time-range-picker navigation).
6. **S15 — macro + summary structured output; `_parse_json` deleted.** `analyze_macro` and `generate_daily_summary` now use `output_config={"format": {"type":"json_schema", ...}}` parsed via the existing `_structured_json`. The macro `direction` free-form `{sector: sentiment}` map can't sit under `additionalProperties:false`, so the **schema models it as an array of `{sector, sentiment}` objects** (sentiment enum) and `analyze_macro` folds it back into the `{sector: sentiment}` map before returning — `write_macro_signals` and the dashboards see the identical stored shape. `_parse_json` is gone (only `_structured_json` remains).
7. **S16 — D1/panel-9 repurposed.** [grafana/daily_digest_dashboard.json](../grafana/daily_digest_dashboard.json) panel-9 changed from "Same-day run disagreements" (permanently empty under one cron) to **"Action flips vs previous run (D1)"**: each row joins a recommendation to its immediately-preceding run for the same ticker where the action changed (day-over-day under the single cron). Title/description/SQL updated; the two action-column color matchers renamed `action 1`/`action 2` → `prev action`/`new action`.

## Validation evidence

- **pytest: 14 passed** (4 outcomes + 5 prices + 5 actions) — unchanged set; no new tests this session (see S-list).
- **Full `python -m src.main --dry-run`: 63 ok / 0 failed**, exit 0. All three structured-output call types (macro, ticker, summary) were exercised against the real API (HTTP 200s — the run completed through "Generating daily summary" + "Run complete" with `overall_sentiment=MIXED` and populated `hot_tickers`, so the macro+summary schemas are API-accepted). Cost line printed. **No coercion warnings / parse failures / refusals.**
- **Flip SQL validated live** against the DB (12 day-over-day flips in the recent range, e.g. ASTS SELL→HOLD, FSLR HOLD→SELL, FIX BUY→WATCH — all within-phase).
- **Dashboard JSON re-parses** (`json.load` OK after the edits).
- Committed + pushed (see below).

> ⚠️ **API credit balance is exhausted.** A second confirmation dry-run returned `400 invalid_request_error: "Your credit balance is too low"` — the first run drained the remaining balance. **Top up at the Anthropic Console before the next cron run**, or the scheduled production run will fail at the first Claude call (`analyze_macro`). This is the highest-priority real-world item for session 10.

> Note: locally, the Bash shell exports an **empty** `ANTHROPIC_API_KEY`, which shadows the real value in `.env` (`load_dotenv` doesn't override existing env vars). Run local commands with `env -u ANTHROPIC_API_KEY .venv/bin/python …` so the `.env` value loads. The GitHub Actions runner doesn't have this problem (secrets are injected directly).

## State of play / caveats

- **`feat/session-09-wave-3` committed + pushed, not merged.** Merging is step 1 of session 10. Wave 3 only reaches production on merge — though everything here is offline hygiene + a dashboard query + telemetry, so nothing changes pipeline behavior except the (harmless) extra usage log line.
- **API credits exhausted** (see above) — fix before the next run.
- **Reddit still dark** — `grep -c '^REDDIT_' .env` = 0. https://www.reddit.com/prefs/apps → "script" app; put `REDDIT_CLIENT_ID/SECRET/USER_AGENT` in `.env` AND the three GitHub Actions secrets.
- Carried: yfinance's internal 404 ERROR lines on ETF calendar lookups (cosmetic, S13); the 252 pre-price_checks matured candidates + pre-fix NULL-entry-price ETF recs stay ungradeable (S11 could recover the latter).

## Invariants (don't break)

- Never write to `stock-snapshots` tables (read-only). Tables this repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- `analyze_ticker` returns `None` on failure — never a fake HOLD.
- Grafana dashboards must be **schema-v2** (`elements`/`layout`).
- Per-session ritual: **worktree + branch first** → confirm task list → batch work → close with docs + numbered handoff → push the branch (never merge to `main` yourself) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## Suggestions (fresh, for discussion; NOT committed work)

- **S17 — feed action flips into the daily-summary prompt.** The flip data now exists (S16 query). Compute the run's flips in [src/main.py](../src/main.py) (compare each ticker's new action to its previous stored row) and pass them into `generate_daily_summary` so the summary text calls out reversals. Completes the Wave 4 "action-flip detection" item.
- **S18 — more unit tests** (the remaining Wave 3 "Tests + CI" gap; CI itself landed). Cover `extract_ticker_mentions` stopwords (`IT`, `GO`, `BE`), `_compute_rsi`/`_pct_change` fixtures, and the per-run dedup window. These run for free now that `tests.yml` exists.
- **S5 — weekly retrospective digest (carried, Wave 4).** Friday run does one extra Claude call summarizing the week (calls vs outcomes, flips, sector exposure); persist + add a panel. ~1 Haiku call/week.
- **S7 — prompt/model provenance columns (carried).** A `prompt_version`/hash + `model_used` column would let outcomes be sliced by prompt era (session 08 + 09 both changed the prompt/parse path).
- **S14 — persist the news shown to the model (carried).** Fold `news` titles into the `sentiment` JSON or a new column.
- **S13 — silence yfinance's 404 ERROR lines (carried, trivial).** `logging.getLogger("yfinance").setLevel(logging.CRITICAL)` around the calendar call.
- **S11 — backfill NULL entry prices (carried).** One-off script to patch old European-ETF recs from historical closes.

## Detailed TODO for session 10 (step-by-step; follow in order)

**Step 0 — Orient.** Read [HANDOFF_09.md](HANDOFF_09.md) (this file) and [PLAN.md](../PLAN.md). Session 09 is committed + validated (pytest 14, dry-run 63/0) — no leftover validation. Scope: confirm merge, **top up API credits**, then start Wave 4.

**Step 1 — Merge gate.** Ask the user to confirm `feat/session-09-wave-3` is merged to `main` (or merge it now — never merge yourself).

**Step 2 — API credits.** Remind the user the API credit balance hit zero this session (a `400 credit balance too low`). Confirm they've topped up before any real run — the scheduled cron will otherwise fail at `analyze_macro`. (You can't check the balance via the API; ask, or attempt a tiny live call and report if it 400s.)

**Step 3 — Workspace.** `git checkout main && git pull`, then `git worktree add .claude/worktrees/session-10-<topic> -b feat/session-10-<topic> main`, and inside it:
```bash
ln -s /home/guillo/Git/stock-recommendations/.env .env
ln -s /home/guillo/Git/stock-recommendations/.venv .venv
```
Confirm the task list. Re-check Reddit creds: `grep -c '^REDDIT_' .env`. (Local runs need `env -u ANTHROPIC_API_KEY` — see caveat above.)

**Step 4 — Post-merge verification (read-only).** Confirm Wave 3 reached `main` harmlessly and the cron kept firing:
```sql
SELECT DATE(generated_at) d, COUNT(*) FROM recommendations
  WHERE generated_at >= '2026-06-29' GROUP BY d ORDER BY d DESC;   -- one batch/weekday
SELECT COUNT(*) FROM recommendation_outcomes;                       -- still growing past 2118
```
Also eyeball the GH Actions run history: the new `tests.yml` should be green on the merge commit, and `run_recommendations.yml` should still be one run/weekday (watch for credit-balance failures if the top-up was late).

**Step 5 — Start Wave 4 (product features).** Pick with the user. Highest-leverage first:
- **S17 — action flips into the summary prompt** (completes the flip-detection item; the dashboard half is done).
- **Persist trending-unknown tickers** (new migration 004 + table, so `find_trending_unknown` results survive).
- **S5 — weekly retrospective digest** (Friday-only extra Claude call + panel).
- **Batched Reddit-mention sentiment** — *gated on Reddit creds existing*.
- Quick win: **S18 more unit tests**, **S13 yfinance log silencing**.

**Step 6 — Validate.** `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`; full `--dry-run` (needs API credits + the env-var unset). If credits are still out, note it and rely on pytest + offline checks.

**Step 7 — Close out.** Update [PLAN.md](../PLAN.md); write `handoffs/HANDOFF_10.md` (what was done, validation evidence, complete copy-pasteable next prompt, detailed TODO an older model can follow, fresh suggestions); commit; push the branch (no merge); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_09.md and PLAN.md before doing anything — HANDOFF_09 has the detailed step-by-step TODO for session 10; follow it in order. Context: session 09 finished Wave 3 on branch feat/session-09-wave-3 (off main @ b4af216, pushed, NOT merged; validated: pytest 14 passed, dry-run 63 ok / 0 failed, no coercions/parse-failures/refusals). Wave 3 delivered: cost telemetry (ClaudeClient accumulates response.usage across the 2+N calls, logs token totals + estimated USD at run end via log_usage() in src/main.py — a real run measured 65 calls / $0.1471 with cache_write=cache_read=0, confirming the session-08 cache_control removal); pinned requirements.txt + a new requirements-dev.txt (pytest) + a CI tests.yml workflow (pytest on every push/PR); a root README.md; S15 (analyze_macro + generate_daily_summary converted to structured output via output_config.format, so _parse_json was deleted — the macro `direction` map is modeled as an array in the schema and folded back to a {sector: sentiment} map before persistence so storage/dashboard are unchanged); and S16 (panel-9 repurposed from the permanently-empty same-day-disagreements table into a day-over-day "Action flips vs previous run" table). Post-merge verification confirmed the single 10:00-UTC cron fires once/weekday, outcomes grew 693→2118, and the per-phase action enum holds live (zero out-of-set actions). TWO real-world flags: (1) the Anthropic API credit balance hit zero mid-session (a 400 "credit balance too low") — confirm with me that I topped it up before any real run, or the cron will fail at analyze_macro; (2) Reddit creds are still missing. Also note: local runs need `env -u ANTHROPIC_API_KEY` because the shell exports an empty key that shadows .env. First confirm with me that I merged feat/session-09-wave-3 to main and topped up API credits. Then create the session worktree + branch and confirm the task list. After that: post-merge verification (single cron still firing, tests.yml green, outcomes growing), then start Wave 4 — S17 (feed action flips into the daily-summary prompt, completing flip detection), persist trending-unknown tickers (migration 004), S5 weekly retrospective, batched Reddit sentiment (gated on creds), plus quick wins S18 (more unit tests) / S13 (silence yfinance 404 logs). Close out per the ritual: update PLAN.md, write handoffs/HANDOFF_10.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push the branch without merging, and print the full next-session prompt in the chat.
