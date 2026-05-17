import logging
import re
import time
from datetime import datetime, timezone

import requests

from src.config import Config

logger = logging.getLogger(__name__)

_DOLLAR_TICKER = re.compile(r"\$([A-Z]{1,5})\b")
_UPPER_WORD = re.compile(r"\b([A-Z]{2,5})\b")

# Common English uppercase words that are not tickers
_STOPWORDS = {
    "I", "A", "AN", "THE", "AND", "OR", "BUT", "FOR", "NOT", "IS", "ARE",
    "AT", "BY", "IN", "OF", "ON", "TO", "UP", "BE", "DO", "GO", "IF",
    "IT", "NO", "SO", "US", "WE", "MY", "AM", "PM", "ETF", "IPO",
    "CEO", "CFO", "CTO", "IMO", "TBH", "FYI", "DD", "TA", "PE", "EPS",
    "GDP", "CPI", "FED", "SEC", "NYSE", "NASDAQ", "SP", "QE", "QT",
    "ATH", "ATL", "YTD", "EOD", "EOY", "WTF", "LOL", "OP",
}

_REDDIT_JSON_URL = "https://www.reddit.com/r/stocks/hot.json"
_USER_AGENT = "stock-recommendations-bot/1.0 (personal finance project)"


def fetch_reddit_posts(cfg: Config) -> list[dict]:
    """Fetches hot posts from /r/stocks using the public JSON API (no auth required)."""
    headers = {"User-Agent": _USER_AGENT}
    params = {"limit": 50, "raw_json": 1}

    resp = requests.get(_REDDIT_JSON_URL, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    posts = []
    for child in data.get("data", {}).get("children", []):
        s = child.get("data", {})
        score = s.get("score", 0)
        upvote_ratio = s.get("upvote_ratio", 0.0)
        if score > 50 and upvote_ratio > 0.7:
            posts.append({
                "id": s.get("id", ""),
                "title": s.get("title", ""),
                "url": s.get("url", ""),
                "score": score,
                "upvote_ratio": upvote_ratio,
                "created_at": datetime.fromtimestamp(
                    s.get("created_utc", 0), tz=timezone.utc
                ).replace(tzinfo=None),
                "selftext": (s.get("selftext") or "")[:500],
            })

    logger.info(f"Fetched {len(posts)} qualifying posts from /r/stocks")
    return posts


def extract_ticker_mentions(
    posts: list[dict], known_symbols: set[str]
) -> dict[str, list[dict]]:
    """
    Returns symbol -> list[post] for known symbols mentioned in posts.
    Detects $TICKER patterns and uppercase words matching known symbols.
    """
    mentions: dict[str, list[dict]] = {}
    for post in posts:
        text = f"{post['title']} {post.get('selftext', '')}"
        found: set[str] = set()

        for m in _DOLLAR_TICKER.finditer(text):
            sym = m.group(1)
            if sym in known_symbols:
                found.add(sym)

        for m in _UPPER_WORD.finditer(text):
            sym = m.group(1)
            if sym in known_symbols and sym not in _STOPWORDS:
                found.add(sym)

        for sym in found:
            mentions.setdefault(sym, []).append(post)

    return mentions


def find_trending_unknown(
    posts: list[dict], known_symbols: set[str]
) -> list[dict]:
    """
    Finds $TICKER mentions in high-score posts (score > 100) for symbols NOT
    in the known tickers table, with more than 3 mentions.
    """
    counts: dict[str, list[int]] = {}
    for post in posts:
        if post["score"] <= 100:
            continue
        text = f"{post['title']} {post.get('selftext', '')}"
        found: set[str] = set()
        for m in _DOLLAR_TICKER.finditer(text):
            sym = m.group(1)
            if sym not in known_symbols and sym not in _STOPWORDS:
                found.add(sym)
        for sym in found:
            counts.setdefault(sym, []).append(post["score"])

    return [
        {
            "symbol": sym,
            "mention_count": len(scores),
            "avg_score": round(sum(scores) / len(scores), 1),
        }
        for sym, scores in counts.items()
        if len(scores) > 3
    ]
