"""Independent fictional counterexamples for explicit submission assumptions."""
import os
import sys
import unittest
import tempfile
import subprocess
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_account_proof import World, U, CH, OTHER, MINE_UID, REQ_AT, AUDIT, RULES, subj
from ghostaudit.caseview import CaseView
from ghostaudit.engine import audit_case
from ghostaudit.data import Request
from ghostaudit.identity import IdentityIndex
from ghostaudit.extract.common import normalize_fields
from ghostaudit.observations import make_obs
from ghostaudit.pipeline import CatalogLink
from ghostaudit.obligations import Obligation, evaluate, action_table
from ghostaudit.linking import link_subject
from ghostaudit.prediction import resolve

AT = "2026-06-10T00:00:00Z"
LATER = "2026-06-11T00:00:00Z"
RULES_ALL = RULES + [{"data_category": "MARKETING_PROFILE", "required_action": "DELETE"}]
Q = Request("fictional-request", U.email, REQ_AT, "COMPLETE", AT, AUDIT, "Delete my account.")


def add(w, rid, fields, system="backup_service", t=AT, available=None):
    w.st.add_obs(make_obs("proof_" + rid, "/row", available or t, t, system, rid, "ui", "ui_record", True, normalize_fields(fields)))
    return w


def run(w, policy="submission", req=Q):
    w.st.finalize()
    return audit_case(req, w.st, IdentityIndex([U], CH), RULES_ALL, decision_policy=policy)


def archive_fields(**changes):
    return {"email": U.email, "archive_path": "s3://fictional-vault/customer-weekly.bin", "checksum": "Verified",
            "last_drill": "2026-05-01", "retention_end": "2026-09-01", **changes}


class ArchivePredictions(unittest.TestCase):
    def test_verified_retained_archive_predicts_risk_without_inventing_a_flag(self):
        w = add(World(), "backup_712", archive_fields())
        strict, predicted = run(w, "strict"), run(w)
        self.assertEqual(strict.obligations[0].verdict, "UNKNOWN")
        ob = next(o for o in predicted.obligations if o.resource_id == "backup_712")
        self.assertEqual((ob.verdict, ob.reason), ("VIOLATION", "predicted_recoverable_archive_risk"))
        self.assertEqual(predicted.decision_inferences[0]["rule"], "recoverable_archive_risk")
        finding = next(s for s in predicted.steps if s["phase"] == "FINDING")
        self.assertEqual((finding["operation"], finding["evidence_id"]), ("REPORT_RESTORE_RISK", "proof_backup_712"))
        self.assertIsNone(w.st._obs[0].f("restore_allowed"))

    def test_archive_listing_alone_or_missing_capability_fields_stays_unknown(self):
        for changes in ({"archive_path": None}, {"checksum": "Failed"}, {"last_drill": None},
                        {"last_drill": "2026-07-01"}, {"retention_end": "2026-05-01"}):
            r = run(add(World(), "backup_712", archive_fields(**changes)))
            self.assertFalse(r.decision_inferences)
            self.assertEqual(next(o for o in r.obligations if o.resource_id == "backup_712").verdict, "UNKNOWN")

    def test_explicit_restore_block_wins_over_recovery_metadata(self):
        r = run(add(World(), "backup_712", archive_fields(restore_allowed=False)))
        self.assertFalse(r.decision_inferences)
        self.assertEqual(next(o for o in r.obligations if o.resource_id == "backup_712").verdict, "COMPLIANT")

    def test_either_future_timestamp_hides_archive_capability(self):
        for t, available in [(AT, "2026-06-20T00:00:00Z"), ("2026-06-20T00:00:00Z", AT)]:
            r = run(add(World(), "backup_712", archive_fields(), t=t, available=available))
            self.assertFalse(r.decision_inferences)
            self.assertFalse([s for s in r.steps if s["resource_id"] == "backup_712"])


def marketing_world(*, fields=None, observed=AT, owner_time=LATER, extra_catalog=()):
    w = add(World(), "marketing_731", fields or {"email": "another.person@example.org"}, "marketing_platform", observed)
    w.st.catalog_links = [CatalogLink(activity_id="catalog_owner", event_time=owner_time, system_id="marketing_platform",
                                     resource_id="marketing_731", email=U.email, user_ref=U.user_id, exclusive=False), *extra_catalog]
    return w


