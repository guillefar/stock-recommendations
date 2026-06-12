# Plan & Status

Living document. Update as work progresses. See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for the static overview and [SPEC.md](SPEC.md) for design rationale.

**Last updated:** 2026-06-12

## Current state

Pipeline is wired end-to-end, **Wave 1 is merged to `main`** (`ca4937a`, pushed 2026-06-12), and the system has had its **first real (non-dry-run) execution** (session 05, 2026-06-12): 63/63 tickers ok, first decisive calls stored (34 WATCH / 27 HOLD / **2 SELL**), daily summary written, and `evaluate_outcomes` **backfilled 693 outcome rows at the 7d horizon** (of 945 matured candidates; 0 at 30d). The 4h per-run dedup was verified with a second same-day run (63/63 "Skipping duplicate", today-count unchanged). Sessions now run in their **own git worktree** (decision, see log).

**Known data caveats:**
- The sibling `price_snapshots` table is stale (last row 2026-05-22), so **new** recommendations can't be graded until **S1 (in-repo `price_checks` fallback, adopted)** lands. The 693 backfilled outcomes all come from the old always-HOLD/WATCH prompt era.
- **Grading semantics skew the backfill**: verdicts are 326 INCORRECT / 113 CORRECT / 254 NEUTRAL, dominated by WATCH-graded-as-bullish in a falling market. The semantics decision is pulled forward to session 06 (decision, see log).
- The daily summary is a per-day upsert, so the 17:00 run overwrites the 11:00 one; the two session-05 runs minutes apart flipped BEARISH→MIXED (model variance on near-identical input). See the per-run-summary suggestion in HANDOFF_05.

**Reddit is dark:** the PRAW collector is committed but has no credentials yet, so every recommendation currently runs with zero Reddit sentiment (technicals + macro only).

## In progress

- _(none)_

## Done (session 05 — 2026-06-12, first real execution + roadmap decisions)

On branch **`chore/session-05-first-real-run`** (off `main` @ `ca4937a`), in its own worktree:

- **Wave 1 merged to `main`** — `fix/wave-1-correctness` fast-forwarded to `ca4937a` and pushed (user completed the push directly).
- **First real (non-dry-run) `src.main` run.** 63 tickers ok / 0 failed, exit 0. Stored actions: 34 WATCH / 27 HOLD / **2 SELL** (first non-WATCH/HOLD rows ever). Daily summary upserted (BEARISH). Only warning: Reddit credentials missing (expected).
- **First real `evaluate_outcomes` run.** **693 outcomes written at 7d** (of 945 matured candidates), 0 at 30d — exactly the predicted backfill. Verdicts: 326 INCORRECT / 113 CORRECT / 254 NEUTRAL (skewed by WATCH-graded-as-bullish; semantics decision pulled to session 06).
- **DB sanity checks passed** (HANDOFF_04 queries): 63 recommendation rows today, 693 outcome rows, today's summary row present.
- **4h dedup verified.** A second `src.main` run logged `Skipping duplicate recommendation` for all 63 tickers; today-count unchanged at 63. Side observation: the run re-upserted the daily summary, flipping BEARISH→MIXED minutes apart (model variance).
- **Roadmap decisions** (S1–S6 + dashboard ideas) recorded in the decisions log; roadmap below restructured accordingly.
- **Reddit still dark** — `.env` has none of the three `REDDIT_*` vars; user task remains open.
- Wave 2 item 1 (ticker news) deliberately **not** started — user chose to close the session after the roadmap discussion.

## Done (session 04 — 2026-06-12, Wave 1)

On branch **`fix/wave-1-correctness`** (off `main` @ `241caa5`):

