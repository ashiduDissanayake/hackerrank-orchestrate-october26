"""Builds the frozen labeled fixture dataset `synth_v2/` (v1 + revised labels + subject-level account-proof scenarios).

WHY v2 EXISTS (recorded in code/docs/DECISIONS.md): after the closeout review the account obligation was split into
 (1) can the SUBJECT's account state be established (subject-keyed query of an authoritative snapshot), and
 (2) can the original account RESOURCE ID be recovered.
fx_case_14 / fx_case_17 in v1 were labeled "account unresolved" because the orphan resource id could not be linked; under the
corrected reasoning the admissible post-request primary+failover snapshot (evidence_f03) carries no row with the subject's
identifiers, so the subject-level state is established ABSENT while account_f14x stays an unlinked, never-emitted candidate.
Those two labels were revised BEFORE running the engine against them. v1 stays untouched as history (its own manifest and
guard test remain); v2 = v1 data + the revised labels + four new scenarios, each in its own month so snapshots cannot leak
between scenarios (earlier-month snapshots are pre-request, later-month ones are after the cutoff).

New scenarios (all fictional):
  fx_case_21 (Mar) subject absent from a clean primary+failover snapshot, other accounts present  -> COMPLETE (audit record step only)
  fx_case_22 (Jul) clean primary but the failover replica holds the subject's row                 -> INCOMPLETE (populated-replica control)
  fx_case_23 (Apr) declared snapshot also holds an unattributable account row                      -> UNDETERMINED (cannot exclude it)
  fx_case_24 (May) the only account snapshot predates the request                                  -> UNDETERMINED (no post-request state)
Authoring defect found at the first engine run and fixed BEFORE v2 was frozen or committed: the fx_case_24 audit-record inventory
declared account_service in its scope, so it was itself a post-request account snapshot and the engine correctly used it. It now
declares no account scope (inventory_with_audit(covers_accounts=False)).
Run: python3 code/evaluation/fixtures/build_fixtures_v2.py   (deterministic)
"""
import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_fixtures as v1  # noqa: E402
from ghostaudit.contract import OP_STATE, canonical_sort  # noqa: E402

OUT2 = os.path.join(HERE, "synth_v2")
MANIFEST2 = os.path.join(HERE, "synth_v2.sha256")
H = v1.H

NEW = {21: ("Mirela", "Constantin"), 22: ("Tobias", "Eriksen"), 23: ("Nadine", "Okafor"), 24: ("Haruki", "Oda")}
MONTH = {21: "2026-03", 22: "2026-07", 23: "2026-04", 24: "2026-05"}


