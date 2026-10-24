"""Builds the frozen labeled fixture dataset `synth_v3/` (v2 + four proof-boundary scenarios).

WHY v3 EXISTS (recorded in code/docs/DECISIONS.md): the 2026-10-25 independent review found two ways the subject-level account
proof could certify a case without having looked at the subject's profile:
  (a) a declared-EMPTY collection that is not a profile collection (account_service / notification_preferences) discharged the
      profile obligation, and
  (b) a clean post-request primary snapshot hid a failover replica whose last capture held an unattributable account row.
The fixes introduce profile-collection coverage, per-copy accounting, and a per-source promotion rule for weakly inferred document
exports. v2 is untouched (history, its own manifest and guard test remain); v3 = v2 data + four scenarios that exercise those rules
through the REAL extractors (JSON bundle, SQL replica tables, SQL document tables), each in its own month so scenarios cannot leak
into each other. Labels were written from the contract before the engine was run against them.

  fx_case_25 (Aug) only account_service snapshot is a declared-empty `notification_preferences` collection      -> UNDETERMINED
  fx_case_26 (Sep) weakly scoped document export that holds the subject's own records and a profile row of
                   another user (so profiles are part of the export) but no profile row for the subject       -> COMPLETE
  fx_case_27 (Oct) the same document export shape that holds NOTHING about the subject                         -> UNDETERMINED
  fx_case_28 (Nov) failover replica last captured BEFORE the request with an unattributable row; clean primary  -> UNDETERMINED
Scenario order matters: a failover capture with an unattributable row is (correctly) visible to every LATER case, because the row could be
anyone's, so that scenario is the last month and cannot leak into the others.
Run: python3 code/evaluation/fixtures/build_fixtures_v3.py   (deterministic)
"""
import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_fixtures as v1  # noqa: E402
import build_fixtures_v2 as v2  # noqa: E402
from ghostaudit.contract import canonical_sort  # noqa: E402

OUT3 = os.path.join(HERE, "synth_v3")
MANIFEST3 = os.path.join(HERE, "synth_v3.sha256")
H = v1.H

NEW = {25: ("Ingrid", "Solberg"), 26: ("Kofi", "Boateng"), 27: ("Lucia", "Ferraro"), 28: ("Dmitri", "Volkov")}
MONTH = {25: "2026-08", 26: "2026-09", 27: "2026-10", 28: "2026-11"}
REQ_DAY = {25: "01", 26: "01", 27: "01", 28: "10"}


def doc_row(rid, system, collection, payload, t):
    return (rid, system, collection, json.dumps({"resource_id": rid, **payload}, sort_keys=True, separators=(",", ":")), t)


def audit_doc(n, t):
    return doc_row(f"audit_record_f{n}", "security_service", "security_audit_events",
                   {"subject_reference": v1.uid(n), "event_name": "account_deletion_reviewed", "actor_type": "automated_privacy_workflow",
                    "integrity_seal": f"sha256:{n:064x}"}, t)


def other_audit_doc(n, t):
    return doc_row(f"audit_record_9{n}", "security_service", "security_audit_events",
                   {"subject_reference": f"user_9{n}", "event_name": "account_deletion_reviewed", "actor_type": "automated_privacy_workflow",
                    "integrity_seal": f"sha256:{9000 + n:064x}"}, t)


def other_profile_doc(n, t):
    return doc_row(f"account_9{n}", "account_service", "customer_profiles",
                   {"customer_reference": f"user_9{n}", "full_name": f"Unrelated Person {n}", "email": f"unrelated.{n}@example.org",
                    "phone": "+1 555 0199", "account_status": "ACTIVE"}, t)


