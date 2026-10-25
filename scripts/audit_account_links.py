"""Audit unresolved account assignments without reading public answer labels.

Compare context v2/v3 for every ambiguous request, list score-optimal alternatives,
inspect admissible join fields, and measure queue order on explicitly linked accounts.
This is diagnosis, never an input to the prediction path.
"""
import argparse
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "code"))
from ghostaudit.data import load_request_history  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.pipeline import build  # noqa: E402
from ghostaudit.workflow import WorkflowAttributor, WorkflowConfig, maximum_assignment  # noqa: E402

JOIN_FIELDS = ("user_id", "user_ref", "subject_reference", "customer_reference", "email", "phone", "email_hash",
               "lookup_key", "trace_lookup_key", "request_id", "job_id", "workflow_id")


def optimal_options(weights, target, tolerance=1e-9):
    """Force every eligible target edge in turn; publish all optima, never an arbitrary winner."""
    best, assignment = maximum_assignment(weights)
    options, alternatives = [], []
    for rid, value in sorted(weights.get(target, {}).items()):
        residual = {key: {r: score for r, score in edges.items() if r != rid}
                    for key, edges in weights.items() if key != target}
        score, mapping = maximum_assignment(residual)
        total = score + value
        if abs(total - best) <= tolerance:
            options.append(rid)
            alternatives.append({"resource_id": rid, "score": total, "assignment": {**mapping, target: rid}})
    null_rows = {key: edges for key, edges in weights.items() if key != target}
    null_score, _ = maximum_assignment(null_rows)
    return {"score": best, "one_internal_optimum": assignment, "equally_optimal_resource_ids": options,
            "null_is_optimal": abs(null_score - best) <= tolerance, "witnesses": alternatives}


def queue_calibration(matcher, history, cutoff):
    batches = defaultdict(list)
    authorized = {q.case_id for q in matcher.history}
    for q in history:
        if q.case_id not in authorized or q.reported_at > cutoff:
            continue
        subject, links = matcher._context(q, cutoff)
        events = [a for a in matcher._window_events(q, cutoff) if a.target_system == "account_service"
                  and a.event_type == "DELETE_RECORD" and a.resource_id in links.links]
        if len({a.resource_id for a in events}) == 1:
            batches[q.reported_at].append((q, min(events, key=lambda a: a.event_time), subject.user_id))
    counts = Counter()
    for group in batches.values():
        for (a, x, ua), (b, y, ub) in combinations(group, 2):
            if ua == ub or a.requested_at == b.requested_at or x.event_time == y.event_time:
                continue
            order = "FIFO" if (a.requested_at < b.requested_at) == (x.event_time < y.event_time) else "LIFO"
            counts[order] += 1
            if x.reported_result == y.reported_result:
                counts["same_result_" + order] += 1
    return {"cutoff": cutoff, "explicit_account_batches": len(batches), "counts": dict(sorted(counts.items())),
            "interpretation": "Descriptive overlapping pairs, not independent trials or a validated queue rule."}


def audit(root, requests_file):
    ds, store = build(str(root), requests_file)
    identity = IdentityIndex(ds.identities, ds.audit_log)
    history = {q.case_id: q for q in load_request_history(str(root))}
    history.update({q.case_id: q for q in ds.requests})
    history = list(history.values())
    old = WorkflowAttributor(store, identity, history, WorkflowConfig(scoring="contextual_v2"), ds.rules)
    new = WorkflowAttributor(store, identity, history, WorkflowConfig(scoring="contextual_v3"), ds.rules)
    records = []
    for q in ds.requests:
        before = old.decisions(q)[0]
        if before["reason"] != "ambiguous_or_low_margin":
            continue
        after = new.decisions(q)[0]
        graph = new._component(q, q.audit_at, "account_service")
        weights = {key: {rid: p["score"] for rid, p in edges.items()} for key, edges in graph.items()}
        witness = optimal_options(weights, q.case_id)
        cv = new._view(q.audit_at)
        evidence = {}
        for rid in weights.get(q.case_id, {}):
            obs = cv.for_resource(rid)
            evidence[rid] = {"observation_count": len(obs),
                             "evidence_ids": sorted({o.evidence_id for o in obs}),
                             "nonempty_join_fields": sorted({key for o in obs for key in JOIN_FIELDS if o.f(key)}),
                             "source_reference_evidence_ids": sorted({o.evidence_id for o in cv.all() if o.f("source_resource_id") == rid})}
        records.append({"case_id": q.case_id, "audit_at": q.audit_at, "previous_margin": before["margin"],
                        "accepted": after["accepted"], "proposal": after.get("proposal"), "margin": after["margin"],
                        "equivalent_assignments": witness, "candidate_evidence": evidence,
                        "ownership_proven": False})
    calibrations = [queue_calibration(old, history, cutoff) for cutoff in sorted({r["audit_at"] for r in records})]
    return {"uses_public_answer_labels": False, "requests_file": requests_file,
            "resolved_as_inference": sum(r["accepted"] for r in records), "previously_ambiguous": len(records),
            "records": records, "queue_calibrations": calibrations}


