# Project Summary — stock-recommendations

A short, structural overview of the codebase. For design rationale and decisions, see [SPEC.md](SPEC.md). For current work-in-progress and TODOs, see [PLAN.md](PLAN.md).

## What it does

Automated pipeline that generates daily BUY/SELL/HOLD/WATCH/AVOID recommendations for the user's stock portfolio by combining:

- **Technicals** — yfinance prices + pandas-computed indicators (RSI, SMA20/50/200, % changes, 52w position, volume ratio).
- **Reddit sentiment** — `/r/stocks` hot posts; mentions of known tickers and detection of trending unknown tickers.
- **Macro news** — RSS feeds (Reuters, MarketWatch, Yahoo Finance) → Claude identifies themes + affected sectors.
- **LLM analysis** — Claude Haiku 4.5 generates: macro signals, per-ticker recommendation, daily market summary.

Runs on **GitHub Actions cron** (no server). Reads from the existing `stock-snapshots` MySQL DB and writes to eight tables it owns.

## Relationship to `stock-snapshots`

A separate sibling project owns `tickers`, `holdings`, `watchlist`, `transactions`, `price_snapshots`. This project **only reads** those tables. It owns:

- `recommendations` — one row per ticker per run.
- `daily_market_summary` — one row per calendar date.
- `reddit_mentions` — audit trail of posts referencing tickers.
- `macro_signals` — themes detected from headlines.
- `recommendation_outcomes` — one row per recommendation per horizon (7d/30d/90d/365d; grading bands widen with the horizon, 30d is the headline metric); grades the forward return. Populated separately by `python -m src.evaluate_outcomes`, not by the main pipeline.
- `price_checks` — one observed price per ticker per day, written by the main run; the evaluator's fallback exit-price source while `price_snapshots` is stale.
- `trending_tickers` — one row per trending-unknown symbol (upserted per run; `times_seen` counts trending runs). Empty until Reddit credentials exist.
- `weekly_retrospectives` — one row per week (keyed on its Monday): Claude's week-in-review for a long-term investor + the `stats` JSON it was built from. Written on Friday runs (S5).

Full DDL: [migrations/](migrations/) (001 recommendation tables, 002 outcomes, 003 price_checks, 004 trending_tickers, 005 weekly_retrospectives).

## Module map

```
src/
├── main.py                 # orchestrator (--dry-run supported)
├── evaluate_outcomes.py    # standalone job: grades past recommendations vs realized prices
├── config.py               # env-var loader → Config dataclass
├── db.py                   # PyMySQL connection + ticker/action/week-outcome/flip queries
├── collectors/
│   ├── prices.py           # yfinance history + RSI/SMA/etc.; fetch_ticker_news + fetch_next_earnings + fetch_etf_info (all feed the per-ticker prompt)
│   ├── reddit.py           # /r/stocks scraping (PRAW) + ticker extraction + trending detection
│   └── news.py             # RSS feed aggregation + dedup
├── analysis/
│   ├── claude_client.py    # Anthropic SDK wrapper; macro + summary calls, per-ticker Message Batches call; structured output; usage/cost telemetry
│   ├── actions.py          # per-phase allowed action sets + coerce_action backstop
│   ├── macro.py            # thin wrapper around claude_client.analyze_macro
│   ├── recommendation.py   # thin wrappers: analyze_ticker (ad-hoc) + analyze_tickers_batch (the run)
│   ├── retrospective.py    # S5: aggregates the week's outcomes/flips/exposure for the retro call
│   └── summary.py          # thin wrapper around claude_client.generate_daily_summary
└── persistence/
    └── writers.py          # writes to all 8 owned tables; 4h dedup window for recommendations
```

## Execution flow ([main.py](src/main.py))

1. Load active tickers from DB (`holdings.quantity > 0` ∪ `watchlist.active = 1`) and known symbol set.
2. Fetch Reddit hot posts from `/r/stocks`.
3. Fetch macro headlines from RSS feeds.
4. **Claude call #1** — macro signal extraction → `macro_signals`. Wrapped in try/except: on failure the run continues with zero macro signals (a Claude outage must not stop price collection).
5. Extract per-ticker Reddit mentions; match by `$TICKER` and uppercase-word patterns against known symbols.
6. **Per-ticker, in three phases:**
   - **6a — collect:** technicals from yfinance (+ upsert today's price into `price_checks` before any Claude involvement), Reddit sentiment summary, news headlines (top 3), next earnings date, the ETF profile for tickers whose `quote_type` is ETF (family, expense ratio, top-5 holdings, sector mix via yfinance `funds_data` — stocks skip the fetch entirely), and the ticker's standing call (`prev_action` + `prev_held_days`, from `get_latest_actions` — read before any of this run's rows land). Failures are isolated per ticker.
   - **6b — one Message Batches call** with all N per-ticker requests (50% token discount; polled up to 45 min, then canceled). Since session 16 each prompt shows "Recomendación vigente: X (mantenida N días)" and requires naming material new information to reverse it (flip-stability). Since session 18 ETF prompts carry a "Perfil del ETF" block (composition + costs) with an instruction to judge the fund by its exposure, not as a single stock.
   - **6c — persist:** each parsed recommendation → `recommendations` (+ `reddit_mentions` for matched posts), linked to the most relevant macro signal for its sector (a POSITIVE/NEGATIVE direction beats a NEUTRAL mention). Unparseable/errored entries count as failures; nothing is persisted for them. Action flips vs each ticker's previous stored recommendation are collected here (S17).
7. Write Reddit mentions for posts with no matched ticker (NULL-ticker rows are deduped by a pre-SELECT, since the UNIQUE key can't compare NULLs).
8. Detect trending unknown tickers (filter: score > 100, mentions > 3) and upsert them into `trending_tickers`.
9. **Claude call #2** — daily summary → `daily_market_summary`; the prompt includes the run's action flips ("Cambios de recomendación vs la corrida anterior") so the summary calls them out, and carries only the first sentence of each recommendation's reasoning (the full text is stored per rec; 63 full reasonings dominated this call's input tokens). On failure the summary returns `None` and nothing is written (never an error placeholder).
10. **Fridays only (or `--force-retro`): Claude call #3** — weekly retrospective → `weekly_retrospectives` (S5): reviews the calls whose 30d horizon matured that week, the week's flips, and sector exposure. Same failure rule: `None` is never persisted, and a retro failure can't kill the run.

Total Claude API interactions per run: 2 plain calls (macro, summary; +1 retro on Fridays) + 1 batch of N ticker requests. Usage and estimated cost (batch tokens at the 50% rate) are logged at run end.

## Infrastructure

- **Runtime**: Python 3.11 (CI) / 3.14 (local). Pinned deps in [requirements.txt](requirements.txt); [tests.yml](.github/workflows/tests.yml) runs pytest on pushes to `main` and on PRs.
- **CI**: [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml) — cron **once per weekday at 10:00 UTC** (12:00 CEST / 11:00 CET — GitHub cron ignores DST) + `workflow_dispatch`; job timeout 60 min, single-flight concurrency group. A second step runs `evaluate_outcomes` even if the main step failed (needs only DB secrets, no API key).
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
