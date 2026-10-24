"""Regression tests for the external review findings (P1-1 .. P2-6). Each test is a counterexample that failed
before the corresponding fix.  Run: python3 code/tests/test_review_findings.py"""
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)
sys.path.insert(0, os.path.join(CODE, "evaluation"))

from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.data import AuditChange, IdentityRow  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.intent import classify  # noqa: E402
from ghostaudit.linking import Chain, Link  # noqa: E402
from ghostaudit.obligations import action_table, evaluate  # noqa: E402
from ghostaudit.observations import Store, make_obs  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.validate import validate_row  # noqa: E402

RULES = [{"data_category": c, "required_action": a} for c, a in (
    ("USER_PROFILE", "DELETE"), ("SUPPORT_MESSAGE", "REDACT"), ("ANALYTICS_PROFILE", "ANONYMIZE"),
    ("ACCOUNT_TOMBSTONE", "REDACT"), ("SECURITY_AUDIT_LOG", "RETAIN"))]
AUDIT_AT = "2026-06-15T12:00:00Z"
T = "2026-06-10T00:00:00Z"


def subject():
    u = IdentityRow("user_9999", "Zed Quill", "zed.quill@example.org", "+44 7700 900123", "a" * 64, "2026-01-01T00:00:00Z")
    return IdentityIndex([u], []).resolve("zed.quill@example.org", AUDIT_AT)


def verdict(system, rid, store_name, kind, fields, record_type=None):
    st = Store()
    f = dict(fields)
    if record_type:
        f["record_type"] = record_type
    st.add_obs(make_obs("evidence_x", "r1", T, T, system, rid, store_name, kind, True, normalize_fields(f)))
    st.finalize()
    cv = CaseView(st, AUDIT_AT)
    ln = Link(rid, system, [Chain("direct", "evidence_x", "r1", "x", "x", T)])
    return evaluate(cv, subject(), ln, action_table(RULES))


class ExposureCoverage(unittest.TestCase):
    def test_phone_in_support_message_text_is_exposure(self):
        for text in ("Please call me on +44 7700 900123 about the order.", "call 07700 900123 or 0044 7700 900123 tomorrow"):
            ob = verdict("support_platform", "support_1", "inventory", "record", {"message_text": text, "ticket_id": "CS-1"})
            self.assertEqual(ob.verdict, "VIOLATION", text)

    def test_subject_name_in_text_is_exposure(self):
        ob = verdict("support_platform", "support_2", "inventory", "record", {"message_text": "Customer Zed Quill asked about delivery."})
        self.assertEqual(ob.verdict, "VIOLATION")

    def test_analytics_with_subject_reference_is_still_attributable(self):
        ob = verdict("analytics_platform", "analytics_1", "inventory", "record", {"subject_reference": "user_9999", "audience_cohort": "x"})
        self.assertEqual(ob.verdict, "VIOLATION")
        self.assertEqual(ob.category, "ANALYTICS_PROFILE")

    def test_clean_records_are_still_compliant(self):
        self.assertEqual(verdict("support_platform", "support_3", "inventory", "record", {"message_text": "Order update sent. Ref ORD-20260123."}).verdict, "COMPLIANT")
        self.assertEqual(verdict("analytics_platform", "analytics_2", "inventory", "record", {"audience_cohort": "x"}).verdict, "COMPLIANT")


class Tombstone(unittest.TestCase):
    def test_explicit_record_type_beats_system_default(self):
        ob = verdict("account_service", "tombstone_1", "bundle", "record", {"subject_reference": "user_9999", "account_status": "DELETED"}, record_type="ACCOUNT_TOMBSTONE")
        self.assertEqual(ob.category, "ACCOUNT_TOMBSTONE")
        self.assertEqual(ob.action, "REDACT")
        self.assertEqual(ob.verdict, "COMPLIANT", "only the stable reference remains: it must NOT be recommended for deletion")

    def test_tombstone_by_collection_and_prefix(self):
        ob = verdict("identity_service", "tombstone_2", "bundle", "record", {"subject_reference": "user_9999", "email": "zed.quill@example.org", "collection": "deleted_customer_references"})
        self.assertEqual((ob.category, ob.verdict), ("ACCOUNT_TOMBSTONE", "VIOLATION"))
        ob = verdict("account_service", "tombstone_3", "bundle", "record", {"subject_reference": "user_9999"})
        self.assertEqual(ob.category, "ACCOUNT_TOMBSTONE")


