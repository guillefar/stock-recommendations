# Plan & Status

Living document. Update as work progresses. See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for the static overview and [SPEC.md](SPEC.md) for design rationale.

**Last updated:** 2026-06-10

## Current state

All 14 modules from the SPEC build plan exist and the pipeline is wired end-to-end. Migration, GitHub Actions workflow, and a Grafana dashboard are committed. The project has been idle since 2026-05-18 ("Adding dashboard"). Has not been validated against a real run since the Reddit collector was switched from PRAW to RSS.

**Known data caveat (2026-06-10):** the sibling `price_snapshots` table is stale — last row is 2026-05-22, while recommendations run through today. Outcome grading therefore finds zero matured candidates until the `stock-snapshots` collector resumes. Not fixable from this repo (read-only).

## In progress

- _(none)_

## Done (this session — 2026-06-10)

- **Fixed the "never BUY/SELL" problem.** Across 1197 stored recommendations the action split was 739 WATCH / 455 HOLD / 3 AVOID / 0 BUY / 0 SELL. Root cause: the recommendation prompt is judgment-only (no rule maps data→action) and its system prompt ordered "analista **conservador** … NUNCA consejos absolutos," which suppressed decisive calls. Rewrote `_RECOMMENDATION_SYSTEM` and added a per-position decision rubric + confidence-calibration guide in [src/analysis/claude_client.py](src/analysis/claude_client.py). `confidence` remains the model's self-reported certainty (0–1), now with explicit bands.
- **Outcome tracking.** New table [migrations/002_create_recommendation_outcomes.sql](migrations/002_create_recommendation_outcomes.sql) and evaluator [src/evaluate_outcomes.py](src/evaluate_outcomes.py) (`python -m src.evaluate_outcomes [--dry-run]`). Grades each matured recommendation at 7d/30d horizons by joining its stored entry price to the first `price_snapshots` row at/after the horizon, computing forward return and a CORRECT/INCORRECT/NEUTRAL verdict. Migration applied to the DB. Logic unit-tested in [tests/test_outcomes.py](tests/test_outcomes.py). Currently grades 0 rows (see data caveat above).
- **New daily-digest dashboard** [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json), built in the **schema-v2 `elements`/`layout` format** to match the user's Grafana (a first classic-schema attempt failed import validation — their Grafana 13.1.x only accepts v2). Date navigation is via the **time-range picker** (the "selected day" panels query `MAX(date) WHERE $__timeFilter(...)`), since the v2 custom-variable dropdown schema proved unreliable. Panels: full daily summary, that day's recommendations, macro signals, top Reddit posts, an all-history action table, an outcomes table, and a hit-rate-by-action table. All 7 panel queries validated against the live DB.
- **Restored** [grafana/recommendations_dashboard.json](grafana/recommendations_dashboard.json) — the working-tree copy had been truncated to invalid JSON (cut off mid-`timeSettings`). Reset to the committed valid version.
- **Switched Reddit collector to PRAW.** [src/collectors/reddit.py](src/collectors/reddit.py) now uses an authenticated read-only PRAW client instead of the blocked `.json` endpoint; added `reddit_client_id/secret/user_agent` to [src/config.py](src/config.py), `praw` to requirements, the three vars to [.env.example](.env.example), and the secrets to [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml). Verified it imports and degrades gracefully (logs + `[]`) when creds are absent. **Inert until credentials are supplied** (see TODO).

## Done (this session — 2026-06-06)

