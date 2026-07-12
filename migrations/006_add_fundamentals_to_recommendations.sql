-- Migration 006: fundamentals snapshot on each recommendation (session 22).
-- Stores the exact fundamentals dict Claude saw when it made the call
-- (fetch_fundamentals shape: trailing_pe, forward_pe, dividend_yield_pct,
-- profit_margin, operating_margin, revenue_growth, earnings_growth,
-- market_cap, currency). NULL for ETFs, the index, untyped tickers, and for
-- every row that predates this migration — enables fundamentals-vs-verdict
-- analysis once s20-informed calls mature (~2026-08-13 at 30d).
-- Additive only; user sign-off given 2026-07-12.

ALTER TABLE recommendations ADD COLUMN fundamentals JSON NULL AFTER sentiment;
