"""M2 tests: dual-time cutoff, identity with provenance, no bypass of CaseView.
Run: python3 code/tests/test_core.py   (repo root; stdlib unittest)
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)
REPO = os.path.dirname(CODE)

from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.data import AuditChange, IdentityRow  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.pipeline import build  # noqa: E402

FX = os.path.join(CODE, "evaluation", "fixtures", "synth_v1")
_cache = {}


def fx():
    if "fx" not in _cache:
        _cache["fx"] = build(FX)
    return _cache["fx"]


def real():
    if "real" not in _cache:
        _cache["real"] = build(os.path.join(REPO, "dataset"))
    return _cache["real"]


class DualTimeFixtures(unittest.TestCase):
    def test_artifact_captured_after_cutoff_is_invisible_even_with_old_record_times(self):
        ds, st = fx()
        cv = CaseView(st, "2026-06-15T12:00:00Z")
        raw = [o for o in st._obs if o.evidence_id == "evidence_f06"]
        self.assertTrue(raw and all(o.observed_at < "2026-06-15" for o in raw), "fixture precondition: old record in a late artifact")
        self.assertFalse([o for o in cv.all() if o.evidence_id == "evidence_f06"])
        self.assertFalse(cv.admissible_evidence("evidence_f06"))

    def test_record_observed_after_cutoff_is_invisible_even_in_an_early_artifact(self):
        ds, st = fx()
        cv = CaseView(st, "2026-06-15T12:00:00Z")
        raw = st._by_resource["search_f05b"]
        self.assertTrue(raw and raw[0].available_at <= "2026-06-15T12:00:00Z", "fixture precondition: artifact itself is available")
        self.assertEqual(cv.for_resource("search_f05b"), [])
        self.assertEqual(len(cv.excluded_for_resource("search_f05b")), 1)
        self.assertEqual(cv.for_identifier("email", "nirmala.pereira@example.org", system="search_service")[0].resource_id, "search_f05")

    def test_boundary_is_inclusive_on_both_times(self):
        ds, st = fx()
        art = st.artifacts["evidence_f02"].available_at
        self.assertTrue(CaseView(st, art).admissible_evidence("evidence_f02"))
        before = "2026-06-14T09:59:59Z"
        self.assertFalse(CaseView(st, before).admissible_evidence("evidence_f02"))
        self.assertTrue(any(o.evidence_id == "evidence_f02" for o in CaseView(st, "2026-06-14T10:00:00Z").all()))

    def test_activity_and_catalog_use_event_time(self):
        ds, st = fx()
        self.assertEqual(len(CaseView(st, "2026-06-02T07:00:00Z").catalog_links()), 0)
        self.assertEqual(len(CaseView(st, "2026-06-02T07:30:00Z").catalog_links()), 1)
        self.assertTrue(CaseView(st, "2026-06-02T07:30:00Z").admissible_evidence("fxact_002"))
        self.assertFalse(CaseView(st, "2026-06-02T07:00:00Z").admissible_evidence("fxact_002"))


class DualTimeRealData(unittest.TestCase):
    """Two real cases carry a later-dated FOUND record inside an artifact captured exactly at audit_at."""

    def test_case_135_and_383(self):
        ds, st = real()
        by_case = {r.case_id: r for r in ds.requests}
        for case, eid, rid in (("case_135", "evidence_13", "account_1417"), ("case_383", "evidence_36", "account_5043")):
            at = by_case[case].audit_at
            self.assertEqual(st.artifacts[eid].available_at, at, case)
            cv = CaseView(st, at)
            seen = [o for o in cv.for_resource(rid) if o.evidence_id == eid]
            self.assertTrue(all(o.present is False or o.f("result") == "NOT_FOUND" for o in seen), f"{case}: later FOUND must not be visible")
            later = [o for o in cv.excluded_for_resource(rid) if o.evidence_id == eid]
            self.assertEqual(len(later), 1, case)
            self.assertEqual(later[0].f("result"), "FOUND")


def _users():
    ids = [IdentityRow("u1", "A B", "new@x.org", "+1 555 0001", "h_new" + "0" * 59, "2026-06-20T00:00:00Z")]
    return ids


class Identity(unittest.TestCase):
    H = lambda self, c: c * 64  # noqa: E731

    def index(self, snapshot_updated, changes):
        u = IdentityRow("u1", "Ann Bee", "new@x.org", "+1 555 0001", self.H("b"), snapshot_updated)
        return IdentityIndex([u], changes)

    def test_post_cutoff_change_excludes_new_identifier_but_keeps_old(self):
        ch = [AuditChange("a1", "u1", "2026-06-20T08:00:00Z", "email", "old@x.org", "new@x.org"),
              AuditChange("a2", "u1", "2026-06-20T08:00:00Z", "email_hash", self.H("a"), self.H("b"))]
        ix = self.index("2026-06-20T08:00:00Z", ch)
        s = ix.resolve("old@x.org", "2026-06-15T12:00:00Z")
        self.assertEqual(s.user_id, "u1")
        emails = {i.value for i in s.identifiers if i.field == "email"}
        self.assertEqual(emails, {"old@x.org"})
        self.assertEqual({i.value for i in s.excluded_future if i.field == "email"}, {"new@x.org"})
        self.assertEqual({i.value for i in s.identifiers if i.field == "email_hash"}, {self.H("a")})
        self.assertEqual(s.conditions, [])
        # the same person looked up AFTER the change sees both, the old one no longer current
        s2 = ix.resolve("old@x.org", "2026-06-21T00:00:00Z")
        self.assertEqual({i.value for i in s2.identifiers if i.field == "email"}, {"old@x.org", "new@x.org"})

    def test_new_identifier_cannot_link_evidence_recorded_before_it_belonged_to_the_user(self):
        ch = [AuditChange("a1", "u1", "2026-06-10T00:00:00Z", "email", "old@x.org", "new@x.org")]
        s = self.index("2026-06-10T00:00:00Z", ch).resolve("new@x.org", "2026-06-15T12:00:00Z")
        new = next(i for i in s.identifiers if i.value == "new@x.org")
        self.assertTrue(new.linkable_at("2026-06-12T00:00:00Z"))
        self.assertFalse(new.linkable_at("2026-06-09T00:00:00Z"), "evidence from before the change cannot be linked by the new value")
        old = next(i for i in s.identifiers if i.value == "old@x.org")
        self.assertTrue(old.linkable_at("2026-06-12T00:00:00Z"), "historical copies of the old value stay linkable after replacement")

    def test_snapshot_dated_after_cutoff_without_audit_record_is_unverified(self):
        s = self.index("2026-06-20T00:00:00Z", []).resolve("new@x.org", "2026-06-15T12:00:00Z")
        self.assertTrue(s.identifiers)
        self.assertTrue(all(not i.verified for i in s.identifiers))
        self.assertTrue(any(c.startswith("snapshot_value_unverifiable") for c in s.conditions))

    def test_unknown_and_inconsistent(self):
        ix = self.index("2026-01-01T00:00:00Z", [])
        self.assertIn("request_email_unknown", ix.resolve("nobody@x.org", "2026-06-15T12:00:00Z").conditions)
        bad = self.index("2026-01-01T00:00:00Z", [AuditChange("a1", "u1", "2026-02-01T00:00:00Z", "email", "o@x.org", "different@x.org")])
        self.assertTrue(any("ends at a value different" in c for c in bad.resolve("o@x.org", "2026-06-15T12:00:00Z").conditions))

    def test_fixture_subjects(self):
        ds, st = fx()
        ix = IdentityIndex(ds.identities, ds.audit_log)
        req = {r.case_id: r for r in ds.requests}
        r16 = req["fx_case_16"]
        s = ix.resolve(r16.email, r16.audit_at)
        self.assertEqual(s.user_id, "user_f16")
        self.assertEqual({i.value for i in s.excluded_future if i.field == "email"}, {"anouk.visser.new@example.org"})
        r13 = req["fx_case_13"]
        s13 = ix.resolve(r13.email, r13.audit_at)
        self.assertEqual(r13.email, "yusuf.marek.old@example.org")
        self.assertEqual(s13.user_id, "user_f13")
        self.assertEqual(len({i.value for i in s13.identifiers if i.field == "email"}), 2)


class RealIdentity(unittest.TestCase):
    def test_all_requests_resolve_cleanly(self):
        ds, st = real()
        ix = IdentityIndex(ds.identities, ds.audit_log)
        bad = [(r.case_id, ix.resolve(r.email, r.audit_at).conditions) for r in ds.requests if ix.resolve(r.email, r.audit_at).conditions]
        self.assertEqual(bad, [])


class NoBypass(unittest.TestCase):
    # build-time modules only. extract/pdf.py reads the catalog rows while BUILDING the store (a document that prints a catalog
    # label gets its resource id from the catalog); the time gating is applied through available_at, see CatalogLabelJoin.
    ALLOWED = {"caseview.py", "observations.py", "pipeline.py", "coverage.py", "pdf.py"}

    def test_case_logic_never_touches_raw_store(self):
        # raw attribute access only; cv.catalog_links() / cv.activity() are the sanctioned CaseView METHODS
        pat = re.compile(r"\._obs\b|\._by_resource\b|\._by_ident\b|\._scopes\b|\.catalog_links\b(?!\s*\()|\bstore\.activity\b|\bstore\.artifacts\b")
        offenders = []
        pkg = os.path.join(CODE, "ghostaudit")
        for root, _, names in os.walk(pkg):
            for n in names:
                if n.endswith(".py") and n not in self.ALLOWED:
                    for i, line in enumerate(open(os.path.join(root, n), encoding="utf-8"), 1):
                        if pat.search(line) and not line.lstrip().startswith("#"):
                            offenders.append(f"{n}:{i}: {line.strip()}")
        self.assertEqual(offenders, [], "case logic must read evidence only through CaseView")


if __name__ == "__main__":
    unittest.main(verbosity=2)
