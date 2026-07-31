import json
from types import SimpleNamespace

from src.analysis.claude_client import ClaudeClient
from src.config import Config


def _client() -> ClaudeClient:
    cfg = Config(
        db_host="x", db_port=3306, db_user="x", db_pass="x", db_name="x",
        anthropic_api_key="test-key",
    )
    return ClaudeClient(cfg)


def _message(payload: dict, input_tokens: int = 100, output_tokens: int = 50):
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


class _FakeBatches:
    """messages.batches stub: create → ended on first retrieve → canned results."""

    def __init__(self, entries):
        self._entries = entries
        self.created_requests = None

    def create(self, requests):
        self.created_requests = requests
        return SimpleNamespace(id="batch_1", processing_status="in_progress")

    def retrieve(self, batch_id):
        return SimpleNamespace(
            id=batch_id,
            processing_status="ended",
            request_counts=SimpleNamespace(
                succeeded=1, errored=1, canceled=0, expired=0
            ),
        )

    def results(self, batch_id):
        return iter(self._entries)


TICKERS = [
    {"id": 1, "symbol": "AAPL", "phase": "WATCHLIST", "technical": {}, "sentiment": {}},
    {"id": 2, "symbol": "XESC.DE", "phase": "HOLDING", "technical": {}, "sentiment": {}},
]


def _patch(client, entries):
    fake = _FakeBatches(entries)
    client._client = SimpleNamespace(messages=SimpleNamespace(batches=fake))
    return fake


def test_batch_maps_results_by_symbol_and_handles_errors():
    client = _client()
    fake = _patch(client, [
        SimpleNamespace(
            custom_id="t0",
            result=SimpleNamespace(
                type="succeeded",
                message=_message({"action": "BUY", "confidence": 0.7, "reasoning": "ok"}),
            ),
        ),
        SimpleNamespace(custom_id="t1", result=SimpleNamespace(type="errored")),
    ])

    results = client.analyze_tickers_batch(TICKERS, macro_signals=[])

    # Dotted symbols can't be custom_ids — requests must be keyed t<index>.
    assert [r["custom_id"] for r in fake.created_requests] == ["t0", "t1"]
    assert results["AAPL"]["action"] == "BUY"
    assert results["XESC.DE"] is None  # errored entry → None, caller counts a failure


def test_batch_coerces_out_of_set_action_per_phase():
    client = _client()
    _patch(client, [
        SimpleNamespace(
            custom_id="t1",
            result=SimpleNamespace(
                type="succeeded",
                # BUY is out-of-set for HOLDING → must coerce to HOLD
                message=_message({"action": "BUY", "confidence": 0.5, "reasoning": "x"}),
            ),
        ),
    ])

    results = client.analyze_tickers_batch(TICKERS, macro_signals=[])
    assert results["XESC.DE"]["action"] == "HOLD"
    assert results["AAPL"] is None  # no entry returned for t0


def test_batch_usage_billed_at_half_rate():
    client = _client()
    _patch(client, [
        SimpleNamespace(
            custom_id="t0",
            result=SimpleNamespace(
                type="succeeded",
                message=_message(
                    {"action": "WATCH", "confidence": 0.5, "reasoning": "x"},
                    input_tokens=1_000_000, output_tokens=1_000_000,
                ),
            ),
        ),
    ])

    client.analyze_tickers_batch(TICKERS[:1], macro_signals=[])
    # Haiku list: $1 in + $5 out per MTok → $6 plain, $3 at the batch discount.
    assert abs(client.estimated_cost_usd() - 3.0) < 1e-9


def test_empty_ticker_list_makes_no_api_call():
    client = _client()
    fake = _patch(client, [])
    assert client.analyze_tickers_batch([], macro_signals=[]) == {}
    assert fake.created_requests is None