class IntentMixed(unittest.TestCase):
    def test_delete_but_keep_required_records(self):
        i = classify("Delete my account, but do not delete records your policy requires retaining.")
        self.assertTrue(i.deletion)

    def test_newsletter_removal_keep_account(self):
        i = classify("Remove me from the newsletter and keep my account.")
        self.assertFalse(i.deletion)

    def test_mixed_signals_are_never_high_confidence_when_contradictory(self):
        i = classify("Delete my account. Do not delete my account.")
        self.assertEqual(i.confidence, "low")

    def test_more_mixed_forms(self):
        self.assertTrue(classify("Please erase my profile and personal data, but keep the invoices the tax rules require.").deletion)
        self.assertFalse(classify("Unsubscribe me from promotional emails but do not close my account.").deletion)
        self.assertTrue(classify("Eliminen mi cuenta, pero no borren los registros que la ley obliga a conservar.").deletion)


class ValidatorCompleteness(unittest.TestCase):
    def _step(self, n, phase, op, state, ev, rid="r1"):
        return {"step_no": n, "phase": phase, "system_id": "search_service", "resource_id": rid, "operation": op, "state": state, "evidence_id": ev}

    def test_finding_without_remediation_and_verification_is_rejected(self):
        steps = [self._step(1, "FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "e1")]
        errs = validate_row("c", "INCOMPLETE", json.dumps(steps))
        self.assertTrue(any("remediation" in e for e in errs) and any("verification" in e for e in errs), errs)

    def test_remediation_must_match_finding_and_verification_must_match_remediation(self):
        steps = [self._step(1, "FINDING", "REPORT_EXPOSED_PII", "PRESENT", "e1"),
                 self._step(2, "REMEDIATION", "DELETE_RECORD", "ABSENT", ""),
                 self._step(3, "VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "")]
        self.assertTrue(validate_row("c", "INCOMPLETE", json.dumps(steps)), "EXPOSED_PII must be remediated by REDACT/ANONYMIZE")

    def test_complete_chain_is_accepted(self):
        steps = [self._step(1, "FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "e1"),
                 self._step(2, "REMEDIATION", "DELETE_RECORD", "ABSENT", ""),
                 self._step(3, "VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "")]
        self.assertEqual(validate_row("c", "INCOMPLETE", json.dumps(steps)), [])


class EvaluatorGate(unittest.TestCase):
    def _run_all(self, labeled_rc, suite_rc=0):
        import importlib
        import subprocess
        import main as evalmain
        importlib.reload(evalmain)
        fake = subprocess.CompletedProcess([], suite_rc, stdout="", stderr="Ran 1 test\nOK" if suite_rc == 0 else "FAILED")
        with mock.patch.object(evalmain.subprocess, "run", return_value=fake), \
                mock.patch.object(evalmain.subprocess, "call", return_value=labeled_rc), \
                mock.patch("builtins.print"):
            with self.assertRaises(SystemExit) as cm:
                evalmain.cmd_all(None)
        return cm.exception.code

    def test_all_fails_when_labeled_evaluation_fails(self):
        self.assertNotEqual(self._run_all(labeled_rc=3), 0)

    def test_all_fails_when_a_suite_fails(self):
        self.assertNotEqual(self._run_all(labeled_rc=0, suite_rc=1), 0)

    def test_all_passes_when_everything_passes(self):
        self.assertEqual(self._run_all(labeled_rc=0), 0)


class UnknownNotCertified(unittest.TestCase):
    def test_default_policy_never_reports_complete_for_undetermined(self):
        from ghostaudit import run as runner
        fx = os.path.join(CODE, "evaluation", "fixtures", "synth_v1")
        ds, store, results = runner.run_dataset(fx)
        und = [r for r in results if r.internal == "UNDETERMINED"]
        self.assertTrue(und)
        for r in und:
            self.assertNotEqual(r.status, "COMPLETE", r.case_id)
        # the opt-in certifying policy exists only to measure the cost of the default
        _, _, cert = runner.run_dataset(fx, unknown_policy="certify_established")
        self.assertTrue(any(r.status == "COMPLETE" and r.internal == "UNDETERMINED" for r in cert))


if __name__ == "__main__":
    unittest.main(verbosity=2)
