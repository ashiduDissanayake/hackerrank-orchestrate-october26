"""Diagnosis of public-sample cases whose gold status is COMPLETE but which the engine no longer certifies.
DIAGNOSIS ONLY: public sample answers are read to explain failures; nothing here feeds prediction logic."""
import csv
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
from ghostaudit import run as runner  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402

ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"), "sample_deletion_requests.csv")
gold = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(open(os.path.join(REPO, "dataset/sample_output.csv")))}
req = {r.case_id: r for r in ds.requests}
ix = IdentityIndex(ds.identities, ds.audit_log)
by = {r.case_id: r for r in results}

def appearances(rid):
    out = []
    for o in store._by_resource.get(rid, ()):
        out.append((o.evidence_id, o.available_at[:16], o.observed_at[:16], o.kind, o.present))
    acts = [(a.activity_id, a.event_time[:16], a.event_type, a.reported_result) for a in store.activity if a.resource_id == rid]
    return out, acts

for cid, (gstat, gsteps) in gold.items():
    if gstat != "COMPLETE":
        continue
    r, rq = by[cid], req[cid]
    have = {(s["resource_id"], s["operation"]) for s in r.steps}
    miss = [s for s in gsteps if (s["resource_id"], s["operation"]) not in have]
    print(f"\n=== {cid} gold=COMPLETE pred={r.status} internal={r.internal} audit_at={rq.audit_at[:16]} reported={rq.reported_at[:16]}")
    print("  text:", rq.request_text[:150])
    print("  engine obligations:", [(o.category, o.resource_id, o.verdict, o.reason) for o in r.obligations])
    print("  linked:", sorted(r.links))
    for s in miss:
        obs, acts = appearances(s["resource_id"])
        late = [x for x in obs if x[1] > rq.audit_at[:16] or x[2] > rq.audit_at[:16]]
        print(f"  MISSING {s['operation']} {s['system_id']}/{s['resource_id']} (gold cites {s['evidence_id']})")
        print(f"      observations: {len(obs)} total, {len(obs)-len(late)} admissible; first 3: {obs[:3]}")
        print(f"      activity claims: {acts}")
