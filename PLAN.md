# Plan & Status

Living document. Update as work progresses. See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for the static overview and [SPEC.md](SPEC.md) for design rationale.

**Last updated:** 2026-06-11

## Current state

Pipeline is wired end-to-end and all modules exist. As of 2026-06-11 a feature branch **`feat/decisive-recommendations-and-digest`** (commit `35560d9`, **not yet pushed/merged**) carries: the decisive-recommendation prompt fix, outcome tracking, the PRAW Reddit swap, and the new daily-digest dashboard. The prompt fix was validated via a local `--dry-run` (produced real SELLs). The pipeline has **not** yet had a real (non-dry-run) execution with the new prompt, so the DB still holds only old all-HOLD/WATCH recommendations.

**Known data caveat:** the sibling `price_snapshots` table is stale — last row is 2026-05-22, while recommendations run through today. Outcome grading therefore finds zero matured candidates until the `stock-snapshots` collector resumes. Not fixable from this repo (read-only).

**Reddit is dark:** the PRAW collector is committed but has no credentials yet, so every recommendation currently runs with zero Reddit sentiment (technicals + macro only).

## In progress

- _(none)_

## Done (session 02 — 2026-06-11)

On branch **`chore/cron-2x-daily-and-datetime-cleanup`** (off `main` @ `370810e`):

- **`datetime.utcnow()` deprecation cleared.** Added a `_utcnow()` helper in [src/persistence/writers.py](src/persistence/writers.py) and swapped all 4 call sites; verified no `DeprecationWarning` under Python 3.14. `reddit.py` was already migrated (stale TODO).
- **Workflow now runs 2×/day.** [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml) has two cron lines (`0 11` and `0 17`, Mon–Fri) with accurate UTC comments, matching SPEC. Updated the secrets list in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) to include the three `REDDIT_*` vars while there.

## Done (this session — 2026-06-10 / 06-11)

- **Committed everything** to branch `feat/decisive-recommendations-and-digest` (`35560d9`); `.env` and `.claude/` excluded. Not pushed — no known remote.
- **Added "Action History by Ticker" graph** to the digest (panel-8): action encoded SELL −2 / AVOID −1 / HOLD 0 / WATCH +1 / BUY +2 with value mappings, mirroring the confidence graph that lives in the other dashboard. Digest is now 8 panels, all queries validated against the live DB.
- **Kept `phase` and `action` as separate dashboard columns** (decision): they only looked redundant under the old prompt (HOLDING↔HOLD, WATCHLIST↔WATCH) and diverge under the new one (e.g. HOLDING+SELL). Open nuance: a HOLDING that comes back `WATCH` is the model being non-committal — under the new rubric holdings should resolve to HOLD/SELL. See TODO "constrain action set per phase".

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
- [ ] **Do a real (non-dry-run) execution with the new prompt** so the DB gets decisive BUY/SELL rows and the dashboard/outcomes have fresh data to show. (Dry-run already validated; `--dry-run` writes nothing.)
- [ ] **Push the branch / open a PR** if the user wants it on a remote (none currently configured).
- [ ] **Constrain the action set per phase (prompt adherence).** Holdings occasionally come back `WATCH`, which under the rubric should be HOLD/SELL only; watchlist names should be BUY/WATCH/AVOID only. Either tighten the prompt wording or post-process `action` against `phase`. Low-risk, improves interpretability.
- [x] **Fix workflow schedule** — done 2026-06-11. Two cron lines `0 14 * * 1-5` and `0 20 * * 1-5` = **11:00 & 17:00 ART (UTC-3)**, Mon–Fri, matching the SPEC 2×/day. (User confirmed cron times are always specified in local Argentina time; GitHub Actions cron is UTC so the offset is baked in.)

### Medium priority

- [ ] **Wire `fetch_ticker_news` into the per-ticker prompt.** [src/collectors/prices.py:43](src/collectors/prices.py#L43) is defined but never called. Including ticker-specific news in `analyze_ticker` is the highest-quality improvement available.
- [x] **Replace `datetime.utcnow()`** — done 2026-06-11. Added a `_utcnow()` helper in [src/persistence/writers.py](src/persistence/writers.py) (`datetime.now(timezone.utc).replace(tzinfo=None)`) and swapped all 4 call sites; verified no `DeprecationWarning` under Python 3.14. `reddit.py` was already migrated (stale TODO entry).
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

- _2026-06-11_ — Built the digest in Grafana **schema-v2** (`elements`/`layout`) after a classic-schema version failed import on the user's Grafana 13.1.x. Date navigation uses the **time-range picker** (not a template-variable dropdown) because the v2 variable schema was unreliable to hand-author.
- _2026-06-11_ — Reverted the 2026-06-06 `.json` decision: confirmed 403 from a residential IP too, so switched the Reddit collector to **authenticated PRAW**. Needs `REDDIT_CLIENT_ID`/`SECRET`/`USER_AGENT`.
- _2026-06-06_ — Chose Reddit `.json` over restoring PRAW for fix B. No auth needed, no new secrets, no new dependency. Risk: may be blocked from GH Actions IPs. PRAW remains the documented fallback. _(superseded 2026-06-11)_
- _2026-06-06_ — Standardized on three top-level docs at repo root: PROJECT_SUMMARY (structural), PLAN (rolling), HANDOFF (session bootstrap). SPEC.md remains the immutable design spec.
