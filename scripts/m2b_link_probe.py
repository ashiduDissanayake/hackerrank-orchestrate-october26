"""M2b diagnostic: for each resource in the labeled public sample answers, which evidence chain (if any) connects it
to the subject? Labels are used ONLY to measure how many expected resources a strict-chain rule can reach; nothing
here is a runtime rule. Chains: (a) direct identifier in an observation of the resource, (b) trace lookup key,
(c) structural (search source_resource_id / catalog link), then activity-only (window) and 'nothing'."""
import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.identity import IdentityIndex, KIND  # noqa: E402
from ghostaudit.linking import link_subject  # noqa: E402
from ghostaudit.pipeline import build  # noqa: E402
from ghostaudit.extract.common import norm_email  # noqa: E402

ds, st = build(os.path.join(REPO, "dataset"), "sample_deletion_requests.csv")
ix = IdentityIndex(ds.identities, ds.audit_log)
gold = {r["case_id"]: json.loads(r["steps_json"]) for r in __import__("csv").DictReader(open(os.path.join(REPO, "dataset/sample_output.csv")))}
req = {r.case_id: r for r in ds.requests}


class DiagView(CaseView):
    """CaseView whose admissibility rule can be relaxed, for the competing-time-rule measurement only. mode 'dual' is production."""

    def __init__(self, store, audit_at, mode="dual"):
        super().__init__(store, audit_at)
        self.mode = mode

    def _ok(self, o):
        if self.mode == "dual":
            return super()._ok(o)
        if self.mode == "obs_only":
            return o.observed_at <= self.audit_at
        return True  # 'any_time': identity validity is still enforced by the linker (Identifier.linkable_at)


_cache = {}


def chains(cv, subj, rid):
    """The chains the PRODUCTION linker (linking.link_subject, including incoming and multi-hop source references and the
    fixed point) holds for this resource. Replaces an earlier hand-rolled walk that missed incoming source references and
    so called a reachable resource unreachable (case_06 / account_006)."""
    key = (id(cv), subj.user_id, cv.audit_at, getattr(cv, "mode", "dual"))
    if key not in _cache:
        _cache[key] = link_subject(cv, subj)
    ln = _cache[key].links.get(rid)
    return [(("c_source_resource" if c.kind == "source" else "a_direct" if c.kind == "direct" else "b_trace" if c.kind == "trace" else "c_catalog"),
             c.evidence_id, c.value) for c in ln.chains] if ln else []


CVS = {}
summary = Counter()
rows = []
for cid, steps in gold.items():
    r = req[cid]
    cv = CVS.setdefault(r.case_id, CaseView(st, r.audit_at))
    subj = ix.resolve(r.email, r.audit_at)
    seen = set()
    for s in steps:
        key = (s["system_id"], s["resource_id"])
        if key in seen:
            continue
        seen.add(key)
        ch = chains(cv, subj, s["resource_id"])
        obs_any = cv.for_resource(s["resource_id"])
        act = [a for a in cv.activity(resource_id=s["resource_id"])]
        kind = "chain:" + sorted({c[0] for c in ch})[0] if ch else ("activity_only" if act and not obs_any else ("observed_no_chain" if obs_any else "nothing"))
        summary[kind] += 1
        rows.append((cid, key, kind, [c[0] for c in ch][:3], [(a.event_time[:16], a.reported_result) for a in act][:2], r.reported_at[:16]))
for r in rows:
    if not r[2].startswith("chain"):
        print(r)
print()
print(dict(summary))


# ---------------------------------------------------------------------------------------------------------------
# Competing time interpretations for the pairs with no strict chain (diagnostic; labels used only to measure)
# ---------------------------------------------------------------------------------------------------------------
print("\n=== reachability of the non-chain pairs under competing time rules ===")


tab = Counter()
detail = []
for cid, steps in gold.items():
    r = req[cid]
    subj = ix.resolve(r.email, r.audit_at)
    seen = set()
    for s in steps:
        key = s["resource_id"]
        if key in seen:
            continue
        seen.add(key)
        if chains(CVS[r.case_id], subj, key):
            continue
        res = {}
        for mode in ("obs_only", "any_time"):
            ch = chains(DiagView(st, r.audit_at, mode), subj, key)
            res[mode] = bool(ch)
            if ch and mode == "any_time":
                o = [o for o in st._by_resource.get(key, ())]
                res["when"] = sorted({(x.evidence_id, x.available_at[:16], x.observed_at[:16]) for x in o})[:2]
        tab[(res["obs_only"], res["any_time"])] += 1
        detail.append((cid, key, res))
print("(reachable under obs_only, reachable with any-time identity) -> count:", dict(tab))
for d in detail:
    print(d[0], d[1], "obs_only" if d[2]["obs_only"] else "", "any_time" if d[2]["any_time"] else "UNREACHABLE", d[2].get("when", ""))
