# Handoff 05 — 2026-06-12 (session 05)

Continues [HANDOFF_04.md](HANDOFF_04.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](PLAN.md); structural map in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); design spec in [SPEC.md](SPEC.md).

## What session 05 did — first real execution + roadmap decisions

No code changes this session — it was the execution/validation/decision session planned in HANDOFF_04. Branch **`chore/session-05-first-real-run`** (off `main` @ `ca4937a`) carries only docs (this file + PLAN.md).

1. **Wave 1 merged.** `fix/wave-1-correctness` fast-forwarded into `main` (`ca4937a`) and pushed (the user completed the push directly mid-session).
2. **First real (non-dry-run) `python -m src.main`.** 63 tickers ok / 0 failed, exit 0. Actions stored: **34 WATCH / 27 HOLD / 2 SELL** — the first non-WATCH/HOLD rows in the DB. Daily summary upserted (BEARISH). Only warning: missing Reddit creds (expected).
3. **First real `python -m src.evaluate_outcomes`.** **693 outcomes written at 7d** (of 945 matured candidates), 0 at 30d — exactly the backfill predicted in HANDOFF_04. Verdicts: **326 INCORRECT / 113 CORRECT / 254 NEUTRAL**.
4. **DB sanity checks passed** (the HANDOFF_04 step-5 queries): 63 recommendation rows today, 693 outcome rows, today's summary present.
5. **4h dedup verified.** A second `src.main` run within the window logged `Skipping duplicate recommendation` for **all 63 tickers**; the today-count stayed 63. Exit 0.
6. **Roadmap decisions** (see PLAN.md decisions log): **adopted S1, S5, D1+D2, D3** (D3 sequenced after the grading fix); **grading-semantics decision pulled forward to session 06**; **S6 deferred**; S2/S3/S4 not adopted for now.
7. **New session ritual:** every session now gets its **own git worktree** (under `.claude/worktrees/`), not just a branch. Symlink `.env` and `.venv` from the main checkout into the worktree (gitignore's `.venv/` pattern misses the symlink — add `.venv` to `.git/info/exclude`, already done once, it's shared across worktrees).

## Observations from the real runs (inputs to future work)

- **Summary variance:** two runs minutes apart produced BEARISH then MIXED; the per-day upsert means the afternoon run always overwrites the morning one. See suggestion S8 below.
- **Verdict skew:** 326/693 INCORRECT largely because WATCH grades as bullish and the market fell over the backfill window; HOLD can never be INCORRECT. This is the session-06 semantics decision, with real data to look at now.
- **No BUY yet:** plausible on a BEARISH day; watch whether BUY ever fires over the coming week.

## State of play

- `main` @ `ca4937a` (Wave 1 included), pushed. Branch `chore/session-05-first-real-run` carries docs only.
- **Reddit is still dark** — none of `REDDIT_CLIENT_ID/SECRET/USER_AGENT` in `.env` (user-side task, open since Wave 1). Reminder: https://www.reddit.com/prefs/apps, "script" app; also add the three GitHub Actions secrets.
- `price_snapshots` still stale (last row 2026-05-22) → **new** recommendations ungradeable until S1 lands (session 06).
- The 2×/day cron is live; from now on outcomes/recs accumulate without manual runs.

## Invariants (don't break)

