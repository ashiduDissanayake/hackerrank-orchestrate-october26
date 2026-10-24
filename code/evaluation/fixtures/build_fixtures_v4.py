"""Builds the frozen labeled fixture dataset `synth_v4/` (v3 + seven scenarios for the 2026-10-25 relationship, absence, label and
episode fixes). v1, v2 and v3 are untouched (their manifests and guard tests remain); v4 = v3 data + the cases below, each in its own
month and BEFORE the earlier fixtures' months so that no scenario leaks into another. Labels were written from the contract before the
engine was run against them.

  fx_case_29 (2026-01)  a search document names its source account (source_resource_id); the account has no observation of its own and
                        was already gone in an earlier declared snapshot than the document was indexed     -> INCOMPLETE (search finding,
                        account verification from the reference alone)
  fx_case_31 (2025-12)  EARLIER request by subject S (window Dec 1-5)
  fx_case_30 (2026-02)  LATER request by the same subject (Feb 10-25); evidence of the earlier window is carried over, evidence of this
                        request is not                                                                      -> INCOMPLETE, steps for this episode only
  fx_case_32 (2025-11)  a tombstone lookup labeled REDACTED that returns the subject's email and name           -> INCOMPLETE (exposed PII)
  fx_case_33 (2025-10)  the same lookup labeled REDACTED that carries the email only as the lookup key          -> COMPLETE
  fx_case_34 (2025-09)  a linked profile seen present; a LATER declared-empty `notification_preferences` bundle AND a later
                        inventory that declares account_service but has no profile table                       -> INCOMPLETE (still present)
  fx_case_35 (2025-08)  the same, but a LATER explicit lookup of the account returns 404                    -> COMPLETE (valid absence)
Authoring note, found BEFORE v4 was frozen: fx_case_35 was first labeled with a later declared-empty `customer_profiles` bundle as the valid
absence. The public sample case_24 shows the opposite (a profile lookup returns the account, a declared-empty bundle captured later does not
make it absent, and the public answer reports it present), and the dataset's bundles are per-batch extracts. The label was wrong, not the
engine; the control now uses an explicit 404, which every reading accepts.
Run: python3 code/evaluation/fixtures/build_fixtures_v4.py   (deterministic)
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
import build_fixtures_v3 as v3  # noqa: E402
from ghostaudit.contract import canonical_sort  # noqa: E402

OUT4 = os.path.join(HERE, "synth_v4")
MANIFEST4 = os.path.join(HERE, "synth_v4.sha256")
H = v1.H
NEW = {29: ("Astrid", "Lindqvist"), 30: ("Rhea", "Kapoor"), 32: ("Teodor", "Marin"), 33: ("Sana", "Qureshi"), 34: ("Bruno", "Teixeira"), 35: ("Mina", "Abe")}
TEXT = "Please erase the account linked to this email address and the personal data attached to it."
# (case id, person n, requested_at, reported_at, audit_at)
REQUESTS = [("fx_case_29", 29, "2026-01-05T09:00:00Z", "2026-01-06T09:00:00Z", "2026-01-25T12:00:00Z"),
            ("fx_case_31", 30, "2025-12-01T09:00:00Z", "2025-12-02T09:00:00Z", "2025-12-05T12:00:00Z"),
            ("fx_case_30", 30, "2026-02-10T09:00:00Z", "2026-02-11T09:00:00Z", "2026-02-25T12:00:00Z"),
            ("fx_case_32", 32, "2025-11-03T09:00:00Z", "2025-11-04T09:00:00Z", "2025-11-20T12:00:00Z"),
            ("fx_case_33", 33, "2025-10-03T09:00:00Z", "2025-10-04T09:00:00Z", "2025-10-20T12:00:00Z"),
            ("fx_case_34", 34, "2025-09-03T09:00:00Z", "2025-09-04T09:00:00Z", "2025-09-20T12:00:00Z"),
            ("fx_case_35", 35, "2025-08-03T09:00:00Z", "2025-08-04T09:00:00Z", "2025-08-20T12:00:00Z")]
SEARCH_DDL = "resource_id TEXT PRIMARY KEY, display_name TEXT, email TEXT NOT NULL, source_resource_id TEXT, indexed_at TEXT NOT NULL"


def inventory(t, rows, covers_accounts=True, n=None):
    """Typed inventory. With covers_accounts the snapshot lists an unrelated person's profile (the table is captured, the subject is absent)."""
    scope = v1.MAIN_SYSTEMS if covers_accounts else [s for s in v1.MAIN_SYSTEMS if s != "account_service"]
    rows = list(rows)
    if covers_accounts:
        o = v2.other_row(n, t)
        rows.append(("customer_profiles", (o[0], o[1], o[2], o[3], None, H(o[3]), o[5], t)))
    return v1.inventory_sql(t, scope, rows)


