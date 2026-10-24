"""Measurement only (feeds the U12 decision; changes no engine behaviour).
Question: if a case's account is searched for in the deletion-worker activity BEFORE the earliest activity row of that
case's own evidence-linked resources, how often is exactly one candidate left? Gold sample answers are read only to
score the measurement."""
import csv
import datetime as dt
import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
from ghostaudit import run as runner  # noqa: E402

FMT = "%Y-%m-%dT%H:%M:%SZ"
T = lambda s: dt.datetime.strptime(s, FMT)  # noqa: E731


def measure(reqfile, label, gold=None):
    ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"), reqfile)
    acts = [a for a in ds.activity if a.source_system == "deletion_worker"]
    acct = [a for a in acts if a.event_type == "DELETE_RECORD" and a.target_system == "account_service"]
    g = {}
    if gold:
        g = {r["case_id"]: [s["resource_id"] for s in json.loads(r["steps_json"]) if s["system_id"] == "account_service"] for r in csv.DictReader(open(gold))}
    rq = {r.case_id: r for r in ds.requests}
    size = Counter(); score = Counter(); noanchor = 0; n = 0
    for r in results:
        if not any(o.category == "USER_PROFILE" and o.verdict == "UNKNOWN" for o in r.obligations):
            continue
        n += 1
        anchors = [a for a in acts if a.resource_id in r.links and a.event_time <= rq[r.case_id].audit_at]
        if not anchors:
            noanchor += 1
            continue
        first = min(T(a.event_time) for a in anchors)
        cands = {a.resource_id for a in acct if first - dt.timedelta(minutes=90) <= T(a.event_time) <= first}
        size[min(len(cands), 4)] += 1
        if r.case_id in g and g[r.case_id]:
            hit = g[r.case_id][0] in cands
            score[("contains_gold", hit, "unique" if len(cands) == 1 else "ambiguous")] += 1
    print(f"{label}: cases with an unresolved account: {n}; with no activity anchor at all: {noanchor}")
    print(f"   candidate-set size after anchoring (0,1,2,3,4+): {[size[i] for i in range(5)]}")
    if gold:
        print("   scored against the public answers:", dict(score))


measure("sample_deletion_requests.csv", "samples", os.path.join(REPO, "dataset/sample_output.csv"))
measure("deletion_requests.csv", "eval (unlabeled: size distribution only)")
