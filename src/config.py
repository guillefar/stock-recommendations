import os
from dataclasses import dataclass


@dataclass
class Config:
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    db_name: str
    # Optional here so API-free entry points (evaluate_outcomes) can load config
    # without it; ClaudeClient validates it's non-empty on construction.
    anthropic_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "stock-recommendations/1.0"


def load_config() -> Config:
    return Config(
        db_host=os.environ["DB_HOST"],
        db_port=int(os.environ.get("DB_PORT", "3306")),
        db_user=os.environ["DB_USER"],
        db_pass=os.environ["DB_PASS"],
        db_name=os.environ["DB_NAME"],
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        reddit_client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
        reddit_client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
        reddit_user_agent=os.environ.get("REDDIT_USER_AGENT", "stock-recommendations/1.0"),
    )
