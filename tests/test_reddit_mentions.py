"""S18: ticker-mention extraction — stopwords, $-prefix, trending threshold."""

from src.collectors.reddit import extract_ticker_mentions, find_trending_unknown


def _post(title, score=200, post_id="p1", selftext=""):
    return {"id": post_id, "title": title, "score": score, "selftext": selftext}


def test_bare_uppercase_known_symbol_is_matched():
    mentions = extract_ticker_mentions([_post("AAPL crushes earnings")], {"AAPL"})
    assert set(mentions) == {"AAPL"}
    assert len(mentions["AAPL"]) == 1


def test_stopword_symbols_not_matched_as_bare_words():
    # "IT", "GO", "BE" are real tickers but also common words — the bare
    # uppercase-word path must skip them even when they're known symbols.
    posts = [_post("IT IS TIME TO GO ALL IN, BE READY")]
    assert extract_ticker_mentions(posts, {"IT", "GO", "BE"}) == {}


def test_dollar_prefix_bypasses_stopwords():
    # An explicit $-prefix is an unambiguous ticker reference, so $IT counts
    # even though bare "IT" is stopworded.
    mentions = extract_ticker_mentions([_post("$IT looks cheap")], {"IT"})
    assert set(mentions) == {"IT"}


def test_unknown_symbols_are_ignored():
    assert extract_ticker_mentions([_post("$ZZZQ to the moon")], {"AAPL"}) == {}


def test_selftext_is_scanned_too():
    mentions = extract_ticker_mentions(
        [_post("Weekly thread", selftext="loading up on $AAPL")], {"AAPL"}
    )
    assert set(mentions) == {"AAPL"}


def _trending_posts(symbol, n, score=150):
    return [_post(f"${symbol} rocket", score=score, post_id=f"p{i}") for i in range(n)]


def test_trending_unknown_needs_more_than_three_mentions():
    known = {"AAPL"}
    assert find_trending_unknown(_trending_posts("ZZZQ", 3), known) == []
    result = find_trending_unknown(_trending_posts("ZZZQ", 4), known)
    assert result == [{"symbol": "ZZZQ", "mention_count": 4, "avg_score": 150.0}]


def test_trending_unknown_ignores_low_score_known_and_stopwords():
    known = {"AAPL"}
    # score must be > 100
    assert find_trending_unknown(_trending_posts("ZZZQ", 5, score=100), known) == []
    # known symbols aren't "unknown"
    assert find_trending_unknown(_trending_posts("AAPL", 5), known) == []
    # stopwords are excluded even with a $-prefix here (high false-positive risk)
    assert find_trending_unknown(_trending_posts("CEO", 5), known) == []
