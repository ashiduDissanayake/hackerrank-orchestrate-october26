"""A treatment label (result REDACTED / ANONYMIZED) must not suppress identifiers that the returned payload actually carries,
while query metadata (the lookup key) stays query metadata. Written before the fix (review finding 4)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)
sys.path.insert(0, HERE)

from test_account_proof import AUDIT, CH, REQ_AT, SNAP, U, World  # noqa: E402
from ghostaudit.data import Request  # noqa: E402
from ghostaudit.engine import audit_case  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.observations import make_obs  # noqa: E402

T = "2026-06-05T00:00:00Z"
RULES = [{"data_category": c, "required_action": a} for c, a in (
    ("USER_PROFILE", "DELETE"), ("SECURITY_AUDIT_LOG", "RETAIN"), ("ACCOUNT_TOMBSTONE", "REDACT"), ("ANALYTICS_PROFILE", "ANONYMIZE"),
    ("SUPPORT_MESSAGE", "REDACT"))]
EMAIL = "rui.costa@example.org"


def case(record, rid, system, kind="record_lookup", store="history"):
    w = World().snap("evidence_1", SNAP, "primary", [])        # a clean profile snapshot, so the account obligation is not the subject here
    w.st.add_obs(make_obs("evidence_t", "/t", T, T, system, rid, store, kind, True, normalize_fields({"resource_id": rid, **record})))
    w.st.add_obs(make_obs("evidence_a", "/a", T, T, "security_service", "audit_record_7", "primary", "record", True,
                          normalize_fields({"subject_reference": "user_7", "retention_until": "2031-12-31T23:59:59Z"})))
    w.st.finalize()
    r = Request("c1", EMAIL, REQ_AT, "NOT_STARTED", "2026-06-02T00:00:00Z", AUDIT, "Please delete my account.")
    res = audit_case(r, w.st, IdentityIndex([U], CH), RULES)
    return res, next(o for o in res.obligations if o.resource_id == rid)


class TombstonePayload(unittest.TestCase):
    BASE = {"record_type": "ACCOUNT_TOMBSTONE", "user_id": "user_7", "account_status": "DELETED"}

    def test_redacted_label_with_returned_email_and_name_is_exposed_pii(self):      # the reviewed counterexample
        res, o = case({**self.BASE, "email": EMAIL, "full_name": "Rui Costa", "result": "REDACTED"}, "tombstone_9", "identity_service")
        self.assertEqual((o.verdict, o.reason), ("VIOLATION", "identifiers_exposed"))
        self.assertEqual(res.internal, "INCOMPLETE")
        self.assertIn(("FINDING", "tombstone_9", "REPORT_EXPOSED_PII"), [(s["phase"], s["resource_id"], s["operation"]) for s in res.steps])

    def test_identifiable_label_with_the_same_payload_is_exposed_pii(self):         # positive control: label changed only
        _, o = case({**self.BASE, "email": EMAIL, "full_name": "Rui Costa", "result": "IDENTIFIABLE"}, "tombstone_9", "identity_service")
        self.assertEqual(o.verdict, "VIOLATION")

    def test_redacted_label_with_only_the_stable_reference_is_compliant(self):      # negative control: valid redacted lookup
        res, o = case({**self.BASE, "result": "REDACTED"}, "tombstone_9", "identity_service")
        self.assertEqual((o.verdict, o.reason), ("COMPLIANT", "treated_record_present"))
        self.assertEqual(res.internal, "COMPLETE")

    def test_redacted_label_exposing_only_a_hash_or_phone_field_is_exposed(self):
        for extra in ({"email_hash": "e" * 64}, {"phone": "+351 912 345 678"}):
            _, o = case({**self.BASE, **extra, "result": "REDACTED"}, "tombstone_9", "identity_service")
            self.assertEqual(o.verdict, "VIOLATION", extra)


class QueryMetadataStaysMetadata(unittest.TestCase):
    def test_support_lookup_keyed_by_the_user_id_and_redacted_is_compliant(self):   # shape of the dataset's REDACTED rows
        _, o = case({"record_type": "SUPPORT_MESSAGE", "lookup_value": "user_7", "result": "REDACTED"}, "support_5", "support_platform")
        self.assertEqual(o.verdict, "COMPLIANT")

    def test_lookup_keyed_by_the_email_is_not_retained_pii_when_redacted(self):
        _, o = case({"record_type": "SUPPORT_MESSAGE", "lookup_value": EMAIL, "subject_reference": "user_7", "result": "REDACTED"}, "support_5", "support_platform")
        self.assertEqual((o.verdict, o.reason), ("COMPLIANT", "treated_record_present"))

    def test_email_returned_in_the_payload_of_a_redacted_support_lookup_is_exposed(self):
        _, o = case({"record_type": "SUPPORT_MESSAGE", "lookup_value": "user_7", "message_text": f"please mail {EMAIL}", "result": "REDACTED"}, "support_5", "support_platform")
        self.assertEqual((o.verdict, o.reason), ("VIOLATION", "identifiers_exposed"))

    def test_dataset_shaped_treated_rows_expose_nothing(self):
        """The shapes of all 17 treatment-result observations in the dataset: only query metadata, so the label stands."""
        from ghostaudit.facts import read
        shapes = [({"record_type": "ANALYTICS_PROFILE", "lookup_value": "no direct identifier", "result": "ANONYMIZED"}, "analytics_platform"),
                  ({"record_type": "ANALYTICS_PROFILE", "lookup_value": "", "result": "ANONYMIZED"}, "analytics_platform"),
                  ({"record_type": "ANALYTICS_PROFILE", "subject_reference": "", "result": "ANONYMIZED"}, "analytics_platform"),
                  ({"record_type": "SUPPORT_MESSAGE", "lookup_value": "user_388", "result": "REDACTED"}, "support_platform"),
                  ({"record_type": "SUPPORT_MESSAGE", "subject_reference": "user_388", "result": "REDACTED"}, "support_platform")]
        for rec, system in shapes:
            o = make_obs("e", "/x", T, T, system, "x_1", "history", "record_lookup", True, normalize_fields({"resource_id": "x_1", **rec}))
            self.assertEqual(read(o).exposed, set(), rec)

    def test_anonymized_analytics_that_still_carries_a_user_reference_is_attributable(self):
        _, o = case({"record_type": "ANALYTICS_PROFILE", "user_id": "user_7", "result": "ANONYMIZED"}, "analytics_5", "analytics_platform")
        self.assertEqual((o.verdict, o.reason), ("VIOLATION", "identifiers_exposed"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
