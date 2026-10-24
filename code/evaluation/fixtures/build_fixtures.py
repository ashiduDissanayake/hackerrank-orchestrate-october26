"""Builds the frozen, independently labeled fixture dataset `synth_v1/`.

Everything here is fictional. Labels are reasoned from the contract (AGENTS.md sec. 6, deletion_rules.csv)
by the author of this file, NOT produced or tuned by the audit engine, and they are frozen (sha256 manifest)
before any engine exists. Known limitations are recorded in code/docs/DECISIONS.md:
  * evidence-citation labels follow the convention "latest admissible artifact whose declared scope covers the
    resource's system and store" (observed in the public samples, not stated by the contract);
  * which resources a deletion verification covers (account absent, retained audit record present) follows the
    public-sample convention and the contract's "required retained record remains available" rule.

Two label files per fixture:
  expected_output.csv    full answer, only for cases the contract determines completely
  expected_internal.json engine-agnostic expectations (intent, accepted/rejected/unresolved links, obligation
                         states) used for cases whose correct output is NOT a plain status (UNKNOWN handling)

Run: python3 code/evaluation/fixtures/build_fixtures.py   (deterministic; rewrites synth_v1/ and the manifest)
"""
import csv
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(REPO, "code"))
from ghostaudit.contract import OP_STATE, canonical_sort  # noqa: E402

OUT = os.path.join(HERE, "synth_v1")
REQ_AT, REP_AT, AUDIT_AT = "2026-06-01T09:00:00Z", "2026-06-02T09:00:00Z", "2026-06-15T12:00:00Z"
T_EARLY, T_BUNDLE, T_LEGAL, T_MAIN, T_R, T_LATE = (
    "2026-06-01T08:00:00Z", "2026-06-14T09:30:00Z", "2026-06-14T08:30:00Z",
    "2026-06-14T10:00:00Z", "2026-06-14T11:00:00Z", "2026-06-20T10:00:00Z",
)
ALL_SYSTEMS = ["account_service", "analytics_platform", "backup_service", "export_service", "integration_service",
               "search_service", "security_service", "support_platform"]
MAIN_SYSTEMS = [s for s in ALL_SYSTEMS if s != "export_service"]  # export_service deliberately NOT in scope

DDL = """CREATE TABLE snapshot_scope (origin_system TEXT PRIMARY KEY, captured_at TEXT NOT NULL);
CREATE TABLE customer_profiles (resource_id TEXT PRIMARY KEY, customer_reference TEXT, full_name TEXT, email TEXT, phone TEXT, email_hash TEXT, account_status TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE customer_search_documents (resource_id TEXT PRIMARY KEY, customer_reference TEXT, display_name TEXT, email TEXT, phone TEXT, email_hash TEXT, index_name TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE customer_analytics_profiles (resource_id TEXT PRIMARY KEY, customer_reference TEXT, email TEXT, phone TEXT, email_hash TEXT, audience_cohort TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE support_records (resource_id TEXT PRIMARY KEY, customer_reference TEXT, requester_name TEXT, requester_email TEXT, requester_phone TEXT, message_excerpt TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE customer_exports (resource_id TEXT PRIMARY KEY, customer_reference TEXT, owner_email TEXT, owner_phone TEXT, object_key TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE connector_subscriptions (resource_id TEXT PRIMARY KEY, customer_reference TEXT, customer_email TEXT, connector_name TEXT NOT NULL, enabled INTEGER NOT NULL CHECK (enabled IN (0,1)), last_delivery_status TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE backup_restore_entries (resource_id TEXT PRIMARY KEY, customer_reference TEXT, customer_email TEXT, archive_key TEXT NOT NULL, restore_allowed INTEGER NOT NULL CHECK (restore_allowed IN (0,1)), updated_at TEXT NOT NULL);
CREATE TABLE security_audit_records (resource_id TEXT PRIMARY KEY, subject_reference TEXT NOT NULL, event_code TEXT NOT NULL, retention_until TEXT NOT NULL, updated_at TEXT NOT NULL);"""

