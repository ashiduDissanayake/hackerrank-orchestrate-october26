"""Repeated requests by one subject: evidence that only serves an EARLIER request's investigation window is not part of a later
request's scope, derived from the subject's own request history (not from a blanket first-request rule, case numbers or timing
alone). Written before the fix (sample case_07/object_19, case_17/account_6523, eval case_33/export_1260)."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)
sys.path.insert(0, HERE)

from test_account_proof import World  # noqa: E402
from ghostaudit.data import IdentityRow  # noqa: E402
from ghostaudit.data import Request  # noqa: E402
from ghostaudit.engine import audit_case  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.observations import make_obs  # noqa: E402

EMAIL = "rui.costa@example.org"
U = IdentityRow("user_7", "Rui Costa", EMAIL, "+351 912 345 678", "e" * 64, "2026-01-01T00:00:00Z")   # the address has been the subject's since January
CH = []
RULES = [{"data_category": c, "required_action": a} for c, a in (("USER_PROFILE", "DELETE"), ("SECURITY_AUDIT_LOG", "RETAIN"), ("SEARCH_INDEX_ENTRY", "DELETE"))]
# first request: Feb 11 -> audited Feb 14; second request: Aug 31 -> audited Sep 12
R0 = Request("r0", EMAIL, "2026-02-11T05:00:00Z", "PARTIALLY_COMPLETE", "2026-02-12T23:00:00Z", "2026-02-14T10:00:00Z", "Please delete my account.")
R1 = Request("r1", EMAIL, "2026-08-31T11:26:00Z", "COMPLETE", "2026-09-01T19:30:00Z", "2026-09-12T08:00:00Z", "Please delete my account.")
FEB, AUG = "2026-02-13T08:00:00Z", "2026-09-05T08:00:00Z"


def doc(w, rid, t, eid, system="search_service", present=True, extra=None):
    w.st.add_obs(make_obs(eid, f"/{rid}", t, t, system, rid, "primary", "record", present, normalize_fields({"email": EMAIL, **(extra or {})})))
    return w


def with_audit(w, t=AUG):
    w.st.add_obs(make_obs("evidence_a", "/a", t, t, "security_service", "audit_record_7", "primary", "record", True,
                          normalize_fields({"subject_reference": "user_7", "retention_until": "2031-12-31T23:59:59Z"})))
    return w


def run(w, req=R1, earlier=(R0,)):
    w.st.finalize()
    return audit_case(req, w.st, IdentityIndex([U], CH), RULES, earlier_requests=list(earlier))


def by_id(res):
    return {o.resource_id: o for o in res.obligations if o.resource_id}


class CarriedOver(unittest.TestCase):
    def test_present_resource_evidenced_only_in_the_earlier_window_is_not_a_finding_but_stays_unresolved(self):
        res = run(with_audit(doc(World(), "search_1", FEB, "evidence_f")))
        o = by_id(res)["search_1"]
        self.assertEqual((o.verdict, o.reason), ("UNKNOWN", "carried_over_present"))
        self.assertEqual(o.detail["earlier_requests"], ["r0"])
        self.assertNotIn("search_1", [s["resource_id"] for s in res.steps])
        self.assertEqual(res.internal, "UNDETERMINED")        # never hidden: present data cannot become a certified COMPLETE

    def test_it_does_not_change_an_established_incomplete(self):
        w = doc(with_audit(World()), "search_1", FEB, "evidence_f")
        doc(w, "search_2", AUG, "evidence_g")                 # a record evidenced after the second request: a real finding
        res = run(w)
        self.assertEqual(res.internal, "INCOMPLETE")
        self.assertEqual(by_id(res)["search_2"].verdict, "VIOLATION")
        self.assertEqual(by_id(res)["search_1"].verdict, "UNKNOWN")

    def test_compliant_resource_of_the_earlier_episode_is_scoped_out_with_a_record_of_it(self):
        w = doc(with_audit(World().snap("evidence_1", "2026-09-04T00:00:00Z", "primary", [{"email": "x@example.org", "user_id": "user_9"}])), "search_1", FEB, "evidence_f")
        doc(w, "search_1", "2026-02-13T12:00:00Z", "evidence_n", present=False)   # absent later in the earlier window
        res = run(w)
        self.assertNotIn("search_1", by_id(res))
        self.assertEqual([c["resource_id"] for c in res.carried_over], ["search_1"])
        self.assertEqual(res.internal, "COMPLETE")

    def test_resource_with_a_chain_at_or_after_the_new_request_stays_in_scope(self):
        w = doc(with_audit(World()), "search_1", FEB, "evidence_f")
        doc(w, "search_1", AUG, "evidence_g")                 # seen again after the second request
        o = by_id(run(w))["search_1"]
        self.assertEqual((o.verdict, o.reason), ("VIOLATION", "record_present"))

    def test_capture_after_the_request_counts_even_if_the_record_time_is_old(self):
        w = with_audit(World())
        w.st.add_obs(make_obs("evidence_g", "/s", AUG, FEB, "search_service", "search_1", "primary", "record", True, normalize_fields({"email": EMAIL})))
        o = by_id(run(w))["search_1"]
        self.assertEqual(o.verdict, "VIOLATION")


class NotCarriedOver(unittest.TestCase):
    def test_evidence_before_the_earlier_request_is_not_inside_its_investigation_window(self):
        res = run(doc(with_audit(World()), "search_1", "2026-01-01T08:00:00Z", "evidence_old"))
        self.assertEqual(by_id(res)["search_1"].verdict, "VIOLATION")

    def test_single_request_subject_keeps_resources_seen_before_the_request(self):
        res = run(doc(with_audit(World()), "search_1", "2026-08-31T08:00:00Z", "evidence_f"), earlier=())
        self.assertEqual(by_id(res)["search_1"].verdict, "VIOLATION")

    def test_overlapping_earlier_request_does_not_scope(self):
        r0 = Request("r0", EMAIL, "2026-08-25T05:00:00Z", "NOT_STARTED", "2026-08-26T00:00:00Z", "2026-09-02T10:00:00Z", "Please delete my account.")
        res = run(doc(with_audit(World()), "search_1", "2026-08-30T08:00:00Z", "evidence_f"), earlier=(r0,))
        self.assertEqual(by_id(res)["search_1"].verdict, "VIOLATION")

    def test_evidence_after_the_earlier_audit_is_not_attributable_to_it(self):
        res = run(doc(with_audit(World()), "search_1", "2026-04-01T08:00:00Z", "evidence_f"))   # between the two requests
        self.assertEqual(by_id(res)["search_1"].verdict, "VIOLATION")

    def test_a_later_request_never_scopes_an_earlier_one(self):
        later = Request("r2", EMAIL, "2026-11-01T05:00:00Z", "NOT_STARTED", "2026-11-02T00:00:00Z", "2026-11-10T10:00:00Z", "Please delete my account.")
        res = run(doc(with_audit(World()), "search_1", "2026-09-05T08:00:00Z", "evidence_f"), earlier=(later,))
        self.assertEqual(by_id(res)["search_1"].verdict, "VIOLATION")

    def test_switch_off_restores_the_unscoped_behaviour(self):
        w = with_audit(doc(World(), "search_1", FEB, "evidence_f"))
        w.st.finalize()
        res = audit_case(R1, w.st, IdentityIndex([U], CH), RULES, earlier_requests=[R0], episode_scoping=False)
        self.assertEqual(by_id(res)["search_1"].verdict, "VIOLATION")


class HistoryFromTheDataRoot(unittest.TestCase):
    def test_earlier_requests_of_the_same_subject_are_found_across_request_files(self):
        from ghostaudit.run import earlier_requests_by_case
        import csv
        with tempfile.TemporaryDirectory() as t:
            for n in ("deletion_rules.csv", "evidence_files.csv", "system_activity.csv", "user_audit_log.csv"):
                open(os.path.join(t, n), "w").write({"deletion_rules.csv": "rule_id,data_category,condition,required_action\n",
                                                     "evidence_files.csv": "file_id,file_path,origin,captured_at\n",
                                                     "system_activity.csv": "activity_id,event_time,event_type,source_system,target_system,resource_id,reported_result,details\n",
                                                     "user_audit_log.csv": "audit_id,user_id,event_time,field_name,old_value,new_value\n"}[n])
            open(os.path.join(t, "user_identities.csv"), "w").write("user_id,name,email,phone,email_hash,updated_at\nuser_7,Rui Costa,rui.costa@example.org,+351 912 345 678,%s,2026-01-01T00:00:00Z\n" % ("e" * 64))
            hdr = "case_id,email,requested_at,reported_status,reported_at,audit_at,request_text\n"
            open(os.path.join(t, "deletion_requests.csv"), "w").write(hdr + "r0,rui.costa@example.org,2026-02-11T05:00:00Z,NOT_STARTED,2026-02-12T00:00:00Z,2026-02-14T10:00:00Z,delete\n")
            open(os.path.join(t, "sample_deletion_requests.csv"), "w").write(hdr + "r1,rui.costa@example.org,2026-08-31T11:26:00Z,NOT_STARTED,2026-09-01T00:00:00Z,2026-09-12T08:00:00Z,delete\n")
            from ghostaudit.data import load_dataset
            ds = load_dataset(t, "sample_deletion_requests.csv")
            ix = IdentityIndex(ds.identities, ds.audit_log)
            hist = earlier_requests_by_case(ds, ix)
            self.assertEqual([r.case_id for r in hist["r1"]], ["r0"])
            self.assertEqual(hist.get("r0", []), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
