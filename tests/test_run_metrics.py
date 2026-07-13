"""Session 24: per-run cost telemetry — the usage_snapshot accessor, the
run_metrics writer, and the main step-12 wiring (dry-run gated, fail-soft)."""

from datetime import date
from types import SimpleNamespace

import src.main as main_mod
from src.analysis.claude_client import MODEL, ClaudeClient
from src.persistence.writers import write_run_metrics

USAGE = {
    "calls": 65, "input": 20_000, "output": 4_000,
    "batch_input": 60_000, "batch_output": 9_000,
    "cache_write": 0, "cache_read": 0,
}


# ── ClaudeClient.usage_snapshot ──────────────────────────────────────────────

def _client():
    return ClaudeClient(SimpleNamespace(anthropic_api_key="test-key"))


def test_usage_snapshot_starts_zeroed_with_all_keys():
    snap = _client().usage_snapshot()
    assert snap == {
        "calls": 0, "input": 0, "output": 0,
        "batch_input": 0, "batch_output": 0,
        "cache_write": 0, "cache_read": 0,
    }


def test_usage_snapshot_is_a_copy_not_the_live_dict():
    client = _client()
    snap = client.usage_snapshot()
    snap["calls"] += 99
    assert client.usage_snapshot()["calls"] == 0


def test_usage_snapshot_reflects_recorded_usage_incl_batch_split():
    client = _client()
    client._record_usage(
        SimpleNamespace(usage=SimpleNamespace(
            input_tokens=100, output_tokens=40,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        )),
    )
    client._record_usage(
        SimpleNamespace(usage=SimpleNamespace(
            input_tokens=1000, output_tokens=200,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        )),
        batch=True,
    )
    snap = client.usage_snapshot()
    assert snap["calls"] == 2
    assert (snap["input"], snap["output"]) == (100, 40)
    assert (snap["batch_input"], snap["batch_output"]) == (1000, 200)


# ── write_run_metrics ────────────────────────────────────────────────────────

class FakeCursor:
    def __init__(self):
        self.executed = []
        self.params = []

    def execute(self, sql, params=None):
        self.executed.append(" ".join(sql.split()))
        self.params.append(params)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_run_metrics_insert_row_shape():
    cur = FakeCursor()
    write_run_metrics(FakeConn(cur), USAGE, 0.09753, tickers_ok=63, tickers_failed=0)
    assert len(cur.executed) == 1
    assert "INSERT INTO run_metrics" in cur.executed[0]
    p = cur.params[0]
    assert p[1] == MODEL
    assert p[2] == 65                       # calls
    assert (p[3], p[4]) == (20_000, 4_000)  # plain input/output
    assert (p[5], p[6]) == (60_000, 9_000)  # batched input/output (50% rate)
    assert (p[7], p[8]) == (0, 0)           # cache counters
    assert p[9] == 0.09753                  # estimated cost
    assert (p[10], p[11]) == (63, 0)        # ok / failed


def test_run_metrics_dry_run_touches_nothing():
    cur = FakeCursor()
    write_run_metrics(
        FakeConn(cur), USAGE, 0.09753, tickers_ok=63, tickers_failed=0, dry_run=True
    )
    assert cur.executed == []


# ── main step-12 wiring ──────────────────────────────────────────────────────

TICKER = {"id": 1, "symbol": "AAPL", "name": "Apple", "sector": "Tech", "phase": "WATCHLIST"}


def _run_main(monkeypatch, dry_run=False, metrics_write_raises=False):
    captured = []

    # Pin a non-Friday so the retro/patterns paths stay out of these tests.
    monkeypatch.setattr(main_mod, "_today", lambda: date(2026, 7, 6))
    monkeypatch.setattr(main_mod, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(
        main_mod, "ClaudeClient",
        lambda cfg: SimpleNamespace(
            log_usage=lambda: None,
            usage_snapshot=lambda: dict(USAGE),
            estimated_cost_usd=lambda: 0.09753,
        ),
    )
    monkeypatch.setattr(
        main_mod, "get_connection",
        lambda cfg: SimpleNamespace(ping=lambda **kw: None, close=lambda: None),
    )
    monkeypatch.setattr(main_mod, "get_active_tickers", lambda conn: [TICKER])
    monkeypatch.setattr(main_mod, "get_known_symbols", lambda conn: {"AAPL"})
    monkeypatch.setattr(main_mod, "get_latest_actions", lambda conn: {})
    monkeypatch.setattr(main_mod, "get_latest_patterns", lambda conn: None)
    monkeypatch.setattr(main_mod, "fetch_reddit_posts", lambda cfg: [])
    monkeypatch.setattr(main_mod, "fetch_macro_headlines", lambda: [])
    monkeypatch.setattr(main_mod, "fetch_prices_and_indicators", lambda s: {"price": 10.0})
    monkeypatch.setattr(main_mod, "fetch_ticker_news", lambda s: [])
    monkeypatch.setattr(main_mod, "fetch_next_earnings", lambda s: None)
    monkeypatch.setattr(main_mod, "run_macro_analysis", lambda client, headlines: [])
    monkeypatch.setattr(
        main_mod, "run_ticker_recommendations_batch",
        lambda client, items, signals, patterns=None: {
            t["symbol"]: {"action": "WATCH", "confidence": 0.5, "reasoning": "r"}
            for t in items
        },
    )
    monkeypatch.setattr(main_mod, "run_daily_summary", lambda client, data: None)
    monkeypatch.setattr(main_mod, "write_price_check", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_macro_signals", lambda conn, s, dry_run=False: [])
    monkeypatch.setattr(main_mod, "write_recommendation", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_reddit_mentions", lambda *a, **kw: None)
    monkeypatch.setattr(main_mod, "write_daily_summary", lambda *a, **kw: None)

    def fake_write_run_metrics(conn, usage, cost, tickers_ok, tickers_failed, dry_run=False):
        if metrics_write_raises:
            raise RuntimeError("DB hiccup")
        captured.append((usage, cost, tickers_ok, tickers_failed, dry_run))

    monkeypatch.setattr(main_mod, "write_run_metrics", fake_write_run_metrics)

    main_mod.main(dry_run=dry_run)
    return captured


def test_run_metrics_written_at_run_end(monkeypatch):
    captured = _run_main(monkeypatch)
    assert len(captured) == 1
    usage, cost, ok, failed, dry_run = captured[0]
    assert usage == USAGE
    assert cost == 0.09753
    assert (ok, failed) == (1, 0)
    assert dry_run is False


def test_run_metrics_forwards_dry_run(monkeypatch):
    captured = _run_main(monkeypatch, dry_run=True)
    assert len(captured) == 1
    assert captured[0][4] is True  # the writer short-circuits internally


def test_run_metrics_failure_never_kills_the_run(monkeypatch):
    # The write raising must not propagate out of main().
    captured = _run_main(monkeypatch, metrics_write_raises=True)
    assert captured == []
