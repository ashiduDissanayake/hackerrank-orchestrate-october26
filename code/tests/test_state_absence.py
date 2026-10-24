"""Absence evidence for an already LINKED resource must meet the same standard as the subject-level account proof:
profile collection/table, complete source, physical copy, time, contradictions. Unsupported omission must not erase
established presence. Written before the fix (review finding 2: three counterexamples reported COMPLETE)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)
sys.path.insert(0, HERE)

from test_account_proof import AUDIT, CH, OTHER, REQ_AT, RULES, SNAP, U, World  # noqa: E402
from ghostaudit.account_proof import account_proof  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.data import Request  # noqa: E402
from ghostaudit.engine import audit_case  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.observations import ScopeDecl, make_obs  # noqa: E402

PRESENT_T = "2026-06-05T00:00:00Z"     # the profile is seen after the request
LATER = "2026-06-10T00:00:00Z"         # a later capture that does not list it


def linked_profile(w):
    """A profile lookup carrying the subject's email: a direct link, present after the request."""
    w.st.add_obs(make_obs("evidence_p", "/p", PRESENT_T, PRESENT_T, "account_service", "account_77", "export", "lookup", True,
                          normalize_fields({"email": "rui.costa@example.org", "status_code": "200"})))
    w.st.add_obs(make_obs("evidence_a", "/a", LATER, LATER, "security_service", "audit_record_7", "primary", "record", True,
                          normalize_fields({"subject_reference": "user_7", "retention_until": "2031-12-31T23:59:59Z"})))
    return w


def run(w):
    w.st.finalize()
    r = Request("c1", "rui.costa@example.org", REQ_AT, "NOT_STARTED", "2026-06-02T00:00:00Z", AUDIT, "Please delete my account.")
    return audit_case(r, w.st, IdentityIndex([U], CH), RULES)


def profile_ob(res):
    return next(o for o in res.obligations if o.resource_id == "account_77")


def ops(res):
    return [(s["phase"], s["resource_id"], s["operation"]) for s in res.steps]


class UnsupportedOmissionDoesNotErasePresence(unittest.TestCase):
    def assertStillPresent(self, w):
        res = run(w)
        self.assertEqual((profile_ob(res).verdict, profile_ob(res).reason), ("VIOLATION", "record_present"))
        self.assertEqual(res.internal, "INCOMPLETE")
        self.assertIn(("FINDING", "account_77", "REPORT_REMAINING_RECORD"), ops(res))
        # and the stricter account proof agrees
        p = account_proof(CaseView(w.st, AUDIT), IdentityIndex([U], CH).resolve("rui.costa@example.org", AUDIT), REQ_AT)
        self.assertNotEqual(p.status, "ABSENT")

    def test_declared_empty_non_profile_collection_does_not_erase_a_linked_profile(self):
        self.assertStillPresent(linked_profile(World().snap("evidence_1", LATER, "primary", [], collection="notification_preferences")))

    def test_explicitly_incomplete_profile_export_does_not_erase_it(self):
        self.assertStillPresent(linked_profile(World().snap("evidence_1", LATER, "primary", [OTHER], complete=False)))

    def test_weak_export_that_does_not_cover_the_subject_does_not_erase_it(self):
        w = linked_profile(World())
        for copy in ("primary", "read_replica"):
            w.st.add_scope(ScopeDecl("evidence_w", LATER, "account_service", copy, "inferred_from_rows", None, (), True))
        w.st.add_obs(make_obs("evidence_w", "r/a", LATER, LATER, "account_service", "account_900", "read_replica", "record", True,
                              normalize_fields({"collection": "customer_profiles", **OTHER})))
        self.assertStillPresent(w)

    def test_inventory_declaring_the_system_without_the_profile_table_does_not_erase_it(self):
        self.assertStillPresent(linked_profile(World().snap("evidence_1", LATER, "primary", [], captured=("support_records",))))

    def test_replica_still_holding_the_profile_keeps_it_present(self):
        w = linked_profile(World().snap("evidence_1", LATER, "primary", [OTHER]))
        w.st.add_scope(ScopeDecl("evidence_1", LATER, "account_service", "failover_replica", "inferred_from_table", None, ("customer_profiles",), True))
        w.st.add_obs(make_obs("evidence_1", "f/77", LATER, LATER, "account_service", "account_77", "failover_replica", "record", True,
                              normalize_fields({"email": "rui.costa@example.org", "user_id": "user_7"})))
        self.assertStillPresent(w)


