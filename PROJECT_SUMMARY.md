# Project Summary — stock-recommendations

A short, structural overview of the codebase. For design rationale and decisions, see [SPEC.md](SPEC.md). For current work-in-progress and TODOs, see [PLAN.md](PLAN.md).

## What it does

Automated pipeline that generates daily BUY/SELL/HOLD/WATCH/AVOID recommendations for the user's stock portfolio by combining:

- **Technicals** — yfinance prices + pandas-computed indicators (RSI, SMA20/50/200, % changes, 52w position, volume ratio).
- **Reddit sentiment** — `/r/stocks` hot posts; mentions of known tickers and detection of trending unknown tickers.
- **Macro news** — RSS feeds (Reuters, MarketWatch, Yahoo Finance) → Claude identifies themes + affected sectors.
- **LLM analysis** — Claude Haiku 4.5 generates: macro signals, per-ticker recommendation, daily market summary.

Runs on **GitHub Actions cron** (no server). Reads from the existing `stock-snapshots` MySQL DB and writes to four new tables it owns.

## Relationship to `stock-snapshots`

A separate sibling project owns `tickers`, `holdings`, `watchlist`, `transactions`, `price_snapshots`. This project **only reads** those tables. It owns:

- `recommendations` — one row per ticker per run.
- `daily_market_summary` — one row per calendar date.
- `reddit_mentions` — audit trail of posts referencing tickers.
- `macro_signals` — themes detected from headlines.

Full DDL: [migrations/001_create_recommendation_tables.sql](migrations/001_create_recommendation_tables.sql).

## Module map

```
src/
├── main.py                 # orchestrator (--dry-run supported)
├── config.py               # env-var loader → Config dataclass
├── db.py                   # PyMySQL connection + get_active_tickers, get_known_symbols
├── collectors/
│   ├── prices.py           # yfinance history + RSI/SMA/etc.; fetch_ticker_news (currently unused)
│   ├── reddit.py           # /r/stocks scraping + ticker extraction + trending detection
│   └── news.py             # RSS feed aggregation + dedup
├── analysis/
│   ├── claude_client.py    # Anthropic SDK wrapper; 3 prompts (macro, ticker, summary); JSON-only outputs
│   ├── macro.py            # thin wrapper around claude_client.analyze_macro
│   ├── recommendation.py   # thin wrapper around claude_client.analyze_ticker
│   └── summary.py          # thin wrapper around claude_client.generate_daily_summary
└── persistence/
    └── writers.py          # INSERTs to all 4 owned tables; daily-dedup logic for recommendations
```

## Execution flow ([main.py](src/main.py))

1. Load active tickers from DB (`holdings.quantity > 0` ∪ `watchlist.active = 1`) and known symbol set.
2. Fetch Reddit hot posts from `/r/stocks`.
3. Fetch macro headlines from RSS feeds.
4. **Claude call #1** — macro signal extraction → `macro_signals`.
5. Extract per-ticker Reddit mentions; match by `$TICKER` and uppercase-word patterns against known symbols.
6. **For each active ticker:**
   - Compute technicals from yfinance.
   - Pick most relevant macro signal by sector.
   - **Claude call #2** — recommendation JSON → `recommendations`, `reddit_mentions`.
7. Write Reddit mentions for posts with no matched ticker.
8. Detect trending unknown tickers (filter: score > 100, mentions > 3).
9. **Claude call #3** — daily summary → `daily_market_summary`.

Total Claude calls per run: `2 + N` where N = number of active tickers.

## Infrastructure

- **Runtime**: Python 3.11 (CI) / 3.14 (local).
- **CI**: [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml) — cron + `workflow_dispatch`.
- **Secrets** (GitHub Actions): `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`, `ANTHROPIC_API_KEY`.
- **Dashboard**: [grafana/recommendations_dashboard.json](grafana/recommendations_dashboard.json) — 1309-line Grafana export.

## Conventions

- Direct code, few abstractions (per SPEC.md).
- Error handling at external boundaries only (yfinance, Reddit, RSS, Claude).
- `--dry-run` flag logs without DB writes.
- Idempotency via `INSERT IGNORE` (reddit_mentions), `ON DUPLICATE KEY UPDATE` (daily summary), SELECT-then-INSERT guard (recommendations).
- All Claude outputs are strict JSON; parser strips markdown fences as a fallback.
