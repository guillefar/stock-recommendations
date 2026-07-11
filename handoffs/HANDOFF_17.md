# Handoff 17 — 2026-07-11 (session 17: token trims + fold-in cleanups)

Continues [HANDOFF_16.md](HANDOFF_16.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 17 did

On branch **`feat/session-17-token-trims`** (off `main` @ `d23d466`), worktree `.claude/worktrees/session-17-token-trims`. Pushed, **not merged**.

Session context: **session 16 was ff-merged to `main` (`d23d466`) and pushed before this session's work started** — the HANDOFF_16 merge gate is cleared, and the Mon 2026-07-13 production run will carry the flip-stability reinforcement regardless of what happens to this branch. This session began as a recovery: an earlier session-17 attempt was interrupted after writing the code + tests but before validating, documenting, or committing anything. The work was found uncommitted-but-green in the worktree, reviewed line-by-line, validated from scratch, and adopted.

1. **Token trims (HANDOFF_12 backlog — all three levers)**, prompt-side only, stored data untouched:
   - **Summary prompt gets first-sentence-only reasonings**: `_first_sentence` in [src/analysis/claude_client.py](../src/analysis/claude_client.py) (regex split on sentence-ending punctuation + whitespace); `generate_daily_summary` renders `{symbol}: {action} (confianza) — {first sentence}`. The full reasoning is still stored per recommendation and shown on dashboards.
   - **Reasoning capped at 2 sentences**: the per-ticker JSON instruction now reads *"máximo 2 frases, citando las señales concretas que pesaron y la tesis al horizonte de 1+ mes"* (was "2-4 frases"). Output tokens cost 5× input — this is the biggest lever.
   - **News trimmed 5→3** both at fetch ([src/main.py](../src/main.py) `fetch_ticker_news(symbol)[:3]`) and at render (`news_titles[:3]`).
2. **Fold-in: `get_active_tickers` UNION refactor** ([src/db.py](../src/db.py)): two INNER-JOIN arms (holdings → `'HOLDING'`; watchlist minus held → `'WATCHLIST'`) replacing the LEFT-JOIN/CASE query. Verified live: **identical 63 rows** to the old query; zero held+watchlisted overlap tickers exist today, and if one appears it comes back once, as HOLDING.
3. **Fold-in: macro→ticker matching prefers directional signals** — `_pick_macro_signal_id` in [src/main.py](../src/main.py): a signal whose `direction[sector]` is POSITIVE/NEGATIVE wins over a NEUTRAL mention; first sector match remains the fallback; no match → NULL link. Unit-tested.
4. **Dashboard description drift fixed** ([grafana/predictions_dashboard.json](../grafana/predictions_dashboard.json), [grafana/track_record_dashboard.json](../grafana/track_record_dashboard.json)): six descriptions still said "7-day" after session 14 repinned the queries to 30d. **Text only — zero `rawSql` lines touched** (verified via `git diff -U0 grafana/ | grep -c rawSql` = 0), so no live SQL re-validation was needed; both files parse, tiles confirmed pinned to `horizon_days=30`.
5. **Tests: 68 passed** (61 + 7 new in [tests/test_token_trims.py](../tests/test_token_trims.py): `_first_sentence` edge cases incl. `¿…?`, summary-prompt truncation, "máximo 2 frases" present, news capped at 3 in the prompt, and 3 `_pick_macro_signal_id` cases).
6. **Docs**: PLAN (current state, session-17 Done, decision-log entry, fold-in checkboxes), PROJECT_SUMMARY (steps 6a/6c/9).

## Validation evidence

- **pytest: 68 passed** — `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`.
- **`get_active_tickers` old vs new compared live** (read-only script): 63 rows each, set-identical `(id, symbol, phase)`; `holdings ∩ watchlist` overlap count = 0.
- **Full dry-run through the real batch API** (2026-07-11 ~18:14 UTC+2, exit 0): **63 ok / 0 failed**, cost **$0.0912** vs the $0.1019–0.1063 session-16 baseline (**−11 to −14%**); usage 9.9K plain-input / 2.0K plain-output / 86.6K batch-input / 11.3K batch-output tokens. **8 flips** (down from 12 in both session-16 dry-runs; 5 of 8 — NBIS SELL→HOLD, AMPX HOLD→SELL, MU AVOID→WATCH, VWRL.AS WATCH→BUY, SOLS→WATCH — repeat session-16's consistent set), summary MIXED.
- **Dashboards**: JSON parses; no `rawSql` changes; horizon pinning verified (`horizon_days=30` on all tiles, 7/30/90/365 on the trend panels).

## Invariants (don't break)

- Never write to `stock-snapshots` tables. This repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`, `trending_tickers`, `weekly_retrospectives`.
- Keep `--dry-run` working (no DB writes; real API calls). `--force-retro` exists for off-Friday retro testing.
- Spanish in Claude prompts; English elsewhere. Claude calls return `None` on failure — **never persist placeholders** (retro included).
- **Long-term orientation (user, 2026-07-10)**: 30d headline horizon; 7d diagnostic only; prompts demand a ≥1-month thesis.
- **`get_latest_actions` must be read before any of this run's recommendation rows land** (before step 6a — it feeds both the prompts and the S17 flip detection). Shape: `{ticker_id: {"action", "held_since"}}`.
- **The "Recomendación vigente" block is omitted when `prev_action` is None** (first-ever run for a ticker).
- **The summary prompt carries only the first sentence of each reasoning** — don't "fix" it back to the full text; the full reasoning lives in the DB. `_first_sentence` must keep returning the whole string when there's no sentence break.
- **Retro "matured this week" = `generated_at + 30d` in the last 7 days**, never `evaluated_at`. Grading bands are per-horizon (`HORIZON_BANDS`); changes = user decision + re-grade.
- Grafana dashboards are **schema-v2**; edit programmatically; `timeSettings` must NOT contain `weekStart`/`nowDelay`/`quickRanges`; no `version` inside `vizConfig.spec` (valid at the `vizConfig` level).
- Batch custom_ids must be `[A-Za-z0-9_-]`. `trending_tickers.times_seen` relies on assignment order in the ON DUPLICATE KEY UPDATE clause.
- Per-session ritual: worktree + branch first → confirm task list → batch work → docs + numbered handoff → push branch (never merge `main` yourself unless asked) → print the full next prompt in chat. **Cross-check the pasted prompt against `git log`/PLAN.md before following it** — this session started with a stale (session-14) prompt and an interrupted session's uncommitted work in the worktree.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## State of play / caveats

- **`main` = `d23d466` (session 16 merged, pushed)**; session 17 is on `feat/session-17-token-trims`, pushed, **awaiting user merge**. If it merges before Mon 07-13 10:00 UTC, the Monday run carries both the flip-stability reinforcement *and* the trims — the cost line will conflate them with the batch baseline, so compare against this handoff's dry-run cost, not $0.0845.
- **Flip-stability evidence is still dry-run-only** (session 16: 12/12 flips, 8 shared, vs 18 baseline). The production answer is the flip-count trend Mon 07-13 → Fri 07-17 (panel-13 / the `Action flips vs previous run:` log line).
- **First real retrospective row lands Friday 2026-07-17**; panel-12 empty until then; panel-14 empty until Reddit creds.
- **Reddit still dark** (`grep -c '^REDDIT_' .env` = 0, 2026-07-11). Batched Reddit sentiment (last open Wave-4 item) stays gated.
- **The HANDOFF_12/16 backlog is now essentially empty**: token trims ✅, fold-ins ✅. Remaining named items: batched Reddit sentiment (gated), S6 event-driven runs (deferred), flip-stability round 2 (only if production flips stay ≥10).
- Carried: 252 pre-price_checks matured candidates ungradeable; `price_snapshots` stale since 2026-05-22; price_checks gap 06-30→07-08 permanent; 90d/365d series fill from ~2026-08-15/2027-05-17.
- **Local runs:** `env -u ANTHROPIC_API_KEY` (empty shell var shadows `.env`). Ad-hoc DB scripts: `load_dotenv('/home/guillo/Git/stock-recommendations/.env')`, env var is `DB_PASS`, add `SET collation_connection = utf8mb4_unicode_ci` as init_command when validating dashboard rawSql.

## Detailed TODO for session 18 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout (`/home/guillo/Git/stock-recommendations`): `git pull`, then `git log --oneline -3` and compare against what the prompt you were given claims — **if they disagree, the repo wins; say so to the user before doing anything**. Also run `git worktree list` and `git -C .claude/worktrees/<newest> status --short` to catch interrupted work.

**Step 1 — Merge gate for session 17.** Ask the user (AskUserQuestion) to approve merging `feat/session-17-token-trims` (prompt trims + two pure-code fold-ins + dashboard description text; no migrations, no rawSql changes; 68 tests green; dry-run evidence above). On approval, from the main checkout: `git checkout main && git merge --ff-only feat/session-17-token-trims && git push`. Best before Mon 07-13 10:00 UTC so the week's cost/flip data reflects the final prompts. **Dashboard note:** the user should re-import `predictions_dashboard.json` and `track_record_dashboard.json` from `main` after the merge (description text changed).

**Step 2 — Verify the Mon 2026-07-13 production run** (and any later ones). `gh run list --workflow=run_recommendations.yml --limit 5`; on each scheduled run's log check: 63 ok / 0 failed; the cost line (if session 17 merged, expect ≈ this handoff's dry-run cost; if not, ≈ $0.10); the `Action flips vs previous run:` count — the week's trend (vs 11 on 07-10, dry-run 12s) is the real verdict on the session-16 reinforcement: settling = counts dropping toward low single digits without same-day reversals. Record the counts in PLAN.

**Step 3 — First production retrospective (on/after Friday 2026-07-17).** After Friday's run: `gh run view <id> --log | grep -i retrospective` (expect "Generating weekly retrospective..." + the upsert line); `SELECT week_start, LEFT(retrospective, 200) FROM weekly_retrospectives;` has the week's row; the user reads digest panel-12. Its flip commentary is a second read on step 2.

**Step 4 — Check Reddit creds** (`grep -c '^REDDIT_' .env`). If >0: add the three GitHub Actions secrets, run one real cycle, verify `reddit_mentions` + `trending_tickers` fill and panel-14 renders; **batched Reddit sentiment** (the last Wave-4 item) becomes buildable and is the obvious next slice.

**Step 5 — Pick the next slice with the user** (AskUserQuestion). The committed backlog is nearly empty, so these are **suggestions for discussion, not committed work**:
1. **Store per-run cost telemetry in the DB** (new small table or a column on `daily_market_summary`): today the cost line lives only in workflow logs; persisting it enables a cost-trend dashboard panel and catches regressions (like a trim silently reverting). Cheap, self-contained.
2. **Flip-stability round 2** — only if step 2 shows flips still ≥10 with same-day reversals: stronger prompt block ("si mantuviste esta llamada menos de 5 días, NO la cambies salvo evento material") or pass the previous reasoning so the model argues against its own prior thesis.
3. **Batched Reddit sentiment** — only if step 4 found creds.
4. **Portfolio lens**: a dashboard view joining `holdings` quantities × latest prices × standing recommendations — "what does the model say about what I actually own, and what is it worth". Read-only, no pipeline changes.
5. **S6 — event-driven runs** (deferred since session 05; only if the user asks).

**Step 6 — Validate** the standard way: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q` (expect 68+); full `env -u ANTHROPIC_API_KEY .venv/bin/python -m src.main --dry-run` (63 ok / 0 failed; `--force-retro` if the retro path was touched); re-extract and run any touched dashboard rawSql with the collation init_command; migrations only with user sign-off.

**Step 7 — Close out per the ritual.** Update PLAN.md; write `handoffs/HANDOFF_18.md` with a complete copy-pasteable next prompt + a detailed TODO an older model can follow + fresh suggestions; commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_17.md and PLAN.md before doing anything — HANDOFF_17 has the detailed step-by-step TODO for session 18; follow it in order, and first cross-check this prompt's claims against git log (if they disagree, the repo wins — say so). Context: main is at d23d466 (session 16 flip-stability merged + pushed). Session 17 (2026-07-11, branch feat/session-17-token-trims, pushed NOT merged) recovered an interrupted session's work and delivered the full HANDOFF_12 token-trim backlog — the daily-summary prompt now gets only the first sentence of each reasoning (_first_sentence; full text still stored), the per-ticker reasoning instruction is "máximo 2 frases" (output = 5× input, biggest lever), news trimmed 5→3 — plus both fold-ins (get_active_tickers UNION refactor, verified live identical 63 rows; _pick_macro_signal_id preferring non-NEUTRAL macro directions, unit-tested) and 7d→30d description-drift fixes in two dashboards (text only, zero rawSql changes). Validation: pytest 68 passed; full dry-run 63 ok / 0 failed at $0.0912 vs the $0.1019–0.1063 pre-trim baseline (−11 to −14%), 8 flips consistent with session 16's. No migrations. Steps: (1) merge gate — user approval, then ff-merge session 17 to main and push, ideally before the Mon 07-13 10:00 UTC run; user re-imports predictions + track-record dashboards after; (2) verify the Mon 07-13 run and the week's flip trend (the production verdict on session 16's reinforcement — vs 11 flips on 07-10); (3) on/after Fri 07-17 verify the first production weekly retrospective (log line + weekly_retrospectives row + panel-12); (4) check Reddit creds (grep -c '^REDDIT_' .env — 0 as of 07-11). Then pick the next slice with the user from HANDOFF_17 step 5 (committed backlog is empty; suggestions: per-run cost telemetry in the DB, flip-stability round 2 only if flips stay ≥10, batched Reddit sentiment only if creds, portfolio lens dashboard). Create the session worktree + branch (feat/session-18-<slug>) once the slice is known, confirm the task list with the user, batch the work, validate (pytest expect 68+, full dry-run 63 ok, rawSql with SET collation_connection = utf8mb4_unicode_ci if dashboards touched), and close out per the ritual: update PLAN.md, write handoffs/HANDOFF_18.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push without merging, and print the full next-session prompt in the chat.
