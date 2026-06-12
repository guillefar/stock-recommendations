import logging

from src.analysis.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


def run_ticker_recommendation(
    client: ClaudeClient,
    ticker_data: dict,
    macro_signals: list[dict],
) -> dict | None:
    """Generates a BUY/SELL/HOLD/WATCH/AVOID recommendation for a single ticker.

    Returns None when Claude's response can't be parsed — nothing should be persisted.
    """
    return client.analyze_ticker(ticker_data, macro_signals)