def inventory_without_profile_table(t, rows):
    """A typed inventory that DECLARES account_service in its snapshot_scope but has no customer_profiles table: the system is named, no profile
    collection was captured."""
    ddl = "\n".join(l for l in v1.DDL.splitlines() if not l.startswith("CREATE TABLE customer_profiles"))
    lines = ["PRAGMA foreign_keys=ON;", "BEGIN TRANSACTION;", ddl]
    lines += [f"INSERT INTO snapshot_scope VALUES ({v1.sql_val(sysid)}, {v1.sql_val(t)});" for sysid in v1.MAIN_SYSTEMS]
    lines += [f"INSERT INTO {table} VALUES ({', '.join(v1.sql_val(v) for v in vals)});" for table, vals in rows]
    return "\n".join(lines + ["COMMIT;", f"-- snapshot_completed_at={t}", ""])


def audit(rid, uid, t):
    return ("security_audit_records", (rid, uid, "ACCOUNT_DELETION_RECORDED", "2031-12-31T23:59:59Z", t))


def js(obj):
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def build():
    v3.OUT3, v3.MANIFEST3 = OUT4, MANIFEST4
    v3.build()                                   # base: identical data to v3 (and therefore v2, v1)
    v1.NAMES.update(NEW)
    reqs, ident, files, exp, internal_add = [], [], [], {}, {}
    for cid, n, req_at, rep_at, aud in REQUESTS:
        reqs.append((cid, v1.email(n), req_at, "NOT_STARTED", rep_at, aud, TEXT))
    for n, name in NEW.items():
        em = v1.email(n)
        ident.append((v1.uid(n), " ".join(name), em, f"+1 555 03{n:02d}", H(em), "2025-06-01T00:00:00Z"))

    def add(fid, rel, origin, t, text):
        v2.write(rel, text)
        files.append((fid, rel, origin, t))

    INV = ("customer_data_inventory_capture")

    # --- fx_case_29: a source reference reaches the account; no observation of the account itself --------------------------------------
    u29, e29 = v1.uid(29), v1.email(29)
    t_inv, t_idx = "2026-01-08T10:00:00Z", "2026-01-10T08:00:00Z"
    add("evidence_i02", "evidence/databases/customer_data_inventory_20260108.sql", INV, t_inv, inventory(t_inv, [audit("audit_record_f29", u29, t_inv)], True, 29))
    add("evidence_i01", "evidence/databases/customer_search_primary_20260110.sql", "customer_search_primary_capture", t_idx, v1.replica_sql(t_idx, "search_primary", {
        "search_documents_primary": (SEARCH_DDL, [("search_f29", "Astrid Lindqvist", e29, "account_f29", "2026-01-09T22:00:00Z"),
                                                  ("search_f29z", "Unrelated Person", "unrelated.29@example.org", "account_f29z", "2026-01-09T22:01:00Z")])}))
    exp["fx_case_29"] = ("INCOMPLETE", [
        v2.step("FINDING", "search_service", "search_f29", "REPORT_REMAINING_RECORD", "evidence_i01"), v2.step("REMEDIATION", "search_service", "search_f29", "DELETE_RECORD"),
        v2.step("VERIFICATION", "account_service", "account_f29", "VERIFY_RECORD_ABSENT"), v2.step("VERIFICATION", "security_service", "audit_record_f29", "VERIFY_RECORD_PRESENT"),
        v2.step("VERIFICATION", "search_service", "search_f29", "VERIFY_RECORD_ABSENT")])
    internal_add["fx_case_29"] = {"intent": "DELETION", "links_accepted": ["search_f29", "account_f29", "audit_record_f29"], "links_rejected": ["search_f29z", "account_f29z"],
        "obligations": {"account_f29": "COMPLIANT:record_absent", "search_f29": "VIOLATION:record_present"},
        "must_not_cite": [], "note": "account_f29 is reached only through search_f29's source_resource_id (system from the account_ namespace); the declared "
        "snapshot evidence_i02 (2026-01-08) predates the document's indexing (01-10) but still shows the account gone: a reference proves no creation time"}

    # --- fx_case_31 (earlier) and fx_case_30 (later): one subject, two requests ------------------------------------------------------------
    u30, e30 = v1.uid(30), v1.email(30)
    ta, tb = "2025-12-03T10:00:00Z", "2026-02-15T10:00:00Z"
    add("evidence_i03", "evidence/databases/customer_data_inventory_20251203.sql", INV, ta, inventory(ta, [audit("audit_record_f31", u30, ta), v1.search_row("search_f31", e30, ta)], True, 31))
    add("evidence_i04", "evidence/databases/customer_data_inventory_20260215.sql", INV, tb, inventory(tb, [audit("audit_record_f30", u30, tb), v1.search_row("search_f30", e30, tb)], True, 30))
    exp["fx_case_31"] = ("INCOMPLETE", [
        v2.step("FINDING", "search_service", "search_f31", "REPORT_REMAINING_RECORD", "evidence_i03"), v2.step("REMEDIATION", "search_service", "search_f31", "DELETE_RECORD"),
        v2.step("VERIFICATION", "security_service", "audit_record_f31", "VERIFY_RECORD_PRESENT"), v2.step("VERIFICATION", "search_service", "search_f31", "VERIFY_RECORD_ABSENT")])
    exp["fx_case_30"] = ("INCOMPLETE", [
        v2.step("FINDING", "search_service", "search_f30", "REPORT_REMAINING_RECORD", "evidence_i04"), v2.step("REMEDIATION", "search_service", "search_f30", "DELETE_RECORD"),
        v2.step("VERIFICATION", "security_service", "audit_record_f30", "VERIFY_RECORD_PRESENT"), v2.step("VERIFICATION", "search_service", "search_f30", "VERIFY_RECORD_ABSENT")])
    internal_add["fx_case_31"] = {"intent": "DELETION", "links_accepted": ["search_f31", "audit_record_f31"], "must_not_cite": ["evidence_i04"],
        "note": "the earlier request (Dec 1-5): its own evidence is in scope"}
    internal_add["fx_case_30"] = {"intent": "DELETION", "links_accepted": ["search_f30", "audit_record_f30", "search_f31", "audit_record_f31"],
        "obligations": {"search_f30": "VIOLATION:record_present"}, "must_not_cite": ["evidence_i03"],
        "note": "the same subject's later request (Feb 10-25). search_f31 and audit_record_f31 are linked only by evidence captured inside the earlier request's "
                "window (evidence_i03, 2025-12-03 <= its audit 2025-12-05): carried over, so no step is emitted for them (search_f31 is absent in evidence_i04 anyway)"}

    # --- fx_case_32 / fx_case_33: treatment label versus returned payload -----------------------------------------------------------------
    for cid, n, payload in (("fx_case_32", 32, True), ("fx_case_33", 33, False)):
        u, e = v1.uid(n), v1.email(n)
        tl, ti = {32: "2025-11-10T09:30:00Z", 33: "2025-10-10T09:30:00Z"}[n], {32: "2025-11-12T10:00:00Z", 33: "2025-10-12T10:00:00Z"}[n]
        rec = {"recorded_at": tl, "system": "identity_service", "resource_id": f"tombstone_f{n}", "record_type": "ACCOUNT_TOMBSTONE", "result": "REDACTED",
               "subject_reference": u, "user_id": u, "account_status": "DELETED"}
        rec.update({"email": e, "full_name": " ".join(NEW[n])} if payload else {"lookup_value": e})
        fe, fi = f"evidence_{'i05' if n == 32 else 'j05'}", f"evidence_{'i06' if n == 32 else 'j06'}"
        ym = tl[:7].replace("-", "")
        add(fe, f"evidence/records/identity_lookup_ledger_{ym}10.json", "records_assurance_ledger", tl, js({"exported_at": tl, "origin": "identity_service", "record_count": 1, "records": [rec]}))
        add(fi, f"evidence/databases/customer_data_inventory_{ym}12.sql", INV, ti, inventory(ti, [audit(f"audit_record_f{n}", u, ti)], True, n))
        if payload:
            exp[cid] = ("INCOMPLETE", [v2.step("FINDING", "identity_service", f"tombstone_f{n}", "REPORT_EXPOSED_PII", fe), v2.step("REMEDIATION", "identity_service", f"tombstone_f{n}", "REDACT_RECORD"),
                                       v2.step("VERIFICATION", "security_service", f"audit_record_f{n}", "VERIFY_RECORD_PRESENT"), v2.step("VERIFICATION", "identity_service", f"tombstone_f{n}", "VERIFY_RECORD_REDACTED")])
            internal_add[cid] = {"intent": "DELETION", "links_accepted": [f"tombstone_f{n}"], "obligations": {f"tombstone_f{n}": "VIOLATION:identifiers_exposed"},
                "note": "result says REDACTED but the returned record carries the subject's email and full name: a treatment label never suppresses returned identifiers"}
        else:
            exp[cid] = ("COMPLETE", [v2.step("VERIFICATION", "security_service", f"audit_record_f{n}", "VERIFY_RECORD_PRESENT", fi),
                                     v2.step("VERIFICATION", "identity_service", f"tombstone_f{n}", "VERIFY_RECORD_REDACTED", fe)])
            internal_add[cid] = {"intent": "DELETION", "links_accepted": [f"tombstone_f{n}"], "obligations": {f"tombstone_f{n}": "COMPLIANT:treated_record_present"},
                "note": "the email appears only as the lookup key (query metadata) of a REDACTED lookup that returns the stable user_id only: the label stands"}

    # --- fx_case_34 / fx_case_35: what a later empty snapshot may and may not erase --------------------------------------------------------
    for cid, n, coll in (("fx_case_34", 34, "notification_preferences"), ("fx_case_35", 35, None)):
        u, e = v1.uid(n), v1.email(n)
        ym = {34: "202509", 35: "202508"}[n]
        t_look, t_bundle, t_inv = f"{ym[:4]}-{ym[4:]}-10T08:30:00Z", f"{ym[:4]}-{ym[4:]}-15T09:00:00Z", f"{ym[:4]}-{ym[4:]}-16T10:00:00Z"
        fx_ = lambda s: f"evidence_{s}"  # noqa: E731
        ids = {34: ("i09", "i10", "i11"), 35: ("j09", "j10", "j11")}[n]
        look = {"exported_at": t_look, "region": "global", "source": "records_assurance_gateway", "service_exports": {"account_service": {"profile_lookups": [{
            "observed_at": t_look, "profile": {"customer_reference": u, "email": e, "email_hash": None, "full_name": " ".join(NEW[n]), "phone": None},
            "resource_id": f"account_f{n}", "status_code": 200}]}}}
        add(fx_(ids[0]), f"evidence/records/service_resource_export_{ym}10_083000.json", "central_observability_export", t_look, js(look))
        if n == 34:
            bundle = {"exported_at": t_bundle, "source": "records_assurance_service", "snapshots": [{"captured_at": t_bundle, "data_store": "account_service", "collection": coll, "records": []}]}
            add(fx_(ids[1]), f"evidence/records/customer_data_snapshot_bundle_{ym}15.json", "records_assurance_snapshot_bundle", t_bundle, js(bundle))
        else:
            gone = {"exported_at": t_bundle, "region": "global", "source": "records_assurance_gateway", "service_exports": {"account_service": {"profile_lookups": [{
                "observed_at": t_bundle, "profile": None, "resource_id": f"account_f{n}", "status_code": 404}]}}}
            add(fx_(ids[1]), f"evidence/records/service_resource_export_{ym}15_090000.json", "central_observability_export", t_bundle, js(gone))
        inv_text = (inventory_without_profile_table(t_inv, [audit(f"audit_record_f{n}", u, t_inv)]) if n == 34
                    else inventory(t_inv, [audit(f"audit_record_f{n}", u, t_inv)], False))
        add(fx_(ids[2]), f"evidence/databases/customer_data_inventory_{ym}16.sql", INV, t_inv, inv_text)
        if n == 34:
            exp[cid] = ("INCOMPLETE", [v2.step("FINDING", "account_service", f"account_f{n}", "REPORT_REMAINING_RECORD", fx_(ids[0])), v2.step("REMEDIATION", "account_service", f"account_f{n}", "DELETE_RECORD"),
                                       v2.step("VERIFICATION", "account_service", f"account_f{n}", "VERIFY_RECORD_ABSENT"), v2.step("VERIFICATION", "security_service", f"audit_record_f{n}", "VERIFY_RECORD_PRESENT")])
            internal_add[cid] = {"intent": "DELETION", "links_accepted": [f"account_f{n}"], "obligations": {f"account_f{n}": "VIOLATION:record_present"},
                "note": "the later bundle is a declared-empty NOTIFICATION_PREFERENCES collection and the later inventory names account_service without a profile table: "
                "neither captured a profile collection, so neither can erase the profile seen present"}
        else:
            exp[cid] = ("COMPLETE", [v2.step("VERIFICATION", "account_service", f"account_f{n}", "VERIFY_RECORD_ABSENT", fx_(ids[1])), v2.step("VERIFICATION", "security_service", f"audit_record_f{n}", "VERIFY_RECORD_PRESENT", fx_(ids[2]))])
            internal_add[cid] = {"intent": "DELETION", "links_accepted": [f"account_f{n}"], "obligations": {f"account_f{n}": "COMPLIANT:record_absent"},
                "note": "a later explicit lookup of the account returns 404: valid absence (no positive-control row needed)"}

    # --- write the data files -------------------------------------------------------------------------------------------------------------
    v2.append_csv(os.path.join(OUT4, "deletion_requests.csv"), reqs)
    v2.append_csv(os.path.join(OUT4, "user_identities.csv"), ident)
    v2.append_csv(os.path.join(OUT4, "evidence_files.csv"), files)
    with open(os.path.join(OUT4, "expected_output.csv"), newline="", encoding="utf-8") as f:
        rows = {r["case_id"]: r for r in csv.DictReader(f)}
    for cid, (status, steps) in exp.items():
        rows[cid] = {"case_id": cid, "deletion_status": status, "steps_json": json.dumps(canonical_sort(steps), sort_keys=True, separators=(",", ":")) if steps else "[]"}
    from ghostaudit.validate import case_sort_key
    with open(os.path.join(OUT4, "expected_output.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for cid in sorted(rows, key=lambda c: case_sort_key(c.replace("fx_case_", "case_"))):
            w.writerow([cid, rows[cid]["deletion_status"], rows[cid]["steps_json"]])
    ip = os.path.join(OUT4, "expected_internal.json")
    internal = json.load(open(ip, encoding="utf-8"))
    internal.update(internal_add)
    json.dump(internal, open(ip, "w", encoding="utf-8"), indent=2, sort_keys=True, ensure_ascii=False)
    open(ip, "a").write("\n")
    manifest = []
    for root, _, names in os.walk(OUT4):
        for nm in sorted(names):
            p = os.path.join(root, nm)
            manifest.append((os.path.relpath(p, OUT4), hashlib.sha256(open(p, "rb").read()).hexdigest()))
    manifest.sort()
    with open(MANIFEST4, "w") as f:
        for rel, h in manifest:
            f.write(f"{h}  {rel}\n")
    print(f"built synth_v4: {len(manifest)} files; manifest -> synth_v4.sha256")


if __name__ == "__main__":
    build()
