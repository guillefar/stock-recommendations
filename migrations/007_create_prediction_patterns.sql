-- Migration 007: Claude-discovered prediction patterns (session 22).
-- Owned by this project. On Friday runs (or --force-patterns), one extra
-- Claude call receives (a) correct-vs-incorrect feature aggregates computed in
-- Python over every graded 30d outcome and (b) its own previous pattern set
-- (latest row here), and returns a refined set — statuses NEW / CONFIRMED /
-- REVISED / RETIRED with evidence + confidence — plus a Spanish narrative.
-- Rows append (no upsert): pattern evolution stays auditable; the newest row
-- is the current truth. User sign-off given 2026-07-12.

CREATE TABLE IF NOT EXISTS prediction_patterns (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  generated_at DATETIME NOT NULL,
  horizon_days INT NOT NULL,              -- 30 for now (headline horizon)
  patterns     JSON,                      -- [{name, description, evidence, status, confidence}]
  narrative    TEXT,                      -- Claude's markdown explanation (Spanish)
  stats        JSON,                      -- the aggregates the miner was fed (audit trail)
  INDEX idx_generated (generated_at)
);
