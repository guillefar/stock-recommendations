-- Migration 001: Create recommendation tables
-- This project only READS from stock-snapshots tables (tickers, holdings, watchlist, price_snapshots).
-- All tables below are new and owned by this project.

CREATE TABLE IF NOT EXISTS macro_signals (
  id               BIGINT AUTO_INCREMENT PRIMARY KEY,
  detected_at      DATETIME NOT NULL,
  theme            VARCHAR(200),
  affected_sectors JSON,
  direction        JSON,
  source_headlines JSON,
  summary          TEXT
);

CREATE TABLE IF NOT EXISTS recommendations (
  id               BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticker_id        INT NOT NULL,
  generated_at     DATETIME NOT NULL,
  action           ENUM('BUY','SELL','HOLD','WATCH','AVOID') NOT NULL,
  confidence       DECIMAL(3,2),
  reasoning        TEXT,
  technical        JSON,
  sentiment        JSON,
  macro_signal_id  BIGINT NULL,
  model_used       VARCHAR(50),
  FOREIGN KEY (ticker_id) REFERENCES tickers(id),
  FOREIGN KEY (macro_signal_id) REFERENCES macro_signals(id),
  INDEX idx_ticker_date (ticker_id, generated_at)
);

CREATE TABLE IF NOT EXISTS daily_market_summary (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY,
  summary_date      DATE NOT NULL,
  generated_at      DATETIME NOT NULL,
  summary           TEXT,
  hot_tickers       JSON,
  overall_sentiment VARCHAR(20),
  source_post_count INT,
  UNIQUE KEY uq_summary_date (summary_date)
);

CREATE TABLE IF NOT EXISTS reddit_mentions (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticker_id       INT,
  post_id         VARCHAR(20) NOT NULL,
  post_title      TEXT,
  post_url        VARCHAR(500),
  post_score      INT,
  post_created_at DATETIME,
  sentiment       ENUM('POSITIVE','NEGATIVE','NEUTRAL','MIXED'),
  captured_at     DATETIME,
  FOREIGN KEY (ticker_id) REFERENCES tickers(id),
  UNIQUE KEY uq_post_ticker (post_id, ticker_id),
  INDEX idx_ticker_date (ticker_id, captured_at)
);
