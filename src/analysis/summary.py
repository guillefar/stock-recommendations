import logging

from src.analysis.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


def run_daily_summary(client: ClaudeClient, analysis_data: dict) -> dict:
    """Generates the daily market summary from all collected analysis data."""
    return client.generate_daily_summary(analysis_data)
