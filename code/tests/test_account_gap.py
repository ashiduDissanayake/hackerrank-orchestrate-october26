"""Account-gap obligation: when it is justified, when a tombstone resolves it, and what it must never do."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.data import IdentityRow, Request  # noqa: E402
from ghostaudit.engine import audit_case  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.observations import Store, make_obs  # noqa: E402

T = "2026-06-10T00:00:00Z"
AT = "2026-06-15T12:00:00Z"
RULES = [{"data_category": c, "required_action": a} for c, a in (
    ("USER_PROFILE", "DELETE"), ("ACCOUNT_TOMBSTONE", "REDACT"), ("SECURITY_AUDIT_LOG", "RETAIN"))]
U = IdentityRow("user_77", "Ana Souza", "ana.souza@example.org", "+351 912 345 678", "b" * 64, "2026-01-01T00:00:00Z")
REQ = Request("c1", "ana.souza@example.org", "2026-06-01T00:00:00Z", "NOT_STARTED", "2026-06-02T00:00:00Z", AT,
              "Please delete my account and personal data.")


def case(records, activity=()):
    st = Store()
    for i, (system, rid, store_name, kind, present, fields) in enumerate(records):
        st.add_obs(make_obs("evidence_t", f"r{i}", T, T, system, rid, store_name, kind, present, normalize_fields(fields)))
    st.activity = list(activity)
    st.finalize()
    return audit_case(REQ, st, IdentityIndex([U], []), RULES)


AUDIT = ("security_service", "audit_record_77", "inventory", "record", True, {"subject_reference": "user_77", "retention_until": "2031-12-31T23:59:59Z"})


class AccountGap(unittest.TestCase):
    def test_tombstone_deleted_status_resolves_the_account_obligation_without_a_step(self):
        r = case([AUDIT, ("identity_service", "tombstone_77", "bundle", "record", True,
                          {"subject_reference": "user_77", "account_status": "DELETED", "collection": "deleted_customer_references"})])
        acct = [o for o in r.obligations if o.category == "USER_PROFILE"]
        self.assertEqual([(o.verdict, o.reason, o.resource_id) for o in acct], [("COMPLIANT", "account_deleted_per_tombstone", None)])
        self.assertEqual(r.internal, "COMPLETE")
        self.assertFalse(any(s["resource_id"] is None for s in r.steps))
        self.assertEqual({s["resource_id"] for s in r.steps}, {"audit_record_77", "tombstone_77"})

    def test_tombstone_that_is_not_deleted_does_not_resolve_it(self):
        r = case([AUDIT, ("identity_service", "tombstone_77", "bundle", "record", True,
                          {"subject_reference": "user_77", "account_status": "ACTIVE", "collection": "deleted_customer_references"})])
        self.assertEqual([o.verdict for o in r.obligations if o.category == "USER_PROFILE"], ["UNKNOWN"])
        self.assertEqual(r.internal, "UNDETERMINED")

    def test_tombstone_with_exposed_pii_still_violates_even_though_account_is_deleted(self):
        r = case([AUDIT, ("identity_service", "tombstone_77", "bundle", "record", True,
                          {"subject_reference": "user_77", "email": "ana.souza@example.org", "account_status": "DELETED", "collection": "deleted_customer_references"})])
        self.assertEqual(r.internal, "INCOMPLETE")
        self.assertTrue(any(s["operation"] == "REPORT_EXPOSED_PII" for s in r.steps))

    def test_gap_is_classified_by_what_is_known(self):
        none = case([AUDIT])
        gap = [o for o in none.obligations if o.category == "USER_PROFILE"][0]
        self.assertEqual((gap.verdict, gap.detail["gap_class"]), ("UNKNOWN", "no_evidence"))
        self.assertEqual(none.internal, "UNDETERMINED")
        self.assertNotEqual(none.status, "COMPLETE")

    def test_linked_account_means_no_gap(self):
        r = case([AUDIT, ("account_service", "account_77", "inventory", "record", True, {"email": "ana.souza@example.org", "account_status": "ACTIVE"})])
        self.assertEqual([(o.verdict, o.reason) for o in r.obligations if o.category == "USER_PROFILE"], [("VIOLATION", "record_present")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
