import logging

from src.analysis.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


def run_daily_summary(client: ClaudeClient, analysis_data: dict) -> dict | None:
    """Generates the daily market summary. None on failure — don't persist."""
    return client.generate_daily_summary(analysis_data)
