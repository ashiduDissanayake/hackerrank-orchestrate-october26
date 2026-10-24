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
from ghostaudit.pipeline import build  # noqa: E402
from ghostaudit.extract.common import norm_email  # noqa: E402

ds, st = build(os.path.join(REPO, "dataset"), "sample_deletion_requests.csv")
ix = IdentityIndex(ds.identities, ds.audit_log)
gold = {r["case_id"]: json.loads(r["steps_json"]) for r in __import__("csv").DictReader(open(os.path.join(REPO, "dataset/sample_output.csv")))}
req = {r.case_id: r for r in ds.requests}


def chains(cv, subj, rid):
    found = []
    idents = {(KIND[i.field], i.value): i for i in subj.identifiers if i.verified}
    for o in cv.for_resource(rid):
        for (kind, val), ident in idents.items():
            if val in (o.f(f"ids_{kind}") or "").split("|") and ident.linkable_at(o.observed_at):
                found.append(("a_direct", o.evidence_id, f"{kind}:{val[:24]}"))
        if subj.user_id and subj.user_id in (o.f("ids_user") or "").split("|"):
            found.append(("a_user_ref", o.evidence_id, subj.user_id))
        tk = (o.f("trace_lookup_key") or "").lower()
        if tk and any(tk == v for (k, v) in idents):
            found.append(("b_trace", o.evidence_id, tk[:30]))
        src = o.f("source_resource_id")
        if src:
            for o2 in cv.for_resource(src):
                for (kind, val), ident in idents.items():
                    if val in (o2.f(f"ids_{kind}") or "").split("|"):
                        found.append(("c_source_resource", o.evidence_id, f"{src}"))
    for c in cv.catalog_links():
        if c.resource_id == rid and (c.user_ref == subj.user_id or c.email in {v for (k, v) in idents if k == "email"}):
            found.append(("c_catalog", c.activity_id, c.email))
    return found


summary = Counter()
rows = []
for cid, steps in gold.items():
    r = req[cid]
    cv = CaseView(st, r.audit_at)
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


class Raw:  # unfiltered view with the same method surface the probe uses (diagnostic only)
    def __init__(self, store, audit_at, mode):
        self.s, self.at, self.mode = store, audit_at, mode

    def _ok(self, o):
        if self.mode == "dual":
            return o.available_at <= self.at and o.observed_at <= self.at
        if self.mode == "obs_only":
            return o.observed_at <= self.at
        return True  # 'any_time': identity only

    def for_resource(self, rid):
        return [o for o in self.s._by_resource.get(rid, ()) if self._ok(o)]

    def catalog_links(self):
        return [c for c in self.s.catalog_links if c.event_time <= self.at]

    def activity(self, resource_id=None):
        return [a for a in self.s.activity if a.resource_id == resource_id and a.event_time <= self.at]


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
        if chains(CaseView(st, r.audit_at), subj, key):
            continue
        res = {}
        for mode in ("obs_only", "any_time"):
            ch = chains(Raw(st, r.audit_at, mode), subj, key)
            res[mode] = bool(ch)
            if ch and mode == "any_time":
                o = [o for o in st._by_resource.get(key, ())]
                res["when"] = sorted({(x.evidence_id, x.available_at[:16], x.observed_at[:16]) for x in o})[:2]
        tab[(res["obs_only"], res["any_time"])] += 1
        detail.append((cid, key, res))
print("(reachable under obs_only, reachable with any-time identity) -> count:", dict(tab))
for d in detail:
    print(d[0], d[1], "obs_only" if d[2]["obs_only"] else "", "any_time" if d[2]["any_time"] else "UNREACHABLE", d[2].get("when", ""))