# ── Session 26: timeout no longer discards a whole run ────────────────────────
# 2 of 8 scheduled runs (2026-07-17, 07-27) hit the old 45-min deadline; the
# client canceled and returned None for all 63 tickers, so a slow batch cost
# the entire run. Cancellation preserves already-completed requests — they just
# aren't retrievable until the batch reaches "ended".


class _SlowBatches:
    """A batch that never ends on its own; cancellation settles it after N polls."""

    def __init__(self, entries, polls_before_settling=1, ever_settles=True):
        self._entries = entries
        self._polls_before_settling = polls_before_settling
        self._ever_settles = ever_settles
        self.canceled = False
        self.polls_after_cancel = 0

    def create(self, requests):
        return SimpleNamespace(id="batch_slow", processing_status="in_progress")

    def cancel(self, batch_id):
        self.canceled = True

    def retrieve(self, batch_id):
        if not self.canceled:
            return SimpleNamespace(id=batch_id, processing_status="in_progress")
        self.polls_after_cancel += 1
        settled = (
            self._ever_settles
            and self.polls_after_cancel >= self._polls_before_settling
        )
        return SimpleNamespace(
            id=batch_id,
            processing_status="ended" if settled else "canceling",
            request_counts=SimpleNamespace(
                succeeded=1, errored=0, canceled=1, expired=0
            ),
        )

    def results(self, batch_id):
        return iter(self._entries)


def _force_timeout(monkeypatch):
    """Makes the deadline expire immediately and sleeps free."""
    monkeypatch.setattr("src.analysis.claude_client.BATCH_DEADLINE_SECONDS", -1)
    monkeypatch.setattr("src.analysis.claude_client.BATCH_POLL_SECONDS", 0)
    monkeypatch.setattr("src.analysis.claude_client.time.sleep", lambda _s: None)


def test_timeout_harvests_completed_requests_instead_of_losing_them(monkeypatch):
    _force_timeout(monkeypatch)
    client = _client()
    fake = _SlowBatches([
        SimpleNamespace(
            custom_id="t0",
            result=SimpleNamespace(
                type="succeeded",
                message=_message({"action": "BUY", "confidence": 0.8, "reasoning": "ok"}),
            ),
        ),
    ])
    client._client = SimpleNamespace(messages=SimpleNamespace(batches=fake))

    results = client.analyze_tickers_batch(TICKERS, macro_signals=[])

    assert fake.canceled  # the wedged batch is still canceled
    # ...but the request that finished before the cancel is recovered.
    assert results["AAPL"]["action"] == "BUY"
    assert results["XESC.DE"] is None  # genuine straggler


def test_timeout_falls_back_to_all_none_if_cancel_never_settles(monkeypatch):
    _force_timeout(monkeypatch)
    monkeypatch.setattr("src.analysis.claude_client.BATCH_CANCEL_GRACE_SECONDS", -1)
    client = _client()
    fake = _SlowBatches([], ever_settles=False)
    client._client = SimpleNamespace(messages=SimpleNamespace(batches=fake))

    results = client.analyze_tickers_batch(TICKERS, macro_signals=[])

    assert fake.canceled
    assert results == {"AAPL": None, "XESC.DE": None}


def test_batch_deadline_fits_inside_the_workflow_job_timeout():
    # The workflow's timeout-minutes must exceed the batch budget or the job is
    # killed mid-poll and nothing is persisted at all.
    from pathlib import Path

    from src.analysis.claude_client import (
        BATCH_CANCEL_GRACE_SECONDS,
        BATCH_DEADLINE_SECONDS,
    )

    wf = Path(__file__).resolve().parents[1] / ".github/workflows/run_recommendations.yml"
    line = next(
        l for l in wf.read_text().splitlines() if "timeout-minutes:" in l
    )
    job_minutes = int(line.split(":", 1)[1].strip())
    budget_minutes = (BATCH_DEADLINE_SECONDS + BATCH_CANCEL_GRACE_SECONDS) / 60
    assert job_minutes > budget_minutes + 10  # headroom for collection + weekly steps
