import os
from dataclasses import dataclass, field


@dataclass
class Config:
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    db_name: str
    anthropic_api_key: str
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str
    dry_run: bool = False


def load_config() -> Config:
    return Config(
        db_host=os.environ["DB_HOST"],
        db_port=int(os.environ.get("DB_PORT", "3306")),
        db_user=os.environ["DB_USER"],
        db_pass=os.environ["DB_PASS"],
        db_name=os.environ["DB_NAME"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        reddit_client_id=os.environ["REDDIT_CLIENT_ID"],
        reddit_client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        reddit_user_agent=os.environ["REDDIT_USER_AGENT"],
    )
