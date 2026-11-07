-- US trading venues, identified by ISO 10383 market identifier codes (MIC).
-- Phase 1 scope is US equities only (plan section 2); further venues need a plan change.
INSERT INTO venues (mic, name, country_code, timezone) VALUES
  ('XNYS', 'New York Stock Exchange', 'US', 'America/New_York'),
  ('XNAS', 'Nasdaq Stock Market', 'US', 'America/New_York'),
  ('XASE', 'NYSE American', 'US', 'America/New_York')
ON CONFLICT (mic) DO NOTHING;
