"""Invariance tests: a case's result must not depend on batch composition, order, unrelated evidence, or anything
dated after its audit_at. Run on the frozen fixtures (known truth) and on a slice of the real dataset.
Run: python3 code/tests/test_invariance.py
"""
import copy
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)
REPO = os.path.dirname(CODE)

from ghostaudit.data import AuditChange, load_dataset  # noqa: E402
from ghostaudit.engine import audit_case  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.observations import make_obs  # noqa: E402
from ghostaudit.pipeline import build_store  # noqa: E402

FX = os.path.join(CODE, "evaluation", "fixtures", "synth_v1")


def sig(r):
    """Everything that must be invariant: status, internal verdict, steps, links, obligations."""
    return (r.status, r.internal, tuple(tuple(sorted(s.items())) for s in r.steps), tuple(sorted(r.links)),
            tuple((o.system_id, o.resource_id, o.verdict, o.reason, o.evidence_id) for o in r.obligations))


def run_all(ds, store, ident, requests=None):
    return {r.case_id: sig(audit_case(r, store, ident, ds.rules)) for r in (requests or ds.requests)}


class Invariance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = load_dataset(FX)
        cls.store = build_store(cls.ds)
        cls.ident = IdentityIndex(cls.ds.identities, cls.ds.audit_log)
        cls.base = run_all(cls.ds, cls.store, cls.ident)

    def test_each_case_alone_equals_batch(self):
        for r in self.ds.requests:
            self.assertEqual(run_all(self.ds, self.store, self.ident, [r])[r.case_id], self.base[r.case_id], r.case_id)

    def test_shuffled_batches(self):
        rng = random.Random(7)
        for _ in range(5):
            reqs = list(self.ds.requests)
            rng.shuffle(reqs)
            self.assertEqual(run_all(self.ds, self.store, self.ident, reqs), self.base)

    def test_extra_requests_do_not_change_results(self):
        import dataclasses
        extra = [dataclasses.replace(r, case_id=f"zz_{i}", requested_at="2027-01-01T00:00:00Z", reported_at="2027-01-02T00:00:00Z",
                                     audit_at="2027-02-01T00:00:00Z") for i, r in enumerate(self.ds.requests)]
        self.assertEqual(len(extra), len(self.ds.requests), "test must not be vacuous")
        got = run_all(self.ds, self.store, self.ident, list(self.ds.requests) + extra)
        self.assertEqual(len(got), 2 * len(self.base))
        for cid, s in self.base.items():
            self.assertEqual(got[cid], s, cid)

    def _inject(self, observations):
        st = copy.copy(self.store)
        st._obs = list(self.store._obs) + observations
        st._scopes = list(self.store._scopes)
        st.finalize()
        return st

    def test_unrelated_evidence_is_ignored(self):
        extra = [make_obs("evidence_f02", f"inj{i}", "2026-06-14T10:00:00Z", "2026-06-14T10:00:00Z", "search_service", f"search_u{i}", "inventory",
                          "record", True, {"email": f"stranger{i}@example.net", "ids_email": f"stranger{i}@example.net"}) for i in range(50)]
        self.assertEqual(run_all(self.ds, self._inject(extra), self.ident), self.base)

    def test_future_evidence_is_ignored(self):
        """Artifacts captured after audit_at, and records observed after it, that would flip every verdict."""
        inj = []
        for r in self.ds.requests:
            em = r.email.lower()
            for i, (av, ob) in enumerate((("2026-06-30T00:00:00Z", "2026-06-10T00:00:00Z"),      # late artifact, old record time
                                          ("2026-06-14T10:00:00Z", "2026-06-20T00:00:00Z"))):    # early artifact, late record time
                inj.append(make_obs("evidence_f02", f"fut-{r.case_id}-{i}", av, ob, "search_service", f"search_fut_{r.case_id}_{i}", "inventory",
                                    "record", True, {"email": em, "ids_email": em}))
        self.assertEqual(run_all(self.ds, self._inject(inj), self.ident), self.base)

    def test_identity_change_after_cutoff_changes_nothing(self):
        """A realistic post-cutoff change: audit rows for email and email_hash, snapshot updated to match."""
        import hashlib
        from ghostaudit.data import IdentityRow
        H = lambda x: hashlib.sha256(x.encode()).hexdigest()  # noqa: E731
        T = "2026-07-01T00:00:00Z"
        ds = copy.copy(self.ds)
        ds.audit_log = list(self.ds.audit_log)
        ds.identities = []
        for u in self.ds.identities:
            new = f"moved.{u.email}"
            ds.audit_log += [AuditChange(f"late_e_{u.user_id}", u.user_id, T, "email", u.email, new),
                             AuditChange(f"late_h_{u.user_id}", u.user_id, T, "email_hash", u.email_hash, H(new))]
            ds.identities.append(IdentityRow(u.user_id, u.name, new, u.phone, H(new), T))
        inj = [make_obs("evidence_f02", f"late-{u.user_id}", "2026-06-14T10:00:00Z", "2026-06-14T10:00:00Z", "search_service", f"search_late_{u.user_id}", "inventory",
                        "record", True, {"email": f"moved.{u.email}", "ids_email": f"moved.{u.email}"}) for u in self.ds.identities]
        ident = IdentityIndex(ds.identities, ds.audit_log)
        got = run_all(ds, self._inject(inj), ident)
        # fx_case_16 already has a genuine post-cutoff change in the fixture; its second change stacks on it, so compare the rest
        for cid, sg in self.base.items():
            self.assertEqual(got[cid], sg, cid)


class InvarianceRealData(unittest.TestCase):
    def test_shuffled_slice_of_real_dataset(self):
        ds = load_dataset(os.path.join(REPO, "dataset"))
        store = build_store(ds)
        ident = IdentityIndex(ds.identities, ds.audit_log)
        rng = random.Random(11)
        sl = rng.sample(ds.requests, 60)
        base = run_all(ds, store, ident, sl)
        shuf = list(sl)
        rng.shuffle(shuf)
        self.assertEqual(run_all(ds, store, ident, shuf), base)
        for r in sl[:10]:
            self.assertEqual(run_all(ds, store, ident, [r])[r.case_id], base[r.case_id])


if __name__ == "__main__":
    unittest.main(verbosity=2)