def append_csv(path, rows):
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def write(rel, text):
    p = os.path.join(OUT2, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def step(phase, system, resource, op, ev=""):
    return {"step_no": 0, "phase": phase, "system_id": system, "resource_id": resource, "operation": op, "state": OP_STATE[op], "evidence_id": ev}


def other_row(n, t):
    return (f"account_{9100 + n}", f"user_{9100 + n}", f"Unrelated Person {n}", f"unrelated.{n}@example.org", "+1 555 0199", "ACTIVE", t)


def inventory_with_audit(n, t, covers_accounts=True):
    """Typed inventory carrying the subject's audit record. With covers_accounts=False the snapshot declares NO account scope
    and lists no account row, so it cannot act as an account snapshot (fx_case_24 needs that)."""
    rows = [v1.audit_row(n, t)]
    scope = v1.MAIN_SYSTEMS
    if covers_accounts:
        r = other_row(n, t)
        rows.append(("customer_profiles", (r[0], r[1], r[2], r[3], None, H(r[3]), r[5], t)))
    else:
        scope = [s for s in v1.MAIN_SYSTEMS if s != "account_service"]
    return v1.inventory_sql(t, scope, rows)


def build():
    v1.OUT, v1.MANIFEST = OUT2, MANIFEST2
    v1.build()                      # base: identical data to v1
    v1.NAMES.update(NEW)

    reqs, ident, files = [], [], []
    exp_steps = {}
    internal_add = {}

    def person(n):
        return v1.uid(n), " ".join(NEW[n]), v1.email(n)

    for n in NEW:
        uid, name, em = person(n)
        m = MONTH[n]
        ident.append((uid, name, em, f"+1 555 02{n:02d}", H(em), "2026-01-10T00:00:00Z"))
        reqs.append((f"fx_case_{n}", em, f"{m}-01T09:00:00Z" if n != 24 else "2026-05-10T09:00:00Z", "NOT_STARTED",
                     f"{m}-02T09:00:00Z" if n != 24 else "2026-05-11T09:00:00Z", f"{m}-15T12:00:00Z" if n != 24 else "2026-05-25T12:00:00Z",
                     "Please erase the account linked to this email address and the personal data attached to it."))

    # --- G1 (Mar): clean snapshot pair --------------------------------------------------------------------------------
    t1, t2 = "2026-03-10T10:00:00Z", "2026-03-10T11:00:00Z"
    write("evidence/databases/customer_data_inventory_20260310.sql", inventory_with_audit(21, t1))
    others = [other_row(21, t2)]
    write("evidence/databases/customer_accounts_failover_replica_20260310.sql", v1.replica_sql(t2, "failover_replica", {
        "customer_profiles_failover_replica": (v1.ACCT_DDL, others), "customer_profiles_primary": (v1.ACCT_DDL, others)}))
    files += [("evidence_g01", "evidence/databases/customer_data_inventory_20260310.sql", "customer_data_inventory_capture", t1),
              ("evidence_g02", "evidence/databases/customer_accounts_failover_replica_20260310.sql", "customer_account_failover_replica_capture", t2)]
    exp_steps["fx_case_21"] = ("COMPLETE", [step("VERIFICATION", "security_service", "audit_record_f21", "VERIFY_RECORD_PRESENT", "evidence_g01")])
    internal_add["fx_case_21"] = {"intent": "DELETION", "links_accepted": ["audit_record_f21"],
        "obligations": {"audit_record_f21": "COMPLIANT", "subject_account": "COMPLIANT:no_profile_for_subject_in_snapshot"},
        "must_not_emit": ["any step with resource_id None", "an invented account resource id"],
        "note": "evidence_g02 is an admissible post-request primary+failover snapshot whose rows all carry other users' identifiers"}

    # --- G2 (Jul): populated-replica control ------------------------------------------------------------------------------
    t1, t2 = "2026-07-10T10:00:00Z", "2026-07-10T11:00:00Z"
    write("evidence/databases/customer_data_inventory_20260710.sql", inventory_with_audit(22, t1))
    mine = (f"account_f22", v1.uid(22), " ".join(NEW[22]), v1.email(22), "+1 555 0222", "ACTIVE", t2)
    o2 = other_row(22, t2)
    write("evidence/databases/customer_accounts_failover_replica_20260710.sql", v1.replica_sql(t2, "failover_replica", {
        "customer_profiles_failover_replica": (v1.ACCT_DDL, [o2, mine]), "customer_profiles_primary": (v1.ACCT_DDL, [o2])}))
    files += [("evidence_g03", "evidence/databases/customer_data_inventory_20260710.sql", "customer_data_inventory_capture", t1),
              ("evidence_g04", "evidence/databases/customer_accounts_failover_replica_20260710.sql", "customer_account_failover_replica_capture", t2)]
    exp_steps["fx_case_22"] = ("INCOMPLETE", [
        step("FINDING", "account_service", "account_f22", "REPORT_REMAINING_RECORD", "evidence_g04"),
        step("REMEDIATION", "account_service", "account_f22", "DELETE_RECORD"),
        step("VERIFICATION", "account_service", "account_f22", "VERIFY_RECORD_ABSENT"),
        step("VERIFICATION", "security_service", "audit_record_f22", "VERIFY_RECORD_PRESENT")])
    internal_add["fx_case_22"] = {"intent": "DELETION", "links_accepted": ["account_f22", "audit_record_f22"],
        "note": "primary is clean but the failover replica holds the subject's row (matched by the user id and email): a clean primary cannot discharge a populated replica"}

    # --- G3 (Apr): declared snapshot also holds an unattributable row ------------------------------------------------------
    t1, t2 = "2026-04-10T10:00:00Z", "2026-04-10T11:00:00Z"
    write("evidence/databases/customer_data_inventory_20260410.sql", inventory_with_audit(23, t1))
    bundle = {"exported_at": t2, "source": "records_assurance_service", "snapshots": [{
        "captured_at": t2, "data_store": "account_service", "collection": "customer_profiles", "records": [
            {"resource_id": "account_9323", "customer_reference": "user_9323", "email": "unrelated.23@example.org", "account_status": "ACTIVE"},
            {"resource_id": "account_g23x", "customer_reference": None, "email": None, "phone": None, "email_hash": None, "full_name": None, "account_status": "ACTIVE"}]}]}
    write("evidence/records/customer_data_snapshot_bundle_20260410.json", json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    files += [("evidence_g05", "evidence/databases/customer_data_inventory_20260410.sql", "customer_data_inventory_capture", t1),
              ("evidence_g06", "evidence/records/customer_data_snapshot_bundle_20260410.json", "records_assurance_snapshot_bundle", t2)]
    internal_add["fx_case_23"] = {"intent": "DELETION", "status": "UNDETERMINED", "links_accepted": ["audit_record_f23"],
        "obligations": {"audit_record_f23": "COMPLIANT", "subject_account": "UNKNOWN:unresolved_link"},
        "must_not_emit": ["any step naming account_g23x", "status COMPLETE"],
        "note": "account_g23x carries no identifier, so it could be the subject's: the snapshot cannot exclude it and absence is not proven"}

    # --- G4 (May): the only account snapshot predates the request ------------------------------------------------------------
    t1, t2 = "2026-05-20T10:00:00Z", "2026-05-05T11:00:00Z"
    write("evidence/databases/customer_data_inventory_20260520.sql", inventory_with_audit(24, t1, covers_accounts=False))
    o4 = [other_row(24, t2)]
    write("evidence/databases/customer_accounts_failover_replica_20260505.sql", v1.replica_sql(t2, "failover_replica", {
        "customer_profiles_failover_replica": (v1.ACCT_DDL, o4), "customer_profiles_primary": (v1.ACCT_DDL, o4)}))
    files += [("evidence_g07", "evidence/databases/customer_data_inventory_20260520.sql", "customer_data_inventory_capture", t1),
              ("evidence_g08", "evidence/databases/customer_accounts_failover_replica_20260505.sql", "customer_account_failover_replica_capture", t2)]
    internal_add["fx_case_24"] = {"intent": "DELETION", "status": "UNDETERMINED", "links_accepted": ["audit_record_f24"],
        "obligations": {"audit_record_f24": "COMPLIANT", "subject_account": "UNKNOWN:unresolved_link"},
        "must_not_emit": ["status COMPLETE"],
        "note": "evidence_g08 (2026-05-05) is older than the request (2026-05-10): it says nothing about the post-request state"}

    # --- revised v1 labels (fx_case_14 / fx_case_17) --------------------------------------------------------------------------
    for n in (14, 17):
        exp_steps[f"fx_case_{n}"] = ("COMPLETE", [step("VERIFICATION", "security_service", f"audit_record_f{n}", "VERIFY_RECORD_PRESENT", "evidence_f02")])

    # --- write the data files ---------------------------------------------------------------------------------------------------
    append_csv(os.path.join(OUT2, "deletion_requests.csv"), reqs)
    append_csv(os.path.join(OUT2, "user_identities.csv"), ident)
    append_csv(os.path.join(OUT2, "evidence_files.csv"), [(a, b, c, d) for a, b, c, d in files])
    with open(os.path.join(OUT2, "expected_output.csv"), newline="", encoding="utf-8") as f:
        rows = {r["case_id"]: r for r in csv.DictReader(f)}
    for cid, (status, steps) in exp_steps.items():
        rows[cid] = {"case_id": cid, "deletion_status": status, "steps_json": json.dumps(canonical_sort(steps), sort_keys=True, separators=(",", ":")) if steps else "[]"}
    from ghostaudit.validate import case_sort_key
    with open(os.path.join(OUT2, "expected_output.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for cid in sorted(rows, key=lambda c: case_sort_key(c.replace("fx_case_", "case_"))):
            w.writerow([cid, rows[cid]["deletion_status"], rows[cid]["steps_json"]])
    ip = os.path.join(OUT2, "expected_internal.json")
    internal = json.load(open(ip, encoding="utf-8"))
    for n in (14, 17):
        internal[f"fx_case_{n}"] = {"intent": "DELETION", "links_accepted": [f"audit_record_f{n}"],
            "obligations": {f"audit_record_f{n}": "COMPLIANT", "subject_account": "COMPLIANT:no_profile_for_subject_in_snapshot"},
            "must_not_emit": ["any step naming account_f14x", "any step with resource_id None"],
            "note": "REVISED in v2. account_f14x is still only an activity-window candidate and is never linked or emitted, but evidence_f03 (post-request "
                    "primary+failover snapshot) holds no row with the subject's identifiers, so the SUBJECT-level account state is established absent"}
    internal.update(internal_add)
    json.dump(internal, open(ip, "w", encoding="utf-8"), indent=2, sort_keys=True, ensure_ascii=False)
    open(ip, "a").write("\n")

    manifest = []
    for root, _, names in os.walk(OUT2):
        for nm in sorted(names):
            p = os.path.join(root, nm)
            manifest.append((os.path.relpath(p, OUT2), hashlib.sha256(open(p, "rb").read()).hexdigest()))
    manifest.sort()
    with open(MANIFEST2, "w") as f:
        for rel, h in manifest:
            f.write(f"{h}  {rel}\n")
    print(f"built synth_v2: {len(manifest)} files; manifest -> synth_v2.sha256")


if __name__ == "__main__":
    build()
