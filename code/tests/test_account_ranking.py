"""Independent controls for account-ranking features; no public answer IDs."""
import os
import sys
import unittest
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from test_account_proof import World, U  # noqa: E402
from test_workflow import Q, CUT, activity, V, CH  # noqa: E402
from test_account_proof import RULES  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.context_features import account_context  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.observations import make_obs  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.workflow import WorkflowAttributor, WorkflowConfig  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
from audit_account_links import optimal_options  # noqa: E402


def subject():
    from ghostaudit.identity import IdentityIndex
    from test_account_proof import CH
    return IdentityIndex([U], CH).resolve(Q.email, CUT)


def evidence(w, at="2026-06-03T00:00:00Z", available=None, present=False, store="primary"):
    o = make_obs("explicit_" + store, "/lookup", available or at, at, "account_service", "account_765", store,
                 "lookup" if not present else "record", present,
                 normalize_fields({"record_type": "USER_PROFILE"}))
    w.st.add_obs(o)


def rank(w, clean=True, anchors=()):
    w.st.finalize()
    proposal = {"resource_id": "account_765", "system_id": "account_service",
                "features": {"anchor_distance_hours": 0.5}}
    return account_context(CaseView(w.st, CUT), proposal, Q, subject(), list(anchors),
                           {"independently_compliant_context": clean})


class AccountContext(unittest.TestCase):
    def test_explicit_current_absence_interacts_with_compliant_context(self):
        w = World(); evidence(w)
        bonus, details = rank(w)
        self.assertEqual(bonus, 1)
        self.assertTrue(details["state_affinity_applied"])
        self.assertEqual(details["explicit_absence_evidence_ids"], ["explicit_primary"])
        self.assertFalse(details["ownership_proven"])

    def test_compliance_alone_and_absence_alone_do_not_supply_the_bonus(self):
        self.assertEqual(rank(World())[0], 0)
        w = World(); evidence(w)
        self.assertEqual(rank(w, clean=False)[0], 0)

    def test_future_capture_and_pre_request_lookup_do_not_supply_state_affinity(self):
        w = World(); evidence(w, available="2026-06-20T00:00:00Z")
        self.assertEqual(rank(w)[0], 0)
        w = World(); evidence(w, at="2026-05-15T00:00:00Z")
        self.assertEqual(rank(w)[0], 0)

    def test_later_presence_or_a_populated_replica_blocks_state_affinity(self):
        w = World(); evidence(w); evidence(w, at="2026-06-04T00:00:00Z", present=True)
        self.assertEqual(rank(w)[0], 0)
        w = World(); evidence(w); evidence(w, present=True, store="replica_eu")
        self.assertEqual(rank(w)[0], 0)

    def test_inventory_omission_does_not_count_as_an_explicit_lookup(self):
        w = World(); w.snap("inventory", "2026-06-04T00:00:00Z", "primary", [])
        bonus, details = rank(w)
        self.assertEqual(bonus, 0)
        self.assertEqual(details["explicit_absence_evidence_ids"], [])

    def test_three_distinct_identity_linked_resources_strengthen_anchor_distance(self):
        anchors = [replace(activity(), resource_id=f"support_{i}", activity_id=f"policy_{i}") for i in range(3)]
        bonus, details = rank(World(), anchors=anchors)
        self.assertEqual(bonus, -0.5)
        self.assertTrue(details["strong_anchor_context"])
        self.assertEqual(details["independent_anchor_count"], 3)

    def test_retries_of_one_resource_do_not_create_independent_anchors(self):
        anchors = [replace(activity(), resource_id="support_one", activity_id=f"retry_{i}") for i in range(4)]
        bonus, details = rank(World(), anchors=anchors)
        self.assertEqual(bonus, 0)
        self.assertFalse(details["strong_anchor_context"])


