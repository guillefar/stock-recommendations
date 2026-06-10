-- Migration 002: Track whether past recommendations turned out correct.
-- Owned by this project. Reads price_snapshots (stock-snapshots) to grade
-- each recommendation's forward return at fixed horizons. Populated by
-- `python -m src.evaluate_outcomes`.

CREATE TABLE IF NOT EXISTS recommendation_outcomes (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY,
  recommendation_id BIGINT NOT NULL,
  ticker_id         INT NOT NULL,
  generated_at      DATETIME NOT NULL,
  action            ENUM('BUY','SELL','HOLD','WATCH','AVOID') NOT NULL,
  confidence        DECIMAL(3,2),
  horizon_days      INT NOT NULL,           -- calendar days after generated_at
  entry_price       DECIMAL(18,6),          -- price at recommendation time
  exit_price        DECIMAL(18,6),          -- first snapshot at/after the horizon
  exit_as_of        DATETIME,               -- when exit_price was observed
  forward_return    DECIMAL(10,6),          -- exit_price / entry_price - 1
  verdict           ENUM('CORRECT','INCORRECT','NEUTRAL') NOT NULL,
  evaluated_at      DATETIME NOT NULL,
  FOREIGN KEY (recommendation_id) REFERENCES recommendations(id),
  FOREIGN KEY (ticker_id) REFERENCES tickers(id),
  UNIQUE KEY uq_rec_horizon (recommendation_id, horizon_days),
  INDEX idx_ticker_date (ticker_id, generated_at)
);
