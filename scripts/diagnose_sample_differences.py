"""Diagnosis of every difference between the sample predictions and dataset/sample_output.csv (DIAGNOSIS ONLY: the public answers are
read here to name which resource ids to look up; nothing in the engine reads them).

For each missing or extra step it reports, from participant files only:
  * production link status (chains held by linking.link_subject under the dual-time cutoff) and the state the engine derived
  * every raw occurrence of the resource id in participant text (SQL/JSON/log/txt, PDFs through pdftotext, the hash-bound image
    transcriptions, activity rows, audit rows) with the file_id, manifest capture time, and what the line says
  * whether each occurrence is admissible at the case's audit_at (artifact time and record time)
  python3 scripts/diagnose_sample_differences.py [--out runs/analysis/sample_differences.json]
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
sys.path.insert(0, os.path.join(REPO, "code", "evaluation"))
import scoring  # noqa: E402
from ghostaudit import run as runner  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402

DS = os.path.join(REPO, "dataset")
man = {r["file_id"]: r for r in csv.DictReader(open(os.path.join(DS, "evidence_files.csv"), encoding="utf-8"))}
TEXTS = {}


def text_of(fid):
    if fid in TEXTS:
        return TEXTS[fid]
    path = os.path.join(DS, man[fid]["file_path"])
    if path.endswith(".pdf"):
        t = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    elif path.endswith(".png"):
        tp = os.path.join(REPO, "code", "ghostaudit", "image_transcriptions", f"{fid}.json")
        t = open(tp, encoding="utf-8").read() if os.path.exists(tp) else ""
    else:
        t = open(path, encoding="utf-8", errors="replace").read()
    TEXTS[fid] = t
    return t


def occurrences(rid):
    out = []
    pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(rid)}(?![A-Za-z0-9_])")
    for fid in sorted(man):
        for i, line in enumerate(text_of(fid).splitlines(), 1):
            if pat.search(line):
                out.append({"file_id": fid, "path": man[fid]["file_path"], "captured_at": man[fid]["captured_at"], "line": i, "text": line.strip()[:220]})
    for fn, idc, tc in (("system_activity.csv", "activity_id", "event_time"), ("user_audit_log.csv", "audit_id", "event_time")):
        for r in csv.DictReader(open(os.path.join(DS, fn), encoding="utf-8")):
            if pat.search(" ".join(r.values())):
                out.append({"file_id": r[idc], "path": fn, "captured_at": r[tc], "line": 0, "text": " | ".join(r.values())[:220]})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(REPO, "runs", "analysis", "sample_differences.json"))
    parser.add_argument("--markdown")
    parser.add_argument("--workflow-mode", choices=["evidence", "joint"], default="evidence")
    parser.add_argument("--workflow-scoring", choices=["contextual", "contextual_v2", "contextual_v3", "anchor"], default="contextual_v3")
    parser.add_argument("--workflow-min-margin", type=float, default=0.0)
    args = parser.parse_args()
    out_path = args.out
    from ghostaudit.workflow import WorkflowConfig
    ds, store, results = runner.run_dataset(DS, "sample_deletion_requests.csv", workflow_mode=args.workflow_mode,
                                           workflow_config=WorkflowConfig(scoring=args.workflow_scoring, min_margin=args.workflow_min_margin))
    gold = scoring.load_output(os.path.join(DS, "sample_output.csv"))
    pred = {r.case_id: {"status": r.status, "steps": r.steps} for r in results}
    m = scoring.score(gold, pred)
    ix = IdentityIndex(ds.identities, ds.audit_log)
    req = {r.case_id: r for r in ds.requests}
    byid = {r.case_id: r for r in results}
    rep = {}
    for cid, c in m["per_case"].items():
        if c["exact"]:
            continue
        r, q = byid[cid], req[cid]
        cv = CaseView(store, q.audit_at)
        entry = {"requested_at": q.requested_at, "audit_at": q.audit_at, "email": q.email, "user_id": r.subject.user_id,
                 "missing": [], "extra": []}
        for kind in ("missing", "extra"):
            for s in c[kind]:
                rid = s["resource_id"]
                ln = r.links.get(rid)
                ob = next((o for o in r.obligations if o.resource_id == rid), None)
                occ = occurrences(rid)
                for o in occ:
                    o["admissible_at_audit"] = o["captured_at"] <= q.audit_at
                admissible = [o for o in occ if o["admissible_at_audit"]]
                cause = ("NO_PARTICIPANT_OCCURRENCE" if not occ else "CAPTURED_AFTER_AUDIT" if not admissible
                         else "OWNERSHIP_UNRESOLVED" if ln is None else "STATE_OR_PLAN_DIFFERENCE")
                entry[kind].append({
                    "resource_id": rid, "cause": cause,
                    "step": f"{s['phase']} {s['system_id']} {rid} {s['operation']} {s['evidence_id'] or '-'}",
                    "production_link": [(ch.kind, ch.evidence_id, ch.locator, ch.time) for ch in ln.chains] if ln else None,
                    "obligation": f"{ob.verdict}:{ob.reason}:{ob.evidence_id}" if ob else None,
                    "observations_admissible": len(cv.for_resource(rid)), "raw_occurrences": occ})
        rep[cid] = entry
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(rep, open(out_path, "w", encoding="utf-8"), indent=1, sort_keys=True, ensure_ascii=False)
    if args.markdown:
        from collections import Counter
        counts = Counter(s["cause"] for e in rep.values() for s in e["missing"])
        exact = sum(c["exact"] for c in m["per_case"].values())
        lines = ["# Remaining public sample differences and evidence requirements", "",
                 "Diagnosis only: labels identify the expected resource to search for after predictions are complete. "
                 "Neither this report nor the labels feed predictions. These are public development results, not a hidden-set score.", "",
                 f"Mode `{args.workflow_mode}`, scoring `{args.workflow_scoring}`, margin floor `{args.workflow_min_margin}`: "
                 f"{exact}/32 exact full answers; {len(rep)} differing rows; {m['step_strict']['fn']} missing steps; {m['step_strict']['fp']} extra steps.", "",
                 "| Case | Expected resource | Cause | Participant occurrences | Audit cutoff |", "|---|---|---|---|---|"]
        for cid, e in rep.items():
            for s in e["missing"]:
                hits = "; ".join(f"{o['file_id']} @ {o['captured_at']}" for o in s["raw_occurrences"])
                lines.append(f"| {cid} | {s['resource_id']} | {s['cause']} | {hits or 'none'} | {e['audit_at']} |")
        lines += ["", "Counts by missing-step cause: " + ", ".join(f"{k}={v}" for k,v in sorted(counts.items())) + ".", "",
                  "Required input to close these differences:", "",
                  "- For an ID with no participant occurrence: a participant-visible record or activity naming the ID and connecting it to the subject, available by audit_at.",
                  "- For later-captured evidence: an admissible earlier capture, or explicit organizer clarification changing the stated time contract. A later capture cannot be used under the current rule.",
                  "- For unresolved ownership: a request/subject correlation key, source reference or other grounded association that distinguishes the competing workflows. Request-number ordering does not prove ownership.",
                  "", "The output schema itself is clear. These requirements concern facts needed to reproduce specific canonical steps without inserting labels into prediction code.", ""]
        os.makedirs(os.path.dirname(os.path.abspath(args.markdown)), exist_ok=True)
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    for cid, e in rep.items():
        print(f"== {cid} request {e['requested_at']} audit {e['audit_at']} {e['user_id']}")
        for kind in ("missing", "extra"):
            for s in e[kind]:
                print(f"  {kind.upper()} {s['step']}")
                print(f"     link={s['production_link']}  obligation={s['obligation']}  admissible observations={s['observations_admissible']}")
                for o in s["raw_occurrences"][:6]:
                    print(f"     {'OK ' if o['admissible_at_audit'] else 'LATE'} {o['file_id']} @{o['captured_at']} L{o['line']}: {o['text'][:140]}")
                if len(s["raw_occurrences"]) > 6:
                    print(f"     ... {len(s['raw_occurrences']) - 6} more")


if __name__ == "__main__":
    main()
