"""Session 17: token trims (summary reasonings, reasoning cap, news lines)
and the macro→ticker non-NEUTRAL matching preference."""

import json
from types import SimpleNamespace

from src.analysis.claude_client import ClaudeClient, _first_sentence
from src.main import _pick_macro_signal_id

_SUMMARY_JSON = {"summary": "ok", "hot_tickers": [], "overall_sentiment": "NEUTRAL"}


def _stub_client(captured):
    client = ClaudeClient.__new__(ClaudeClient)
    client._usage = {
        "calls": 0, "input": 0, "output": 0,
        "batch_input": 0, "batch_output": 0,
        "cache_write": 0, "cache_read": 0,
    }

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(_SUMMARY_JSON))],
        )

    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    return client


def test_first_sentence_extraction():
    assert _first_sentence("RSI en 40. La tesis sigue intacta.") == "RSI en 40."
    assert _first_sentence("Una sola frase sin más") == "Una sola frase sin más"
    assert _first_sentence("¿Sube? No lo sé.") == "¿Sube?"
    assert _first_sentence("") == ""


def test_summary_prompt_uses_first_sentence_only():
    captured = {}
    client = _stub_client(captured)
    client.generate_daily_summary({
        "tickers_analyzed": ["AAPL"],
        "recommendations": [{
            "symbol": "AAPL", "action": "BUY", "confidence": 0.7,
            "reasoning": "Precio recuperando la SMA50 con RSI saliendo de sobreventa. "
                         "Además el sector acompaña y el volumen confirma.",
        }],
    })
    prompt = captured["messages"][0]["content"]
    assert "Precio recuperando la SMA50 con RSI saliendo de sobreventa." in prompt
    assert "Además el sector acompaña" not in prompt


def test_ticker_prompt_caps_reasoning_at_two_sentences():
    client = ClaudeClient.__new__(ClaudeClient)
    params = client._ticker_request_params(
        {"symbol": "AAPL", "phase": "WATCHLIST", "technical": {}, "sentiment": {}}, []
    )
    assert "máximo 2 frases" in params["messages"][0]["content"]


def test_ticker_prompt_trims_news_to_three():
    client = ClaudeClient.__new__(ClaudeClient)
    news = [{"title": f"Headline {i}"} for i in range(1, 6)]
    params = client._ticker_request_params(
        {"symbol": "AAPL", "phase": "WATCHLIST", "technical": {}, "sentiment": {},
         "news": news}, []
    )
    prompt = params["messages"][0]["content"]
    assert "Headline 3" in prompt
    assert "Headline 4" not in prompt


def test_pick_macro_prefers_directional_signal():
    signals = [
        {"affected_sectors": ["Tech"], "direction": {"Tech": "NEUTRAL"}},
        {"affected_sectors": ["Tech"], "direction": {"Tech": "NEGATIVE"}},
    ]
    assert _pick_macro_signal_id("Tech", signals, [10, 20]) == 20


def test_pick_macro_falls_back_to_first_match():
    signals = [
        {"affected_sectors": ["Energy"], "direction": {"Energy": "POSITIVE"}},
        {"affected_sectors": ["Tech"], "direction": {"Tech": "NEUTRAL"}},
        {"affected_sectors": ["Tech"], "direction": {}},
    ]
    assert _pick_macro_signal_id("Tech", signals, [10, 20, 30]) == 20


def test_pick_macro_none_without_sector_match():
    signals = [{"affected_sectors": ["Energy"], "direction": {"Energy": "POSITIVE"}}]
    assert _pick_macro_signal_id("Tech", signals, [10]) is None
