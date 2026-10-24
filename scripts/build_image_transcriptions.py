"""Writes code/ghostaudit/image_transcriptions/*.json.

THESE ARE HAND-AUTHORED TRANSCRIPTIONS, not machine extraction. The 11 PNG screenshots were inspected visually by the
coding agent (claude-sonnet-5-5 via Claude Code's image viewer, 2026-10-24) and the visible records were typed in.
Each file is bound to its PNG by sha256, and tests/test_image_transcriptions.py independently cross-checks every
transcribed identifier against local OCR (tesseract, 3x upscale) in both directions, so neither an invented nor an
omitted identifier goes unnoticed. Re-running this script only re-serialises the data below.

Time rule: available_at = max(manifest captured_at, header_time shown on the screen);
           observed_at  = max(captured_at, any dated record timestamp shown for that record).
Dated-record timestamps later than the capture time are kept (not corrected): the engine's dual-time cutoff then
makes such a record invisible to any audit that precedes it.
Resource ids that a screen does not print (object_19, tombstone_17) come from the data-catalog row named in
`resource_id_source`; `available_at` is raised to that row's event_time so the id is never used before it existed.
"""
import hashlib
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "code", "ghostaudit", "image_transcriptions")
IMG = os.path.join(REPO, "dataset", "evidence", "images")

T = {
    "evidence_04": ("account_admin_console_20260926.png", "2026-09-26T11:00:00Z"),
    "evidence_09": ("search_index_inspector_20260901.png", "2026-09-01T06:00:00Z"),
    "evidence_14": ("connector_management_console_20260807.png", "2026-08-07T08:00:00Z"),
    "evidence_19": ("analytics_profile_view_20260713.png", "2026-07-13T10:00:00Z"),
    "evidence_23": ("customer_export_console_20260618.png", "2026-06-18T12:00:00Z"),
    "evidence_28": ("support_ticket_console_20260524.png", "2026-05-24T07:00:00Z"),
    "evidence_32": ("backup_restore_console_20260429.png", "2026-04-29T09:00:00Z"),
    "evidence_37": ("security_audit_explorer_20260905.png", "2026-09-05T07:00:00Z"),
    "evidence_42": ("deleted_account_reference_20260310.png", "2026-03-10T06:00:00Z"),
    "evidence_46": ("object_storage_browser_20260213.png", "2026-02-13T08:00:00Z"),
    "evidence_60": ("marketing_profile_console.png", "2026-09-16T07:20:00Z"),
}


def rec(resource_id, system, observed_at, fields, present=True, kind="ui_record", **extra):
    r = {"resource_id": resource_id, "system_id": system, "kind": kind, "present": present, "observed_at": observed_at, "fields": fields}
    r.update(extra)
    return r


D = {}
D["evidence_04"] = dict(screen="account admin console: customer overview", header_time=None, records=[
    rec("account_5762", "account_service", "2026-09-26T11:00:00Z", {
        "name": "Haruka Sato", "email": "haruka.s1838@zoho.com", "phone": "+81 90 7610 2507", "customer_reference": "user_11",
        "loyalty_tier": "Silver", "member_since": "12 Jan 2024", "default_address": "2-18-4 Kichijoji, Musashino, Tokyo 180-0004"}),
    rec("support_9538", "support_platform", "2026-09-26T11:00:00Z", {"ticket_id": "CS-8538", "customer_reference": "user_11"}, present=None, kind="ui_reference",
        note="listed under the customer's details as 'CS-8538 · support_9538'; a reference, the record itself is not shown")],
    omitted="order rows ORD-20265762 and ORD-20265518 (not resources)",
    ocr_recheck_boxes={"account_5762": [240, 132, 420, 156]})
D["evidence_09"] = dict(screen="search console: customer directory query email:g.silva76@gmail.com", header_time="2026-09-01T06:00:14Z", records=[
    rec("search_428", "search_service", "2026-09-01T06:00:14Z", {"name": "Gabriel Silva", "email": "g.silva76@gmail.com", "customer_reference": "user_13",
        "index": "customer_directory_v3", "indexed_at": "2026-09-01T05:58:21Z"}),
    rec("search_1874", "search_service", "2026-09-01T06:00:14Z", {"email": "g.silva76.jr@gmail.com", "index": "customer_directory_v3", "indexed_at": "2026-09-01T05:55:03Z"},
        note="near-miss decoy: a different address (.jr) returned by the same query")],
    omitted="activity panel queries (customer_reference:user_9842, display_name 'Aditi Jain') are past searches, not records",
    omitted_identifiers=["user_9842"])