class JointRanking(unittest.TestCase):
    def world(self, strong=False):
        w = World()
        other = replace(Q, case_id="another-request", email=V.email)
        for j, owner in enumerate([U, V]):
            rid = "audit_record_" + str(750 + j)
            w.st.add_obs(make_obs("subjects", "/" + rid, "2026-06-03T00:00:00Z", "2026-06-03T00:00:00Z",
                                  "security_service", rid, "primary", "record", True,
                                  normalize_fields({"subject_reference": owner.user_id, "retention_until": "2031-01-01T00:00:00Z"})))
        events = [activity("account_900", "2026-06-02T10:48:00Z", aid="op_one"),
                  activity("account_901", "2026-06-02T11:08:00Z", aid="op_two")]
        for i in range(2 if strong else 1):
            rid = "account_" + str(900 + i)
            w.st.add_obs(make_obs("lookups", "/" + rid, "2026-06-03T00:00:00Z", "2026-06-03T00:00:00Z",
                                  "account_service", rid, "primary", "lookup", False,
                                  normalize_fields({"record_type": "USER_PROFILE"})))
        if strong:
            for i, minute in enumerate([38, 45, 52]):
                rid, at = f"support_{780+i}", f"2026-06-02T11:{minute}:00Z"
                w.st.add_obs(make_obs("subjects", "/" + rid, "2026-06-03T00:00:00Z", at,
                                      "support_platform", rid, "primary", "record", True,
                                      normalize_fields({"subject_reference": V.user_id, "record_type": "SUPPORT_MESSAGE"})))
                events.append(replace(activity(), activity_id=f"anchor_{i}", resource_id=rid,
                                      target_system="support_platform", event_type="REDACT_RECORD", event_time=at))
        else:
            w.st.add_obs(make_obs("subjects", "/search", "2026-06-03T00:00:00Z", "2026-06-03T00:00:00Z",
                                  "search_service", "search_790", "primary", "record", True,
                                  normalize_fields({"email": V.email})))
        w.st.activity = events
        w.st.finalize()
        return w, other

    def test_observed_state_affinity_resolves_a_joint_tie_without_treating_claims_as_state(self):
        w, other = self.world()
        ix = IdentityIndex([U, V], CH)
        old = WorkflowAttributor(w.st, ix, [Q, other], WorkflowConfig(scoring="contextual_v2"), RULES)
        self.assertFalse(old.proposals(Q))
        self.assertFalse(old.proposals(other))
        new = WorkflowAttributor(w.st, ix, [other, Q], WorkflowConfig(), RULES)
        self.assertEqual(new.proposals(Q)[0]["resource_id"], "account_900")
        self.assertEqual(new.proposals(other)[0]["resource_id"], "account_901")
        self.assertFalse(new.proposals(other)[0]["features"]["account_context"]["state_affinity_applied"])
        self.assertFalse(new.proposals(other)[0]["certified"])

    def test_independent_anchors_resolve_two_equally_absent_profiles_and_ignore_case_id_order(self):
        w, other = self.world(strong=True)
        ix = IdentityIndex([U, V], CH)
        old = WorkflowAttributor(w.st, ix, [Q, other], WorkflowConfig(scoring="contextual_v2"), RULES)
        self.assertFalse(old.proposals(Q))
        a, b = replace(Q, case_id="zebra"), replace(other, case_id="ant")
        new = WorkflowAttributor(w.st, ix, [b, a], WorkflowConfig(), RULES)
        self.assertEqual(new.proposals(a)[0]["resource_id"], "account_900")
        self.assertEqual(new.proposals(b)[0]["resource_id"], "account_901")


class AmbiguityWitnesses(unittest.TestCase):
    def test_equal_global_assignments_publish_both_targets(self):
        result = optimal_options({"one": {"x": 3, "y": 3}, "two": {"x": 2, "y": 2}}, "one")
        self.assertEqual(result["equally_optimal_resource_ids"], ["x", "y"])
        self.assertEqual(len(result["witnesses"]), 2)
        self.assertEqual({w["score"] for w in result["witnesses"]}, {5})

    def test_unique_assignment_does_not_publish_a_weaker_alternative(self):
        result = optimal_options({"one": {"x": 4, "y": 2}, "two": {"x": 3, "y": 4}}, "one")
        self.assertEqual(result["equally_optimal_resource_ids"], ["x"])

    def test_null_assignment_is_retained_when_every_candidate_is_worse(self):
        result = optimal_options({"one": {"x": -2}}, "one")
        self.assertTrue(result["null_is_optimal"])
        self.assertEqual(result["equally_optimal_resource_ids"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
