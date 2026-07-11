-- Migration 004: Persist trending-unknown tickers (Wave 4).
-- Owned by this project. `find_trending_unknown` surfaces symbols mentioned in
-- high-score Reddit posts that aren't in the tickers table; until now they only
-- hit logs and the daily-summary text. One row per symbol, upserted per run, so
-- "should I watchlist this?" candidates survive and can trend over time.
-- Stays empty until Reddit credentials exist.

CREATE TABLE IF NOT EXISTS trending_tickers (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  symbol        VARCHAR(10) NOT NULL,
  first_seen    DATE NOT NULL,              -- first run the symbol trended on
  last_seen     DATE NOT NULL,              -- most recent run it trended on
  times_seen    INT NOT NULL DEFAULT 1,     -- number of runs it trended on
  mention_count INT NOT NULL,               -- qualifying posts in the latest run
  avg_score     DECIMAL(10,1),              -- avg post score in the latest run
  UNIQUE KEY uq_symbol (symbol)
);
