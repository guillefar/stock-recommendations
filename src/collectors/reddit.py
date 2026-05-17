import logging
import re
from datetime import datetime, timezone

import feedparser

from src.config import Config

logger = logging.getLogger(__name__)

_DOLLAR_TICKER = re.compile(r"\$([A-Z]{1,5})\b")
_UPPER_WORD = re.compile(r"\b([A-Z]{2,5})\b")

_STOPWORDS = {
    "I", "A", "AN", "THE", "AND", "OR", "BUT", "FOR", "NOT", "IS", "ARE",
    "AT", "BY", "IN", "OF", "ON", "TO", "UP", "BE", "DO", "GO", "IF",
    "IT", "NO", "SO", "US", "WE", "MY", "AM", "PM", "ETF", "IPO",
    "CEO", "CFO", "CTO", "IMO", "TBH", "FYI", "DD", "TA", "PE", "EPS",
    "GDP", "CPI", "FED", "SEC", "NYSE", "NASDAQ", "SP", "QE", "QT",
    "ATH", "ATL", "YTD", "EOD", "EOY", "WTF", "LOL", "OP",
}

_RSS_URL = "https://www.reddit.com/r/stocks/hot.rss?limit=50"
_POST_ID_RE = re.compile(r"/comments/([a-z0-9]+)/")


def fetch_reddit_posts(cfg: Config) -> list[dict]:
    """Fetches hot posts from /r/stocks via RSS (works from datacenter IPs, no auth needed)."""
    try:
        feed = feedparser.parse(
            _RSS_URL,
            request_headers={"User-Agent": "feedparser/6 (stock-recommendations personal project)"},
        )
        if not feed.entries:
            logger.warning("Reddit RSS returned no entries")
            return []

        posts = []
        for entry in feed.entries:
            url = entry.get("link", "")
            m = _POST_ID_RE.search(url)
            post_id = m.group(1) if m else url

            published = entry.get("published_parsed")
            if published:
                created_at = datetime(*published[:6], tzinfo=timezone.utc).replace(tzinfo=None)
            else:
                created_at = datetime.utcnow()

            posts.append({
                "id": post_id,
                "title": entry.get("title", ""),
                "url": url,
                "score": 0,       # not available in RSS
                "upvote_ratio": 1.0,
                "created_at": created_at,
                "selftext": (entry.get("summary") or "")[:500],
            })

        logger.info(f"Fetched {len(posts)} posts from /r/stocks RSS")
        return posts
    except Exception as e:
        logger.warning(f"Reddit RSS fetch failed: {e} — continuing without Reddit data")
        return []


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
