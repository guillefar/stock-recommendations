# Project Summary — stock-recommendations

A short, structural overview of the codebase. For design rationale and decisions, see [SPEC.md](SPEC.md). For current work-in-progress and TODOs, see [PLAN.md](PLAN.md).

## What it does

Automated pipeline that generates BUY/SELL/HOLD/WATCH/AVOID recommendations (Mon/Wed/Fri) for the user's stock portfolio by combining:

- **Technicals** — yfinance prices + pandas-computed indicators (RSI, SMA20/50/200, % changes, 52w position, volume ratio).
- **Reddit sentiment** — `/r/stocks` hot posts; mentions of known tickers and detection of trending unknown tickers.
- **Macro news** — RSS feeds (Reuters, MarketWatch, Yahoo Finance) → Claude identifies themes + affected sectors.
- **LLM analysis** — Claude Haiku 4.5 generates: macro signals, per-ticker recommendation, daily market summary.

Runs on **GitHub Actions cron** (no server). Reads from the existing `stock-snapshots` MySQL DB and writes to eight tables it owns.

## Relationship to `stock-snapshots`

A separate sibling project owns `tickers`, `holdings`, `watchlist`, `transactions`, `price_snapshots`. This project **only reads** those tables. It owns:

- `recommendations` — one row per ticker per run. Since session 22 each row also stores the `fundamentals` JSON snapshot Claude saw (equities only; NULL otherwise and for all pre-s22 rows).
- `daily_market_summary` — one row per calendar date.
- `reddit_mentions` — audit trail of posts referencing tickers.
- `macro_signals` — themes detected from headlines.
- `recommendation_outcomes` — one row per recommendation per horizon (7d/30d/90d/180d/365d; grading bands widen with the horizon, 30d is the headline metric); grades the forward return. Populated separately by `python -m src.evaluate_outcomes`, not by the main pipeline.
- `price_checks` — one observed price per ticker per day, written by the main run; the evaluator's fallback exit-price source while `price_snapshots` is stale.
- `trending_tickers` — one row per trending-unknown symbol (upserted per run; `times_seen` counts trending runs). Empty until Reddit credentials exist.
- `weekly_retrospectives` — one row per week (keyed on its Monday): Claude's week-in-review for a long-term investor + the `stats` JSON it was built from. Written on Friday runs (S5).
- `prediction_patterns` — one row per pattern-mining run (Fridays; append-only, newest row = current set): Claude's evolving patterns on when the system's calls are right or wrong, plus the narrative and the `stats` aggregates it was fed (session 22).
- `run_metrics` — one row per completed run (append-only; dry-runs never write): the run's Claude usage totals (batched tokens separate — the Batches API bills 50%), estimated cost in USD, and ok/failed ticker counts (session 24). Makes the cost trend queryable instead of log-only.

Full DDL: [migrations/](migrations/) (001 recommendation tables, 002 outcomes, 003 price_checks, 004 trending_tickers, 005 weekly_retrospectives, 006 fundamentals column, 007 prediction_patterns, 008 run_metrics).

## Module map

```
src/
├── main.py                 # orchestrator (--dry-run supported)
├── evaluate_outcomes.py    # standalone job: grades past recommendations vs realized prices
├── config.py               # env-var loader → Config dataclass
├── db.py                   # PyMySQL connection + ticker/action/week-outcome/flip/pattern-feature queries
├── collectors/
│   ├── prices.py           # yfinance history + RSI/SMA/etc.; fetch_ticker_news + fetch_next_earnings + fetch_etf_info + fetch_fundamentals (all feed the per-ticker prompt)
│   ├── reddit.py           # /r/stocks scraping (PRAW) + ticker extraction + trending detection
│   └── news.py             # RSS feed aggregation + dedup
├── analysis/
│   ├── claude_client.py    # Anthropic SDK wrapper; macro + summary calls, per-ticker Message Batches call; structured output; usage/cost telemetry
│   ├── actions.py          # per-phase allowed action sets + coerce_action backstop
│   ├── macro.py            # thin wrapper around claude_client.analyze_macro
│   ├── recommendation.py   # thin wrappers: analyze_ticker (ad-hoc) + analyze_tickers_batch (the run)
│   ├── patterns.py         # session 22: buckets every graded outcome into hit-rate aggregates for the pattern-mining call; session 25: select_patterns_for_prompt gates the stored set for prompt injection
│   ├── retrospective.py    # S5: aggregates the week's outcomes/flips/exposure for the retro call
│   └── summary.py          # thin wrapper around claude_client.generate_daily_summary
└── persistence/
    └── writers.py          # writes to all 9 owned tables; 4h dedup window for recommendations
```

