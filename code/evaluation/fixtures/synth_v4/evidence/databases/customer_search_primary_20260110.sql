-- Ghost Data Still Exists: point-in-time database snapshot (fictional fixture)
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-01-10T08:00:00Z
-- Database topology: search_primary
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE search_documents_primary (
resource_id TEXT PRIMARY KEY, display_name TEXT, email TEXT NOT NULL, source_resource_id TEXT, indexed_at TEXT NOT NULL
);
INSERT INTO "search_documents_primary" VALUES('search_f29', 'Astrid Lindqvist', 'astrid.lindqvist@example.org', 'account_f29', '2026-01-09T22:00:00Z');
INSERT INTO "search_documents_primary" VALUES('search_f29z', 'Unrelated Person', 'unrelated.29@example.org', 'account_f29z', '2026-01-09T22:01:00Z');
COMMIT;
