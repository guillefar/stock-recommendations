"""Session 14: the per-ticker prompt frames a long-term (≥1 month) horizon."""

from src.analysis.claude_client import _RECOMMENDATION_SYSTEM, ClaudeClient
from src.config import Config


def _client() -> ClaudeClient:
    cfg = Config(
        db_host="x", db_port=3306, db_user="x", db_pass="x", db_name="x",
        anthropic_api_key="test-key",
    )
    return ClaudeClient(cfg)


def test_system_prompt_frames_long_term_investor():
    assert "largo plazo" in _RECOMMENDATION_SYSTEM
    assert "meses o años" in _RECOMMENDATION_SYSTEM


def test_ticker_prompt_has_horizon_block():
    params = _client()._ticker_request_params(
        {"id": 1, "symbol": "AAPL", "phase": "WATCHLIST", "technical": {}, "sentiment": {}},
        macro_signals=[],
    )
    prompt = params["messages"][0]["content"]
    assert "Horizonte de inversión: mínimo un mes" in prompt
    # Short-term indicators are timing inputs, not the thesis.
    assert "timing de entrada/salida" in prompt
    assert "tesis al horizonte de 1+ mes" in prompt
