# Handoff 02 — 2026-06-11 (session 02)

Continues [HANDOFF_01.md](HANDOFF_01.md). For evergreen orientation see [HANDOFF.md](HANDOFF.md); rolling status/TODOs in [PLAN.md](PLAN.md); structural map in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); original design in [SPEC.md](SPEC.md).

## Repo facts (unchanged from HANDOFF_01)

- **Path:** `/home/guillo/Git/stock-recommendations` (the sibling `/home/guillo/Git/stock` is a *different* project, `stock-snapshots`, which owns the DB).
- **Virtualenv:** `.venv` (with a dot). Run as `.venv/bin/python -m src.main` from the repo root.
- **DB:** read-only against `stock-snapshots` tables; this project owns `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`.
- **Git remote now exists** (`origin`). As of HANDOFF_01's close, `main`, `origin/main`, and `feat/decisive-recommendations-and-digest` (+ its remote) all sat at `370810e`.

## Working agreement (NEW — applies to every future session)

The user codified a per-session ritual (also saved to Claude memory as `feedback-session-workflow`):

1. **Branch first.** Start each session by creating a new branch for the changes — before editing. Don't work on `main`.
2. **Confirm a task list.** After the opening prompt, write the list of what you'll do this session and **get the user's confirmation** before executing.
3. **Batch non-conflicting work.** Group TODOs/changes that don't overlap and apply them together.
4. **Close out.** End each session by updating `PROJECT_SUMMARY.md`/`PLAN.md` if needed, writing the next numbered `HANDOFF_NN.md`, and handing over the prompt for the next session.

## What session 02 changed

On branch **`chore/cron-2x-daily-and-datetime-cleanup`** (off `main` @ `370810e`):

1. **`datetime.utcnow()` deprecation cleared** — [src/persistence/writers.py](src/persistence/writers.py). Added a module-level `_utcnow()` (`datetime.now(timezone.utc).replace(tzinfo=None)`) and swapped all 4 call sites. Values written to MySQL are still naive-UTC (byte-for-byte identical). Verified the module imports under Python 3.14.5 with `-W error::DeprecationWarning` and no warning fires. `reddit.py` was already migrated — the HANDOFF_01/PLAN TODO entry for it was stale.
2. **Workflow → 2×/day** — [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml). Replaced the single `0 11 * * 1-5` line (whose comment wrongly said "13:00 UTC") with two lines, `0 11` and `0 17`, Mon–Fri, accurate UTC comments. **Assumption flagged:** GitHub Actions cron is always UTC, so these fire at 11:00/17:00 UTC. If the user meant local time, adjust.
3. **Docs** — marked the two TODOs done in [PLAN.md](PLAN.md), added a "Done (session 02)" block, and updated the secrets list in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) to include `REDDIT_CLIENT_ID/SECRET/USER_AGENT`.

## State of play (still-open blockers, unchanged)

- **No real (non-dry-run) run yet** with the decisive prompt → DB still holds only the old all-WATCH/HOLD recommendations.
- **Reddit is dark** — PRAW collector committed but no `REDDIT_CLIENT_ID/SECRET/USER_AGENT` in `.env` or GitHub secrets, so every run has zero Reddit sentiment.
- **`price_snapshots` is stale** (last row 2026-05-22) → `evaluate_outcomes` grades 0 rows. External (sibling collector), not fixable here.

## Immediate next steps

1. **Commit/push this branch** if not already, and decide whether to merge to `main` (changes are low-risk and self-contained).
2. Pick the next blocker-independent code-quality TODO, or tackle a blocker (Reddit creds → first real run).
3. Confirm the cron times are meant as **UTC** (they are, in GitHub Actions) — flagged above.

## Invariants (don't break)

- Never write to `stock-snapshots` tables/views. Read-only.
- Keep `--dry-run` working (no DB writes).
- All Claude outputs are strict JSON parsed by `claude_client._parse_json`.
- Spanish in the Claude system/user prompts; English elsewhere.
- Recommend concrete, scoped changes over option dumps — recommend, then offer to implement.
