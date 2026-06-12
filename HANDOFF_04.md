# Handoff 04 — 2026-06-12 (session 04)

Continues [HANDOFF_03.md](HANDOFF_03.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](PLAN.md); structural map in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); design spec in [SPEC.md](SPEC.md).

## What session 04 did — Wave 1 (Correctness & unblocking)

All code items of Wave 1, on branch **`fix/wave-1-correctness`** (off `main` @ `241caa5`). **Not yet merged.**

1. **Per-run dedup.** [src/persistence/writers.py](src/persistence/writers.py): `write_recommendation` skips only if the ticker already has a row within `DEDUP_WINDOW_HOURS = 4` (was: same calendar day). Fixes the 2×/day no-op bug; the 17:00 ART run now writes real rows. Same-slot workflow retries are still deduped.
2. **Parse failures are never persisted.** `analyze_ticker` ([src/analysis/claude_client.py](src/analysis/claude_client.py)) returns `None` on unparseable JSON instead of a fake `HOLD/0.5` row; the wrapper in [src/analysis/recommendation.py](src/analysis/recommendation.py) is typed `dict | None` accordingly.
3. **Per-ticker error isolation.** Per-ticker body in [src/main.py](src/main.py) wrapped in try/except → log + count + continue. Missing technicals and `None` recommendations also count as failures. Final log line: `tickers_ok=… tickers_failed=… (failed: […])`. Exits non-zero (SystemExit(1)) only when *every* ticker failed.
4. **`evaluate_outcomes` scheduled.** New step after `src.main` in [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml), with `if: ${{ !cancelled() }}` so grading runs even if the main step fails. It needs `ANTHROPIC_API_KEY` in env only because `load_config()` requires the var; the evaluator never calls Claude.
5. **Fold-in: single DB connection.** main opens one connection for the whole run (was 2+2N opens), with `conn.ping(reconnect=True)` before each write phase since the connection idles during Claude/yfinance calls.

## Validation done

- `python -m src.main --dry-run` — full pass: **63 tickers ok / 0 failed**, no DB writes, summary generated.
- `python -m src.evaluate_outcomes --dry-run` — **693 candidates graded at 7d, 0 at 30d** (see surprise below).
- `tests/test_outcomes.py` — 3/3 pass. pytest was installed **into the local venv only**; adding it to requirements is still Wave 3.

## New finding (corrects HANDOFF_03/PLAN claims)

The "outcomes grade 0 rows" claim was wrong. `price_snapshots` is stale (last row 2026-05-22) but old recommendations **matured against the snapshots that do exist**: the evaluator's first scheduled run will **backfill ~693 outcome rows at the 7d horizon**, all from the old always-HOLD/WATCH prompt era. Expect the digest's hit-rate panels to suddenly populate — dominated by HOLD/WATCH grading semantics (the Wave 3 "grading semantics" decision becomes more urgent once this lands).

## State of play

- **Branch `fix/wave-1-correctness` needs merging to `main`** (next session, or user merges).
- **No real (non-dry-run) run yet** with the decisive prompt.
- **Reddit is dark** — `REDDIT_CLIENT_ID/SECRET/USER_AGENT` still missing (user-side task, still open from Wave 1).
- `price_snapshots` still stale for *new* recommendations; external to this repo.

## Invariants (don't break)

- Never write to `stock-snapshots` tables. Read-only.
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- Per-session ritual: branch first → confirm task list → batch work → close with docs + numbered handoff + next-session prompt.

## Prompt for the next session

> Read HANDOFF_04.md and PLAN.md. First merge `fix/wave-1-correctness` to `main` and push. Then, if I've added the Reddit credentials, verify a run picks them up; either way, do the **first real (non-dry-run) execution** (workflow_dispatch or local) and sanity-check the new rows in the DB — including the ~693 backfilled 7d outcomes. If time remains, start **Wave 2 — Signal quality** (news into the ticker prompt first).
