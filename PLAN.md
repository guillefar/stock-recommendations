# Plan & Status

Living document. Update as work progresses. See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for the static overview and [SPEC.md](SPEC.md) for design rationale.

**Last updated:** 2026-06-12

## Current state

Pipeline is wired end-to-end. **Wave 1.5 is merged to `main`** (`881038d`, 2026-06-12) and **Wave 2 is half done on branch `feat/session-07-d3-wave-2`** (session 07, 2026-06-12; pushed, not merged): ticker news (top 5 yfinance headlines) and the next earnings date now ride into the per-ticker prompt as optional Spanish blocks (omitted when empty, so ETFs keep the original prompt), and the **D3 confidence-calibration panel** (panel-11: hit-rate by confidence band × action, NEUTRAL excluded from the denominator like panel-7) is on the digest dashboard. D3's query already shows real calibration signal on the 693 backfilled outcomes: WATCH hit-rate climbs **59% → 69% → 80%** across the <0.40 / 0.40–0.59 / 0.60–0.79 bands. Post-merge verification finding: the 2×/day cron schedule only reached `main` ~2026-06-12, so all historical scheduled runs were the single 14:00 UTC cron (63 recs/day, not 126 — **not a bug**); 2026-06-12 is the first day both crons (14:00/20:00 UTC) run the Wave 1.5 code, so cron-driven `price_checks` accumulation starts then. Wave 2 items remaining: constrain action set per phase; structured JSON output.

Previous state (session 06, Wave 1.5): grading semantics were decided and implemented (WATCH movement-graded, HOLD −10% loss band — see decisions log), and all 693 outcomes were **re-graded: 335 CORRECT / 155 INCORRECT / 203 NEUTRAL** (was 113/326/254). **S1 landed**: migration 003 `price_checks` is applied to the DB, `src.main` upserts one price row per ticker per run, and `evaluate_outcomes` falls back to `price_checks` when `price_snapshots` has no row in the horizon window — today already has **63/63 tickers covered**. D1 (same-day disagreements) + D2 (action mix over time) panels added to the digest dashboard (schema v2). Bonus fix: yfinance returned NaN closes mid-session for 21 European ETFs (so Claude saw `price: None` and those recs stored NULL entry prices); the collector now uses the last *valid* close.

**Known data caveats:**
- `price_snapshots` is still stale (last row 2026-05-22). `price_checks` accumulates from the cron starting 2026-06-12 (Wave 1.5 merge date); new recommendations become gradeable at 7d from ~2026-06-19. 252 matured candidates have no exit price in either table (the gap between 2026-05-22 snapshots and the first price_checks rows); most of the 2026-05-29 → 2026-06-05 era recs will stay ungradeable forever (no exit price exists for their window).
- Recs from the 21 European ETFs with the NaN-close bug have NULL entry prices (ungradeable) up to 2026-06-12; fixed going forward.
- The daily summary is a per-day upsert, so the 17:00 run overwrites the 11:00 one; the two session-05 runs minutes apart flipped BEARISH→MIXED (model variance on near-identical input). See the per-run-summary suggestion S8 in HANDOFF_05.

**Reddit is dark:** the PRAW collector is committed but has no credentials yet, so every recommendation currently runs with zero Reddit sentiment (technicals + macro only).

## In progress

- **Wave 2 (signal quality)** — items 1–2 (ticker news, earnings awareness) done on `feat/session-07-d3-wave-2`, awaiting merge; items 3–4 (action-set-per-phase constraint, structured JSON output) remain for a next session.

## Done (session 07 — 2026-06-12, D3 + Wave 2 first half)

On branch **`feat/session-07-d3-wave-2`** (off `main` @ `881038d`), in worktree `.claude/worktrees/session-07-d3-wave-2`:

- **Post-merge verification.** `price_checks`: 63 rows for 2026-06-12 only (session 06's local run; the cron hadn't fired since the merge at check time). `recommendation_outcomes`: 693, unchanged as expected. Anomaly chased and resolved: recs are 63/day not 126/day because the 2×/day schedule (`0 14` + `0 20` UTC, i.e. 11:00/17:00 ART) only reached `main` ~2026-06-12 — GH run history shows exactly one scheduled run/day, all ~13:30–16:30 UTC (the 14:00 cron plus GitHub's delay), every one successful. Nothing broken; the 20:00 cron starts firing 2026-06-12.
- **D3 — confidence-calibration panel** added to [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json) as panel-11 ("Hit Rate by Confidence Band (D3)", schema v2, GridLayoutItem at y=72): bands <0.40 / 0.40–0.59 / 0.60–0.79 / 0.80+ (a 4th band was added below the HANDOFF_06 draft because real confidences go down to 0.25), columns total/correct/incorrect/neutral + hit-rate-%, hit-rate defined as correct/decided (NEUTRAL excluded) to match panel-7, action color-mapped, hit-rate color-background (red <40 / yellow 40–60 / green ≥60). Query validated against the live DB before insertion; diff was purely additive (203 lines).
- **Wave 2 item 1 — ticker news in the prompt.** [src/main.py](src/main.py) fetches `fetch_ticker_news(symbol)[:5]` per ticker and passes it in `ticker_data["news"]`; `analyze_ticker` in [src/analysis/claude_client.py](src/analysis/claude_client.py) renders a "Noticias recientes del ticker:" block (titles only), omitted entirely when no titles.
- **Wave 2 item 2 — earnings awareness.** New `fetch_next_earnings` in [src/collectors/prices.py](src/collectors/prices.py) (yfinance `Ticker.calendar`, handles dict + DataFrame schemas, try/except → None; pure date-picking logic in `_pick_next_earnings`); prompt gets "Próximo reporte de earnings: YYYY-MM-DD — si es inminente, considera el riesgo del evento…" when known. ETFs have no calendar → yfinance logs a (harmless, cosmetic) internal 404 ERROR line and the block is omitted.
- **Tests:** new [tests/test_prices.py](tests/test_prices.py) covering `_pick_next_earnings` (5 tests: earliest-future pick, today counts, stale/empty → None, datetime+Timestamp normalization, garbage tolerated).
- **Validated:** pytest **9/9**; full `src.main --dry-run` **63 ok / 0 failed**, no writes; live smoke test (AAPL: 5 headlines + earnings 2026-07-30; XESC.DE: no calendar → None); prompt assembly verified with a stubbed API client — blocks present with data, absent without (`Noticias`/`earnings` strings absent from the no-data prompt).
- **Reddit still dark** — `.env` has none of the three `REDDIT_*` vars (checked this session); user task remains open.

## Done (session 06 — 2026-06-12, Wave 1.5)

On branch **`feat/session-06-wave-1-5`** (off `main` @ `604e229`), in worktree `.claude/worktrees/session-06-wave-1-5`:

- **Grading semantics implemented** (user decisions, see log): `grade()` in [src/evaluate_outcomes.py](src/evaluate_outcomes.py) — WATCH movement-graded (`WATCH_MOVE_THRESHOLD = 0.05`), HOLD loss band (`HOLD_LOSS_BAND = 0.10`), BUY/SELL/AVOID unchanged. [tests/test_outcomes.py](tests/test_outcomes.py) rewritten for the new rules (4 tests, all pass).
- **Backfill re-graded** (authorized): deleted all 693 `recommendation_outcomes` rows, re-ran the evaluator → 693 rows again. Verdicts went **113 C / 326 I / 254 N → 335 C / 155 I / 203 N** (WATCH 250 C / 81 I / 104 N; HOLD 84 C / 74 I / 99 N; AVOID 1 C) — exactly the distribution predicted when the user picked the options.
- **S1 landed.** [migrations/003_create_price_checks.sql](migrations/003_create_price_checks.sql) applied to the DB (UNIQUE on ticker_id + as_of_date). New `write_price_check` in [src/persistence/writers.py](src/persistence/writers.py) (upsert; respects dry-run; warns + skips on NULL price), called per ticker in [src/main.py](src/main.py) right after the technical fetch so the price lands even if the recommendation later fails. `_fetch_matured` in [src/evaluate_outcomes.py](src/evaluate_outcomes.py) now returns a second exit-price candidate from `price_checks` (calendar-day window, since it's a DATE column) and the loop falls back to it when `price_snapshots` has none.
- **Bonus fix — NaN closes.** 21 of 63 tickers (all European ETFs) had `technical.price = None` because yfinance emits today's row with NaN Close mid-session; [src/collectors/prices.py](src/collectors/prices.py) now drops NaN closes before taking the last. Validated by backfilling exactly those 21 tickers' price rows (21/21 ok).
- **D1+D2 panels** added to [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json) (panel-9 table, panel-10 stacked-bars timeseries; schema-v2 `elements`/`layout`; both queries validated against the live DB — D1 is legitimately empty until a day has two disagreeing runs).
- **Validated:** pytest 4/4; `src.main --dry-run` 63 ok / 0 failed, no writes; one real `src.main` (exit 0, recs dedup-skipped as expected, price_checks written); `evaluate_outcomes --dry-run` clean; `price_checks` ends the day at **63/63 tickers**.
- **Reddit still dark** — `.env` has none of the three `REDDIT_*` vars; user task remains open.

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

### Wave 1.5 — Outcome integrity & freshness (done session 06, awaiting merge)

- [x] **Decide grading semantics with the user, then implement** — done session 06: WATCH movement-graded, HOLD −10% band (decisions log); `grade()` + tests updated; backfill re-graded 335 C / 155 I / 203 N.
- [x] **S1 — in-repo price-snapshot fallback** — done session 06: migration 003 applied, per-run upserts in main, evaluator fallback. Unblocks grading of post-2026-05-22 recommendations ~7 days after merge.
- [x] **D1+D2 digest panels** — done session 06 (panel-9 / panel-10, schema v2, queries validated).
- [x] **Merge `feat/session-06-wave-1-5` to `main`** — done 2026-06-12 (`881038d`); cron `price_checks` accumulate from 2026-06-12.

### Wave 2 — Signal quality

- [x] **Wire `fetch_ticker_news` into the per-ticker prompt** — done session 07: top 5 headlines as an optional "Noticias recientes del ticker:" block.
- [x] **Earnings awareness** — done session 07: `fetch_next_earnings` (schema-tolerant, degrades to None) + "Próximo reporte de earnings:" prompt line.
- [ ] **Constrain action set per phase.** HOLDING → {HOLD, SELL}; WATCHLIST → {BUY, WATCH, AVOID}. Tighten the prompt wording AND post-validate: coerce out-of-set actions to the nearest valid one and log the coercion.
- [ ] **Structured JSON output instead of text parsing.** Replace `_parse_json` string-stripping with the API's structured/tool-use output so malformed JSON becomes impossible. **Read the `/claude-api` skill at implementation time** for the current recommended mechanism; also sanity-check whether the tiny system prompts even reach the cacheable minimum (likely not → drop or restructure `cache_control`).
- [x] **Validate via `--dry-run`** — done session 07 for items 1–2 (63 ok / 0 failed); repeat when items 3–4 change the prompts again.

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
- [x] **Confidence-calibration panel (D3, adopted session 05)** — done session 07: panel-11, 4 bands (<0.40 added — real confidences reach 0.25), hit-rate = correct/decided. Already shows monotone calibration for WATCH (59→69→80%).
- [ ] **S5 — weekly retrospective digest (adopted session 05).** On Friday's 17:00 run, one extra Claude call writes a week-in-review in Spanish (calls vs outcomes, action flips, sector exposure); persist it and add a digest panel. ~1 Haiku call/week.

### Fold-in cleanups (no scheduled wave — grab when touching the area)

- [x] One DB connection per run instead of `2 + 2N` opens ([src/main.py](src/main.py)) — done session 04 with Wave 1's main-loop edit.
- [ ] Refactor [src/db.py:20](src/db.py#L20) `get_active_tickers` to a UNION of two INNER JOINs.
- [ ] Macro→ticker matching ([src/main.py:102-106](src/main.py#L102-L106)): prefer signals where `direction[sector]` is non-NEUTRAL over "first sector match wins".
- [x] ~~UNIQUE-key idempotency on DATE(generated_at)~~ — superseded by the two-recs/day decision (see Wave 1).

## Decisions log

- _2026-06-12 (session 07)_ — **D3 definitions**: hit-rate = correct / decided (NEUTRAL excluded), matching panel-7, and a 4th `< 0.40` confidence band added (real confidences go down to 0.25; the HANDOFF_06 draft's `ELSE '0.4–0.59'` would have mislabeled 40 rows). News/earnings prompt blocks are **omitted entirely** when empty so data-less tickers (ETFs) keep the exact pre-Wave-2 prompt.
- _2026-06-12 (session 06)_ — **Grading semantics decided** (user choice with the 693-row backfill as evidence): **WATCH is movement-graded** — CORRECT if |forward_return| ≥ 5% ("worth watching" = it moved), INCORRECT if |forward_return| < 2% (the watch wasted attention), NEUTRAL in between; **HOLD gets a −10% band** — INCORRECT if forward_return < −10% (that holding deserved a SELL), CORRECT if |forward_return| ≤ 2%, NEUTRAL otherwise (upside never penalized). BUY/SELL/AVOID stay directional with the ±2% neutral band. All 693 backfilled outcomes deleted and re-graded under the new rules (authorized; fully re-derivable).
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