- **Fix B — restored real Reddit post scores.** Switched [src/collectors/reddit.py](src/collectors/reddit.py) from the RSS endpoint (which doesn't expose `score` or `upvote_ratio`) to Reddit's public `.json` endpoint. Now applies the SPEC filter (`score >= 50` and `upvote_ratio >= 0.7`). This re-enables `find_trending_unknown`, fixes `sentiment.avg_score`, and makes the daily-summary `top_posts` sort meaningful.
- Created [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md), this file ([PLAN.md](PLAN.md)), and [HANDOFF.md](HANDOFF.md) for cross-session context.

## TODO — prioritized

### High priority

- [ ] **Provide Reddit credentials.** The collector was switched to PRAW (done — see below) but is inert until `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` exist. Create a "script" app at https://www.reddit.com/prefs/apps, then add the values to local `.env` AND as GitHub Actions secrets (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`). Until then every recommendation runs with zero Reddit sentiment.
- [ ] **Run end-to-end against production DB with `--dry-run`** to surface any other regressions; capture one ticker's full Claude prompt and response for eyeball review.
- [ ] **Fix workflow schedule.** [.github/workflows/run_recommendations.yml:5](.github/workflows/run_recommendations.yml#L5) — cron is `0 11 * * 1-5` (once/day) but SPEC says 2x/day; comment claims "13:00 UTC" but cron is 11:00 UTC. Either match the comment or commit to the 2x/day schedule.

### Medium priority

- [ ] **Wire `fetch_ticker_news` into the per-ticker prompt.** [src/collectors/prices.py:43](src/collectors/prices.py#L43) is defined but never called. Including ticker-specific news in `analyze_ticker` is the highest-quality improvement available.
- [ ] **Replace `datetime.utcnow()`** throughout [src/persistence/writers.py](src/persistence/writers.py) and [src/collectors/reddit.py](src/collectors/reddit.py). Deprecated on 3.12+; user runs 3.14 locally. Switch to `datetime.now(timezone.utc).replace(tzinfo=None)`.
- [ ] **Add minimal tests** (started — [tests/test_outcomes.py](tests/test_outcomes.py) covers `grade()`; note `pytest` is not yet in requirements.txt):
  - `extract_ticker_mentions` with stopword cases (e.g., posts mentioning `IT`, `GO`, `BE`).
  - `_compute_rsi`, `_pct_change` against fixtures.
  - `_parse_json` against markdown-fence and leading-text variants.
- [ ] **Idempotency hardening for `recommendations`.** [src/persistence/writers.py:76](src/persistence/writers.py#L76) does SELECT-then-INSERT; races under concurrent runs. Add a generated column on `DATE(generated_at)` plus UNIQUE `(ticker_id, that_date)`, then switch to `INSERT IGNORE`.
- [ ] **Pin `requirements.txt`.** yfinance breaks compat often — there's already a workaround for a varying news schema in [src/collectors/prices.py:50](src/collectors/prices.py#L50).
- [ ] **Cost telemetry.** Log `response.usage` totals (input/output/cache-read) at the end of each run. Validates whether `cache_control: ephemeral` on system prompts actually helps across the N ticker calls.

### Low priority

- [ ] One DB connection per run instead of `2 + 2N` opens. Reorganize the conn open/close pairs in [src/main.py](src/main.py).
- [ ] Refactor [src/db.py:20](src/db.py#L20) `get_active_tickers` from LEFT JOIN + OR-in-WHERE to a UNION of two INNER JOINs.
- [ ] Macro→ticker matching ([src/main.py:102-106](src/main.py#L102-L106)) is "first sector match wins"; prefer signals where `direction[sector]` is non-NEUTRAL.
- [ ] Per-post sentiment for `reddit_mentions` — column is currently hardcoded NULL in [src/persistence/writers.py:60](src/persistence/writers.py#L60). One batched Haiku call per run could populate it, or drop the column.
- [ ] Repo-root `README.md` pointing newcomers at SPEC.md / PROJECT_SUMMARY.md / PLAN.md.
- [ ] Document the Grafana dashboard: how to import, expected datasource UID, what each panel shows.

## Decisions log

- _2026-06-06_ — Chose Reddit `.json` over restoring PRAW for fix B. No auth needed, no new secrets, no new dependency. Risk: may be blocked from GH Actions IPs. PRAW remains the documented fallback.
- _2026-06-06_ — Standardized on three top-level docs at repo root: PROJECT_SUMMARY (structural), PLAN (rolling), HANDOFF (session bootstrap). SPEC.md remains the immutable design spec.
