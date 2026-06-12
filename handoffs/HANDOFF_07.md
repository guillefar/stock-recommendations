# Handoff 07 — 2026-06-12 (session 07)

Continues [HANDOFF_06.md](HANDOFF_06.md). Evergreen orientation in [HANDOFF.md](HANDOFF.md); rolling status/roadmap in [PLAN.md](PLAN.md); structural map in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); design spec in [SPEC.md](SPEC.md).

## What session 07 did — D3 panel + Wave 2 first half

Branch **`feat/session-07-d3-wave-2`** (off `main` @ `881038d`), in worktree `.claude/worktrees/session-07-d3-wave-2`. Pushed, **not merged** — merging is the user's call and the first gate for next session.

1. **Merge gate cleared + post-merge verification.** `feat/session-06-wave-1-5` was merged to `main` (`881038d`) before the session. DB checks: `price_checks` had only 2026-06-12's 63 rows (session 06's local run — the cron hadn't fired since the merge at check time); `recommendation_outcomes` still 693 (expected; post-merge recs mature at 7d). **Anomaly chased and resolved:** recommendations are 63/day, not the expected 126/day — because the 2×/day schedule (`0 14` + `0 20` UTC in [.github/workflows/run_recommendations.yml](.github/workflows/run_recommendations.yml)) only reached `main` around 2026-06-12. `gh run list` shows exactly one scheduled run per weekday, all ~13:30–16:30 UTC (the 14:00 cron + GitHub's usual delay), every one successful. **Nothing is broken**; 2026-06-12 is the first day both crons run, and the first day cron-driven `price_checks` accumulate.
2. **D3 — confidence-calibration panel** (panel-11, "Hit Rate by Confidence Band (D3)") added to [grafana/daily_digest_dashboard.json](grafana/daily_digest_dashboard.json), schema v2, GridLayoutItem at y=72. Bands `< 0.40` / `0.40–0.59` / `0.60–0.79` / `0.80+` — the 4th band was added beyond the HANDOFF_06 draft because real confidences go down to 0.25 (the draft's `ELSE` branch would have mislabeled 40 rows). Columns: band, action (color-mapped like the other panels), total, correct, incorrect, neutral, hit rate % (correct/decided, NEUTRAL excluded — same definition as panel-7; color-background red <40 / yellow 40–60 / green ≥60). Query validated against the live DB **before** insertion; the JSON diff was purely additive (+203 lines). Current data already shows monotone calibration for WATCH: **59% → 69% → 80%** across rising bands.
3. **Wave 2 item 1 — ticker news in the prompt.** [src/main.py](src/main.py) now calls `fetch_ticker_news(symbol)[:5]` per ticker (inside the per-ticker try, after the price check) and passes `news` in `ticker_data`; `analyze_ticker` in [src/analysis/claude_client.py](src/analysis/claude_client.py) renders a Spanish "Noticias recientes del ticker:" block (titles only), **omitted entirely** when there are no titles.
4. **Wave 2 item 2 — earnings awareness.** New `fetch_next_earnings` + pure helper `_pick_next_earnings` in [src/collectors/prices.py](src/collectors/prices.py): reads yfinance `Ticker.calendar` (handles both the dict and DataFrame schemas), normalizes datetime/pd.Timestamp, picks the earliest date ≥ today, returns `'YYYY-MM-DD'` or None on anything unexpected. Prompt line: "Próximo reporte de earnings: … — si es inminente, considera el riesgo del evento en la acción y el confidence.", omitted when unknown.
5. **Tests.** New [tests/test_prices.py](tests/test_prices.py): 5 tests for `_pick_next_earnings` (earliest-future pick, today counts as upcoming, stale/empty calendar → None, datetime+Timestamp normalization, garbage values tolerated).

## Validation evidence

- pytest: **9/9 pass** (4 outcomes + 5 prices).
- Full `src.main --dry-run`: **63 ok / 0 failed**, exit 0, no writes (all writers logged `[dry-run]`).
- Live collector smoke test: AAPL → 5 headlines + earnings `2026-07-30`; XESC.DE (ETF) → no calendar, degrades to None.
- Prompt assembly verified with a stubbed Anthropic client: with news+earnings both blocks render between the Reddit and macro sections; with neither, the prompt is byte-identical in that region to the pre-Wave-2 prompt (asserted `Noticias`/`earnings` absent).
- D3 SQL run against the live DB before panel insertion (6 band×action rows, sensible numbers).

## State of play / caveats

- **`feat/session-07-d3-wave-2` pushed, not merged.** The cron runs `main`, so news/earnings don't reach production prompts until the user merges. Merging is step 1 of next session.
- **First post-merge cron runs happen 2026-06-12** (14:00 + 20:00 UTC). Expect `price_checks` ≈ 63/day (weekdays) from then on; if the 20:00 run writes, recs jump to ~126/day and D1 (same-day disagreements) can finally populate.
- New recommendations become gradeable at 7d from **~2026-06-19**; `recommendation_outcomes` should then grow past 693.
- **Cosmetic log noise:** for tickers without fundamentals (the ~13 ETFs), yfinance's *internal* logger emits `ERROR yfinance — HTTP Error 404: … No fundamentals data found` on the calendar lookup. Our code catches everything and degrades; the line is harmless but looks alarming in cron logs (see S13).
- The 252 pre-price_checks matured candidates and the pre-fix NULL-entry-price European-ETF recs remain permanently ungradeable (accepted; S11 could recover the latter).
- **Reddit is still dark** — `.env` has none of `REDDIT_CLIENT_ID/SECRET/USER_AGENT` (checked this session). https://www.reddit.com/prefs/apps, "script" app; also add the three GitHub Actions secrets.

## Invariants (don't break)

- Never write to `stock-snapshots` tables (read-only). Tables this repo owns: `recommendation_outcomes`, `price_checks`.
- Keep `--dry-run` working (no DB writes).
- Spanish in Claude prompts; English elsewhere.
- Grafana dashboards must be **schema-v2** (`elements`/`layout`) — classic schema fails import on the user's Grafana 13.1.x.
- Per-session ritual: **worktree + branch first** → confirm task list → batch work → close with docs + numbered handoff (complete next prompt, detailed TODO an older model can follow, fresh suggestions) → push the branch (never merge to `main` yourself) → print the full next prompt in chat.
- **Communication:** the user only sees the turn's *final* message and AskUserQuestion dialogs — put any explanation they must read inside the question text/options or in the final message, never in mid-turn text.

## Suggestions (fresh, for discussion; NOT committed work)

- **S13 — silence yfinance's internal 404 ERROR lines (trivial).** `logging.getLogger("yfinance").setLevel(logging.CRITICAL)` once in main (or only around the calendar call) stops the ~13 scary-but-harmless ERROR lines per run. Trade-off: hides real yfinance errors too — our own collectors already log their own warnings, so little is lost.
- **S14 — persist the news shown to the model (small).** Reasoning can now cite headlines, but they aren't stored anywhere — a rec that says "por las noticias de X" can't be audited later. Cheap fix: include `news` titles in the `sentiment` JSON column (or a new column) in `write_recommendation`.
- **S12 — price_checks gap-fill (carried, more relevant now).** If the cron skips days, exit prices vanish for those horizons. A step in `evaluate_outcomes` could backfill missing daily closes from yfinance history into `price_checks`.
- **S11 — backfill NULL entry prices (carried).** One-off script to patch `technical.$.price` for old European-ETF recs from historical closes; recovers hundreds of gradeable rows.
- **S7 — prompt/model provenance columns (carried).** Now *more* valuable: Wave 2 just changed the prompt, so pre/post comparisons of hit-rate are otherwise confounded.
- **S8 — per-run daily summaries (carried).** The per-day upsert still loses the morning run's sentiment; pairs with D1 once 2 runs/day exist.

## Detailed TODO for session 08 (step-by-step; follow in order)

**Step 0 — Orient.** Read [HANDOFF_07.md](HANDOFF_07.md) (this file) and [PLAN.md](PLAN.md) completely. Session 08 scope: **post-merge + cron verification, then finish Wave 2** (action-set-per-phase constraint + structured JSON output).

**Step 1 — Merge gate.** Ask the user to confirm `feat/session-07-d3-wave-2` is merged to `main` (or to merge it now — never merge yourself). If it isn't, stop and resolve that first.

**Step 2 — Workspace.** From the main checkout: `git checkout main && git pull`. Then `git worktree add .claude/worktrees/session-08-<topic> -b feat/session-08-<topic> main`, and inside it:
```bash
ln -s /home/guillo/Git/stock-recommendations/.env .env
ln -s /home/guillo/Git/stock-recommendations/.venv .venv
```
Confirm the session task list with the user. Re-check Reddit creds: `grep -c '^REDDIT_' .env` (0 as of session 07).

**Step 3 — Cron verification (read-only).** Now that both crons run the new code:
```sql
SELECT as_of_date, COUNT(*) FROM price_checks GROUP BY as_of_date ORDER BY as_of_date DESC LIMIT 7;     -- expect ~63/weekday from 2026-06-12
SELECT DATE(generated_at) d, HOUR(generated_at) h, COUNT(*) FROM recommendations
  WHERE generated_at >= '2026-06-12' GROUP BY d, h ORDER BY d DESC, h;                                   -- expect TWO buckets/day (~14 & ~20 UTC)
SELECT COUNT(*) FROM recommendation_outcomes;                                                            -- >693 once recs from 2026-06-12+ mature (~06-19)
```
Also `gh run list --workflow=run_recommendations.yml --limit 10` — confirm two scheduled runs/day appear and succeed. If the 20:00 cron still never fires, investigate (workflow file on main? GitHub skipping?) before building anything new. Check whether D1 (panel-9) now shows same-day disagreements.

**Step 4 — Wave 2 item 3: constrain action set per phase.** HOLDING → {HOLD, SELL}; WATCHLIST → {BUY, WATCH, AVOID}. Two halves: (a) tighten the prompt wording in `analyze_ticker` (the rules text already implies it; make the JSON schema line state the allowed set for the ticker's phase); (b) post-validate in [src/main.py](src/main.py) or claude_client: if the returned action is outside the phase's set, coerce to the nearest valid one (define the mapping explicitly, e.g. HOLDING: BUY→HOLD, WATCH→HOLD, AVOID→SELL; WATCHLIST: HOLD→WATCH, SELL→AVOID) and **log the coercion** with both values. Add unit tests for the coercion function (pure).

**Step 5 — Wave 2 item 4: structured JSON output.** Replace `_parse_json` string-stripping with the API's structured/tool-use output so malformed JSON becomes impossible. **Read the `/claude-api` skill first** for the current recommended mechanism (tool-use forced choice vs response_format). Keep `analyze_ticker` returning `None` on failure (no fake fallbacks). While in there, sanity-check whether the tiny system prompts even reach the cacheable minimum (likely not → drop or restructure `cache_control`).

**Step 6 — Validate.** `.venv/bin/python -m pytest tests/ -q`; full `.venv/bin/python -m src.main --dry-run` (63 ok expected; prompts/parsing changed, so check several logged actions and confidences look sane, and that no coercion fires unexpectedly often). No real run needed (cron covers it).

**Step 7 — Close out.** Update PLAN.md (check off Wave 2 items 3–4, refresh Current state, decisions log for the coercion mapping). Write HANDOFF_08.md: what was done, validation evidence, complete copy-pasteable next prompt, detailed TODO an older model can follow, fresh suggestions. Commit, push the branch (no merge), print the full next prompt in chat.

## Prompt for the next session (copy-paste exactly)

> Read HANDOFF_07.md and PLAN.md before doing anything — HANDOFF_07 contains the detailed step-by-step TODO for this session (session 08); follow it in order. Context: session 07 completed the D3 confidence-calibration panel (panel-11, 4 bands, hit-rate = correct/decided; WATCH already calibrates 59→69→80%) and the first half of Wave 2 on branch feat/session-07-d3-wave-2 (pushed, NOT merged): ticker news (top 5 yfinance headlines) and next-earnings-date now ride into the per-ticker prompt as optional Spanish blocks omitted when empty; pytest 9/9, dry-run 63 ok / 0 failed. Post-merge verification found the 63-vs-126 recs/day "anomaly" is just the 2×/day cron schedule having only reached main on 2026-06-12 — nothing broken. First confirm with me that I merged feat/session-07-d3-wave-2 to main — news/earnings don't reach production prompts until then. Then create the session worktree + branch and confirm the task list with me. Session 08 scope: verify the cron now writes price_checks daily AND two recommendation batches/day (~14 & ~20 UTC; investigate if the 20:00 cron never fires), check whether outcomes grew past 693 (recs from 2026-06-12 mature ~06-19) and whether D1 finally shows disagreements, then finish Wave 2: constrain the action set per phase (HOLDING→{HOLD,SELL}, WATCHLIST→{BUY,WATCH,AVOID}; prompt wording + post-validation coercion with explicit mapping, logged, unit-tested) and switch to structured/tool-use JSON output instead of _parse_json string-stripping (read the /claude-api skill first; keep None-on-failure; also sanity-check the cache_control no-op on tiny system prompts). Validate with pytest and a full --dry-run; no real run needed (cron covers it). Also check whether I added the Reddit credentials yet. Close out per the ritual: update PLAN.md, write HANDOFF_08.md with the complete next prompt + a detailed TODO an older model can follow + fresh suggestions, push the branch without merging, and print the full next-session prompt in the chat.
