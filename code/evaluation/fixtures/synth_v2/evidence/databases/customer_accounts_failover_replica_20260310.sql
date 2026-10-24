-- Ghost Data Still Exists: point-in-time database snapshot (fictional fixture)
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-03-10T11:00:00Z
-- Database topology: failover_replica
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_profiles_failover_replica (
resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, account_status TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT INTO "customer_profiles_failover_replica" VALUES('account_9121', 'user_9121', 'Unrelated Person 21', 'unrelated.21@example.org', '+1 555 0199', 'ACTIVE', '2026-03-10T11:00:00Z');
CREATE TABLE customer_profiles_primary (
resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, account_status TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT INTO "customer_profiles_primary" VALUES('account_9121', 'user_9121', 'Unrelated Person 21', 'unrelated.21@example.org', '+1 555 0199', 'ACTIVE', '2026-03-10T11:00:00Z');
COMMIT;
