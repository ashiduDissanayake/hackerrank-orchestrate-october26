"""Subject-level account-absence proof: gates, controls, and the guarantee that no resource id is invented."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
REPO = os.path.dirname(CODE)
sys.path.insert(0, CODE)

from ghostaudit.account_proof import account_proof  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.data import AuditChange, IdentityRow  # noqa: E402
from ghostaudit.engine import audit_case  # noqa: E402
from ghostaudit.extract.common import normalize_fields  # noqa: E402
from ghostaudit.identity import IdentityIndex, Subject  # noqa: E402
from ghostaudit.observations import ScopeDecl, Store, make_obs  # noqa: E402
from ghostaudit.data import Request  # noqa: E402

REQ_AT, AUDIT = "2026-06-01T00:00:00Z", "2026-06-15T12:00:00Z"
SNAP = "2026-06-10T00:00:00Z"
U = IdentityRow("user_7", "Rui Costa", "rui.costa@example.org", "+351 912 345 678", "e" * 64, "2026-05-01T00:00:00Z")
CH = [AuditChange("a1", "user_7", "2026-05-01T00:00:00Z", "email", "rui.old@example.org", "rui.costa@example.org")]
RULES = [{"data_category": c, "required_action": a} for c, a in (("USER_PROFILE", "DELETE"), ("SECURITY_AUDIT_LOG", "RETAIN"))]


def subj():
    return IdentityIndex([U], CH).resolve("rui.costa@example.org", AUDIT)


class World:
    def __init__(self):
        self.st = Store()

    def snap(self, eid, t, copy, rows, basis="declared", collection=None, system="account_service", scope=True, captured=None, complete=True):
        if scope:
            cap = captured if captured is not None else ((collection,) if collection else (("customer_profiles",) if basis != "inferred_from_rows" else ()))
            self.st.add_scope(ScopeDecl(eid, t, system, copy, basis, collection, cap, complete))
        for i, f in enumerate(rows):
            f = dict(f)
            if collection:
                f["collection"] = collection
            self.st.add_obs(make_obs(eid, f"{copy}/{i}", t, t, system, f"account_{eid}_{copy}_{i}", copy, "record", True, normalize_fields(f)))
        return self

    def obs(self, eid, t, kind, present, fields, rid="account_x"):
        self.st.add_obs(make_obs(eid, "o", t, t, "account_service", rid, "export", kind, present, normalize_fields(fields)))
        return self

    def proof(self, audit=AUDIT, **kw):
        self.st.finalize()
        return account_proof(CaseView(self.st, audit), subj(), REQ_AT, **kw)


OTHER = {"email": "someone.else@example.org", "user_id": "user_999"}
MINE_UID = {"email": "different@example.org", "user_id": "user_7"}


class Gates(unittest.TestCase):
    def test_declared_snapshot_without_the_subject_proves_absence(self):
        p = World().snap("evidence_1", SNAP, "primary", [OTHER]).proof()
        self.assertEqual((p.status, p.evidence_id), ("ABSENT", "evidence_1"))

    def test_populated_replica_is_not_discharged_by_a_clean_primary(self):   # the user_05 control pattern
        w = World().snap("evidence_1", SNAP, "primary", [OTHER]).snap("evidence_1", SNAP, "failover_replica", [OTHER, MINE_UID], basis="inferred_from_table")
        p = w.proof()
        self.assertEqual(p.status, "PRESENT")
        self.assertEqual(p.copies["failover_replica"].status, "present")

    def test_subject_is_queried_by_every_identifier(self):
        for row in ({"user_id": "user_7"}, {"email": "rui.old@example.org"}, {"phone": "00351 912 345 678"}, {"email_hash": "e" * 64},
                    {"message_text": "call 912 345 678"}):
            p = World().snap("evidence_1", SNAP, "primary", [row]).proof()
            self.assertEqual(p.status, "PRESENT", row)

    def test_unidentifiable_row_makes_the_copy_indeterminate(self):
        p = World().snap("evidence_1", SNAP, "primary", [OTHER, {"account_status": "ACTIVE"}]).proof()
        self.assertEqual(p.status, "INDETERMINATE")

    def test_rows_hidden_by_the_cutoff_make_it_indeterminate(self):
        w = World().snap("evidence_1", SNAP, "primary", [OTHER])
        w.st.add_obs(make_obs("evidence_1", "late", SNAP, "2026-06-20T00:00:00Z", "account_service", "account_late", "primary", "record", True,
                              normalize_fields({"email": "x@example.org", "user_id": "user_1"})))
        self.assertEqual(w.proof().status, "INDETERMINATE")

    def test_snapshot_before_the_request_is_not_evidence_of_the_post_request_state(self):
        p = World().snap("evidence_1", "2026-05-20T00:00:00Z", "primary", [OTHER]).proof()
        self.assertEqual(p.status, "NO_COVERAGE")
        self.assertIn("primary", p.reason)

    def test_snapshot_captured_after_the_cutoff_is_invisible(self):
        self.assertEqual(World().snap("evidence_1", "2026-06-20T00:00:00Z", "primary", [OTHER]).proof().status, "NO_COVERAGE")

    def test_latest_snapshot_per_copy_wins_in_both_directions(self):
        recreated = World().snap("evidence_1", "2026-06-05T00:00:00Z", "primary", [OTHER]).snap("evidence_2", "2026-06-12T00:00:00Z", "primary", [MINE_UID])
        self.assertEqual(recreated.proof().status, "PRESENT")
        cleaned = World().snap("evidence_1", "2026-06-05T00:00:00Z", "primary", [MINE_UID]).snap("evidence_2", "2026-06-12T00:00:00Z", "primary", [OTHER])
        p = cleaned.proof()
        self.assertEqual((p.status, p.evidence_id), ("ABSENT", "evidence_2"))

    def test_weak_scope_never_supports_absence_but_never_hides_presence(self):
        absent = World().snap("evidence_1", SNAP, "primary", [OTHER], basis="inferred_from_rows")
        self.assertEqual(absent.proof().status, "NO_COVERAGE")
        self.assertEqual(absent.proof(allow_weak=True).status, "ABSENT")
        present = World().snap("evidence_1", SNAP, "primary", [OTHER]).snap("evidence_2", SNAP, "read_replica", [MINE_UID], basis="inferred_from_rows")
        self.assertEqual(present.proof().status, "PRESENT")

    def test_direct_lookup_evidence_beats_a_later_declared_empty_snapshot(self):
        w = World().obs("evidence_9", "2026-06-12T09:00:00Z", "lookup", True, {"email": "rui.costa@example.org", "status_code": "200"})
        w.snap("evidence_1", "2026-06-12T12:00:00Z", "primary", [])
        self.assertEqual(w.proof().status, "PRESENT")

    def test_direct_presence_from_before_the_request_does_not_count(self):
        w = World().obs("evidence_9", "2026-05-20T09:00:00Z", "lookup", True, {"email": "rui.costa@example.org", "status_code": "200"})
        w.snap("evidence_1", "2026-06-12T12:00:00Z", "primary", [OTHER])
        self.assertEqual(w.proof().status, "ABSENT")

    def test_primary_copy_is_required(self):
        self.assertEqual(World().snap("evidence_1", SNAP, "failover_replica", [OTHER], basis="inferred_from_table").proof().status, "NO_COVERAGE")

    def test_require_row_option_demands_a_positive_control(self):
        empty = World().snap("evidence_1", SNAP, "primary", [])
        self.assertEqual(empty.proof().status, "ABSENT")
        self.assertEqual(empty.proof(require_row=True).status, "INDETERMINATE")


PRE = "2026-05-20T00:00:00Z"            # before REQ_AT
UNATTRIBUTABLE = {"account_status": "ACTIVE"}


class ProofBoundaries(unittest.TestCase):
    """Review findings: what a snapshot may be taken to cover, and which copies the proof can leave unasserted."""

    def test_declared_empty_non_profile_collection_does_not_cover_profiles(self):
        p = World().snap("evidence_1", SNAP, "primary", [], collection="notification_preferences").proof()
        self.assertEqual(p.status, "NO_COVERAGE")

    def test_non_profile_collection_rows_neither_prove_nor_disprove(self):
        w = World().snap("evidence_1", SNAP, "primary", [{"email": "rui.costa@example.org"}], collection="notification_preferences")
        w.snap("evidence_2", SNAP, "primary", [OTHER])
        self.assertEqual(w.proof().status, "ABSENT")          # the preference row is not a profile; the profile table is clean

    def test_inventory_scope_without_the_profile_table_is_not_profile_coverage(self):
        self.assertEqual(World().snap("evidence_1", SNAP, "primary", [], captured=("support_records",)).proof().status, "NO_COVERAGE")

    def test_incomplete_source_does_not_support_absence(self):
        self.assertEqual(World().snap("evidence_1", SNAP, "primary", [OTHER], complete=False).proof().status, "NO_COVERAGE")

    def test_unattributable_pre_request_replica_row_blocks_the_proof(self):
        w = World().snap("evidence_0", PRE, "failover_replica", [UNATTRIBUTABLE], basis="inferred_from_table")
        w.snap("evidence_1", SNAP, "primary", [OTHER])
        p = w.proof()
        self.assertEqual(p.status, "INDETERMINATE")
        self.assertIn("failover_replica", p.reason)

    def test_replica_that_held_the_subject_before_the_request_and_was_not_recaptured_blocks_the_proof(self):
        w = World().snap("evidence_0", PRE, "failover_replica", [MINE_UID], basis="inferred_from_table")
        w.snap("evidence_1", SNAP, "primary", [OTHER])
        self.assertEqual(w.proof().status, "INDETERMINATE")

    def test_later_strong_capture_of_the_replica_supersedes_the_old_state(self):
        w = World().snap("evidence_0", PRE, "failover_replica", [UNATTRIBUTABLE], basis="inferred_from_table")
        w.snap("evidence_1", SNAP, "primary", [OTHER]).snap("evidence_1", SNAP, "failover_replica", [OTHER], basis="inferred_from_table")
        self.assertEqual(w.proof().status, "ABSENT")

    def test_replica_lagging_the_primary_in_one_capture_blocks_the_proof(self):
        w = World().snap("evidence_0", PRE, "primary", [MINE_UID]).snap("evidence_0", PRE, "failover_replica", [OTHER], basis="inferred_from_table")
        w.snap("evidence_1", SNAP, "primary", [OTHER])
        p = w.proof()
        self.assertEqual(p.status, "INDETERMINATE")
        self.assertIn("failover_replica", p.reason)

    def test_replica_captured_clean_before_the_request_is_excluded_with_a_stated_basis(self):
        w = World().snap("evidence_0", PRE, "failover_replica", [OTHER], basis="inferred_from_table").snap("evidence_1", SNAP, "primary", [OTHER])
        p = w.proof()
        self.assertEqual(p.status, "ABSENT")
        self.assertIn("failover_replica", p.excluded)
        self.assertIn("never evidenced", p.excluded["failover_replica"])

    def test_weakly_scoped_replica_that_never_showed_the_subject_does_not_block(self):
        w = World().snap("evidence_0", PRE, "read_replica", [OTHER], basis="inferred_from_rows").snap("evidence_1", SNAP, "primary", [OTHER])
        self.assertEqual(w.proof().status, "ABSENT")

    def test_weakly_scoped_replica_that_held_the_subject_does_block(self):
        w = World().snap("evidence_0", PRE, "read_replica", [MINE_UID], basis="inferred_from_rows").snap("evidence_1", SNAP, "primary", [OTHER])
        self.assertEqual(w.proof().status, "INDETERMINATE")


class WeakSourcePromotion(unittest.TestCase):
    """A weakly inferred scope (document-table export) supports absence only when its OWN source shows it covers this subject."""

    def _doc_artifact(self, w, subject_rows=True, profile_rows=True, complete=True, eid="evidence_1", t=SNAP):
        """Primary + read_replica document tables; an audit row for the subject in the primary copy, a profile row of someone else in the replica."""
        for copy in ("primary", "read_replica"):
            w.st.add_scope(ScopeDecl(eid, t, "account_service", copy, "inferred_from_rows", None, (), complete))
        if subject_rows:
            w.st.add_obs(make_obs(eid, "p/a", t, t, "security_service", "audit_record_7", "primary", "record", True,
                                  normalize_fields({"subject_reference": "user_7", "retention_until": "2031-12-31T23:59:59Z"})))
        if profile_rows:
            w.st.add_obs(make_obs(eid, "r/a", t, t, "account_service", "account_900", "read_replica", "record", True,
                                  normalize_fields({"collection": "customer_profiles", **OTHER})))
        return w

    def test_promoted_when_the_artifact_holds_the_subjects_rows_and_the_profile_collection(self):
        p = self._doc_artifact(World()).proof()
        self.assertEqual(p.status, "ABSENT")
        self.assertEqual(p.copies["primary"].basis, "inferred_from_rows+subject_in_source")

    def test_not_promoted_when_the_artifact_has_nothing_about_the_subject(self):
        self.assertEqual(self._doc_artifact(World(), subject_rows=False).proof().status, "NO_COVERAGE")

    def test_not_promoted_when_no_profile_collection_appears_in_the_artifact(self):
        self.assertEqual(self._doc_artifact(World(), profile_rows=False).proof().status, "NO_COVERAGE")

    def test_not_promoted_when_the_source_is_incomplete(self):
        self.assertEqual(self._doc_artifact(World(), complete=False).proof().status, "NO_COVERAGE")

    def test_promotion_is_switchable(self):
        self.assertEqual(self._doc_artifact(World()).proof(weak_promotion=False).status, "NO_COVERAGE")

    def test_the_subjects_own_profile_in_the_replica_is_still_found(self):
        w = self._doc_artifact(World())
        w.st.add_obs(make_obs("evidence_1", "r/b", SNAP, SNAP, "account_service", "account_901", "read_replica", "record", True,
                              normalize_fields({"collection": "customer_profiles", **MINE_UID})))
        self.assertEqual(w.proof().status, "PRESENT")


class Engine(unittest.TestCase):
    def _case(self, world):
        world.st.finalize()
        r = Request("c1", "rui.costa@example.org", REQ_AT, "NOT_STARTED", "2026-06-02T00:00:00Z", AUDIT, "Please delete my account.")
        return audit_case(r, world.st, IdentityIndex([U], CH), RULES)

    def test_proof_records_subject_level_absence_without_inventing_a_resource(self):
        world = World().snap("evidence_1", SNAP, "primary", [OTHER])
        world.st.add_obs(make_obs("evidence_1", "a", SNAP, SNAP, "security_service", "audit_record_7", "primary", "record", True,
                                  normalize_fields({"subject_reference": "user_7", "retention_until": "2031-12-31T23:59:59Z"})))
        res = self._case(world)
        acct = [o for o in res.obligations if o.category == "USER_PROFILE"]
        self.assertEqual([(o.resource_id, o.verdict, o.reason, o.evidence_id) for o in acct], [(None, "COMPLIANT", "no_profile_for_subject_in_snapshot", "evidence_1")])
        self.assertEqual(res.internal, "COMPLETE")
        self.assertEqual([s["resource_id"] for s in res.steps], ["audit_record_7"], "no account step: no account id is evidenced")

    def _with_audit_record(self, world):
        world.st.add_obs(make_obs("evidence_1", "a", SNAP, SNAP, "security_service", "audit_record_7", "primary", "record", True,
                                  normalize_fields({"subject_reference": "user_7", "retention_until": "2031-12-31T23:59:59Z"})))
        return world

    def test_empty_notification_collection_plus_retained_record_is_not_certified_complete(self):
        res = self._case(self._with_audit_record(World().snap("evidence_1", SNAP, "primary", [], collection="notification_preferences")))
        self.assertEqual(res.internal, "UNDETERMINED")
        self.assertEqual([o.verdict for o in res.obligations if o.category == "USER_PROFILE"], ["UNKNOWN"])

    def test_unattributable_replica_row_plus_clean_primary_is_not_certified_complete(self):
        world = World().snap("evidence_0", PRE, "failover_replica", [UNATTRIBUTABLE], basis="inferred_from_table").snap("evidence_1", SNAP, "primary", [OTHER])
        res = self._case(self._with_audit_record(world))
        self.assertEqual(res.internal, "UNDETERMINED")

    def test_a_linked_account_resource_takes_precedence_over_the_proof(self):
        world = World().snap("evidence_1", SNAP, "primary", [OTHER])
        world.st.add_obs(make_obs("evidence_2", "l", SNAP, SNAP, "account_service", "account_77", "export", "lookup", True, normalize_fields({"email": "rui.costa@example.org"})))
        res = self._case(world)
        self.assertEqual([(o.resource_id, o.verdict) for o in res.obligations if o.category == "USER_PROFILE"], [("account_77", "VIOLATION")])
        self.assertEqual(res.internal, "INCOMPLETE")


class RealSnapshotControls(unittest.TestCase):
    """evidence_54: SQL primary/failover profile snapshot (declared tables with a NOT NULL user_id column)."""

    @classmethod
    def setUpClass(cls):
        from ghostaudit.pipeline import build
        cls.ds, cls.st = build(os.path.join(REPO, "dataset"))
        cls.ix = IdentityIndex(cls.ds.identities, cls.ds.audit_log)

    def probe(self, user_id, audit="2026-09-03T00:00:00Z"):
        ids = [i for i in self.ix.users if i == user_id]
        if ids:
            row = self.ix.users[user_id]
            s = self.ix.resolve(row.email, audit)
        else:
            s = Subject(user_id, "n/a", identifiers=[], audit_at=audit)
        return account_proof(CaseView(self.st, audit), s, "2026-08-18T00:00:00Z")

    def test_user_01_and_user_02_have_no_profile_in_primary_or_failover(self):
        for u in ("user_01", "user_02"):
            p = self.probe(u)
            self.assertEqual(p.status, "ABSENT", u)
            self.assertEqual({c: e.status for c, e in p.copies.items() if e.evidence_id == "evidence_54"}, {"primary": "absent", "failover_replica": "absent"})

    def test_user_05_is_present_only_in_the_failover_replica(self):
        p = self.probe("user_05")
        self.assertEqual(p.status, "PRESENT")
        self.assertEqual(p.copies["failover_replica"].status, "present")

    def test_a_populated_profile_is_present_in_both_copies(self):
        p = self.probe("user_8741")
        self.assertEqual(p.status, "PRESENT")
        self.assertEqual({c: e.status for c, e in p.copies.items() if e.evidence_id == "evidence_54"}, {"primary": "present", "failover_replica": "present"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