def markdown(report):
    lines = ["# Phase 1: account-link investigation", "",
             "This audit does not read sample_output.csv, peer predictions or organizer data. It compares the two ranking modes on participant inputs. "
             "An accepted assignment remains an uncertified ownership inference, not a newly discovered identity chain.", "",
             f"Context v3 accepts {report['resolved_as_inference']} of {report['previously_ambiguous']} previously ambiguous account assignments.", "",
             "| Case | New proposal | Margin | Equally score-optimal alternatives |", "|---|---|---:|---|"]
    for r in report["records"]:
        proposal = r["proposal"]["resource_id"] if r["accepted"] else "abstain"
        options = r["equivalent_assignments"]["equally_optimal_resource_ids"]
        lines.append(f"| {r['case_id']} | {proposal} | {r['margin']:.6f} | {', '.join(options)} |")
    lines += ["", "## What changed", "",
              "- Current explicit absence interacts with an independently compliant case context. A broad inventory omission, stale lookup or future capture supplies no affinity; a known present copy blocks it.",
              "- Three distinct identity-linked policy resources strengthen the existing anchor-distance feature. Repeated operations on one resource do not count as independent anchors.",
              "- Both signals remain ranking assumptions. State is assessed separately, and original evidence-only predictions and the strict export gate are unchanged.",
              "", "## Why the remaining assignments abstain", "",
              "Each witness below is a feasible global assignment with the same objective score. The ambiguity is in the admissible account-to-subject association. "
              "This establishes ambiguity under the current model; it is not a claim that all possible inference methods are equivalent."]
    for r in report["records"]:
        if r["accepted"]:
            continue
        w = r["equivalent_assignments"]
        lines += ["", f"### {r['case_id']} at {r['audit_at']}", "",
                  f"Best score: {w['score']:.9f}. Distinct equally optimal targets: " + ", ".join(w["equally_optimal_resource_ids"]) + ".", "",
                  "```json", json.dumps(w["witnesses"][:2], indent=1, sort_keys=True), "```", "",
                  "Candidate evidence visible by the cutoff:", "", "| Resource | Observations | Capture IDs | Nonempty join fields |", "|---|---:|---|---|"]
        for rid, e in sorted(r["candidate_evidence"].items()):
            lines.append(f"| {rid} | {e['observation_count']} | {', '.join(e['evidence_ids']) or 'none'} | {', '.join(e['nonempty_join_fields']) or 'none'} |")
    lines += ["", "## Queue-order calibration", "",
              "Calibration uses accounts with explicit subject links and operations in their request windows, available by the target cutoff. "
              "It does not use the public answer file. Pairs overlap and the counts are descriptive, not independent accuracy trials."]
    for c in report["queue_calibrations"]:
        lines += ["", f"At {c['cutoff']}: {json.dumps(c['counts'], sort_keys=True)} across {c['explicit_account_batches']} batches."]
    lines += ["", "Neither first-in-first-out nor reverse request order is established by these observations, so neither was added as a tie-break. "
              "The raw alias pass found no additional account association; numeric suffix matches referred to other resource namespaces, unrelated subjects or unrelated activity IDs.", "",
              "To establish the remaining ownership links, supply a participant-visible request/job/subject correlation key or a source reference tying each account ID to its subject by audit_at. "
              "No case-number allocation or later capture was used to fill the missing association.", "",
              "Reproduce: `python3 scripts/audit_account_links.py`. Public sample accuracy is measured separately by `python3 scripts/evaluate_workflow.py`.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=REPO / "dataset")
    parser.add_argument("--requests", default="sample_deletion_requests.csv")
    parser.add_argument("--out", type=Path, default=REPO / "runs/analysis/account_link_phase1.json")
    parser.add_argument("--markdown", type=Path, default=REPO / "code/docs/ACCOUNT_LINK_PHASE1.md")
    args = parser.parse_args()
    report = audit(args.data, args.requests)
    for p in [args.out, args.markdown]:
        p.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(f"Previously ambiguous: {report['previously_ambiguous']}; accepted as inference: {report['resolved_as_inference']}; "
          f"still ambiguous: {report['previously_ambiguous'] - report['resolved_as_inference']}")
    for r in report["records"]:
        print(r["case_id"], r["proposal"]["resource_id"] if r["accepted"] else "abstain",
              "margin", round(r["margin"], 6), "optimal options", r["equivalent_assignments"]["equally_optimal_resource_ids"])


if __name__ == "__main__":
    main()
