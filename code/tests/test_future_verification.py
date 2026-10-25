"""Future checks in proven-INCOMPLETE cases must not assert unknown current facts."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ghostaudit.obligations import Obligation  # noqa: E402
from ghostaudit.planner import plan  # noqa: E402


def violation():
    return Obligation("search_service", "search_live", "SEARCH_INDEX_ENTRY", "DELETE", "VIOLATION", "record_present", "proof")


def unknown(reason="no_admissible_evidence", resource="account_known", action="DELETE", system="account_service", category="USER_PROFILE"):
    return Obligation(system, resource, category, action, "UNKNOWN", reason)


class FutureVerification(unittest.TestCase):
    def test_known_account_gets_a_future_check_without_a_fabricated_finding_or_remediation(self):
        steps = plan([violation(), unknown()], "INCOMPLETE")
        account = [s for s in steps if s["resource_id"] == "account_known"]
        self.assertEqual([(s["phase"], s["operation"], s["evidence_id"]) for s in account],
                         [("VERIFICATION", "VERIFY_RECORD_ABSENT", "")])
        self.assertEqual([s["step_no"] for s in steps], list(range(1, len(steps) + 1)))

    def test_required_retained_record_gets_a_future_presence_check(self):
        audit = unknown("retained_record_not_found", "audit_known", "RETAIN", "security_service", "SECURITY_AUDIT_LOG")
        checks = [s for s in plan([violation(), audit], "INCOMPLETE") if s["resource_id"] == "audit_known"]
        self.assertEqual([(s["phase"], s["operation"], s["state"], s["evidence_id"]) for s in checks],
                         [("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT", "")])

    def test_an_unresolved_case_without_a_real_finding_gets_no_future_check_escape(self):
        self.assertEqual(plan([unknown()], "INCOMPLETE"), [])
        null_violation = violation(); null_violation.resource_id = None
        self.assertEqual(plan([unknown(), null_violation], "INCOMPLETE"), [])

    def test_unknown_ownership_policy_or_resource_id_does_not_produce_a_check(self):
        for reason in ["conflicting_identity_evidence", "shared_attachment", "category_unresolved", "unresolved_link"]:
            self.assertFalse([s for s in plan([violation(), unknown(reason)], "INCOMPLETE") if s["resource_id"] == "account_known"])
        self.assertFalse([s for s in plan([violation(), unknown(resource=None)], "INCOMPLETE") if s["system_id"] == "account_service"])
        self.assertFalse([s for s in plan([violation(), unknown(category=None)], "INCOMPLETE") if s["resource_id"] == "account_known"])

    def test_excluded_obligations_do_not_gain_future_checks(self):
        for flag in ("no_step", "no_obligation"):
            ob = unknown(); ob.detail[flag] = True
            self.assertFalse([s for s in plan([violation(), ob], "INCOMPLETE") if s["resource_id"] == ob.resource_id])

    def test_complete_cases_still_require_current_compliant_evidence(self):
        self.assertEqual(plan([unknown()], "COMPLETE"), [])

    def test_inferred_ownership_keeps_its_uncertainty_and_only_adds_the_future_check(self):
        ob = unknown("inferred_profile_state_not_established")
        checks = [s for s in plan([violation(), ob], "INCOMPLETE") if s["resource_id"] == ob.resource_id]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["operation"], "VERIFY_RECORD_ABSENT")
        self.assertEqual(ob.verdict, "UNKNOWN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
