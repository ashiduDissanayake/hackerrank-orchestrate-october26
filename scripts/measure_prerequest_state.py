"""Diagnostic: does an obligation whose decisive state evidence predates requested_at behave differently from one resting on
post-request evidence? Public answers are used ONLY to count whether the answer lists the resource (diagnosis, never a rule).
  python3 scripts/measure_prerequest_state.py"""
import csv
import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
from ghostaudit import run as runner  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.state import copy_states  # noqa: E402

DS = os.path.join(REPO, "dataset")


def decisive_time(cv, r, o, ln):
    """Time of the evidence the verdict rests on (the obligation's cited evidence, else the newest event of the resource)."""
    if not o.resource_id or not ln:
        return None
    cs = copy_states(cv, o.resource_id, ln.system_id, ln.since(), r.subject, o.category)
    evs = [e.time for e in cs.events]
    return max(evs) if evs else None


for reqfile in ("sample_deletion_requests.csv", "deletion_requests.csv"):
    ds, store, results = runner.run_dataset(DS, reqfile)
    req = {x.case_id: x for x in ds.requests}
    gold = {}
    if reqfile.startswith("sample"):
        gold = {r["case_id"]: {s["resource_id"] for s in json.loads(r["steps_json"])} for r in csv.DictReader(open(os.path.join(DS, "sample_output.csv")))}
    tab = Counter()
    for r in results:
        if r.internal == "NOT_APPLICABLE":
            continue
        cv = CaseView(store, req[r.case_id].audit_at)
        for o in r.obligations:
            if not o.resource_id or o.category in ("DATA_FLOW", "BACKUP_ARCHIVE") or o.detail.get("no_step"):
                continue
            ln = r.links.get(o.resource_id)
            t = decisive_time(cv, r, o, ln)
            rel = "none" if t is None else ("pre_request" if t < req[r.case_id].requested_at else "post_request")
            key = (o.verdict, o.category if o.verdict != "UNKNOWN" else "-", rel)
            if gold:
                key += ("in_gold" if o.resource_id in gold[r.case_id] else "NOT_in_gold",)
            tab[key] += 1
    print("==", reqfile)
    for k, v in sorted(tab.items()):
        print("  ", v, k)
