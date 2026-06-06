import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

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

_JSON_URL = "https://www.reddit.com/r/stocks/hot.json?limit=50"
_USER_AGENT = "stock-recommendations/1.0 (personal project)"

MIN_SCORE = 50
MIN_UPVOTE_RATIO = 0.7


def fetch_reddit_posts(cfg: Config) -> list[dict]:
    """Fetches hot posts from /r/stocks via Reddit's public JSON endpoint.

    Filters by SPEC thresholds: score >= 50 and upvote_ratio >= 0.7.
    """
    try:
        req = urllib.request.Request(_JSON_URL, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning(f"Reddit JSON fetch failed: {e} — continuing without Reddit data")
        return []

    children = payload.get("data", {}).get("children", [])
    posts = []
    dropped = 0
    for child in children:
        d = child.get("data", {})
        score = d.get("score", 0)
        upvote_ratio = d.get("upvote_ratio", 0.0)
        if score < MIN_SCORE or upvote_ratio < MIN_UPVOTE_RATIO:
            dropped += 1
            continue

        created_utc = d.get("created_utc")
        if created_utc:
            created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).replace(tzinfo=None)
        else:
            created_at = datetime.now(timezone.utc).replace(tzinfo=None)

        permalink = d.get("permalink") or ""
        posts.append({
            "id": d.get("id", ""),
            "title": d.get("title", ""),
            "url": f"https://www.reddit.com{permalink}" if permalink else d.get("url", ""),
            "score": score,
            "upvote_ratio": upvote_ratio,
            "created_at": created_at,
            "selftext": (d.get("selftext") or "")[:500],
        })

    logger.info(
        f"Fetched {len(posts)} posts from /r/stocks "
        f"(dropped {dropped} below score>={MIN_SCORE} or upvote_ratio>={MIN_UPVOTE_RATIO})"
    )
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
