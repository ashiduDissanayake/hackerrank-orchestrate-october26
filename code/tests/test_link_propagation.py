"""Relationship propagation: a resource named by a linked record's explicit source reference must reach policy evaluation
(or an explicit unresolved diagnostic); state is judged separately from the link. Written before the fix (case_06 finding)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)
sys.path.insert(0, HERE)

from test_account_proof import AUDIT, CH, OTHER, REQ_AT, RULES, SNAP, U, World  # noqa: E402
from ghostaudit.data import Request  # noqa: E402
from ghostaudit.engine import audit_case  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.observations import make_obs  # noqa: E402

RULES_ALL = RULES + [{"data_category": "SEARCH_INDEX_ENTRY", "required_action": "DELETE"}]
DOC_T = "2026-06-12T00:00:00Z"            # after the request, before the cutoff


def search_doc(w, rid="search_1", src="account_6", t=DOC_T, email="rui.costa@example.org", eid="evidence_s", extra=None):
    f = {"email": email, "source_resource_id": src, **(extra or {})}
    w.st.add_obs(make_obs(eid, f"/{rid}", t, t, "search_service", rid, "primary", "record", True, normalize_fields(f)))
    return w


def run(w, audit=AUDIT):
    w.st.finalize()
    r = Request("c1", "rui.costa@example.org", REQ_AT, "NOT_STARTED", "2026-06-02T00:00:00Z", audit, "Please delete my account.")
    return audit_case(r, w.st, IdentityIndex([U], CH), RULES_ALL)


def accts(res):
    return {o.resource_id: o for o in res.obligations if o.category == "USER_PROFILE" and o.resource_id}


class SourceReferenceReachesPolicy(unittest.TestCase):
    def test_referenced_account_gets_a_system_and_an_absence_verification(self):
        w = search_doc(World().snap("evidence_1", SNAP, "primary", [OTHER]))
        res = run(w)
        o = accts(res)["account_6"]
        self.assertEqual((o.system_id, o.verdict, o.reason), ("account_service", "COMPLIANT", "record_absent"))
        self.assertEqual(res.internal, "INCOMPLETE")
        ver = [s for s in res.steps if s["resource_id"] == "account_6"]
        self.assertEqual([(s["phase"], s["operation"], s["evidence_id"]) for s in ver], [("VERIFICATION", "VERIFY_RECORD_ABSENT", "")])

    def test_link_records_how_its_system_was_resolved(self):
        res = run(search_doc(World().snap("evidence_1", SNAP, "primary", [OTHER])))
        ln = res.links["account_6"]
        self.assertEqual(ln.system_basis, "namespace_prefix")
        self.assertEqual([c.kind for c in ln.chains], ["source"])

    def test_stale_reference_to_an_already_deleted_account_is_still_judged_by_its_absence(self):
        """The index document learned the id LATER than the snapshot that shows the account gone; the reference proves no creation time."""
        w = World().snap("evidence_1", "2026-06-05T00:00:00Z", "primary", [OTHER])
        res = run(search_doc(w, t="2026-06-13T00:00:00Z"))
        self.assertEqual(accts(res)["account_6"].verdict, "COMPLIANT")

    def test_present_referenced_account_is_a_violation_with_its_own_finding(self):
        w = search_doc(World().snap("evidence_1", SNAP, "primary", [OTHER]))
        w.st.add_obs(make_obs("evidence_a", "/a6", DOC_T, DOC_T, "account_service", "account_6", "export", "lookup", True, normalize_fields({"status_code": "200"})))
        res = run(w)
        o = accts(res)["account_6"]
        self.assertEqual(o.verdict, "VIOLATION")
        self.assertIn(("FINDING", "account_6", "REPORT_REMAINING_RECORD"), [(s["phase"], s["resource_id"], s["operation"]) for s in res.steps])

    def test_reference_with_no_state_evidence_is_an_explicit_unknown_not_a_silent_drop(self):
        res = run(search_doc(World()))                      # no account snapshot or lookup at all
        o = accts(res)["account_6"]
        self.assertEqual(o.verdict, "UNKNOWN")
        self.assertNotIn("account_6", [s["resource_id"] for s in res.steps])

    def test_unresolvable_category_is_an_explicit_unknown(self):
        res = run(search_doc(World().snap("evidence_1", SNAP, "primary", [OTHER]), src="zz_77"))
        o = {x.resource_id: x for x in res.obligations}["zz_77"]
        self.assertEqual((o.verdict, o.reason), ("UNKNOWN", "category_unresolved"))
        self.assertEqual(res.internal, "INCOMPLETE")        # the search doc is still a proven violation; the unknown is a plan gap

    def test_reference_observed_after_the_cutoff_creates_no_link(self):
        res = run(search_doc(World().snap("evidence_1", SNAP, "primary", [OTHER]), t="2026-06-20T00:00:00Z"))
        self.assertNotIn("account_6", res.links)

    def test_referenced_account_showing_another_person_is_rejected(self):
        w = search_doc(World().snap("evidence_1", SNAP, "primary", [OTHER]))
        w.st.add_obs(make_obs("evidence_a", "/a6", DOC_T, DOC_T, "account_service", "account_6", "export", "lookup", True,
                              normalize_fields({"email": "someone.else@example.org", "status_code": "200"})))
        res = run(w)
        self.assertNotIn("account_6", res.links)
        self.assertIn("account_6", [r[0] for r in res.rejected])


class FixedPoint(unittest.TestCase):
    def test_cycle_loses_all_links_when_its_only_identity_root_is_rejected(self):
        w = World().snap("evidence_1", SNAP, "primary", [OTHER])
        search_doc(w, rid="search_root", src="search_b", eid="evidence_root", email="other.person@example.org",
                   extra={"lookup_key": U.email})
        search_doc(w, rid="search_b", src="search_c", eid="evidence_b", email="")
        search_doc(w, rid="search_c", src="search_b", eid="evidence_c", email="")
        res = run(w)
        self.assertFalse({"search_root", "search_b", "search_c"} & set(res.links))

    def test_cycle_keeps_an_independent_valid_identity_root(self):
        w = World().snap("evidence_1", SNAP, "primary", [OTHER])
        search_doc(w, rid="search_root", src="search_b", eid="evidence_root", email="other.person@example.org",
                   extra={"lookup_key": U.email})
        search_doc(w, rid="search_b", src="search_c", eid="evidence_b", email="")
        search_doc(w, rid="search_c", src="search_b", eid="evidence_c", email=U.email)
        res = run(w)
        self.assertNotIn("search_root", res.links)
        self.assertTrue({"search_b", "search_c"} <= set(res.links))

    def test_chains_are_followed_and_cycles_terminate(self):
        w = World().snap("evidence_1", SNAP, "primary", [OTHER])
        search_doc(w, rid="search_1", src="search_2", eid="evidence_s1")
        search_doc(w, rid="search_2", src="search_1", eid="evidence_s2", email="")        # cycle; no identifier of its own
        search_doc(w, rid="search_3", src="account_6", eid="evidence_s3", email="")
        # search_2 only becomes linked through search_1; search_3 is never referenced by a linked record
        res = run(w)
        self.assertIn("search_2", res.links)
        self.assertNotIn("search_3", res.links)
        self.assertEqual([c.kind for c in res.links["search_2"].chains], ["source"])

    def test_two_hop_reference_reaches_the_account(self):
        w = World().snap("evidence_1", SNAP, "primary", [OTHER])
        search_doc(w, rid="search_1", src="search_2", eid="evidence_s1")
        search_doc(w, rid="search_2", src="account_6", eid="evidence_s2", email="")
        res = run(w)
        self.assertEqual(accts(res)["account_6"].verdict, "COMPLIANT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