- Never write to `stock-snapshots` tables. Read-only. (New tables this repo owns — e.g. S1's `price_checks` — are fine.)
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- Grafana dashboards must be **schema-v2** (`elements`/`layout`) — classic schema fails import on the user's Grafana 13.1.x.
- Per-session ritual: **worktree + branch first** → confirm task list → batch work → close with docs + numbered handoff (complete next prompt, detailed TODO an older model can follow, fresh suggestions) → push the branch (never merge to `main` yourself) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs — put any explanation they must read inside the question text/options or in the final message, never in mid-turn text.

## Suggestions — new functionality / redesigns (fresh, for discussion; NOT committed work)

- **S7 — Prompt/model provenance columns (low effort, high analytical value).** Add `prompt_version` and `model` columns to `recommendations` (migration alongside S1's). Backfill-by-era is already implicitly visible (all-WATCH/HOLD vs decisive), but explicit versioning makes every future prompt change A/B-queryable and keeps hit-rate comparisons honest across eras.
- **S8 — Per-run daily summaries instead of per-day upsert (low effort).** Session 05 showed the upsert flipping BEARISH→MIXED between runs. Add a `run_slot` (or timestamp key) so both daily runs persist; digest shows the latest but morning/afternoon sentiment divergence becomes data (pairs with D1).
- **S9 — Macro-signal effectiveness panel (low-medium effort).** `macro_signals` rows exist but nothing measures whether they help. Join signals to next-day sector moves (or to recommendation outcomes of matching-sector tickers) in a digest panel: "when macro said RISK_OFF for tech, what happened?"
- **S10 — Position-size awareness (medium effort, needs user data).** SELL on a 2% position and SELL on a 40% position are very different advice. If the user provides approximate position sizes (new table or .env), include them in HOLDING prompts and weight the daily summary's risk callouts.

## Detailed TODO for session 06 (step-by-step; follow in order)

**Step 0 — Orient.** Read [HANDOFF_05.md](HANDOFF_05.md) (this file) and [PLAN.md](PLAN.md) completely before editing anything. The session's scope is **Wave 1.5** (PLAN.md): grading semantics + S1, then D1+D2 panels if time.

**Step 1 — Workspace.** From the main checkout on updated `main` (`git checkout main && git pull`): create a **worktree + branch** for the session (EnterWorktree tool or `git worktree add .claude/worktrees/session-06-<topic> -b <type>/session-06-<topic> main`). Then symlink env and venv into it:
```bash
ln -s /home/guillo/Git/stock-recommendations/.env .env
ln -s /home/guillo/Git/stock-recommendations/.venv .venv
```
Write the session task list and **confirm it with the user before executing** (explanations inside the AskUserQuestion text, not mid-turn prose).

**Step 2 — Grading-semantics decision (with the user, before coding).** Present options with current-data context (693 rows: 326 INCORRECT / 113 CORRECT / 254 NEUTRAL):
- WATCH: (a) exclude from hit-rate entirely, (b) grade on |move| ≥ some threshold ("worth watching" = it moved), (c) keep as bullish (status quo).
- HOLD: (a) INCORRECT if the price fell more than a band (e.g. −10%) over the horizon, (b) keep never-INCORRECT (status quo).
- BUY/SELL/AVOID grading stays as-is (directional).
Record the decision in PLAN.md's decisions log **before** implementing.

**Step 3 — Implement the chosen semantics.** Edit `grade()` in [src/evaluate_outcomes.py](src/evaluate_outcomes.py); update/extend [tests/test_outcomes.py](tests/test_outcomes.py) to cover the new rules; run `.venv/bin/python -m pytest tests/test_outcomes.py -q` (pytest lives in the venv only).

**Step 4 — Re-grade the backfill (destructive but re-derivable; the next-session prompt authorizes it).**
```bash
.venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv()
from src.config import load_config; from src.db import get_connection
conn = get_connection(load_config()); cur = conn.cursor()
cur.execute('DELETE FROM recommendation_outcomes'); conn.commit()
print('deleted, remaining:', cur.execute('SELECT COUNT(*) FROM recommendation_outcomes') and cur.fetchone())
conn.close()"
.venv/bin/python -m src.evaluate_outcomes
```
Expect ~693 rows again (the exact count can shift slightly as more recs mature) with a verdict distribution that reflects the new semantics. Record before/after verdict counts in HANDOFF_06.

**Step 5 — S1: `price_checks` fallback.**
1. Write `migrations/003_create_price_checks.sql`: `price_checks(id PK, ticker_id FK, as_of_date DATE, price DECIMAL, created_at)`, UNIQUE on `(ticker_id, as_of_date)`. Follow the style of [migrations/002_create_recommendation_outcomes.sql](migrations/002_create_recommendation_outcomes.sql).
2. Apply it to the DB with the repo connection (same pattern as step 4's snippet, executing the file's SQL).
3. In [src/main.py](src/main.py): after each ticker's analysis, upsert today's price (already in `technical`) into `price_checks` — respect `--dry-run` (no writes).
4. In [src/evaluate_outcomes.py](src/evaluate_outcomes.py): when `price_snapshots` has no row at/after the horizon date, fall back to `price_checks` the same way. Prefer `price_snapshots` when both exist.
5. Validate: `.venv/bin/python -m src.main --dry-run` (63 ok, no writes), pytest, then one real `src.main` (the 4h dedup will skip recommendation rows if within the window — `price_checks` upserts should still happen; if the day's cron already ran, that's fine) and check `SELECT COUNT(*) FROM price_checks`.

**Step 6 — D1+D2 digest panels (only if time remains; re-confirm with the user).** Edit [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json) (schema-v2 `elements`/`layout` only):
- D1: table of tickers where the day's two runs disagree on action (self-join `recommendations` on ticker + DATE(generated_at), differing actions/run times).
- D2: stacked bars of action counts per day (`GROUP BY DATE(generated_at), action`).
Validate both SQL queries against the live DB before embedding them.

**Step 7 — Close out.** Update PLAN.md (check off Wave 1.5 items done; refresh Current state; decisions log). Write HANDOFF_06.md with: what was done, validation evidence (incl. before/after verdict counts), a **complete copy-pasteable next-session prompt**, a **detailed step-by-step TODO like this one**, and a **fresh suggestions section** (consider S7–S10 above if still undecided). Commit, **push the session branch** (do not merge), and **print the full next-session prompt in the chat reply**.

## Prompt for the next session (copy-paste exactly)

> Read HANDOFF_05.md and PLAN.md before doing anything — HANDOFF_05 contains the detailed step-by-step TODO for this session (session 06); follow it in order. Context: Wave 1 is merged to main; the first real runs happened in session 05 (63 recs/day incl. the first 2 SELLs; 693 outcomes backfilled at 7d with verdicts 326 INCORRECT / 113 CORRECT / 254 NEUTRAL, skewed by grading semantics). Session 06 scope is Wave 1.5 from PLAN.md. Start by creating the session worktree + branch (worktree per session is the standing rule) and confirming the task list with me. Then: walk me through the grading-semantics options for WATCH and HOLD with the current data and ask me to decide (put the explanation inside the question, I don't see mid-turn text); implement the chosen semantics in evaluate_outcomes.py + tests. I authorize deleting all rows of recommendation_outcomes and re-grading them under the new semantics (they are fully re-derivable). Then implement S1: migration 003 price_checks table — I authorize applying the migration to the DB — write one price row per ticker per run in src.main, and make evaluate_outcomes fall back to price_checks when price_snapshots has no row in the horizon window. Validate with --dry-run, pytest, and one real run. If time remains, add the D1 (morning-vs-afternoon disagreement) and D2 (action-mix-over-time) panels to the digest dashboard in schema v2, validating queries against the DB first. Also check whether I added the Reddit credentials yet. Close out per the ritual: update PLAN.md, write HANDOFF_06.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push the branch without merging, and print the full next-session prompt in the chat.
