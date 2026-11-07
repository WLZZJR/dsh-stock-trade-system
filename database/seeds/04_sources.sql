-- Internal sources. Every fact row needs a registered source_id (DATABASE.md 16.1), including
-- mock test data and hand-imported files, so these two exist before anything is written.
INSERT INTO providers (name, provider_type, status) VALUES
  ('system_mock', 'internal', 'active'),
  ('manual_import', 'internal', 'active')
ON CONFLICT (name) DO NOTHING;

INSERT INTO data_sources (provider_id, source_name, source_type, license_scope)
SELECT p.id, v.source_name, v.source_type, v.license_scope
FROM (VALUES
  ('system_mock', 'system_mock', 'mock', 'synthetic_test_data'),
  ('manual_import', 'manual_import', 'manual', 'user_supplied')
) AS v(provider_name, source_name, source_type, license_scope)
JOIN providers p ON p.name = v.provider_name
WHERE NOT EXISTS (
  SELECT 1 FROM data_sources d WHERE d.provider_id = p.id AND d.source_name = v.source_name
);