NAMES = {  # fictional
    1: ("Ilse", "Varga"), 2: ("Marta", "Quiroga"), 3: ("Haruto", "Sawada"), 4: ("Jonas", "Weber"),
    5: ("Nirmala", "Pereira"), 6: ("Oskar", "Lind"), 7: ("Tamsin", "Okoro"), 8: ("Bela", "Horvat"),
    9: ("Rui", "Carvalho"), 11: ("Selma", "Aydin"), 12: ("Dara", "Fenwick"), 13: ("Yusuf", "Marek"),
    14: ("Petra", "Novotny"), 15: ("Lorcan", "Brady"), 16: ("Anouk", "Visser"), 17: ("Emeka", "Obi"),
}
H = lambda s: hashlib.sha256(s.encode()).hexdigest()  # noqa: E731


def uid(n):
    return f"user_f{n:02d}"


def email(n):
    f, l = NAMES[n]
    return f"{f.lower()}.{l.lower()}@example.org"


def sql_val(v):
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return f"'{v}'"
    return "'" + str(v).replace("'", "''") + "'"


def inventory_sql(captured, scope, rows):
    """rows: list of (table, tuple_of_values)."""
    lines = ["PRAGMA foreign_keys=ON;", "BEGIN TRANSACTION;", DDL]
    for s in scope:
        lines.append(f"INSERT INTO snapshot_scope VALUES ({sql_val(s)}, {sql_val(captured)});")
    for table, vals in rows:
        lines.append(f"INSERT INTO {table} VALUES ({', '.join(sql_val(v) for v in vals)});")
    lines += ["COMMIT;", f"-- snapshot_completed_at={captured}", ""]
    return "\n".join(lines)


def account_row(n, status="ACTIVE", t=T_EARLY):
    f, l = NAMES[n]
    return ("customer_profiles", (f"account_f{n:02d}", None, f"{f} {l}", email(n), None, H(email(n)), status, t))


def audit_row(n, t=T_MAIN):
    return ("security_audit_records", (f"audit_record_f{n:02d}", uid(n), "ACCOUNT_DELETION_RECORDED", "2031-12-31T23:59:59Z", t))


def search_row(rid, em, t):
    return ("customer_search_documents", (rid, None, None, em, None, None, "customer_directory_v3", t))


def analytics_row(rid, em, eh, t):
    return ("customer_analytics_profiles", (rid, None, em, None, eh, "returning_customer", t))


def replica_sql(captured, topology, tables):
    out = ["-- Ghost Data Still Exists: point-in-time database snapshot (fictional fixture)",
           "-- Dialect: SQLite-compatible SQL", f"-- Captured at: {captured}", f"-- Database topology: {topology}",
           "-- Compare the primary and any replica tables for replication drift.", "", "BEGIN TRANSACTION;"]
    for name, (cols_ddl, rows) in tables.items():
        out.append(f"CREATE TABLE {name} (\n{cols_ddl}\n);")
        for r in rows:
            out.append(f"INSERT INTO \"{name}\" VALUES({', '.join(sql_val(v) for v in r)});")
    out += ["COMMIT;", ""]
    return "\n".join(out)


ACCT_DDL = ("resource_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, full_name TEXT NOT NULL, email TEXT NOT NULL, "
            "phone TEXT NOT NULL, account_status TEXT NOT NULL, updated_at TEXT NOT NULL")
DOC_DDL = ("resource_id TEXT PRIMARY KEY, origin_system TEXT NOT NULL, collection_name TEXT NOT NULL, "
           "record_json TEXT NOT NULL CHECK (json_valid(record_json)), updated_at TEXT NOT NULL")


