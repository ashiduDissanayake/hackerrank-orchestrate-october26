"""Independent synthetic controls for the opt-in workflow experiment (no public-answer fixtures)."""
import itertools
import math
import os
import random
import sys
import unittest
import tempfile
import subprocess
from dataclasses import replace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from test_account_proof import CH, U, World  # noqa: E402
from ghostaudit.data import ActivityRow, IdentityRow, Request, Dataset, ManifestEntry  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.observations import make_obs  # noqa: E402
from ghostaudit.workflow import WorkflowAttributor, WorkflowConfig, maximum_assignment  # noqa: E402

CUT = "2026-06-15T12:00:00Z"
Q = Request("arbitrary-request", U.email, "2026-06-01T00:00:00Z", "COMPLETE", "2026-06-02T12:00:00Z", CUT, "Please delete my account.")
V = IdentityRow("user_8", "Mina Silva", "mina.silva@example.org", "+351 913 456 789", "f" * 64, "2026-05-01T00:00:00Z")


def activity(rid="account_900", at="2026-06-02T11:58:00Z", result="SUCCESS", source="deletion_worker", aid="activity_w"):
    return ActivityRow(aid, at, "DELETE_RECORD", source, "account_service", rid, result, "Worker reported an operation result.")


def matcher(events=None, history=None, observations=(), config=None):
    w = World()
    w.st.activity = events if events is not None else [activity()]
    for o in observations:
        w.st.add_obs(o)
    w.st.finalize()
    return WorkflowAttributor(w.st, IdentityIndex([U, V], CH), history if history is not None else [Q], config)


class Assignment(unittest.TestCase):
    def test_joint_optimum_beats_independent_greedy_choices(self):
        score, matches = maximum_assignment({"one": {"first": 4, "second": 3}, "two": {"first": 3.9}})
        self.assertAlmostEqual(score, 6.9)
        self.assertEqual(matches, {"one": "second", "two": "first"})

    def test_negative_edges_are_left_unassigned(self):
        self.assertEqual(maximum_assignment({"one": {"first": -2}}), (0, {}))

    def test_forbidden_edge_measures_the_best_real_alternative(self):
        rows = {"one": {"first": 4, "second": 3}, "two": {"first": 3.9}}
        self.assertAlmostEqual(maximum_assignment(rows, ("one", "second"))[0], 4)

    def test_solver_matches_exhaustive_search_on_small_random_graphs(self):
        rng = random.Random(302)
        for _ in range(35):
            rows = {str(i): {str(j): rng.randrange(-3, 8) / 2 for j in range(3) if rng.random() < .8} for i in range(3)}
            best = 0
            for choice in itertools.product(*[[None] + list(es) for es in rows.values()]):
                selected = [r for r in choice if r is not None]
                if len(selected) != len(set(selected)):
                    continue
                best = max(best, sum(rows[k][rid] for k, rid in zip(rows, choice) if rid is not None))
            self.assertAlmostEqual(maximum_assignment(rows)[0], best)

    def test_nonfinite_scores_and_margins_are_rejected(self):
        for n in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                maximum_assignment({"one": {"first": n}})
            with self.assertRaises(ValueError):
                WorkflowConfig(min_margin=n)


class Proposals(unittest.TestCase):
    def test_single_candidate_keeps_its_claim_and_uncertainty_provenance(self):
        p = matcher().proposals(Q)[0]
        self.assertEqual(p["resource_id"], "account_900")
        self.assertEqual(p["activity_id"], "activity_w")
        self.assertEqual(p["basis"], "inferred_workflow_assignment")
        self.assertFalse(p["certified"])
        self.assertGreater(p["margin"], .25)

    def test_equal_competing_requests_abstain_regardless_of_case_names(self):
        other = replace(Q, case_id="zzz", email=V.email)
        m = matcher(history=[Q, other])
        self.assertEqual(m.proposals(Q), [])
        self.assertEqual(m.proposals(other), [])
        self.assertEqual(m.decisions(Q)[0]["reason"], "ambiguous_or_low_margin")

    def test_outcomes_are_attribution_clues_not_deletion_state(self):
        other = replace(Q, case_id="second", email=V.email, reported_status="NOT_STARTED")
        events = [activity(), activity("account_901", "2026-06-02T11:57:00Z", "FAILED", aid="activity_second")]
        m = matcher(events, [Q, other])
        self.assertEqual(m.proposals(Q)[0]["resource_id"], "account_900")
        self.assertEqual(m.proposals(other)[0]["resource_id"], "account_901")

    def test_row_shuffle_and_case_id_renaming_cannot_resolve_a_tie(self):
        other = replace(Q, case_id="001", email=V.email)
        for history in ([Q, other], [other, Q], [replace(other, case_id="ZZ"), replace(Q, case_id="AA")]):
            m = matcher(history=history)
            for q in history:
                self.assertFalse(m.proposals(q))

    def test_a_future_request_cannot_steal_an_earlier_candidate(self):
        future = replace(Q, case_id="future", email=V.email, requested_at="2026-06-20T00:00:00Z")
        self.assertEqual(matcher(history=[Q, future]).proposals(Q), matcher().proposals(Q))

    def test_future_activity_does_not_enter_the_graph(self):
        self.assertEqual(matcher([activity(at="2026-06-20T00:00:00Z")]).proposals(Q), [])

    def test_future_identity_evidence_does_not_change_an_earlier_assignment(self):
        later = make_obs("later", "/a", "2026-06-20T00:00:00Z", "2026-06-02T00:00:00Z", "account_service", "account_900", "primary", "record", True,
                         normalize_fields({"email": V.email}))
        self.assertEqual(matcher(observations=[later]).proposals(Q), matcher().proposals(Q))

    def test_returned_other_identity_is_a_hard_exclusion(self):
        o = make_obs("now", "/a", "2026-06-03T00:00:00Z", "2026-06-02T00:00:00Z", "account_service", "account_900", "primary", "record", True,
                     normalize_fields({"email": V.email}))
        self.assertEqual(matcher(observations=[o]).proposals(Q), [])

    def test_non_deletion_worker_activity_does_not_supply_candidates(self):
        self.assertEqual(matcher([activity(source="unrelated_worker")]).proposals(Q), [])

    def test_non_deletion_request_cannot_receive_inferred_resources(self):
        q = replace(Q, request_text="Please update my phone and keep my account active.")
        self.assertEqual(matcher(history=[q]).proposals(q), [])

    def test_record_outside_the_window_does_not_supply_candidates(self):
        self.assertEqual(matcher([activity(at="2026-06-02T09:00:00Z")]).proposals(Q), [])

    def test_operation_before_the_request_does_not_supply_candidates(self):
        q = replace(Q, requested_at="2026-06-02T11:59:00Z")
        self.assertFalse(matcher(history=[q]).proposals(q))

    def test_existing_exact_account_link_is_not_replaced(self):
        o = make_obs("now", "/a", "2026-06-03T00:00:00Z", "2026-06-02T00:00:00Z", "account_service", "account_exact", "primary", "record", True,
                     normalize_fields({"email": U.email}))
        self.assertFalse(matcher(observations=[o]).proposals(Q))

    def test_a_high_margin_setting_can_abstain_without_mutating_other_runs(self):
        strict = matcher(config=WorkflowConfig(min_margin=100))
        self.assertFalse(strict.proposals(Q))
        self.assertTrue(matcher().proposals(Q))


