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
  every push and PR.

## Database

Migrations in [migrations/](migrations/) (apply in order: `001` → `003`). This
project **only writes** to `recommendations`, `daily_market_summary`,
`reddit_mentions`, `macro_signals`, `recommendation_outcomes`, and `price_checks`.
It never writes to `stock-snapshots` tables.

## Grafana dashboards

Two dashboards live in [grafana/](grafana/), authored in **schema v2**
(`elements` / `layout`) for Grafana 13.1.x:

- `daily_digest_dashboard.json` — the daily digest (summary, recommendations,
  macro signals, outcomes, hit-rate and calibration panels).
- `recommendations_dashboard.json` — recommendation/confidence history.

To import: **Dashboards → New → Import**, paste the JSON, and select your MySQL
datasource when prompted. Date navigation uses the **time-range picker** (the
"selected day" panels query `MAX(date) WHERE $__timeFilter(...)`), not a
template-variable dropdown — pick the day via the time range at the top right.
