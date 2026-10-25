"""Fictional controls for context ranking; none uses a public answer or case id."""
import os
import sys
import unittest
import tempfile
import json
from dataclasses import replace
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from test_workflow import Q, U, V, CH, CUT  # noqa: E402
from test_account_proof import World, RULES  # noqa: E402
from ghostaudit.data import ActivityRow  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.observations import make_obs  # noqa: E402
from ghostaudit.context_features import learned_cadence  # noqa: E402
from ghostaudit.workflow import WorkflowAttributor, WorkflowConfig  # noqa: E402


def event(rid, at, system="support_platform", op="REDACT_RECORD", aid=None):
    return ActivityRow(aid or "activity_" + rid, at, op, "deletion_worker", system, rid, "SUCCESS", "Operation claim")


class Cadence(unittest.TestCase):
    def test_period_is_estimated_from_times_instead_of_a_fixed_interval(self):
        anchors = [event("support_" + str(i), at) for i, at in enumerate([
            "2026-06-02T11:00:00Z", "2026-06-02T11:02:50Z", "2026-06-02T11:04:50Z"])]
        self.assertEqual(learned_cadence(anchors)["period_seconds"], 17)
        self.assertEqual(learned_cadence(list(reversed(anchors))), learned_cadence(anchors))

    def test_two_points_or_retries_of_one_record_do_not_establish_a_cadence(self):
        anchors = [event("same", at) for at in ["2026-06-02T11:00:00Z", "2026-06-02T11:02:50Z", "2026-06-02T11:04:50Z"]]
        self.assertIsNone(learned_cadence(anchors))
        self.assertIsNone(learned_cadence([replace(a, resource_id=str(i)) for i, a in enumerate(anchors[:2])]))

    def test_irregular_and_account_only_operations_do_not_supply_a_policy_clock(self):
        irregular = [event(str(i), at) for i, at in enumerate([
            "2026-06-02T11:00:00Z", "2026-06-02T11:00:11Z", "2026-06-02T11:01:37Z"])]
        self.assertIsNone(learned_cadence(irregular))
        self.assertIsNone(learned_cadence([replace(a, target_system="account_service", event_type="DELETE_RECORD") for a in irregular]))


def synthetic_matcher(future_anchors=False, same_phase=False):
    w = World()
    events = []
    for j, subject in enumerate([U, V]):
        shift = 0 if j == 0 or same_phase else 6
        for i, secs in enumerate([0, 170, 290]):
            minute, second = divmod(secs + shift, 60)
            at = f"2026-06-02T11:{minute:02d}:{second:02d}Z"
            rid = f"support_{700 + j * 10 + i}"
            available = "2026-06-20T00:00:00Z" if future_anchors else "2026-06-03T00:00:00Z"
            w.st.add_obs(make_obs("anchors", "/" + rid, available, at, "support_platform", rid, "primary", "record", True,
                                  normalize_fields({"email": subject.email, "record_type": "SUPPORT_MESSAGE"})))
            events.append(event(rid, at))
    for i, at in enumerate(["2026-06-02T11:06:14Z", "2026-06-02T11:06:20Z"]):
        rid = f"analytics_{900 + i}"
        w.st.add_obs(make_obs("analytics", "/" + rid, "2026-06-03T00:00:00Z", at, "analytics_platform", rid, "primary", "record", True,
                              normalize_fields({"record_type": "ANALYTICS_PROFILE", "email": None, "user_ref": None})))
        events.append(event(rid, at, "analytics_platform", "ANONYMIZE_RECORD"))
    w.st.activity = events
    w.st.finalize()
    other = replace(Q, case_id="independent-request", email=V.email)
    return WorkflowAttributor(w.st, IdentityIndex([U, V], CH), [Q, other], WorkflowConfig(scoring="contextual_v2"), RULES), other