class OwnerPredictions(unittest.TestCase):
    def test_later_stable_mapping_predicts_ownership_but_does_not_merge_people(self):
        w = marketing_world()
        r = run(w)
        ob = next(o for o in r.obligations if o.resource_id == "marketing_731")
        self.assertEqual(ob.verdict, "VIOLATION")
        self.assertEqual(r.decision_inferences[0]["source_evidence_ids"], ["catalog_owner", "proof_marketing_731"])
        self.assertNotIn("another.person@example.org", [i.value for i in r.subject.identifiers])
        self.assertEqual(run(w, "strict").obligations[0].verdict, "UNKNOWN")

    def test_competing_stable_user_id_cannot_be_overridden(self):
        r = run(marketing_world(fields={"email": "another.person@example.org", "user_id": "user_999"}))
        self.assertFalse(r.decision_inferences)
        self.assertEqual(r.obligations[0].verdict, "UNKNOWN")

    def test_newer_or_same_time_contact_evidence_keeps_the_conflict(self):
        for t in (LATER, "2026-06-12T00:00:00Z"):
            self.assertFalse(run(marketing_world(observed=t)).decision_inferences)

    def test_future_mapping_and_competing_latest_mapping_do_not_resolve_ownership(self):
        self.assertFalse(run(marketing_world(owner_time="2026-06-20T00:00:00Z")).decision_inferences)
        other = CatalogLink(activity_id="other_owner", event_time=LATER, system_id="marketing_platform", resource_id="marketing_731",
                            email="another.person@example.org", user_ref="user_999", exclusive=False)
        self.assertFalse(run(marketing_world(extra_catalog=[other])).decision_inferences)

    def test_policy_and_shared_attachment_conflicts_stay_unresolved(self):
        w = marketing_world(); w.st.finalize(); cv = CaseView(w.st, AUDIT); s = subj(); links = link_subject(cv, s).links
        for cat, act in [("SUPPORT_ATTACHMENT", "DELETE"), ("SUPPORT_MESSAGE", "REDACT")]:
            ob = Obligation("marketing_platform", "marketing_731", cat, act, "UNKNOWN", "conflicting_identity_evidence")
            obs, decisions = resolve(Q, cv, s, [ob], links, action_table(RULES_ALL))
            self.assertEqual(obs[0].verdict, "UNKNOWN"); self.assertFalse(decisions)


class SnapshotPredictions(unittest.TestCase):
    def old(self, **kw):
        return World().snap("snapshot_old", "2026-05-20T00:00:00Z", "primary", [OTHER], **kw)

    def test_clean_old_snapshot_predicts_subject_absence_without_an_id(self):
        w = self.old()
        strict, predicted = run(w, "strict"), run(w)
        self.assertEqual(strict.internal, "UNDETERMINED")
        ob = next(o for o in predicted.obligations if o.category == "USER_PROFILE")
        self.assertIsNone(ob.resource_id)
        self.assertEqual(ob.verdict, "COMPLIANT")
        self.assertEqual(predicted.decision_inferences[0]["rule"], "clean_snapshot_persistence")
        self.assertEqual(predicted.steps, [])  # the policy never invents an account id to fill a row

    def test_partial_non_profile_and_unattributable_snapshots_cannot_supply_persistence(self):
        worlds = [self.old(complete=False), self.old(collection="notification_preferences"),
                  World().snap("anon", "2026-05-20T00:00:00Z", "primary", [{}]),
                  World().snap("future", "2026-06-20T00:00:00Z", "primary", [OTHER])]
        for w in worlds:
            self.assertFalse(run(w).decision_inferences)

    def test_a_profile_ever_seen_or_a_populated_replica_blocks_the_assumption(self):
        w = self.old().snap("older_presence", "2026-05-10T00:00:00Z", "primary", [MINE_UID])
        self.assertFalse(run(w).decision_inferences)
        w = self.old().snap("replica", "2026-05-20T00:00:00Z", "failover_replica", [MINE_UID])
        self.assertFalse(run(w).decision_inferences)

    def test_case_names_do_not_change_decisions_and_invalid_modes_fail(self):
        a, b = run(self.old()), run(self.old(), req=replace(Q, case_id="different-name"))
        self.assertEqual(a.decision_inferences, b.decision_inferences)
        self.assertEqual(a.steps, b.steps)
        with self.assertRaises(ValueError): run(self.old(), "typo")


class DisclosureAndReadiness(unittest.TestCase):
    def test_strict_gate_rejects_predictions_even_if_configuration_is_falsified(self):
        from ghostaudit import export
        r = run(add(World(), "backup_712", archive_fields()))
        manifest = {"config": {"decision_policy": "strict", "workflow_mode": "evidence", "unknown_policy": "not_certified"},
                    "undetermined_cases": [], "plan_gap_cases": [], "git": {"dirty_code_files": []}}
        with patch("ghostaudit.export.validate_output", return_value=[]):
            reasons = export.gate(SimpleNamespace(manifest=[]), [r], "ignored.csv", manifest, run_tests=False)
        self.assertTrue(any("decision assumptions" in x for x in reasons))

    def test_invalid_candidate_returns_failure_and_keeps_the_review_artifacts(self):
        code = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data = os.path.join(code, "evaluation", "fixtures", "synth_v4")
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, os.path.join(code, "main.py"), "candidate", "--data", data,
                                "--workflow-mode", "evidence", "--decision-policy", "strict", "--artifact-dir", tmp],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            with open(os.path.join(tmp, "output.manifest.json")) as f:
                m = json.load(f)
            self.assertGreater(m["validation_error_count"], 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "output.csv")))
            self.assertFalse(m["certified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
