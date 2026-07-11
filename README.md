# stock-recommendations

Automated pipeline that generates daily **BUY / SELL / HOLD / WATCH / AVOID**
recommendations for the user's stock portfolio by combining technical indicators,
Reddit sentiment, macro news, and Claude (Haiku 4.5) analysis. It runs on a
GitHub Actions cron — no server — reading from the sibling `stock-snapshots`
MySQL database (read-only) and writing to the tables it owns.

## Documentation

| Doc | What's in it |
| --- | --- |
| [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | Static structural overview — what each module does, the data model, the tables this project owns vs. reads. |
| [SPEC.md](SPEC.md) | Design spec and rationale (the immutable "why"). |
| [PLAN.md](PLAN.md) | Rolling status, the wave roadmap, and the decisions log. Start here for "what's the current state". |
| [handoffs/](handoffs/) | Per-session handoffs (`HANDOFF_NN.md`) + evergreen orientation in [handoffs/HANDOFF.md](handoffs/HANDOFF.md). |

## Running locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt        # runtime deps (pinned)
pip install -r requirements-dev.txt    # + pytest, for tests

cp .env.example .env                   # fill in DB_* + ANTHROPIC_API_KEY (+ optional REDDIT_*)

python -m src.main --dry-run           # full run, logs only — no DB writes
python -m src.main                      # real run (writes recommendations + price_checks)
python -m src.main --force-retro       # also generate the weekly retrospective off-Friday
python -m src.evaluate_outcomes --dry-run   # grade matured recommendations
python -m pytest tests/ -q             # unit tests (pure logic, no DB/API)
```

Required env vars: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`,
`ANTHROPIC_API_KEY`. Optional: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
`REDDIT_USER_AGENT` (without them every run has zero Reddit sentiment).

## Scheduling (GitHub Actions)

- [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml)
  — runs the pipeline once per weekday at **12:00 CEST (10:00 UTC)**, then grades
  outcomes. GitHub cron is UTC and ignores DST (fires 11:00 local in CET winter).
  Needs the env vars above as repository secrets.
- [.github/workflows/tests.yml](.github/workflows/tests.yml) — runs `pytest` on
  pushes to `main` and on every PR.

## Database

Migrations in [migrations/](migrations/) (apply in order: `001` → `005`). This
project **only writes** to `recommendations`, `daily_market_summary`,
`reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`,
`trending_tickers`, and `weekly_retrospectives`.
It never writes to `stock-snapshots` tables.

## Grafana dashboards

Five dashboards live in [grafana/](grafana/), authored in **schema v2**
(`elements` / `layout`) for Grafana 13.1.x:

- `predictions_dashboard.json` — the **simplified view**: the latest call per
  ticker (action, confidence, entry price, one-line reasoning, and that
  ticker's own historical hit rate) plus the weekly hit-rate trend.
- `daily_digest_dashboard.json` — the daily digest (summary, recommendations,
  macro signals, outcomes, hit-rate and calibration panels, the weekly
  retrospective, flips-per-run trend, and trending watchlist candidates).
- `recommendations_dashboard.json` — recommendation/confidence history.
- `track_record_dashboard.json` — model accuracy over time: a scorecard header
  (overall hit rate, decisiveness, sample size), a **weekly hit-rate trend**
  (when the model was right, by horizon), and **hit rate by sector** and **by
  RSI band** (what correct calls share). Hit rate = CORRECT ÷ (CORRECT+INCORRECT),
  so neutral calls are excluded; all panels default to the **30-day** horizon
  (long-term orientation — 7d is a timing diagnostic on the trend chart) and
  respect the time picker.
- `ticker_deep_dive_dashboard.json` — **per-stock track record**: a multi-select
  **Ticker** variable scopes every panel — 30d hit-rate scorecard, price history
  (from `price_checks`), hit rate by horizon, weekly verdict bars, and the full
  call history with each call's 30-day grade.

To import: **Dashboards → New → Import**, paste the JSON, and select your MySQL
datasource when prompted. Date navigation uses the **time-range picker** (the
"selected day" panels query `MAX(date) WHERE $__timeFilter(...)`), not a
template-variable dropdown — pick the day via the time range at the top right.
The ticker deep-dive is the exception: it adds a **Ticker** dropdown for
symbol selection (time scoping still comes from the picker).
