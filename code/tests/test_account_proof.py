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

    def snap(self, eid, t, copy, rows, basis="declared", collection=None, system="account_service", scope=True):
        if scope:
            self.st.add_scope(ScopeDecl(eid, t, system, copy, basis, collection))
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
        self.assertEqual(p.uncovered, ["primary"])

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