- **Per-run dedup (2×/day no-op bug fixed).** [src/persistence/writers.py](src/persistence/writers.py): `write_recommendation` now skips only if the ticker has a row within the last `DEDUP_WINDOW_HOURS = 4` hours (was: same calendar day). The 17:00 ART run now writes its own rows; same-slot workflow retries are still deduped.
- **Parse failures are never persisted.** `analyze_ticker` in [src/analysis/claude_client.py](src/analysis/claude_client.py) returns `None` on unparseable JSON instead of the old `HOLD/0.5/"Error al parsear respuesta"` fallback; main logs an error, counts the ticker as failed, and writes nothing.
- **Per-ticker error isolation.** The per-ticker body in [src/main.py](src/main.py) is wrapped in try/except (log + continue). The run-complete line reports `tickers_ok=… tickers_failed=… (failed: […])`; the process exits non-zero only when *every* ticker failed. Missing technical data also counts as a failure now.
- **`evaluate_outcomes` scheduled.** Second workflow step in [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml), with `if: ${{ !cancelled() }}` so grading runs even if the main step fails (it's independent). Needs `ANTHROPIC_API_KEY` in env only because `load_config()` requires it.
- **Fold-in: single DB connection per run.** main now opens one connection for the whole run (was 2+2N) with `conn.ping(reconnect=True)` before each write phase to survive idle-out during Claude/yfinance calls.
- **Validated:** `python -m src.main --dry-run` full pass (63 tickers ok / 0 failed, no writes); `python -m src.evaluate_outcomes --dry-run` (693 graded at 7d — see Current state); `tests/test_outcomes.py` 3/3 pass (pytest installed into the local venv only; adding it to requirements stays Wave 3).

## Done (session 03 — 2026-06-12)

- **Deep repo review + agreed roadmap.** Findings folded into the wave plan above; headline new issues found: the 2×/day-vs-daily-dedup no-op bug, parse-failure fallbacks persisted as real recommendations, no error isolation per ticker, `evaluate_outcomes` never scheduled, `cache_control` likely a no-op on tiny system prompts.
- **Merged `chore/cron-2x-daily-and-datetime-cleanup` → `main`** (fast-forward to `2197dc1`) and pushed.
- **Rewrote the TODO section as the wave roadmap** (this file) after user confirmation of scope and the two-recs/day + no-notifications decisions. Session handoff: [HANDOFF_03.md](HANDOFF_03.md).

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

## Roadmap — waves (agreed 2026-06-12)

Scope confirmed with the user on 2026-06-12: **Waves 1–4 are committed work**; the old low-priority cleanups are **not** a scheduled wave — fold them in opportunistically when touching the same code (see "Fold-in cleanups"). Each wave ≈ one session. Decisions baked in: **two recommendations/day** (per-run dedup, not per-day), **no push notifications for now** (flips surface in the summary + dashboard instead).

### Wave 1 — Correctness & unblocking

- [x] **Per-run recommendations (fixes the 2×/day no-op bug)** — done session 04: 4h dedup window (`DEDUP_WINDOW_HOURS`) in [src/persistence/writers.py](src/persistence/writers.py).
- [x] **Never persist parse-failure fallbacks** — done session 04: `analyze_ticker` returns `None`, main skips + counts the failure.
- [x] **Per-ticker error isolation** — done session 04: try/except per ticker in [src/main.py](src/main.py), ok/failed counts in the final log line, exit non-zero only if all failed.
- [x] **Schedule `evaluate_outcomes`** — done session 04: second workflow step. Note it will backfill ~693 7d outcomes from old recs on first real run (snapshots through 2026-05-22 matured them).
- [ ] **USER: Provide Reddit credentials.** Create a "script" app at https://www.reddit.com/prefs/apps; put `REDDIT_CLIENT_ID/SECRET/USER_AGENT` in local `.env` AND GitHub Actions secrets. Until then every run has zero Reddit sentiment.
- [x] **First real (non-dry-run) execution** — done session 05 (local): 63/63 ok, 2 SELL rows stored, 693 outcomes backfilled, dedup verified with a second run.
- [x] **Merge `chore/cron-2x-daily-and-datetime-cleanup` to `main`** — done 2026-06-12 (fast-forward to `2197dc1`, pushed).

### Wave 1.5 — Outcome integrity & freshness (adopted session 05; next session)

- [ ] **Decide grading semantics with the user, then implement.** Today WATCH grades as bullish and HOLD can never be INCORRECT — the 693-row backfill came out 326 INCORRECT / 113 CORRECT / 254 NEUTRAL largely by semantics. Options to put to the user: exclude WATCH from hit-rate or grade it on |move|; make HOLD INCORRECT beyond a band (e.g. ±10%). Record in decisions log, update `grade()` in [src/evaluate_outcomes.py](src/evaluate_outcomes.py) + [tests/test_outcomes.py](tests/test_outcomes.py), then **re-grade**: delete + regenerate the backfilled rows (they are fully re-derivable).
- [ ] **S1 — in-repo price-snapshot fallback.** Migration 003: `price_checks(ticker_id, as_of_date, price)` owned by this repo; write one row per ticker per run (price already fetched in `technical`); `evaluate_outcomes` falls back to it when `price_snapshots` has no row in the horizon window. Unblocks grading of all post-2026-05-22 recommendations.
- [ ] **D1+D2 digest panels** (if time): per-day morning-vs-afternoon disagreement table + daily action-mix stacked bars. Schema-v2 `elements`/`layout` format only; validate queries against the live DB.

### Wave 2 — Signal quality

- [ ] **Wire `fetch_ticker_news` into the per-ticker prompt.** [src/collectors/prices.py:43](src/collectors/prices.py#L43) exists but is never called. Pass top ~5 headlines into `analyze_ticker`. Highest-quality single improvement available.
- [ ] **Earnings awareness.** Fetch the next earnings date via yfinance and add "Próximo earnings: ..." to the ticker prompt — imminent earnings should temper/inform the call.
- [ ] **Constrain action set per phase.** HOLDING → {HOLD, SELL}; WATCHLIST → {BUY, WATCH, AVOID}. Tighten the prompt wording AND post-validate: coerce out-of-set actions to the nearest valid one and log the coercion.
- [ ] **Structured JSON output instead of text parsing.** Replace `_parse_json` string-stripping with the API's structured/tool-use output so malformed JSON becomes impossible. **Read the `/claude-api` skill at implementation time** for the current recommended mechanism; also sanity-check whether the tiny system prompts even reach the cacheable minimum (likely not → drop or restructure `cache_control`).
- [ ] **Validate via `--dry-run`** before merging (prompts changed).

### Wave 3 — Observability & hygiene

- [ ] **Cost telemetry.** Accumulate `response.usage` (input/output/cache-read tokens) across the `2+N` calls; log totals + estimated USD at run end. Use it to confirm the caching decision from Wave 2.
- [ ] **Tests + CI.** Add `pytest` to requirements (or a dev-requirements file) and a test step/workflow. Cover: `extract_ticker_mentions` stopwords (`IT`, `GO`, `BE`), `_compute_rsi`/`_pct_change` fixtures, action-per-phase coercion (Wave 2), per-run dedup window (Wave 1). [tests/test_outcomes.py](tests/test_outcomes.py) already covers `grade()`.
- [ ] **Pin `requirements.txt`.** yfinance breaks compat often — there's already a schema workaround at [src/collectors/prices.py:50](src/collectors/prices.py#L50).
- [ ] **README.md** at repo root pointing at SPEC / PROJECT_SUMMARY / PLAN / HANDOFFs, plus Grafana import notes (datasource uid, time-range-picker navigation).
- [ ] **Decide outcome-grading semantics.** Today `WATCH` is graded as bullish and `HOLD` can never be INCORRECT — both inflate hit-rates. Decide (e.g., exclude WATCH from hit-rate, or grade it on |move|; make HOLD INCORRECT beyond some band) and record in the decisions log.

### Wave 4 — Product features (no notifications; some items gated)

- [ ] **Action-flip detection.** When a ticker's new action differs from its previous one (HOLD→SELL, WATCH→BUY…), include the flips in the daily-summary prompt input and add a "recent flips" panel/table to the digest dashboard. (This is the no-notifications substitute.)
- [ ] **Persist trending-unknown tickers.** Today `find_trending_unknown` results only hit logs/summary text. New table (migration 003) so "should I watchlist this?" signals survive and can trend over time.
- [ ] **Batched Reddit-mention sentiment.** One extra Haiku call per run to classify that run's mentions; fills the always-NULL `reddit_mentions.sentiment` ([src/persistence/writers.py:65](src/persistence/writers.py#L65)). **Gated on Reddit creds existing.**
- [ ] **Confidence-calibration panel (D3, adopted session 05).** Hit-rate bucketed by confidence band (0.4–0.59 / 0.6–0.79 / 0.8+) on the digest dashboard. ~~Gated on outcomes data~~ **ungated** by the 693-row backfill; **sequence after the Wave 1.5 grading-semantics fix** or the numbers mislead.
- [ ] **S5 — weekly retrospective digest (adopted session 05).** On Friday's 17:00 run, one extra Claude call writes a week-in-review in Spanish (calls vs outcomes, action flips, sector exposure); persist it and add a digest panel. ~1 Haiku call/week.

### Fold-in cleanups (no scheduled wave — grab when touching the area)

- [x] One DB connection per run instead of `2 + 2N` opens ([src/main.py](src/main.py)) — done session 04 with Wave 1's main-loop edit.
- [ ] Refactor [src/db.py:20](src/db.py#L20) `get_active_tickers` to a UNION of two INNER JOINs.
- [ ] Macro→ticker matching ([src/main.py:102-106](src/main.py#L102-L106)): prefer signals where `direction[sector]` is non-NEUTRAL over "first sector match wins".
- [x] ~~UNIQUE-key idempotency on DATE(generated_at)~~ — superseded by the two-recs/day decision (see Wave 1).

## Decisions log

- _2026-06-12 (session 05)_ — **Roadmap picks from S1–S6 + dashboard ideas**: adopted **S1** (in-repo `price_checks` fallback), **S5** (weekly retrospective), **D1+D2** (morning-vs-afternoon divergence + action-mix-over-time digest panels), **D3** (confidence-calibration panel, sequenced after the grading-semantics fix). **S6 (event-driven runs) deferred**; S2/S3/S4 not adopted for now (revisit once outcomes are fresh).
- _2026-06-12 (session 05)_ — **Grading-semantics decision pulled forward** from Wave 3 to the next session (Wave 1.5): the 693-row backfill is visibly skewed (326 INCORRECT) by WATCH-graded-as-bullish, and outcome-based panels shouldn't be built on top of it.
- _2026-06-12 (session 05)_ — **Each session works in its own git worktree** (not just a branch), per user instruction. Worktrees live under `.claude/worktrees/`; symlink `.env` and `.venv` from the main checkout into the worktree.
- _2026-06-12_ — **Two recommendations per day**: with the 2×/day cron, each run writes its own row per ticker (per-run dedup window, not per-calendar-day). Morning/afternoon divergence becomes visible data.
- _2026-06-12_ — **No push notifications for now** (Telegram/email declined). Action flips surface via the daily summary and a dashboard panel instead (Wave 4).
- _2026-06-12_ — **Roadmap scope**: Waves 1–4 committed; old low-priority cleanups are fold-in work, not a scheduled wave.
- _2026-06-11_ — Built the digest in Grafana **schema-v2** (`elements`/`layout`) after a classic-schema version failed import on the user's Grafana 13.1.x. Date navigation uses the **time-range picker** (not a template-variable dropdown) because the v2 variable schema was unreliable to hand-author.
- _2026-06-11_ — Reverted the 2026-06-06 `.json` decision: confirmed 403 from a residential IP too, so switched the Reddit collector to **authenticated PRAW**. Needs `REDDIT_CLIENT_ID`/`SECRET`/`USER_AGENT`.
- _2026-06-06_ — Chose Reddit `.json` over restoring PRAW for fix B. No auth needed, no new secrets, no new dependency. Risk: may be blocked from GH Actions IPs. PRAW remains the documented fallback. _(superseded 2026-06-11)_
- _2026-06-06_ — Standardized on three top-level docs at repo root: PROJECT_SUMMARY (structural), PLAN (rolling), HANDOFF (session bootstrap). SPEC.md remains the immutable design spec.
