-- Migration 003: In-repo daily price observations (S1).
-- Owned by this project. The sibling stock-snapshots `price_snapshots` table
-- went stale (last row 2026-05-22), leaving new recommendations ungradeable.
-- `src.main` upserts one row per ticker per run (price already fetched for the
-- technical analysis); `evaluate_outcomes` falls back to this table when
-- price_snapshots has no row in the horizon window.

CREATE TABLE IF NOT EXISTS price_checks (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticker_id   INT NOT NULL,
  as_of_date  DATE NOT NULL,                -- trading day the price was observed
  price       DECIMAL(18,6) NOT NULL,
  created_at  DATETIME NOT NULL,
  FOREIGN KEY (ticker_id) REFERENCES tickers(id),
  UNIQUE KEY uq_ticker_day (ticker_id, as_of_date)
);