## Execution flow ([main.py](src/main.py))

1. Load active tickers from DB (`holdings.quantity > 0` ∪ `watchlist.active = 1`) and known symbol set.
2. Fetch Reddit hot posts from `/r/stocks`.
3. Fetch macro headlines from RSS feeds.
4. **Claude call #1** — macro signal extraction → `macro_signals`. Wrapped in try/except: on failure the run continues with zero macro signals (a Claude outage must not stop price collection).
5. Extract per-ticker Reddit mentions; match by `$TICKER` and uppercase-word patterns against known symbols.
6. **Per-ticker, in three phases:**
   - **6a — collect:** technicals from yfinance (+ upsert today's price into `price_checks` before any Claude involvement), Reddit sentiment summary, news headlines (top 3), next earnings date, the ETF profile for tickers whose `quote_type` is ETF (family, expense ratio, top-5 holdings, sector mix via yfinance `funds_data` — stocks skip the fetch entirely), the fundamentals snapshot for tickers whose `quote_type` is EQUITY (trailing/forward P/E, dividend yield, margins, revenue/earnings growth, market cap via yfinance `Ticker.info` — ETFs/index/untyped skip it), and the ticker's standing call (`prev_action` + `prev_held_days`, from `get_latest_actions` — read before any of this run's rows land). Failures are isolated per ticker.
   - **6b — one Message Batches call** with all N per-ticker requests (50% token discount; polled up to 45 min, then canceled). Since session 16 each prompt shows "Recomendación vigente: X (mantenida N días)" and requires naming material new information to reverse it (flip-stability). Since session 18 ETF prompts carry a "Perfil del ETF" block (composition + costs) with an instruction to judge the fund by its exposure, not as a single stock. Since session 25 every prompt can carry a "Patrones históricos del propio sistema" block — the newest mined pattern set gated by `select_patterns_for_prompt` (status CONFIRMED/REVISED, confidence ≥ 0.7, top 3 by confidence; read once per run before 6a, fail-soft) and framed as weighable historical biases, never absolute rules. The block is empty until the Friday miner first confirms a pattern, so prompts stay byte-identical until then.
   - **6c — persist:** each parsed recommendation → `recommendations` (+ `reddit_mentions` for matched posts), linked to the most relevant macro signal for its sector (a POSITIVE/NEGATIVE direction beats a NEUTRAL mention) and carrying the ticker's `fundamentals` snapshot when one was fetched (session 22). Unparseable/errored entries count as failures; nothing is persisted for them. Action flips vs each ticker's previous stored recommendation are collected here (S17).
7. Write Reddit mentions for posts with no matched ticker (NULL-ticker rows are deduped by a pre-SELECT, since the UNIQUE key can't compare NULLs).
8. Detect trending unknown tickers (filter: score > 100, mentions > 3) and upsert them into `trending_tickers`.
9. **Claude call #2** — daily summary → `daily_market_summary`; the prompt includes the run's action flips ("Cambios de recomendación vs la corrida anterior") so the summary calls them out, and carries only the first sentence of each recommendation's reasoning (the full text is stored per rec; 63 full reasonings dominated this call's input tokens). On failure the summary returns `None` and nothing is written (never an error placeholder).
10. **Fridays only (or `--force-retro`): Claude call #3** — weekly retrospective → `weekly_retrospectives` (S5): reviews the calls whose 30d horizon matured that week, the week's flips, and sector exposure. Same failure rule: `None` is never persisted, and a retro failure can't kill the run.
11. **Fridays only (or `--force-patterns`): Claude call #4** — pattern mining → `prediction_patterns` (session 22): every graded 30d outcome is bucketed in Python (action, confidence band, RSI band, price-vs-SMA50, 52w position, volume, ETF-vs-stock, sector, P/E band, dividend status + action×RSI and action×type crosses) and fed to Claude together with its own previous pattern set; it returns the refined set (NEW/CONFIRMED/REVISED/RETIRED with evidence + confidence) and a Spanish narrative. Append-only rows; same failure rule as the retro. Since session 25 the loop closes: the CONFIRMED/REVISED patterns it produces feed back into the next run's per-ticker prompts (step 6b).
12. **Run metrics** → `run_metrics` (session 24): the run's accumulated Claude usage (`ClaudeClient.usage_snapshot()`), estimated cost and ok/failed ticker counts are appended as one row. Runs last so every call is counted; a failure here never kills the run; dry-runs never write.

Total Claude API interactions per run: 2 plain calls (macro, summary; +2 on Fridays — retro and pattern mining) + 1 batch of N ticker requests. Usage and estimated cost (batch tokens at the 50% rate) are logged at run end and persisted to `run_metrics`.

## Infrastructure

- **Runtime**: Python 3.11 (CI) / 3.14 (local). Pinned deps in [requirements.txt](requirements.txt); [tests.yml](.github/workflows/tests.yml) runs pytest on pushes to `main` and on PRs.
- **CI**: [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml) — cron **Mon/Wed/Fri at 10:00 UTC** (12:00 CEST / 11:00 CET — GitHub cron ignores DST; Friday must stay — it triggers the weekly retrospective) + `workflow_dispatch`; job timeout 60 min, single-flight concurrency group. A second step runs `evaluate_outcomes` even if the main step failed (needs only DB secrets, no API key).
- **Secrets** (GitHub Actions): `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`, `ANTHROPIC_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`.
- **Dashboards** (datasource uid `cfadv004ogglcf`, MySQL; all schema-v2 `elements`/`layout`; import via Dashboards → New → Import):
  - [grafana/recommendations_dashboard.json](grafana/recommendations_dashboard.json) — the original overview (schema-v2 export).
  - [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json) — daily digest. "Selected day" = the latest day inside the time-range picker, so narrowing the picker to one day shows that day's full summary, recommendations, macro signals, and top Reddit posts. Also carries an **Action History by Ticker** graph (action encoded SELL −2 … BUY +2), the action-flips table (D1), action mix over time (D2), the outcomes table, hit-rate-by-action and the confidence-calibration table (D3). `phase` (HOLDING/WATCHLIST — do you own it) and `action` (the recommendation) are kept as distinct columns on purpose: they diverge (e.g. HOLDING+SELL).
  - [grafana/track_record_dashboard.json](grafana/track_record_dashboard.json) — model accuracy: scorecard header (hit rate, decisiveness, sample size), weekly hit-rate trend, hit rate by sector and by RSI band.
  - [grafana/predictions_dashboard.json](grafana/predictions_dashboard.json) — the simplified view: latest call per ticker (with each ticker's own historical hit rate) + the weekly hit-rate trend.

## Conventions

- Direct code, few abstractions (per SPEC.md).
- Error handling at external boundaries only (yfinance, Reddit, RSS, Claude).
- `--dry-run` flag logs without DB writes.
- Idempotency via `INSERT IGNORE` + NULL-ticker pre-SELECT (reddit_mentions), `ON DUPLICATE KEY UPDATE` (daily summary, price_checks), 4h-window SELECT guard (recommendations).
- All three Claude call types use **structured output** (`output_config.format`, json_schema) — malformed JSON is impossible; a refusal/truncation returns `None` and is never persisted (no fake HOLD, no placeholder summary).
- Spanish in Claude prompts; English everywhere else.
