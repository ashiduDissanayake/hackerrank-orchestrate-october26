-- Ghost Data Still Exists: point-in-time database snapshot (fictional fixture)
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-06-14T11:00:00Z
-- Database topology: failover_replica
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_profiles_failover_replica (
resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, account_status TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT INTO "customer_profiles_failover_replica" VALUES('account_9001', 'user_9001', 'Unrelated One', 'unrelated.one@example.org', '+1 555 0100', 'ACTIVE', '2026-06-14T11:00:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_9002', 'user_9002', 'Unrelated Two', 'unrelated.two@example.org', '+1 555 0101', 'ACTIVE', '2026-06-14T11:00:00Z');
INSERT INTO "customer_profiles_failover_replica" VALUES('account_f06', 'user_f06', 'Oskar Lind', 'oskar.lind@example.org', '+1 555 010 0006', 'ACTIVE', '2026-06-14T11:00:00Z');
CREATE TABLE customer_profiles_primary (
resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, full_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, account_status TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT INTO "customer_profiles_primary" VALUES('account_9001', 'user_9001', 'Unrelated One', 'unrelated.one@example.org', '+1 555 0100', 'ACTIVE', '2026-06-14T11:00:00Z');
INSERT INTO "customer_profiles_primary" VALUES('account_9002', 'user_9002', 'Unrelated Two', 'unrelated.two@example.org', '+1 555 0101', 'ACTIVE', '2026-06-14T11:00:00Z');
COMMIT;
