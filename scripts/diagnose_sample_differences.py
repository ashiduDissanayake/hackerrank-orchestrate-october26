"""Diagnosis of every difference between the sample predictions and dataset/sample_output.csv (DIAGNOSIS ONLY: the public answers are
read here to name which resource ids to look up; nothing in the engine reads them).

For each missing or extra step it reports, from participant files only:
  * production link status (chains held by linking.link_subject under the dual-time cutoff) and the state the engine derived
  * every raw occurrence of the resource id in participant text (SQL/JSON/log/txt, PDFs through pdftotext, the hash-bound image
    transcriptions, activity rows, audit rows) with the file_id, manifest capture time, and what the line says
  * whether each occurrence is admissible at the case's audit_at (artifact time and record time)
  python3 scripts/diagnose_sample_differences.py [--out runs/analysis/sample_differences.json]
"""
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
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(REPO, "runs", "analysis", "sample_differences.json")
    ds, store, results = runner.run_dataset(DS, "sample_deletion_requests.csv")
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
                entry[kind].append({
                    "step": f"{s['phase']} {s['system_id']} {rid} {s['operation']} {s['evidence_id'] or '-'}",
                    "production_link": [(ch.kind, ch.evidence_id, ch.locator, ch.time) for ch in ln.chains] if ln else None,
                    "obligation": f"{ob.verdict}:{ob.reason}:{ob.evidence_id}" if ob else None,
                    "observations_admissible": len(cv.for_resource(rid)), "raw_occurrences": occ})
        rep[cid] = entry
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(rep, open(out_path, "w", encoding="utf-8"), indent=1, sort_keys=True, ensure_ascii=False)
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
