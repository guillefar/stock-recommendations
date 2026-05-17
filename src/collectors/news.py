import logging

import feedparser

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    "https://www.reutersagency.com/feed/?best-sectors=business-finance",
    "http://feeds.marketwatch.com/marketwatch/topstories/",
    "https://finance.yahoo.com/news/rssindex",
]


def fetch_macro_headlines(max_total: int = 30) -> list[dict]:
    """Fetches and deduplicates headlines from RSS feeds."""
    seen: set[str] = set()
    headlines: list[dict] = []

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                headlines.append({
                    "title": title,
                    "source": source,
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
                if len(headlines) >= max_total:
                    return headlines
        except Exception as e:
            logger.error(f"Error fetching RSS feed {feed_url}: {e}")

    return headlines
