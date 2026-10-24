-- Ghost Data Still Exists: point-in-time database snapshot (fictional fixture)
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-06-14T08:30:00Z
-- Database topology: regional_replicas
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_data_primary (
resource_id TEXT PRIMARY KEY, origin_system TEXT NOT NULL, collection_name TEXT NOT NULL, record_json TEXT NOT NULL CHECK (json_valid(record_json)), updated_at TEXT NOT NULL
);
INSERT INTO "customer_data_primary" VALUES('legal_hold_f15', 'legal_service', 'retained_order_records', '{"resource_id": "legal_hold_f15", "subject_reference": "user_f15", "order_reference": "ORD-F15", "retention_reason": "payment_dispute_and_tax_record", "retained_until": "2033-12-31T23:59:59Z"}', '2026-06-14T08:30:00Z');
CREATE TABLE customer_data_replica_ap_south (
resource_id TEXT PRIMARY KEY, origin_system TEXT NOT NULL, collection_name TEXT NOT NULL, record_json TEXT NOT NULL CHECK (json_valid(record_json)), updated_at TEXT NOT NULL
);
INSERT INTO "customer_data_replica_ap_south" VALUES('legal_hold_f15', 'legal_service', 'retained_order_records', '{"resource_id": "legal_hold_f15", "subject_reference": "user_f15", "order_reference": "ORD-F15", "retention_reason": "payment_dispute_and_tax_record", "retained_until": "2033-12-31T23:59:59Z"}', '2026-06-14T08:30:00Z');
COMMIT;