def build():
    v2.OUT2, v2.MANIFEST2 = OUT3, MANIFEST3
    v2.build()                                 # base: identical data to v2 (and therefore v1)
    v1.NAMES.update(NEW)
    reqs, ident, files = [], [], []
    exp_steps, internal_add = {}, {}

    for n in NEW:
        em = v1.email(n)
        m, d = MONTH[n], REQ_DAY[n]
        ident.append((v1.uid(n), " ".join(NEW[n]), em, f"+1 555 02{n:02d}", H(em), "2026-01-10T00:00:00Z"))
        reqs.append((f"fx_case_{n}", em, f"{m}-{d}T09:00:00Z", "NOT_STARTED", f"{m}-{int(d) + 1:02d}T09:00:00Z", f"{m}-25T12:00:00Z",
                     "Please erase the account linked to this email address and the personal data attached to it."))

    # --- fx_case_25 (Aug): declared-empty collection that is not a profile collection ------------------------------------------
    t1, t2 = "2026-08-10T10:00:00Z", "2026-08-10T11:00:00Z"
    v2.write("evidence/databases/customer_data_inventory_20260810.sql", v2.inventory_with_audit(25, t1, covers_accounts=False))
    bundle = {"exported_at": t2, "source": "records_assurance_service", "snapshots": [{
        "captured_at": t2, "data_store": "account_service", "collection": "notification_preferences", "records": []}]}
    v2.write("evidence/records/customer_data_snapshot_bundle_20260810.json", json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    files += [("evidence_h01", "evidence/databases/customer_data_inventory_20260810.sql", "customer_data_inventory_capture", t1),
              ("evidence_h02", "evidence/records/customer_data_snapshot_bundle_20260810.json", "records_assurance_snapshot_bundle", t2)]
    internal_add["fx_case_25"] = {"intent": "DELETION", "status": "UNDETERMINED", "links_accepted": ["audit_record_f25"],
        "obligations": {"audit_record_f25": "COMPLIANT", "subject_account": "UNKNOWN:unresolved_link"},
        "must_not_emit": ["status COMPLETE"],
        "note": "evidence_h02 declares an EMPTY account_service collection, but the collection is notification_preferences: no profile collection was captured"}

    # --- fx_case_26 (Sep): weak document export that covers the subject ---------------------------------------------------------------
    t = "2026-09-10T11:00:00Z"
    primary27 = [audit_doc(26, t), other_audit_doc(26, t)]
    replica27 = [audit_doc(26, t), other_audit_doc(26, t), other_profile_doc(26, t)]
    v2.write("evidence/databases/customer_data_reporting_replica_20260910.sql", v1.replica_sql(t, "reporting_replica", {
        "customer_data_primary": (v1.DOC_DDL, primary27), "customer_data_reporting_replica": (v1.DOC_DDL, replica27)}))
    files += [("evidence_h05", "evidence/databases/customer_data_reporting_replica_20260910.sql", "customer_data_reporting_replica_capture", t)]
    exp_steps["fx_case_26"] = ("COMPLETE", [v2.step("VERIFICATION", "security_service", "audit_record_f26", "VERIFY_RECORD_PRESENT", "evidence_h05")])
    internal_add["fx_case_26"] = {"intent": "DELETION", "links_accepted": ["audit_record_f26"],
        "obligations": {"audit_record_f26": "COMPLIANT", "subject_account": "COMPLIANT:no_profile_for_subject_in_snapshot"},
        "must_not_emit": ["any step with resource_id None"],
        "note": "evidence_h05 is a document-table export (weak scope). It holds the subject's audit record in BOTH copies and exports profile rows "
                "(another user's, in the replica), so the profile collection is part of the export and the subject's data was included: "
                "the missing profile row is evidence of absence in both copies (per-source promotion)"}

    # --- fx_case_27 (Oct): the same export shape with nothing about the subject ----------------------------------------------------------
    t, t1 = "2026-10-10T11:00:00Z", "2026-10-10T12:00:00Z"
    v2.write("evidence/databases/customer_data_inventory_20261010.sql", v2.inventory_with_audit(27, t1, covers_accounts=False))
    primary28 = [other_audit_doc(27, t)]
    replica28 = [other_audit_doc(27, t), other_profile_doc(27, t)]
    v2.write("evidence/databases/customer_data_reporting_replica_20261010.sql", v1.replica_sql(t, "reporting_replica", {
        "customer_data_primary": (v1.DOC_DDL, primary28), "customer_data_reporting_replica": (v1.DOC_DDL, replica28)}))
    files += [("evidence_h06", "evidence/databases/customer_data_inventory_20261010.sql", "customer_data_inventory_capture", t1),
              ("evidence_h07", "evidence/databases/customer_data_reporting_replica_20261010.sql", "customer_data_reporting_replica_capture", t)]
    internal_add["fx_case_27"] = {"intent": "DELETION", "status": "UNDETERMINED", "links_accepted": ["audit_record_f27"],
        "obligations": {"audit_record_f27": "COMPLIANT", "subject_account": "UNKNOWN:unresolved_link"},
        "must_not_emit": ["status COMPLETE"],
        "note": "evidence_h07 exports other users' records only; an export that never mentions the subject says nothing about the subject's profile"}

    # --- fx_case_28 (Nov): failover replica last seen before the request with an unattributable row ------------------------------
    t0, t1 = "2026-11-05T11:00:00Z", "2026-11-20T10:00:00Z"
    o0 = v2.other_row(28, t0)
    ghost = ("account_g28x", "", "", "", "", "ACTIVE", t0)
    v2.write("evidence/databases/customer_accounts_failover_replica_20261105.sql", v1.replica_sql(t0, "failover_replica", {
        "customer_profiles_failover_replica": (v1.ACCT_DDL, [o0, ghost]), "customer_profiles_primary": (v1.ACCT_DDL, [o0])}))
    v2.write("evidence/databases/customer_data_inventory_20261120.sql", v2.inventory_with_audit(28, t1))
    files += [("evidence_h03", "evidence/databases/customer_accounts_failover_replica_20261105.sql", "customer_account_failover_replica_capture", t0),
              ("evidence_h04", "evidence/databases/customer_data_inventory_20261120.sql", "customer_data_inventory_capture", t1)]
    internal_add["fx_case_28"] = {"intent": "DELETION", "status": "UNDETERMINED", "links_accepted": ["audit_record_f28"],
        "obligations": {"audit_record_f28": "COMPLIANT", "subject_account": "UNKNOWN:unresolved_link"},
        "must_not_emit": ["any step naming account_g28x", "status COMPLETE"],
        "note": "evidence_h04 is a clean post-request primary snapshot, but the failover replica was last captured before the request (evidence_h03) "
                "with a row that carries no identifier: it could be the subject's and nothing shows its state afterwards"}

    # --- write the data files -------------------------------------------------------------------------------------------------------------
    v2.append_csv(os.path.join(OUT3, "deletion_requests.csv"), reqs)
    v2.append_csv(os.path.join(OUT3, "user_identities.csv"), ident)
    v2.append_csv(os.path.join(OUT3, "evidence_files.csv"), files)
    with open(os.path.join(OUT3, "expected_output.csv"), newline="", encoding="utf-8") as f:
        rows = {r["case_id"]: r for r in csv.DictReader(f)}
    for cid, (status, steps) in exp_steps.items():
        rows[cid] = {"case_id": cid, "deletion_status": status, "steps_json": json.dumps(canonical_sort(steps), sort_keys=True, separators=(",", ":")) if steps else "[]"}
    from ghostaudit.validate import case_sort_key
    with open(os.path.join(OUT3, "expected_output.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for cid in sorted(rows, key=lambda c: case_sort_key(c.replace("fx_case_", "case_"))):
            w.writerow([cid, rows[cid]["deletion_status"], rows[cid]["steps_json"]])
    ip = os.path.join(OUT3, "expected_internal.json")
    internal = json.load(open(ip, encoding="utf-8"))
    internal.update(internal_add)
    json.dump(internal, open(ip, "w", encoding="utf-8"), indent=2, sort_keys=True, ensure_ascii=False)
    open(ip, "a").write("\n")

    manifest = []
    for root, _, names in os.walk(OUT3):
        for nm in sorted(names):
            p = os.path.join(root, nm)
            manifest.append((os.path.relpath(p, OUT3), hashlib.sha256(open(p, "rb").read()).hexdigest()))
    manifest.sort()
    with open(MANIFEST3, "w") as f:
        for rel, h in manifest:
            f.write(f"{h}  {rel}\n")
    print(f"built synth_v3: {len(manifest)} files; manifest -> synth_v3.sha256")


if __name__ == "__main__":
    build()
