# Handoff 01 — 2026-06-11

Session-specific handoff capturing the work done on 2026-06-10/11 and everything needed to continue. For the evergreen orientation guide see [HANDOFF.md](HANDOFF.md); for rolling status/TODOs see [PLAN.md](PLAN.md); for the structural map see [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); for original design see [SPEC.md](SPEC.md).

## Repo facts

- **Path:** `/home/guillo/Git/stock-recommendations` (note: `/home/guillo/Git/stock` is a *different* project — the sibling `stock-snapshots`, which owns the DB).
- **Virtualenv:** `.venv` (with a dot). Run modules as `python -m src.main` **from the repo root** with `.venv` activated, or `.venv/bin/python -m ...`.
- **Branch:** `feat/decisive-recommendations-and-digest`, commit `35560d9`, **not pushed** (no remote configured). `main` is the base.
- **DB access:** credentials in `.env` (gitignored). The same MySQL DB is owned by `stock-snapshots`; this project is **read-only** against `tickers`, `holdings`, `watchlist`, `transactions`, `price_snapshots`, and the view `v_ticker_status_multi`. It owns `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, and (new) `recommendation_outcomes`.
- To run DB scripts locally, load env explicitly when using a heredoc: `load_dotenv('/home/guillo/Git/stock-recommendations/.env')` (bare `load_dotenv()` fails under `python - <<EOF`).

## What this session changed (all in commit `35560d9`)

1. **Decisive-recommendation prompt fix** — [src/analysis/claude_client.py](src/analysis/claude_client.py). The old system prompt ("analista conservador … NUNCA consejos absolutos") plus the absence of any data→action rule produced **0 BUY / 0 SELL across 1197 stored recommendations** (739 WATCH / 455 HOLD / 3 AVOID). Rewrote `_RECOMMENDATION_SYSTEM` to allow decisive calls and added, in the user prompt, a **per-position decision rubric** (HOLDING → SELL/HOLD; WATCHLIST → BUY/WATCH/AVOID) and a **confidence-calibration guide** (0.8–1.0 strong … <0.4 noise). A local `--dry-run` then produced real SELLs (13 SELL / 1 AVOID across 63 tickers; still 0 BUY because that day's market read was BEARISH — expected, not a bug).

2. **Outcome tracking** — [migrations/002_create_recommendation_outcomes.sql](migrations/002_create_recommendation_outcomes.sql) (**already applied to the DB**) + [src/evaluate_outcomes.py](src/evaluate_outcomes.py) (`python -m src.evaluate_outcomes [--dry-run]`). For each matured recommendation it takes the entry price from the recommendation's stored `technical.price`, finds the first `price_snapshots` row in `[generated_at + horizon, +horizon+14d)` for horizons 7 and 30 days, computes forward return, and assigns CORRECT/INCORRECT/NEUTRAL via `grade()`. Unit-tested in [tests/test_outcomes.py](tests/test_outcomes.py) (run with `pytest`, which is **not** in requirements yet). **Currently grades 0 rows** because `price_snapshots` stops at 2026-05-22 (sibling collector stale) while the earliest recommendation is 2026-05-17 — no ticker has a price 7 days post-recommendation.

3. **Reddit → PRAW** — [src/collectors/reddit.py](src/collectors/reddit.py). The unauthenticated `.json` endpoint is **confirmed 403** from both CI and a residential IP. Now uses authenticated read-only PRAW; added `reddit_client_id/secret/user_agent` to [src/config.py](src/config.py), `praw>=7.7.1` to requirements, the three vars to [.env.example](.env.example), and the secrets to [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml). **Inert until credentials exist** — degrades gracefully (logs warning, returns `[]`).

4. **New daily-digest dashboard** — [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json). **Grafana schema-v2** (`elements`/`layout`, version `13.1.0-…`) to match the user's Grafana 13.1.x — a classic-schema (`panels[]`/`schemaVersion`) version **failed import validation**, that was the root cause of the user's earlier error. 8 panels: daily summary (full text), that day's recommendations, macro signals, top Reddit posts, **Action History by Ticker graph** (action encoded −2..+2), all-history action table, outcomes table, hit-rate-by-action. Date navigation is via the **time-range picker** (panels query `MAX(date) WHERE $__timeFilter(...)`), because the v2 template-variable dropdown schema was unreliable to author by hand. Datasource name in the JSON: `cfadv004ogglcf`. All 8 queries validated against the live DB.

5. **Restored** [grafana/recommendations_dashboard.json](grafana/recommendations_dashboard.json) — the working-tree copy had been truncated to invalid JSON; reset to the committed valid version. It's also schema-v2 and still has the per-ticker confidence graph.

## How to validate dashboard SQL fast

Substitute `$__timeFilter(col)` → `col >= '2025-01-01'`, replace `$summary_date`/picker with a real date, and run each `rawSql` through PyMySQL. (Used this all session; every panel returns rows except outcomes/hit-rate which are legitimately empty until `price_snapshots` advances.)

## Open questions / nuances surfaced

- **WATCH on a holding** = the model being non-committal on something you own; functionally a soft HOLD. Under the new rubric a HOLDING should resolve to HOLD or SELL only. Tracked as the "constrain action set per phase" TODO.
- `phase` (own it?) and `action` (advice) are intentionally both shown; the divergent rows (HOLDING+SELL, WATCHLIST+BUY) are the point.

## Immediate next steps (see PLAN.md "TODO" for the full list)

1. Get Reddit credentials into `.env` + GitHub secrets; re-run `--dry-run` and confirm `Fetched N posts from /r/stocks`.
2. Do a **real** `python -m src.main` run so the DB gets decisive rows and the dashboard fills.
3. Decide whether to push the branch / open a PR.
4. (When `price_snapshots` is fresh) run `python -m src.evaluate_outcomes` and confirm the outcomes/hit-rate panels populate.

## Invariants (don't break)

- Never write to `stock-snapshots` tables/views. Read-only.
- Keep `--dry-run` working (no DB writes).
- All Claude outputs are strict JSON parsed by `claude_client._parse_json`.
- Spanish is used in the Claude system/user prompts; English elsewhere.
- The user prefers concrete, scoped recommendations over option dumps — recommend, then offer to implement.
