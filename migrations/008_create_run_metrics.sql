-- Migration 008: per-run cost telemetry (session 24).
-- Owned by this project. Every completed pipeline run appends one row with
-- the Claude usage totals ClaudeClient accumulated across all its calls
-- (macro + summary + the 63 batched ticker calls + Friday retro/patterns)
-- and the run's ok/failed ticker counts. Dry-runs never write. Until now the
-- cost line lived only in the workflow logs (claude.log_usage()) — persisting
-- it makes the cost trend queryable — e.g. proving the Mon/Wed/Fri cadence's
-- ~-40% saving with data. Batched tokens are stored separately because the
-- Batches API bills them at 50%. Rows append (no upsert): the run history is
-- the audit trail. User sign-off given 2026-07-12.

CREATE TABLE IF NOT EXISTS run_metrics (
  id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_at              DATETIME NOT NULL,
  model_used          VARCHAR(64) NOT NULL,   -- claude_client.MODEL at run time
  calls               INT NOT NULL,           -- Claude API calls this run (2 + N batch + extras)
  input_tokens        INT NOT NULL,           -- non-batched input (full price)
  output_tokens       INT NOT NULL,           -- non-batched output (full price)
  batch_input_tokens  INT NOT NULL,           -- per-ticker batch input (billed 50%)
  batch_output_tokens INT NOT NULL,           -- per-ticker batch output (billed 50%)
  cache_write_tokens  INT NOT NULL,           -- expected 0 since session 08, kept for audit
  cache_read_tokens   INT NOT NULL,           -- expected 0 since session 08, kept for audit
  estimated_cost_usd  DECIMAL(10,6) NOT NULL, -- ClaudeClient.estimated_cost_usd()
  tickers_ok          INT NOT NULL,           -- recommendations written this run
  tickers_failed      INT NOT NULL,           -- tickers that returned no recommendation
  INDEX idx_run_at (run_at)
);