def build():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    for d in ("evidence/databases", "evidence/records", "evidence/logs"):
        os.makedirs(os.path.join(OUT, d))

    deleting = [4, 5, 6, 7, 8, 9, 11, 12, 13, 15, 16, 14, 17]
    na_cases = {1: "I need a copy of last year's invoices for my records. Please leave my profile and purchase history in place.",
                2: "Quiero actualizar mi correo electrónico; por favor no elimine nada de mi cuenta.",
                3: "注文履歴のデータをエクスポートしてください。アカウントは削除しないでください。"}
    texts = {n: "Please erase the account linked to this email address and the personal data attached to it." for n in deleting}
    texts[4] = "Bitte löschen Sie mein Konto und alle damit verbundenen persönlichen Daten."

    cases = list(range(1, 18))
    if 10 in cases:
        cases.remove(10)  # no case 10: numbering kept stable with the label notes
    cid = lambda n: f"fx_case_{n:02d}"  # noqa: E731

    # ---- identities, audit log -------------------------------------------------------------
    ident, audit = [], []
    hist11 = f"selma.aydin.old@example.org"
    hist13 = f"yusuf.marek.old@example.org"
    new16 = "anouk.visser.new@example.org"
    for n in cases:
        e = email(n)
        t = "2026-01-10T00:00:00Z"
        if n == 11:
            audit.append(("fxa_01", uid(n), "2026-05-01T08:00:00Z", "email", hist11, e))
            audit.append(("fxa_02", uid(n), "2026-05-01T08:00:00Z", "email_hash", H(hist11), H(e)))
            t = "2026-05-01T08:00:00Z"
        if n == 13:
            audit.append(("fxa_03", uid(n), "2026-04-01T08:00:00Z", "email", hist13, e))
            audit.append(("fxa_04", uid(n), "2026-04-01T08:00:00Z", "email_hash", H(hist13), H(e)))
            t = "2026-04-01T08:00:00Z"
        if n == 16:  # identity change AFTER audit_at
            audit.append(("fxa_05", uid(n), "2026-06-20T08:00:00Z", "email", e, new16))
            audit.append(("fxa_06", uid(n), "2026-06-20T08:00:00Z", "email_hash", H(e), H(new16)))
            ident.append((uid(n), " ".join(NAMES[n]), new16, "+31 6 5550 0016", H(new16), "2026-06-20T08:00:00Z"))
            continue
        ident.append((uid(n), " ".join(NAMES[n]), e, f"+1 555 010 {n:04d}", H(e), t))

    # ---- requests --------------------------------------------------------------------------
    reqs = []
    for n in cases:
        req_email = hist11 if n == 11 and False else email(n)  # F11 requests with CURRENT email; history is on evidence
        if n == 13:
            req_email = hist13  # F13 requests with a HISTORICAL email
        r_at, rep_at = REQ_AT, REP_AT
        if n == 17:
            r_at, rep_at = "2026-06-01T10:00:00Z", "2026-06-02T08:00:00Z"
        text = na_cases.get(n) or texts[n]
        status = "COMPLETE" if n in (4, 5, 9, 12, 15) else "NOT_STARTED"
        reqs.append((cid(n), req_email, r_at, status, rep_at, AUDIT_AT, text))

    # ---- evidence artifacts ----------------------------------------------------------------
    # S_early: links (account rows with emails, plus resources linked by identifier before deletion)
    early = []
    for n in (4, 5, 6, 7, 8, 9, 11, 12, 13, 15, 16):
        early.append(account_row(n))
    early.append(analytics_row("analytics_f04", email(4), None, T_EARLY))
    early.append(search_row("search_f05", email(5), T_EARLY))
    early.append(search_row("search_f12", email(12), T_EARLY))
    early.append(search_row("search_f16", email(16), T_EARLY))
    s_early = inventory_sql(T_EARLY, ALL_SYSTEMS, early)

    # S_main: current state at the cut (export_service NOT in scope)
    main = []
    for n in (4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17):
        main.append(audit_row(n))
    main.append(analytics_row("analytics_f04", None, None, T_MAIN))                      # F04 anonymized
    main.append(search_row("search_f12d", "dara.fenwick.jr@example.org", T_MAIN))       # F12 decoy (near-miss)
    main.append(("connector_subscriptions", ("data_flow_f11", None, email(11), "customer_events_connector", 1, "delivered", T_MAIN)))
    main.append(("backup_restore_entries", ("backup_f11", None, hist11, "archive/customer-data/backup_f11.tar.zst", 1, T_MAIN)))
    main.append(analytics_row("analytics_f13", None, H(hist13), T_MAIN))                # F13 historical-hash residue
    main.append(search_row("search_f16", email(16), T_MAIN))                            # F16 own residue
    main.append(search_row("search_f16b", new16, T_MAIN))                               # F16 identifier not yet valid
    s_main = inventory_sql(T_MAIN, MAIN_SYSTEMS, main)

    # R: account primary + failover (F06 residue only in failover)
    others = [("account_9001", "user_9001", "Unrelated One", "unrelated.one@example.org", "+1 555 0100", "ACTIVE", T_R),
              ("account_9002", "user_9002", "Unrelated Two", "unrelated.two@example.org", "+1 555 0101", "ACTIVE", T_R)]
    f06 = ("account_f06", uid(6), " ".join(NAMES[6]), email(6), "+1 555 010 0006", "ACTIVE", T_R)
    r_sql = replica_sql(T_R, "failover_replica", {
        "customer_profiles_failover_replica": (ACCT_DDL, others + [f06]),
        "customer_profiles_primary": (ACCT_DDL, others),
    })

    # B: bundle with tombstones (F08 exposed, F09 clean)
    bundle = {"exported_at": T_BUNDLE, "source": "records_assurance_service", "snapshots": [{
        "captured_at": T_BUNDLE, "data_store": "identity_service", "collection": "deleted_customer_references",
        "records": [
            {"resource_id": "tombstone_f08", "subject_reference": uid(8), "name": " ".join(NAMES[8]), "email": email(8),
             "phone": "+36 20 555 0008", "email_hash": H(email(8)), "account_status": "DELETED"},
            {"resource_id": "tombstone_f09", "subject_reference": uid(9), "name": None, "email": None, "phone": None,
             "email_hash": None, "account_status": "DELETED"},
        ]}]}

    # L: legal hold present in primary AND replica (retention permits it)
    hold = json.dumps({"resource_id": "legal_hold_f15", "subject_reference": uid(15), "order_reference": "ORD-F15",
                       "retention_reason": "payment_dispute_and_tax_record", "retained_until": "2033-12-31T23:59:59Z"})
    legal_row = ("legal_hold_f15", "legal_service", "retained_order_records", hold, T_LEGAL)
    l_sql = replica_sql(T_LEGAL, "regional_replicas", {
        "customer_data_primary": (DOC_DDL, [legal_row]),
        "customer_data_replica_ap_south": (DOC_DDL, [legal_row]),
    })

    # S_late: captured AFTER audit_at; old observations of residue that must be ignored (F05)
    late = [search_row("search_f05", email(5), "2026-06-05T00:00:00Z")]
    s_late = inventory_sql(T_LATE, ALL_SYSTEMS, late)

    # X: adversarial export, available before audit_at but containing a record observed after it (F05)
    export_x = {"exported_at": T_MAIN, "region": "global", "source": "records_assurance_gateway", "service_exports": {
        "search_service": {"index_queries": [{"hits": 1, "observed_at": "2026-06-16T00:00:00Z",
                                              "query": email(5), "resource_id": "search_f05b"}]}}}

    files = [  # (file_id, relative path, origin, captured_at, content)
        ("evidence_f01", "evidence/databases/customer_data_inventory_20260601.sql", "customer_data_inventory_capture", T_EARLY, s_early),
        ("evidence_f02", "evidence/databases/customer_data_inventory_20260614.sql", "customer_data_inventory_capture", T_MAIN, s_main),
        ("evidence_f03", "evidence/databases/customer_accounts_failover_replica_20260614.sql", "customer_account_failover_replica_capture", T_R, r_sql),
        ("evidence_f04", "evidence/records/customer_data_snapshot_bundle_20260614.json", "records_assurance_snapshot_bundle", T_BUNDLE, json.dumps(bundle, indent=2, sort_keys=True) + "\n"),
        ("evidence_f05", "evidence/databases/customer_data_regional_replicas_20260614.sql", "customer_data_regional_replicas_capture", T_LEGAL, l_sql),
        ("evidence_f06", "evidence/databases/customer_data_inventory_20260620.sql", "customer_data_inventory_capture", T_LATE, s_late),
        ("evidence_f07", "evidence/records/service_resource_export_20260614.json", "service_resource_export", T_MAIN, json.dumps(export_x, indent=2, sort_keys=True) + "\n"),
    ]
    for fid, rel, origin, cap, content in files:
        with open(os.path.join(OUT, rel), "w", encoding="utf-8") as f:
            f.write(content)

    def w(name, header, rows):
        with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f, lineterminator="\n")
            wr.writerow(header)
            wr.writerows(rows)

    w("deletion_requests.csv", ["case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"], reqs)
    w("user_identities.csv", ["user_id", "name", "email", "phone", "email_hash", "updated_at"], ident)
    w("user_audit_log.csv", ["audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"], audit)
    w("evidence_files.csv", ["file_id", "file_path", "origin", "captured_at"], [(a, b, c, d) for a, b, c, d, _ in files])
    shutil.copy(os.path.join(REPO, "dataset", "deletion_rules.csv"), os.path.join(OUT, "deletion_rules.csv"))

    activity = [
        ("fxact_001", "2026-06-02T07:45:00Z", "DELETE_RECORD", "deletion_worker", "account_service", "account_f14x", "SUCCESS",
         "Deletion worker submitted primary profile account_f14x to account_service."),
        ("fxact_002", "2026-06-02T07:30:00Z", "LINK_RESOURCE_IDENTITY", "data_catalog", "export_service", "export_f07", "SUCCESS",
         f"Data catalog linked export_f07 (export_f07) to {email(7)} and {uid(7)}."),
        ("fxact_003", "2026-06-01T12:00:00Z", "DELETE_RECORD", "deletion_worker", "account_service", "account_f04", "FAILED",
         "Deletion worker submitted primary profile account_f04 to account_service."),
    ]
    w("system_activity.csv", ["activity_id", "event_time", "event_type", "source_system", "target_system", "resource_id", "reported_result", "details"], activity)

    # ---- labels ----------------------------------------------------------------------------
    E_EARLY, E_MAIN, E_R, E_B, E_L = "evidence_f01", "evidence_f02", "evidence_f03", "evidence_f04", "evidence_f05"

    def step(phase, system, resource, op, ev=""):
        return {"step_no": 0, "phase": phase, "system_id": system, "resource_id": resource, "operation": op,
                "state": OP_STATE[op], "evidence_id": ev}

    def ver(system, resource, op, ev=""):
        return step("VERIFICATION", system, resource, op, ev)

    def acct_audit(n, ev_acct, ev_audit):
        return [ver("account_service", f"account_f{n:02d}", "VERIFY_RECORD_ABSENT", ev_acct),
                ver("security_service", f"audit_record_f{n:02d}", "VERIFY_RECORD_PRESENT", ev_audit)]

    exp = {}
    for n in na_cases:
        exp[cid(n)] = ("NOT_APPLICABLE", [])
    exp[cid(4)] = ("COMPLETE", acct_audit(4, E_R, E_MAIN) + [ver("analytics_platform", "analytics_f04", "VERIFY_RECORD_ANONYMIZED", E_MAIN)])
    exp[cid(5)] = ("COMPLETE", acct_audit(5, E_R, E_MAIN) + [ver("search_service", "search_f05", "VERIFY_RECORD_ABSENT", E_MAIN)])
    exp[cid(6)] = ("INCOMPLETE", [step("FINDING", "account_service", "account_f06", "REPORT_REMAINING_RECORD", E_R),
                                  step("REMEDIATION", "account_service", "account_f06", "DELETE_RECORD")] + acct_audit(6, "", ""))
    exp[cid(8)] = ("INCOMPLETE", [step("FINDING", "identity_service", "tombstone_f08", "REPORT_EXPOSED_PII", E_B),
                                  step("REMEDIATION", "identity_service", "tombstone_f08", "REDACT_RECORD")] + acct_audit(8, "", "")
                   + [ver("identity_service", "tombstone_f08", "VERIFY_RECORD_REDACTED")])
    exp[cid(9)] = ("COMPLETE", acct_audit(9, E_R, E_MAIN) + [ver("identity_service", "tombstone_f09", "VERIFY_RECORD_REDACTED", E_B)])
    exp[cid(11)] = ("INCOMPLETE", [step("FINDING", "integration_service", "data_flow_f11", "REPORT_ACTIVE_DATA_FLOW", E_MAIN),
                                   step("FINDING", "backup_service", "backup_f11", "REPORT_RESTORE_RISK", E_MAIN),
                                   step("REMEDIATION", "integration_service", "data_flow_f11", "DISABLE_DATA_FLOW"),
                                   step("REMEDIATION", "backup_service", "backup_f11", "BLOCK_RESTORE")] + acct_audit(11, "", "")
                    + [ver("integration_service", "data_flow_f11", "VERIFY_DATA_FLOW_DISABLED"),
                       ver("backup_service", "backup_f11", "VERIFY_RESTORE_BLOCKED")])
    exp[cid(12)] = ("COMPLETE", acct_audit(12, E_R, E_MAIN) + [ver("search_service", "search_f12", "VERIFY_RECORD_ABSENT", E_MAIN)])
    exp[cid(13)] = ("INCOMPLETE", [step("FINDING", "analytics_platform", "analytics_f13", "REPORT_EXPOSED_PII", E_MAIN),
                                   step("REMEDIATION", "analytics_platform", "analytics_f13", "ANONYMIZE_RECORD")] + acct_audit(13, "", "")
                    + [ver("analytics_platform", "analytics_f13", "VERIFY_RECORD_ANONYMIZED")])
    exp[cid(15)] = ("COMPLETE", acct_audit(15, E_R, E_MAIN) + [ver("legal_service", "legal_hold_f15", "VERIFY_RECORD_PRESENT", E_L)])
    exp[cid(16)] = ("INCOMPLETE", [step("FINDING", "search_service", "search_f16", "REPORT_REMAINING_RECORD", E_MAIN),
                                   step("REMEDIATION", "search_service", "search_f16", "DELETE_RECORD")] + acct_audit(16, "", "")
                    + [ver("search_service", "search_f16", "VERIFY_RECORD_ABSENT")])

    # F06 must also list account_f06 absence/finding only from R; F06 audit record linked via subject_reference (S_main)
    rows = []
    for c in sorted(exp):
        status, steps = exp[c]
        rows.append((c, status, json.dumps(canonical_sort(steps), sort_keys=True, separators=(",", ":")) if steps else "[]"))
    w("expected_output.csv", ["case_id", "deletion_status", "steps_json"], rows)

    internal = {
        cid(1): {"intent": "NOT_DELETION"}, cid(2): {"intent": "NOT_DELETION"}, cid(3): {"intent": "NOT_DELETION"},
        cid(4): {"intent": "DELETION", "links_accepted": ["analytics_f04", "account_f04", "audit_record_f04"],
                 "note": "analytics_f04 is anonymized at the cut; link holds via the earlier observation carrying the email (chain d)"},
        cid(5): {"intent": "DELETION", "must_not_cite": ["evidence_f06", "evidence_f07"],
                 "links_rejected": ["search_f05b"],
                 "note": "evidence_f06 is captured after audit_at (old row inside a later artifact); evidence_f07 is available before "
                         "audit_at but its record is observed after audit_at. Both must be ignored; search_f05b must not be linked or cited."},
        cid(6): {"intent": "DELETION", "note": "residue only in the failover replica of an artifact covering primary and failover"},
        cid(7): {"intent": "DELETION", "status": "UNDETERMINED",
                 "links_accepted": ["export_f07", "audit_record_f07"],
                 "obligations": {"export_f07": "UNKNOWN:no_admissible_evidence", "audit_record_f07": "COMPLIANT"},
                 "must_not_emit": ["VERIFY_RECORD_ABSENT for export_f07", "status COMPLETE"],
                 "note": "export_service is not in the scope of any admissible snapshot, so absence of export_f07 is not evidence"},
        cid(8): {"intent": "DELETION", "note": "tombstone present with name/email/phone/hash -> assessed for prohibited identifiers"},
        cid(9): {"intent": "DELETION", "note": "tombstone holds only the stable user reference -> compliant"},
        cid(11): {"intent": "DELETION", "links_accepted": ["data_flow_f11", "backup_f11"],
                  "note": "backup_f11 links through the HISTORICAL email in force before the 2026-05-01 change"},
        cid(12): {"intent": "DELETION", "links_rejected": ["search_f12d"],
                  "note": "search_f12d email is a near-miss (.jr) of the subject email and must not link"},
        cid(13): {"intent": "DELETION", "links_accepted": ["analytics_f13"],
                  "note": "linked through the historical email_hash (audit log, change on 2026-04-01 <= audit_at)"},
        cid(14): {"intent": "DELETION", "status": "UNDETERMINED", "links_accepted": ["audit_record_f14"],
                  "links_unresolved": [{"candidates": ["account_f14x"], "reason": "unresolved_link"}],
                  "obligations": {"audit_record_f14": "COMPLIANT", "subject_account": "UNKNOWN:unresolved_link"},
                  "must_not_emit": ["any step naming account_f14x", "status COMPLETE"],
                  "note": "account_f14x is reachable only through an activity-window match shared with fx_case_17"},
        cid(15): {"intent": "DELETION", "note": "retained legal hold is present in primary and replica; that is permitted"},
        cid(16): {"intent": "DELETION", "links_accepted": ["search_f16"], "links_rejected": ["search_f16b"],
                  "note": "the subject's current email only becomes theirs on 2026-06-20, after audit_at; evidence under it cannot link"},
        cid(17): {"intent": "DELETION", "status": "UNDETERMINED", "links_accepted": ["audit_record_f17"],
                  "links_unresolved": [{"candidates": ["account_f14x"], "reason": "unresolved_link"}],
                  "obligations": {"audit_record_f17": "COMPLIANT", "subject_account": "UNKNOWN:unresolved_link"},
                  "must_not_emit": ["any step naming account_f14x", "status COMPLETE"],
                  "note": "same shared candidate as fx_case_14; neither case may claim it (order/batch independence)"},
    }
    with open(os.path.join(OUT, "expected_internal.json"), "w", encoding="utf-8") as f:
        json.dump(internal, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")

    # ---- freeze manifest --------------------------------------------------------------------
    manifest = []
    for root, _, names in os.walk(OUT):
        for nm in sorted(names):
            p = os.path.join(root, nm)
            manifest.append((os.path.relpath(p, OUT), hashlib.sha256(open(p, "rb").read()).hexdigest()))
    manifest.sort()
    with open(os.path.join(HERE, "synth_v1.sha256"), "w") as f:
        for rel, h in manifest:
            f.write(f"{h}  {rel}\n")
    print(f"built {len(cases)} cases, {len(manifest)} files; manifest -> synth_v1.sha256")


if __name__ == "__main__":
    build()
