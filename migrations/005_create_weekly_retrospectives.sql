-- Migration 005: Weekly retrospective digest (S5, Wave 4).
-- Owned by this project. On Friday runs, one extra Claude call reviews the week
-- for a long-term investor: the calls whose 30d horizon matured this week and
-- how they graded, the week's action flips, and current sector exposure.
-- One row per ISO week (keyed on its Monday), upserted so a workflow retry
-- refreshes rather than duplicates.

CREATE TABLE IF NOT EXISTS weekly_retrospectives (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  week_start    DATE NOT NULL,              -- Monday of the reviewed week
  generated_at  DATETIME NOT NULL,
  retrospective TEXT,                       -- Claude's markdown review (Spanish)
  stats         JSON,                       -- the aggregates the review was built from
  UNIQUE KEY uq_week_start (week_start)
);