class AuditAndRelease(unittest.TestCase):
    def _audit(self, scope):
        from ghostaudit.engine import audit_case
        from test_account_proof import RULES
        w = World()
        if scope:
            w.snap("evidence_scope", "2026-05-15T00:00:00Z" if scope == "old" else "2026-06-10T00:00:00Z", "primary", [])
        w.st.add_obs(make_obs("evidence_audit", "/a", "2026-06-10T00:00:00Z", "2026-06-10T00:00:00Z", "security_service", "audit_record_7", "primary", "record", True,
                              normalize_fields({"subject_reference": U.user_id, "retention_until": "2031-12-31T23:59:59Z"})))
        w.st.activity = [activity()]
        w.st.finalize()
        ix = IdentityIndex([U, V], CH)
        at = WorkflowAttributor(w.st, ix, [Q])
        res = audit_case(Q, w.st, ix, RULES, workflow_inferences=at.proposals(Q), workflow_decisions=at.decisions(Q))
        return res

    def test_success_claim_without_state_evidence_never_becomes_verified_absence(self):
        r = self._audit(scope=False)
        self.assertTrue(r.workflow_inferences)
        self.assertEqual(r.internal, "UNDETERMINED")
        self.assertEqual([(o.verdict, o.reason) for o in r.obligations if o.resource_id == "account_900"], [("UNKNOWN", "no_admissible_evidence")])
        self.assertNotIn("account_900", [s["resource_id"] for s in r.steps])

    def test_ownership_hypothesis_and_independent_state_proof_are_both_recorded(self):
        r = self._audit(scope=True)
        self.assertEqual(r.internal, "COMPLETE")
        self.assertEqual([s["resource_id"] for s in r.steps if s["operation"] == "VERIFY_RECORD_ABSENT"], ["account_900"])
        self.assertEqual(r.workflow_inferences[0]["basis"], "inferred_workflow_assignment")
        self.assertFalse(r.workflow_inferences[0]["certified"])

    def test_a_pre_request_snapshot_cannot_certify_a_newly_inferred_profile(self):
        r = self._audit(scope="old")
        self.assertEqual(r.internal, "UNDETERMINED")
        self.assertNotIn("account_900", [s["resource_id"] for s in r.steps])

    def test_a_structurally_valid_inferred_answer_cannot_pass_the_gate(self):
        from ghostaudit import export, run
        r = self._audit(scope=True)
        with tempfile.TemporaryDirectory() as tmp:
            ds = Dataset(tmp, [Q], [], [], [], [], [ManifestEntry(eid, "unused", "synthetic", "2026-06-10T00:00:00Z") for eid in ("evidence_scope", "evidence_audit")])
            out = os.path.join(tmp, "o.csv")
            run.write_output([r], out)
            self.assertEqual(export.validate_output(ds, out), [])
            for mode in ("joint", "evidence"):  # results also guard against a forged configuration
                m = export.build_manifest([], {"workflow_mode": mode, "unknown_policy": "not_certified", "png_extraction": "complete"}, ds, [r], out, [])
                reasons = export.gate(ds, [r], out, m, allow_dirty=True, run_tests=False)
                self.assertTrue(any("workflow inference" in s for s in reasons))
                self.assertFalse(m["certified"])

    def test_run_cannot_write_the_certified_submission_path(self):
        from pathlib import Path
        repo = Path(__file__).resolve().parents[2]
        target = repo / "output.csv"
        before = target.read_bytes() if target.exists() else None
        p = subprocess.run([sys.executable, str(repo / "code/main.py"), "run", "--data", "/does/not/exist", "--out", str(target), "--workflow-mode", "joint"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("only export", p.stderr)
        self.assertEqual(target.read_bytes() if target.exists() else None, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
