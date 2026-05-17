import logging

from src.analysis.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


def run_macro_analysis(client: ClaudeClient, headlines: list[dict]) -> list[dict]:
    """Runs macro analysis on RSS headlines. Returns a list of macro signal dicts."""
    if not headlines:
        logger.info("No headlines to analyze")
        return []
    signals = client.analyze_macro(headlines)
    logger.info(f"Macro analysis detected {len(signals)} signals")
    return signals