D["evidence_14"] = dict(screen="connector management console: topology", header_time="2026-08-07T08:00:00Z", records=[
    rec("data_flow_1121", "integration_service", "2026-08-07T08:00:00Z", {
        "subject_selector": "jain.aditi@gmail.com", "destination": "customer_analytics_warehouse", "mode": "continuous_sync", "status": "Healthy",
        "events_per_hour": "1284", "last_contact": "2026-08-07T07:59:42Z", "enabled": "true",
        "enabled_basis": "Status Healthy, Sync mode Continuous sync, 1,284 events/hour, last contact 18 s before capture"}),
    rec("data_flow_9846", "integration_service", "2026-08-07T08:00:00Z", {
        "subject_selector": "lucia-torres@gmail.com", "destination": "customer_analytics_warehouse", "mode": "continuous_sync",
        "events_per_hour": "842", "last_contact": "2026-08-07T07:59:36Z", "enabled": "true",
        "enabled_basis": "row shows Continuous mode, 842 events/hour, last contact 24 s before capture (status shown only for data_flow_1121)"})],
    omitted="rows 'Order notifications' and 'Delivery tracking' (no resource id, no personal identifier)")
D["evidence_19"] = dict(screen="analytics profile view: event timeline", header_time=None, records=[
    rec("analytics_7438", "analytics_platform", "2026-07-13T14:22:00Z", {
        "name": "Omar Darwish", "email": "darwish.omar@icloud.com", "customer_reference": "user_20", "audience": "Returning shopper", "market": "AE",
        "last_activity": "2026-07-13T14:22:00Z"},
        note="Last activity 14:22 UTC is LATER than the manifest capture time 10:00Z; observed_at keeps the later time")])
D["evidence_23"] = dict(screen="customer download center: data exports", header_time=None, records=[
    rec("export_1261", "export_service", "2026-06-20T14:18:00Z", {"owner_email": "marcus.lee@northstar.shop", "status": "Collecting", "file_name": "customer_export_1261.zip", "created": "2026-06-20T14:18:00Z"},
        note="created 20 Jun 14:18 is after the capture time; kept"),
    rec("export_1260", "export_service", "2026-06-18T12:00:00Z", {"owner_email": "ingrid.dahl@outlook.com", "status": "Ready", "file_name": "customer_export_1260.zip",
        "created": "2026-06-18T06:42:00Z", "expires": "2026-06-25T06:42:00Z", "size": "18.4 MB", "download_count": "0", "included": "Profile · Orders · Saved addresses"}),
    rec("export_1259", "export_service", "2026-06-18T12:00:00Z", {"owner_email": "sara.kim@northstar.shop", "status": "Packaging", "file_name": "customer_export_1259.zip", "created": "2026-06-17T11:03:00Z"}),
    rec("export_1258", "export_service", "2026-06-18T12:00:00Z", {"owner_email": "daniel.park@northstar.shop", "status": "Ready", "file_name": "customer_export_1258.zip", "created": "2026-06-16T09:27:00Z"})])
D["evidence_28"] = dict(screen="helpline console: ticket conversation CS-5034", header_time=None, records=[
    rec("support_1034", "support_platform", "2026-05-24T07:00:00Z", {
        "ticket_id": "CS-5034", "subject": "Where is my delivery?", "name": "Kofi Agyeman", "email": "kagyeman8947@fastmail.com", "assigned_agent": "Maya Chen",
        "message_text": "Could you let me know where my order is and when it is expected to arrive? | We received your message and are checking the order details. | "
                        "The parcel reached the regional hub and is on track for delivery on 26 May. | Thanks for the update.",
        "order": "ORD-20265034"},
        note="conversation times 09:12-09:35 carry no date, so observed_at is the capture time")])
D["evidence_32"] = dict(screen="vault recovery manager: customer-platform archives", header_time=None, records=[
    rec("backup_9291", "backup_service", "2026-04-29T09:00:00Z", {"customer_email": "bluepeakco@outlook.com", "region": "ap-southeast-1", "created": "2026-04-26T02:00:00Z", "size": "102.3 GB", "tier": "Archive"}),
    rec("backup_9288", "backup_service", "2026-04-29T09:00:00Z", {"customer_email": "miller.logistics@company.com", "region": "us-west-2", "created": "2026-04-26T02:00:00Z", "size": "67.1 GB", "tier": "Archive"}),
    rec("backup_9287", "backup_service", "2026-04-29T09:00:00Z", {
        "customer_email": "areed1433@gmail.com", "region": "eu-west-1", "created": "2026-04-26T02:00:00Z", "size": "84.7 GB", "tier": "Archive", "encryption": "AES-256",
        "archive_path": "s3://northstar-backups/customer-platform/weekly/segment-42-20260426.tar.zst", "checksum": "Verified", "last_drill": "2026-03-29", "retention_end": "2026-07-26"},
        note="no restore-allowed / restore-blocked state is shown for any archive"),
    rec("backup_9286", "backup_service", "2026-04-29T09:00:00Z", {"customer_email": "summit-retail@company.com", "region": "us-east-1", "created": "2026-04-26T02:00:00Z", "size": "91.4 GB", "tier": "Archive"})],
    omitted="activity entries about backup_9286 and backup_9281 restores (completed events, not records)",
    omitted_identifiers=["backup_9281"])
