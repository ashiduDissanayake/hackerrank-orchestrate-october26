-- Ghost Data Still Exists: point-in-time database snapshot (fictional fixture)
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-10-10T11:00:00Z
-- Database topology: reporting_replica
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_data_primary (
resource_id TEXT PRIMARY KEY, origin_system TEXT NOT NULL, collection_name TEXT NOT NULL, record_json TEXT NOT NULL CHECK (json_valid(record_json)), updated_at TEXT NOT NULL
);
INSERT INTO "customer_data_primary" VALUES('audit_record_927', 'security_service', 'security_audit_events', '{"actor_type":"automated_privacy_workflow","event_name":"account_deletion_reviewed","integrity_seal":"sha256:0000000000000000000000000000000000000000000000000000000000002343","resource_id":"audit_record_927","subject_reference":"user_927"}', '2026-10-10T11:00:00Z');
CREATE TABLE customer_data_reporting_replica (
resource_id TEXT PRIMARY KEY, origin_system TEXT NOT NULL, collection_name TEXT NOT NULL, record_json TEXT NOT NULL CHECK (json_valid(record_json)), updated_at TEXT NOT NULL
);
INSERT INTO "customer_data_reporting_replica" VALUES('audit_record_927', 'security_service', 'security_audit_events', '{"actor_type":"automated_privacy_workflow","event_name":"account_deletion_reviewed","integrity_seal":"sha256:0000000000000000000000000000000000000000000000000000000000002343","resource_id":"audit_record_927","subject_reference":"user_927"}', '2026-10-10T11:00:00Z');
INSERT INTO "customer_data_reporting_replica" VALUES('account_927', 'account_service', 'customer_profiles', '{"account_status":"ACTIVE","customer_reference":"user_927","email":"unrelated.27@example.org","full_name":"Unrelated Person 27","phone":"+1 555 0199","resource_id":"account_927"}', '2026-10-10T11:00:00Z');
COMMIT;
