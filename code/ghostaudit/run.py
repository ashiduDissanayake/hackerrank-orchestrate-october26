"""Run the engine over a data root and write output.csv + a diagnostics report."""
import csv
import json
import os
from collections import Counter

from .data import load_request_history
from .engine import audit_case
from .identity import IdentityIndex
from .pipeline import build
from .validate import case_sort_key


def earlier_requests_by_case(ds, ident):
    """case_id -> the subject's EARLIER requests (same resolved user_id, audited before this request was made), taken from every
    request file in the data root. Resolution uses only identity data valid at each request's own audit_at."""
    history = load_request_history(ds.root)
    subject = {r.case_id: ident.resolve(r.email, r.audit_at).user_id for r in history}
    out = {}
    for r in ds.requests:
        u = subject.get(r.case_id) or ident.resolve(r.email, r.audit_at).user_id
        out[r.case_id] = [e for e in history if e.case_id != r.case_id and u is not None and subject[e.case_id] == u and e.audit_at <= r.requested_at]
    return out


def run_dataset(root, requests_file="deletion_requests.csv", unknown_policy="not_certified", **audit_kwargs):
    ds, store = build(root, requests_file)
    ident = IdentityIndex(ds.identities, ds.audit_log)
    earlier = earlier_requests_by_case(ds, ident)
    results = [audit_case(r, store, ident, ds.rules, unknown_policy, earlier_requests=earlier[r.case_id], **audit_kwargs) for r in ds.requests]
    results.sort(key=lambda r: case_sort_key(r.case_id))
    return ds, store, results


def write_output(results, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        for r in results:
            w.writerow([r.case_id, r.status, json.dumps(r.steps, sort_keys=True, separators=(",", ":"), ensure_ascii=False)])


def diagnostics(results):
    c = Counter()
    for r in results:
        c[f"status:{r.status}"] += 1
        c[f"internal:{r.internal}"] += 1
        if r.unresolved:
            c["cases_with_unresolved"] += 1
        if r.conditions:
            c["cases_with_identity_conditions"] += 1
        for o in r.obligations:
            c[f"obligation:{o.verdict}:{o.reason}"] += 1
        if r.intent and r.intent.confidence == "low":
            c["intent_low_confidence"] += 1
        if r.internal != "NOT_APPLICABLE" and not r.steps:
            c["deletion_cases_with_zero_steps"] += 1
    return dict(sorted(c.items()))


def case_detail(r):
    return {
        "case_id": r.case_id, "status": r.status, "internal": r.internal,
        "intent": vars(r.intent) if r.intent else None,
        "user_id": r.subject.user_id if r.subject else None,
        "conditions": r.conditions,
        "links": {rid: {"system": l.system_id, "chains": [vars(c) if hasattr(c, "__dict__") else c.__dict__ if False else
                                                          {"kind": c.kind, "evidence_id": c.evidence_id, "locator": c.locator, "field": c.field, "value": c.value}
                                                          for c in l.chains][:3]} for rid, l in r.links.items()},
        "rejected": r.rejected,
        "obligations": [{"system": o.system_id, "resource": o.resource_id, "category": o.category, "action": o.action,
                         "verdict": o.verdict, "reason": o.reason, "evidence": o.evidence_id, "detail": o.detail} for o in r.obligations],
        "window_candidates": r.candidates[:10],
    }


def write_diagnostics(results, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"summary": diagnostics(results), "cases": [case_detail(r) for r in results]}, f, indent=1, sort_keys=True, ensure_ascii=False, default=str)