D["evidence_37"] = dict(screen="security audit explorer: account events for subject user_03", header_time=None, records=[
    rec(f"audit_record_00{n}", "security_service", "2026-09-05T07:00:00Z", {"subject_reference": "user_03", "event_name": name, "category": cat, "actor_type": actor, "integrity": "Valid", "recorded_at": ts})
    for n, name, cat, actor, ts in (
        (3, "Account closure recorded", "Account lifecycle", "Automated workflow", "2026-08-25T04:03:00Z"),
        (2, "Session revoked", "Session management", "Security system", "2026-08-25T03:21:00Z"),
        (1, "Recovery challenge completed", "Authentication", "User (self)", "2026-08-24T16:14:00Z"),
        (6, "Email change confirmed", "Profile update", "User (self)", "2026-08-22T11:27:00Z"),
        (5, "Login from new device", "Authentication", "User (self)", "2026-08-20T09:42:00Z"),
        (4, "Password changed", "Authentication", "User (self)", "2026-08-18T14:05:00Z"))],
    omitted="detail panel for audit_record_003: fingerprint 8f0c...31ad, signature Valid, journal 2026-Q3 (not identifiers); no retention_until is shown")
D["evidence_42"] = dict(screen="customer reference registry: user_17 retained reference", header_time=None, records=[
    rec("tombstone_17", "identity_service", "2026-03-10T07:18:00Z", {"customer_reference": "user_17", "status": "Retained reference", "reference_type": "Customer key",
        "owner_team": "Account Platform", "created": "2024-01-11T08:42:00Z", "most_recent_update": "2026-03-10T07:18:00Z", "collection": "deleted_customer_references"},
        resource_id_source="activity_4011 (data catalog, 2026-03-10T06:07:01Z): 'tombstone_17 (user_17)'; the screen shows only the customer key user_17",
        available_at_override="2026-03-10T06:07:01Z",
        note="no name, email, phone or hash is shown: only the stable reference. Most recent update 07:18 is later than the capture time; kept")],
    omitted="linked records ORD-20263245, CS-3245, CS-3378, FIN-7742 (order/support/finance references, not resources)")
D["evidence_46"] = dict(screen="object storage browser: northstar-customer-data / support-attachments / 2026 / 02", header_time="2026-02-13T08:00:00Z", records=[
    rec("object_19", "object_storage", "2026-02-13T08:00:00Z", {
        "file_name": "delivery_confirmation_19.pdf", "record_type": "SUPPORT_ATTACHMENT", "size": "684 KB", "version": "v3", "content_type": "application/pdf",
        "uploader": "support-service", "modified": "2026-02-12T18:42:00Z", "path": "eu-west-1/support-attachments/2026/02"},
        resource_id_source="activity_4007 (data catalog, 2026-02-13T08:07:01Z): 'object_19 (delivery_confirmation_19.pdf)'; the screen shows the file name only",
        available_at_override="2026-02-13T08:07:01Z")],
    omitted="7 other objects (return labels, invoice, parcel photo, two customer exports): file names only, no resource ids or personal identifiers")
D["evidence_60"] = dict(screen="audience operations: marketing profile", header_time=None, records=[
    rec("marketing_001", "marketing_platform", "2026-09-16T07:20:00Z", {
        "name": "Soo-jin Park", "email": "sj.park@naver.com", "phone": "+82 10-5837-9451", "email_opt_in": "true", "sms_opt_in": "false", "market": "South Korea",
        "last_refreshed": "2026-09-15T23:40:00Z", "audience": "Returning customers - East Asia"},
        note="CONFLICT: the data catalog (activity_4008) says marketing_001 belongs to kwame-mensah@proton.me / user_09; this screen shows a different person")])


def main():
    os.makedirs(OUT, exist_ok=True)
    for eid, (fname, captured) in T.items():
        path = os.path.join(IMG, fname)
        body = D[eid]
        doc = {
            "evidence_id": eid, "source_path": f"evidence/images/{fname}", "source_sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
            "manifest_captured_at": captured, "method": "agent_visual_transcription (hand-authored; see scripts/build_image_transcriptions.py)",
            "transcriber": "claude-sonnet-5-5 via Claude Code image viewer", "transcribed_on": "2026-10-24", **body,
        }
        with open(os.path.join(OUT, f"{eid}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1, sort_keys=True, ensure_ascii=False)
            f.write("\n")
    print(f"wrote {len(T)} transcriptions to {os.path.relpath(OUT, REPO)}")


if __name__ == "__main__":
    main()