class ContextRanking(unittest.TestCase):
    def test_an_absent_lookup_does_not_supply_an_anonymous_record_candidate(self):
        w = World()
        rid, at = "analytics_876", "2026-06-02T11:06:14Z"
        w.st.add_obs(make_obs("empty", "/lookup", "2026-06-03T00:00:00Z", at, "analytics_platform", rid, "primary", "lookup", False,
                              normalize_fields({"record_type": "ANALYTICS_PROFILE", "http_status": "404"})))
        w.st.activity = [event(rid, at, "analytics_platform", "ANONYMIZE_RECORD")]
        w.st.finalize()
        m = WorkflowAttributor(w.st, IdentityIndex([U, V], CH), [Q], WorkflowConfig(), RULES)
        self.assertFalse(m.proposals(Q))

    def test_a_later_absence_overrides_an_old_anonymous_record_for_candidate_eligibility(self):
        w = World()
        rid = "analytics_876"
        for at, present, kind in [("2026-06-02T11:00:00Z", True, "record"), ("2026-06-02T11:30:00Z", False, "lookup")]:
            w.st.add_obs(make_obs("states", "/" + at, "2026-06-03T00:00:00Z", at, "analytics_platform", rid, "primary", kind, present,
                                  normalize_fields({"record_type": "ANALYTICS_PROFILE"})))
        w.st.activity = [event(rid, "2026-06-02T11:06:14Z", "analytics_platform", "ANONYMIZE_RECORD")]
        w.st.finalize()
        m = WorkflowAttributor(w.st, IdentityIndex([U, V], CH), [Q], WorkflowConfig(), RULES)
        self.assertFalse(m.proposals(Q))

    def test_distinct_identity_anchored_clocks_rank_anonymous_policy_operations(self):
        m, other = synthetic_matcher()
        a = next(p for p in m.proposals(Q) if p["system_id"] == "analytics_platform")
        b = next(p for p in m.proposals(other) if p["system_id"] == "analytics_platform")
        self.assertEqual(a["resource_id"], "analytics_900")
        self.assertEqual(b["resource_id"], "analytics_901")
        self.assertEqual(a["features"]["context"]["cadence"]["period_seconds"], 17)
        self.assertFalse(a["certified"])

    def test_identical_clocks_do_not_break_a_tie_by_request_name(self):
        m, other = synthetic_matcher(same_phase=True)
        self.assertFalse(m.proposals(Q))
        self.assertFalse(m.proposals(other))

    def test_post_cutoff_identity_observations_cannot_supply_clock_anchors(self):
        m, other = synthetic_matcher(future_anchors=True)
        self.assertFalse(m.proposals(Q))
        self.assertFalse(m.proposals(other))
        for d in m.decisions(Q):
            for p in d["candidates"]:
                self.assertIsNone(p["features"]["context"]["cadence"])


class CandidateArtifact(unittest.TestCase):
    def test_requested_filename_keeps_unknowns_and_validation_errors_visible(self):
        from ghostaudit import export, run
        data = os.path.join(os.path.dirname(HERE), "evaluation", "fixtures", "synth_v4")
        ds, store, results = run.run_dataset(data, workflow_mode="joint")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "source.csv")
            run.write_output(results, path)
            errors = export.validate_output(ds, path)
            manifest = export.build_manifest([], {"workflow_mode": "joint"}, ds, results, path, errors)
            paths, register = export.write_candidate(ds, results, errors, manifest, tmp)
            self.assertEqual(open(paths["output.csv"], "rb").read(), open(path, "rb").read())
            m = json.load(open(paths["output.manifest.json"]))
            self.assertFalse(m["certified"])
            self.assertFalse(m["final"])
            self.assertEqual(m["kind"], "submission_candidate")
            self.assertEqual(m["validation_errors"], errors)
            self.assertTrue(register)
            self.assertEqual(export.validate_output(ds, paths["output.csv"]), errors)
            self.assertFalse(os.path.exists(os.path.join(tmp, "output_best_effort.csv")))
            # An explicit candidate must not replace a previously certified artifact.
            m["certified"] = True
            with open(paths["output.manifest.json"], "w") as f:
                json.dump(m, f)
            before = open(paths["output.csv"], "rb").read()
            with self.assertRaises(ValueError):
                export.write_candidate(ds, results, errors, manifest, tmp)
            self.assertEqual(open(paths["output.csv"], "rb").read(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
