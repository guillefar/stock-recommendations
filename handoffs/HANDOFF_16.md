# Handoff 16 — 2026-07-11 (session 16: flip-stability prompt reinforcement)

Continues [HANDOFF_15.md](HANDOFF_15.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](../PLAN.md); structural map in [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md); design spec in [SPEC.md](../SPEC.md).

## What session 16 did

On branch **`feat/session-16-flip-stability`** (off `main` @ `6ee146c`), worktree `.claude/worktrees/session-16-flip-stability`. Pushed, **not merged**.

Session context: it ran on **Saturday 2026-07-11**, hours after session 15 closed — so HANDOFF_15's steps 2 (Mon 07-13 production run) and 3 (Friday 07-17 retrospective) were **impossible, not skipped**; they carry forward below.

1. **Step 1 confirmed**: the user imported the digest dashboard (main's copy) and all three new panels render — panel-13 shows the flip bars; panels 12/14 legitimately empty until 07-17 / Reddit creds.
2. **Step 4 checked**: Reddit creds still absent (`grep -c '^REDDIT_' .env` = 0).
3. **Slice picked with the user: flip-stability reinforcement** (the HANDOFF_15 recommendation). The user chose to act now rather than wait a week of production data — justified by 11→18 flips across 07-10/07-11 with same-day reversals and the ad-hoc retrospective's explicit recommendation.
4. **`get_latest_actions` extended** ([src/db.py](../src/db.py)): returns `{ticker_id: {"action", "held_since"}}`; `held_since` = MIN(generated_at) after the ticker's last different-action row (start of the current streak). Validated live: 63 rows, streaks 55d (stable HOLDs) down to 1d (the 07-10 churn), zero NULLs.
5. **Standing call in the ticker prompt**: [src/main.py](../src/main.py) reads `previous_actions` **before step 6a** (still before any of this run's rows land — S17 flip semantics intact, flip detection in 6c uses the same dict) and attaches `prev_action` + `prev_held_days` (`_today() - held_since.date()`) to each prepared ticker. [src/analysis/claude_client.py](../src/analysis/claude_client.py) `_ticker_request_params` renders, between the horizon block and the decision rules: *"Recomendación vigente: X (mantenida N días). Cambiarla exige nombrar en el reasoning la información nueva y material que invalida la tesis anterior (earnings/guidance, ruptura técnica sostenida, cambio macro estructural). Si no existe esa información, mantén la recomendación vigente: un movimiento de precio de pocos días es ruido, no una tesis nueva."* — omitted entirely on a ticker's first-ever run. `_RECOMMENDATION_SYSTEM` got the matching sentence ("revertir una recomendación reciente exige información nueva y material").
6. **Tests**: new [tests/test_prompt_prev_action.py](../tests/test_prompt_prev_action.py) (6 tests: block with days-held, singular "1 día", absent without prev action, prev action without held-days, system-prompt wording, main()→batch wiring with a pinned `_today`). `test_summary_flips` updated to the richer `get_latest_actions` shape. **61 passed** (was 55).
7. **Docs**: PLAN (current state, session-16 Done, decision-log entry, in-progress rewrite), PROJECT_SUMMARY (steps 6a–6c).

## Validation evidence

- **pytest: 61 passed** — `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q`.
- **New SQL validated live** (read-only): 63 rows, every row has `held_since`, streak ages sane (55d for never-flipped HOLDs; 1–2d for the 07-09/07-10 flip cohort).
- **Two consecutive full dry-runs through the real batch API** (2026-07-11 ~03:33 and ~03:36 UTC+2, both exit 0): **63 ok / 0 failed** each, cost **$0.1063 / $0.1019** (no meaningful token increase), summary MIXED both times.
- **Flip counts: 12 and 12** (baseline: 18 in the 07-11 pre-change dry-run, same stored 07-10 production actions as comparison base). **8 of 12 flips identical across both runs** — NBIS SELL→HOLD, AMPX HOLD→SELL, SMCI/MU/CLS/APLD/AVAV AVOID→WATCH, VWRL.AS WATCH→BUY — i.e. consistent theses (mostly corrections of the 07-10 spike day), not ping-pong. The 4 non-shared flips per run are WATCH→BUY entries on ETFs (borderline-entry-point variance).
- **Reasoning quality spot-check**: an ad-hoc single `analyze_ticker` call for MU (prev AVOID, held 1 day) returned WATCH with reasoning citing concrete named signals (RSI 40.4, price below SMA20, AI/SK-Hynix news, distant earnings) — the instruction shapes the reasoning rather than being ignored.
- **No dashboards or migrations touched** this session — no rawSql pass or schema changes needed.

## Invariants (don't break)

- Never write to `stock-snapshots` tables. This repo owns: `recommendations`, `daily_market_summary`, `reddit_mentions`, `macro_signals`, `recommendation_outcomes`, `price_checks`, `trending_tickers`, `weekly_retrospectives`.
- Keep `--dry-run` working (no DB writes; real API calls). `--force-retro` exists for off-Friday retro testing.
- Spanish in Claude prompts; English elsewhere. Claude calls return `None` on failure — **never persist placeholders** (retro included).
- **Long-term orientation (user, 2026-07-10)**: 30d headline horizon; 7d diagnostic only; prompts demand a ≥1-month thesis.
- **`get_latest_actions` must be read before any of this run's recommendation rows land** (now before step 6a — it feeds both the prompts and the S17 flip detection). Its return shape is `{ticker_id: {"action", "held_since"}}` — three tests stub it.
- **The "Recomendación vigente" block is omitted when `prev_action` is None** (first-ever run for a ticker) — don't make it unconditional.
- **Retro "matured this week" = `generated_at + 30d` in the last 7 days**, never `evaluated_at`. Grading bands are per-horizon (`HORIZON_BANDS`); changes = user decision + re-grade.
- Grafana dashboards are **schema-v2**; edit programmatically; `timeSettings` must NOT contain `weekStart`/`nowDelay`/`quickRanges`; no `version` inside `vizConfig.spec` (valid at the `vizConfig` level).
- Batch custom_ids must be `[A-Za-z0-9_-]`. `trending_tickers.times_seen` relies on assignment order in the ON DUPLICATE KEY UPDATE clause.
- Per-session ritual: worktree + branch first → confirm task list → batch work → docs + numbered handoff → push branch (never merge `main` yourself unless asked) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs.

## State of play / caveats

- **`main` = `6ee146c`**; session 16 is on `feat/session-16-flip-stability`, pushed, **awaiting user merge**. Until it merges, production runs use the pre-reinforcement prompt — merge before Mon 07-13 if the user wants the first production data point to carry it.
- **Flip-stability evidence so far is dry-run-only** (12/12 with 8 shared, vs 18 baseline). The real test is panel-13 over the production week after merge: expect the count to drift below ~10 as the 07-10 churn cohort's corrections settle into streaks.
- **First real retrospective row lands Friday 2026-07-17**; panel-12 empty until then; panel-14 empty until Reddit creds.
- **Reddit still dark** (`grep -c '^REDDIT_' .env` = 0, 2026-07-11). Batched Reddit sentiment (last open Wave-4 item) stays gated.
- Remaining backlog: token trims (HANDOFF_12: first-sentence-only reasonings into the summary prompt ~−3K tokens, 2-sentence reasoning cap since output is 5× input, fewer news lines), fold-in cleanups (`get_active_tickers` UNION refactor; macro→ticker matching preferring non-NEUTRAL signals), S6 event-driven runs (deferred).
- Carried: 252 pre-price_checks matured candidates ungradeable; `price_snapshots` stale since 2026-05-22; price_checks gap 06-30→07-08 permanent; 90d/365d series fill from ~2026-08-15/2027-05-17.
- **Local runs:** `env -u ANTHROPIC_API_KEY` (empty shell var shadows `.env`). Ad-hoc DB scripts: `load_dotenv('/home/guillo/Git/stock-recommendations/.env')`, env var is `DB_PASS`, add `SET collation_connection = utf8mb4_unicode_ci` as init_command when validating dashboard rawSql.

## Detailed TODO for session 17 (step-by-step; follow in order)

**Step 0 — Orient.** Read this file and [PLAN.md](../PLAN.md). From the main checkout: `git pull`. If session 16 is already merged, skip to step 2. Create the session worktree only once you know the slice (step 5): `git worktree add .claude/worktrees/session-17-<slug> -b feat/session-17-<slug> main`, then inside it `ln -sf /home/guillo/Git/stock-recommendations/.env .env && ln -sf /home/guillo/Git/stock-recommendations/.venv .venv`.

**Step 1 — Merge gate for session 16.** Ask the user to review/approve `feat/session-16-flip-stability` (prompt-only + db-query change, no migrations, no dashboard edits). On approval: `git checkout main && git merge --ff-only feat/session-16-flip-stability && git push`. It should land **before Mon 07-13 10:00 UTC** so the first production data point carries the reinforcement.

**Step 2 — Verify the Mon 2026-07-13 production run.** `gh run list --workflow=run_recommendations.yml --limit 3`; on the scheduled run check: cost line ~$0.10, `Action flips vs previous run:` count (the headline number — compare against 11 on 07-10 and the dry-run 12s), zero yfinance 404 lines, summary tone long-term. Record the flip count in PLAN. Repeat for any further runs that have happened (Tue–Thu): the flip trend across the week is the actual answer to "did the reinforcement work" — settling means counts dropping toward low single digits with flips that don't reverse the previous day's.

**Step 3 — First production retrospective (if on/after Friday 2026-07-17).** After Friday's run: `gh run view <id> --log | grep -i retrospective` shows "Generating weekly retrospective..." + the upsert line; `SELECT week_start, LEFT(retrospective, 200) FROM weekly_retrospectives` has the week's row; the user reads panel-12. This retrospective covers the week where the reinforcement landed — its flip commentary is a second read on step 2.

**Step 4 — Check Reddit creds** (`grep -c '^REDDIT_' .env`). If >0: add the three GitHub Actions secrets, run one real cycle, verify `reddit_mentions` + `trending_tickers` fill and panel-14 renders; batched Reddit sentiment becomes buildable.

**Step 5 — Pick the next slice with the user** (AskUserQuestion). Ranked suggestions (fresh):
1. **Token trims** (HANDOFF_12 backlog; cost is a declared priority): send only the first sentence of each reasoning to the summary prompt (~−3K input tokens/run), cap ticker reasoning at 2 sentences (output tokens are 5× input — biggest lever), trim news to 3 lines. Validate cost delta with a dry-run before/after (~$0.10 baseline).
2. **Flip-stability round 2** — only if step 2 shows the count still ≥10 with same-day reversals: options are a stronger block (e.g. explicit "si mantuviste esta llamada menos de 5 días, NO la cambies salvo evento material") or passing the previous reasoning summary so the model argues against its own prior thesis.
3. **Batched Reddit sentiment** — only if step 4 found creds.
4. **Fold-ins**: `get_active_tickers` UNION refactor, macro→ticker matching prefers non-NEUTRAL signals.
5. **S6 — event-driven runs** (deferred since session 05; only if the user asks).

**Step 6 — Validate** the standard way: `env -u ANTHROPIC_API_KEY .venv/bin/python -m pytest tests/ -q` (expect 61+); full `env -u ANTHROPIC_API_KEY .venv/bin/python -m src.main --dry-run` (63 ok / 0 failed, ~$0.10; `--force-retro` if the retro path was touched); re-extract and run any touched dashboard rawSql with the collation init_command; migrations only with user sign-off.

**Step 7 — Close out per the ritual.** Update PLAN.md; write `handoffs/HANDOFF_17.md` with a complete copy-pasteable next prompt + a detailed TODO an older model can follow + fresh suggestions; commit; push the branch (no merge unless asked); print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read handoffs/HANDOFF_16.md and PLAN.md before doing anything — HANDOFF_16 has the detailed step-by-step TODO for session 17; follow it in order. Context: session 16 (2026-07-11, Saturday) delivered flip-stability prompt reinforcement on feat/session-16-flip-stability — pushed, NOT merged, awaiting user review. The change: get_latest_actions now also returns each action's streak start (held_since); main reads it before step 6a and passes prev_action + prev_held_days into every prepared ticker; the per-ticker prompt shows "Recomendación vigente: X (mantenida N días)" and requires naming material new information in the reasoning to reverse it (omitted on first-ever runs); the system prompt got matching wording. Evidence: two consecutive dry-runs gave 12 flips each with 8/12 identical across runs (consistent theses, mostly corrections of the 07-10 churn cohort) vs the 18-flip ping-pong baseline; costs $0.1063/$0.1019; pytest 61 passed; the new SQL validated live (63 rows, streaks 55d down to 1d). No migrations or dashboard changes. Steps: (1) merge gate — get user approval and ff-merge session 16 to main BEFORE the Mon 07-13 10:00 UTC run so production carries the reinforcement; (2) verify the Mon 07-13 run and any later ones (cost ~$0.10, the "Action flips vs previous run:" count vs 11 on 07-10 — the week's trend answers whether the reinforcement worked); (3) if it's on/after Fri 07-17, verify the first production weekly retrospective (log line + weekly_retrospectives row + panel-12, user reads it); (4) check Reddit creds (grep -c '^REDDIT_' .env — 0 as of 07-11). Then pick the next slice with the user: token trims (HANDOFF_12 — top recommendation, cost is a priority: first-sentence-only reasonings to the summary prompt, 2-sentence reasoning cap, fewer news lines), flip-stability round 2 (only if flips stay ≥10 with same-day reversals), batched Reddit sentiment (only if creds), or fold-in cleanups. Create the session worktree + branch (feat/session-17-<slug>) once the slice is known, confirm the task list with the user, batch the work, validate (pytest expect 61+, full dry-run 63 ok ~$0.10, rawSql with SET collation_connection = utf8mb4_unicode_ci if dashboards touched), and close out per the ritual: update PLAN.md, write handoffs/HANDOFF_17.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push without merging, and print the full next-session prompt in the chat.
