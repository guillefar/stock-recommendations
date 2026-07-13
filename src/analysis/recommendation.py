import logging

from src.analysis.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


def run_ticker_recommendation(
    client: ClaudeClient,
    ticker_data: dict,
    macro_signals: list[dict],
    patterns: list[dict] | None = None,
) -> dict | None:
    """Generates a BUY/SELL/HOLD/WATCH/AVOID recommendation for a single ticker.

    Returns None when Claude's response can't be parsed — nothing should be persisted.
    `patterns` is the gated mined pattern set (session 25); None/[] omits the block.
    """
    return client.analyze_ticker(ticker_data, macro_signals, patterns)


def run_ticker_recommendations_batch(
    client: ClaudeClient,
    ticker_items: list[dict],
    macro_signals: list[dict],
    patterns: list[dict] | None = None,
) -> dict[str, dict | None]:
    """Batch variant used by the daily run (Message Batches API, 50% cost).

    Returns {symbol: recommendation}; None entries mean that ticker failed and
    nothing should be persisted for it. `patterns` is run-global like
    macro_signals: the gated mined pattern set injected into every prompt.
    """
    return client.analyze_tickers_batch(ticker_items, macro_signals, patterns)
