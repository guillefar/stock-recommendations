# Session Handoff

Read this first when starting a new Claude Code session on this repo.

## Where you are

- **Repo**: `/home/guillo/Git/stock-recommendations`
- **User**: Guillermo (email: mail.agustinf@gmail.com)
- **Main branch**: `main`. Currently no remote tracking is enforced — confirm before pushing.
- **You are**: Claude Code (Opus 4.7) running inside VSCode.

## What this project is — in one paragraph

A Python pipeline that runs on GitHub Actions cron, reads the active stock portfolio from a MySQL DB owned by a sibling project (`stock-snapshots`), gathers yfinance technicals + `/r/stocks` posts + RSS macro headlines, asks Claude Haiku 4.5 for per-ticker BUY/SELL/HOLD/WATCH/AVOID recommendations and a daily summary, and writes results to four owned tables. See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for the structural map and [SPEC.md](SPEC.md) for design rationale.

## How to orient yourself

Read in this order (≈ 10 minutes total):

1. [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) — what the modules are and how they wire together.
2. [PLAN.md](PLAN.md) — **canonical source of current state, in-progress work, TODOs, and decisions log.** Update this when work progresses.
3. [SPEC.md](SPEC.md) — original design spec; treat as immutable (don't rewrite, but flag if reality has drifted).
4. `git log --oneline -10` — last few commits.

After that, open whatever module you're touching.

## What was done in the last session (2026-06-06)

- Created [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md), [PLAN.md](PLAN.md), and this file.
- **Applied "fix B"**: rewrote [src/collectors/reddit.py](src/collectors/reddit.py) to use Reddit's public `.json` endpoint instead of RSS. The RSS feed exposes neither `score` nor `upvote_ratio`, which silently killed `find_trending_unknown` (score>100 filter never matched), zeroed every recommendation's `sentiment.avg_score`, and made the daily-summary `top_posts` sort meaningless. The JSON endpoint provides both, and the new code re-applies the SPEC filter (`score >= 50` and `upvote_ratio >= 0.7`).
- Removed `feedparser` import from `reddit.py`; it's still needed by `collectors/news.py` so it stays in `requirements.txt`.
- Kept the `cfg: Config` parameter on `fetch_reddit_posts` (unused) to avoid touching `main.py` and to leave the door open for a PRAW fallback.

**The fix has not been validated against a live run.** Highest-priority next step.

## Key risks / things to verify

- **Reddit `.json` may 403 from GitHub Actions IPs.** Reddit has been aggressively blocking unauthenticated datacenter requests in 2024–2025. The RSS feed worked specifically because of this. If CI logs show `Reddit JSON fetch failed`, the documented fallback is to restore PRAW with new `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` secrets — see [PLAN.md](PLAN.md).
- The local Python is 3.14; CI pins 3.11. `datetime.utcnow()` calls in `writers.py` (and previously `reddit.py`) trigger DeprecationWarning locally — still on the medium-priority TODO list.
- The Grafana dashboard JSON was committed with no provisioning instructions and no commit message context.

## Repo invariants

- **Never modify `stock-snapshots` tables or SPs.** This project is read-only against `tickers`, `holdings`, `watchlist`, `transactions`, `price_snapshots`.
- Direct code, few abstractions. No defensive try/except around internal code (only at external boundaries).
- `--dry-run` flag must keep working — it's the only safe way to test against the production DB.
- All Claude outputs are strict JSON; the parser in `claude_client._parse_json` is the only place that handles formatting variance.

## Persistent memory

Project memories at `~/.claude/projects/-home-guillo-Git-stock-recommendations/memory/` already capture project-overview and state. Re-read them but **verify before acting** on any factual claim (file paths, "is broken") — git may have moved on since they were written.

## Conventions in this repo

- File references in chat use markdown links: `[file.py:42](src/file.py#L42)`.
- Spanish is used in some user-facing prompts (Claude system prompts) and a few code comments; English in everything else.
- The user prefers concrete, scoped suggestions over a wall of options; recommend, then offer to implement.

## Session-bootstrap prompt

Paste this into the next session to load context:

> Read `HANDOFF.md` at the root of this repo (`/home/guillo/Git/stock-recommendations`) and follow its "How to orient yourself" section. Then ask me what to work on. Don't make changes yet.
