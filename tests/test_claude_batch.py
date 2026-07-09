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