class ValidAbsenceIsStillAccepted(unittest.TestCase):
    def assertAbsent(self, w):
        res = run(w)
        self.assertEqual((profile_ob(res).verdict, profile_ob(res).reason), ("COMPLIANT", "record_absent"))
        self.assertEqual(res.internal, "COMPLETE")
        self.assertIn(("VERIFICATION", "account_77", "VERIFY_RECORD_ABSENT"), ops(res))

    def test_complete_declared_profile_snapshot_that_omits_it(self):
        self.assertAbsent(linked_profile(World().snap("evidence_1", LATER, "primary", [OTHER])))

    def test_genuinely_empty_profile_table_needs_no_positive_control(self):
        self.assertAbsent(linked_profile(World().snap("evidence_1", LATER, "primary", [])))

    def test_explicit_404_lookup(self):
        w = linked_profile(World())
        w.st.add_obs(make_obs("evidence_n", "/n", LATER, LATER, "account_service", "account_77", "export", "lookup", False, normalize_fields({"status_code": "404"})))
        self.assertAbsent(w)

    def test_weak_export_promoted_per_source(self):
        w = linked_profile(World())
        for copy in ("primary", "read_replica"):
            w.st.add_scope(ScopeDecl("evidence_w", LATER, "account_service", copy, "inferred_from_rows", None, (), True))
        w.st.add_obs(make_obs("evidence_w", "p/a", LATER, LATER, "security_service", "audit_record_7", "primary", "record", True,
                              normalize_fields({"subject_reference": "user_7"})))
        w.st.add_obs(make_obs("evidence_w", "r/a", LATER, LATER, "account_service", "account_900", "read_replica", "record", True,
                              normalize_fields({"collection": "customer_profiles", **OTHER})))
        self.assertAbsent(w)

    def test_later_presence_beats_an_earlier_complete_absence(self):
        w = linked_profile(World().snap("evidence_1", "2026-06-03T00:00:00Z", "primary", [OTHER]))   # absent before it is seen again
        res = run(w)
        self.assertEqual(profile_ob(res).verdict, "VIOLATION")


class CategoryCoverage(unittest.TestCase):
    """A typed inventory table evidences capture of the categories its rows hold (support_records holds messages, never attachments)."""

    def test_table_and_collection_names_map_to_categories(self):
        from ghostaudit.coverage_rules import covers_category
        sc = lambda *names: ScopeDecl("e", "t", "support_platform", "primary", "declared", None, names, True)  # noqa: E731
        self.assertTrue(covers_category(sc("support_records"), "SUPPORT_MESSAGE"))
        self.assertFalse(covers_category(sc("support_records"), "SUPPORT_ATTACHMENT"))
        self.assertTrue(covers_category(sc("ticket_attachments"), "SUPPORT_ATTACHMENT"))
        self.assertFalse(covers_category(sc("notification_preferences"), "USER_PROFILE"))
        self.assertIsNone(covers_category(sc(), "USER_PROFILE"), "document-table exports do not name what they captured")

    def test_attachment_seen_present_is_not_erased_by_a_messages_inventory(self):
        """case_34/support_9538 pattern: a PII scan shows the attachment, a LATER inventory that only captures support_records omits it."""
        rules = RULES + [{"data_category": "SUPPORT_ATTACHMENT", "required_action": "DELETE"}]
        w = World()
        w.st.add_obs(make_obs("evidence_p", "/p", PRESENT_T, PRESENT_T, "support_platform", "support_9538", "log", "attachment_pii_scan", True,
                              normalize_fields({"matched_value": "+351 912 345 678", "file": "delivery_confirmation_32.pdf"})))
        w.st.add_obs(make_obs("evidence_a", "/a", LATER, LATER, "security_service", "audit_record_7", "primary", "record", True,
                              normalize_fields({"subject_reference": "user_7"})))
        w.st.add_scope(ScopeDecl("evidence_i", LATER, "support_platform", "inventory", "declared", None, ("support_records",), True))
        w.st.finalize()
        r = Request("c1", "rui.costa@example.org", REQ_AT, "NOT_STARTED", "2026-06-02T00:00:00Z", AUDIT, "Please delete my account.")
        res = audit_case(r, w.st, IdentityIndex([U], CH), rules)
        o = next(x for x in res.obligations if x.resource_id == "support_9538")
        self.assertEqual((o.category, o.verdict, o.reason), ("SUPPORT_ATTACHMENT", "VIOLATION", "record_present"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
