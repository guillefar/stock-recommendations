# Plan & Status

Living document. Update as work progresses. See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for the static overview and [SPEC.md](SPEC.md) for design rationale.

**Last updated:** 2026-06-06

## Current state

All 14 modules from the SPEC build plan exist and the pipeline is wired end-to-end. Migration, GitHub Actions workflow, and a Grafana dashboard are committed. The project has been idle since 2026-05-18 ("Adding dashboard"). Has not been validated against a real run since the Reddit collector was switched from PRAW to RSS.

## In progress

- _(none)_

## Done (this session — 2026-06-06)

- **Fix B — restored real Reddit post scores.** Switched [src/collectors/reddit.py](src/collectors/reddit.py) from the RSS endpoint (which doesn't expose `score` or `upvote_ratio`) to Reddit's public `.json` endpoint. Now applies the SPEC filter (`score >= 50` and `upvote_ratio >= 0.7`). This re-enables `find_trending_unknown`, fixes `sentiment.avg_score`, and makes the daily-summary `top_posts` sort meaningful.
- Created [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md), this file ([PLAN.md](PLAN.md)), and [HANDOFF.md](HANDOFF.md) for cross-session context.

## TODO — prioritized

### High priority

- [ ] **Verify the Reddit fix in CI.** Reddit has aggressively blocked unauthenticated requests from datacenter IPs in 2024–2025. The `.json` endpoint may 403 on GitHub Actions while the RSS feed worked. Trigger `workflow_dispatch` once and check the log line `Fetched N posts from /r/stocks`. Fallback if blocked: restore PRAW with `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` secrets.
- [ ] **Run end-to-end against production DB with `--dry-run`** to surface any other regressions; capture one ticker's full Claude prompt and response for eyeball review.
- [ ] **Fix workflow schedule.** [.github/workflows/run_recommendations.yml:5](.github/workflows/run_recommendations.yml#L5) — cron is `0 11 * * 1-5` (once/day) but SPEC says 2x/day; comment claims "13:00 UTC" but cron is 11:00 UTC. Either match the comment or commit to the 2x/day schedule.

### Medium priority

- [ ] **Wire `fetch_ticker_news` into the per-ticker prompt.** [src/collectors/prices.py:43](src/collectors/prices.py#L43) is defined but never called. Including ticker-specific news in `analyze_ticker` is the highest-quality improvement available.
- [ ] **Replace `datetime.utcnow()`** throughout [src/persistence/writers.py](src/persistence/writers.py) and [src/collectors/reddit.py](src/collectors/reddit.py). Deprecated on 3.12+; user runs 3.14 locally. Switch to `datetime.now(timezone.utc).replace(tzinfo=None)`.
- [ ] **Add minimal tests** ([tests/](tests/) is empty):
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
