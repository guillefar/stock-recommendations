# Handoff 03 — 2026-06-12 (session 03)

Continues [HANDOFF_02.md](HANDOFF_02.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](PLAN.md); structural map in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); design spec in [SPEC.md](SPEC.md).

## What session 03 did

This was a **review + planning session** — no code changes.

1. **Deep repo review.** New issues found (now encoded as Wave 1 of the roadmap in [PLAN.md](PLAN.md)):
   - **2×/day no-op bug:** [src/persistence/writers.py:98-109](src/persistence/writers.py#L98-L109) dedups recommendations per calendar day, so the second daily cron run pays all Claude calls and writes nothing (while still duplicating `macro_signals` and overwriting the summary).
   - **Parse-failure pollution:** [src/analysis/claude_client.py:132-135](src/analysis/claude_client.py#L132-L135) returns a `HOLD/0.5/"Error al parsear respuesta"` fallback that gets written to the DB as a real recommendation and later graded by outcomes.
   - **No per-ticker error isolation** in [src/main.py](src/main.py) — one API/network failure aborts the whole unattended run.
   - **`evaluate_outcomes` is never scheduled** — manual-only today.
   - `cache_control: ephemeral` on the tiny system prompts is likely below the cacheable minimum (verify via cost telemetry, Wave 3).
   - Grading nuances: `WATCH` graded as bullish, `HOLD` can never be INCORRECT → inflated hit-rates (decision deferred to Wave 3).
2. **Merged `chore/cron-2x-daily-and-datetime-cleanup` → `main`** (fast-forward, `main` now `2197dc1`) and pushed.
3. **Agreed a wave roadmap with the user** and rewrote PLAN.md's TODO section accordingly.

## User decisions made this session (binding)

- **Two recommendations per day** — change dedup to per-run (e.g., skip only if a row exists in the last ~4h), not per-calendar-day.
- **No push notifications for now** — action flips go in the daily summary + a dashboard panel instead (Wave 4).
- **Scope: Waves 1–4 committed**; the old low-priority cleanups are fold-in items, not a scheduled wave.

## State of play (unchanged blockers)

- **No real (non-dry-run) run yet** with the decisive prompt — DB still all old WATCH/HOLD rows.
- **Reddit is dark** — `REDDIT_CLIENT_ID/SECRET/USER_AGENT` still missing (user-side task, Wave 1).
- **`price_snapshots` stale** (last row 2026-05-22) → outcomes grade 0 rows. External to this repo.

## Next session = Wave 1 (Correctness & unblocking)

See PLAN.md "Wave 1" for the precise items: per-run dedup, skip-don't-persist parse failures, per-ticker try/except, schedule `evaluate_outcomes` in the workflow. Fold in the single-DB-connection cleanup while editing the main loop. Then (user-permitting) Reddit creds + first real run.

Implementation notes for Wave 1:
- The per-run dedup window must still protect against same-slot retries (workflow re-run) — ~4h window or (ticker_id, date, AM/PM-slot) key.
- When a ticker's recommendation fails (parse or API), don't write anything for it; count failures and report in the final log line; exit non-zero only if **all** tickers failed.
- `evaluate_outcomes` as a second workflow step is harmless while it grades 0 rows.

## Invariants (don't break)

- Never write to `stock-snapshots` tables. Read-only.
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- Per-session ritual: branch first → confirm task list → batch work → close with docs + numbered handoff + next-session prompt.

## Prompt for the next session

> Read HANDOFF_03.md and PLAN.md. Today we do **Wave 1 — Correctness & unblocking**: (1) per-run recommendation dedup (two recs/day decision), (2) never persist parse-failure fallbacks, (3) per-ticker error isolation in main.py, (4) schedule evaluate_outcomes in the GitHub workflow, folding in the single-DB-connection cleanup while you're in the main loop. Branch first, confirm the task list with me, then implement, test with --dry-run, and close out with docs + HANDOFF_04.
