"""Run manifests and the final export gate.

A run manifest records everything needed to regenerate a CSV byte-for-byte: the exact command, configuration,
sha256 of every input file and of the code that ran, the git commit and whether the tree was dirty, plus the output
hash and the unresolved-case register. `export` is the only command that writes the submission path (repo-root
output.csv) and only when every gate passes.
"""
import csv
import hashlib
import json
import os
import subprocess
import sys

from .validate import validate_rows

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(CODE)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_hash(files, base):
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode())
        h.update(sha256_file(os.path.join(base, rel)).encode())
    return h.hexdigest()


def input_hashes(root):
    """sha256 of every file under the data root (csv + evidence), keyed by relative path."""
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            if n.startswith("."):
                continue
            p = os.path.join(d, n)
            out[os.path.relpath(p, root)] = sha256_file(p)
    return dict(sorted(out.items()))


def code_files():
    """Every file that can change a prediction: all of code/ghostaudit (sources, image transcriptions, any prompt or
    config added later; any extension), the CLI entry point, and the dependency manifest. Caches and bytecode are excluded."""
    out = {}
    for d, dirs, names in os.walk(os.path.join(CODE, "ghostaudit")):
        dirs[:] = sorted(x for x in dirs if x != "__pycache__")
        for n in names:
            if n.endswith((".pyc", ".pyo")) or n.startswith("."):
                continue
            p = os.path.join(d, n)
            out[os.path.relpath(p, REPO)] = p
    for rel in ("code/main.py", "code/requirements.txt"):
        p = os.path.join(REPO, rel)
        if os.path.exists(p):
            out[rel] = p
    return dict(sorted(out.items()))


def code_hash():
    h = hashlib.sha256()
    for rel, p in code_files().items():
        h.update(rel.encode())
        h.update(sha256_file(p).encode())
    return h.hexdigest()


def dirty_code_paths(dirty_files, code_rel):
    """The dirty paths that are prediction-affecting: a code file itself, or an untracked directory (git reports `dir/`) that
    contains one. `code_rel` is the set of repo-relative prediction-affecting paths (code_files())."""
    return [f for f in dirty_files if f in code_rel or (f.endswith("/") and any(c.startswith(f) for c in code_rel))]


def git_state():
    def git(*a):
        r = subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True)
        return r.stdout.rstrip("\n") if r.returncode == 0 else None   # keep leading spaces: porcelain lines start with a status column
    status = git("status", "--porcelain")
    dirty_files = [l[3:] for l in (status or "").splitlines() if not l[3:].startswith(("runs/", "output"))]
    # Producing-code provenance: what matters for reproducing the output is whether a PREDICTION-AFFECTING file differs from the
    # commit. Reports, docs, tests and packaging scripts may change in later commits without changing the output, so they are
    # recorded (dirty_files) but do not make the producing commit ambiguous; code_sha256 identifies the exact code either way.
    dirty_code = dirty_code_paths(dirty_files, set(code_files()))
    return {"commit": (git("rev-parse", "HEAD") or "").strip() or None, "dirty": bool(dirty_files), "dirty_files": dirty_files[:20], "dirty_code_files": dirty_code[:20]}


def evidence_time_resolver(ds):
    """file_id -> captured_at, activity_id/audit_id -> event_time (so every citable id is time-checked)."""
    times = {m.file_id: m.captured_at for m in ds.manifest}
    times.update({a.activity_id: a.event_time for a in ds.activity})
    times.update({a.audit_id: a.event_time for a in ds.audit_log})
    return times.get


def build_manifest(argv, config, ds, results, out_path, validation_errors):
    und = [r.case_id for r in results if r.internal == "UNDETERMINED"]
    counts = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {
        "command": argv,
        "config": config,
        "python": sys.version.split()[0],
        "git": git_state(),
        "code_sha256": code_hash(),
        "code_files": len(code_files()),
        "code_files_sha256": {rel: sha256_file(p) for rel, p in code_files().items()},
        "runtime_model_calls": 0,   # the pipeline is deterministic code; no LLM is called at run time
        "prompts": [],
        "inputs_sha256": input_hashes(ds.root),
        "output_sha256": sha256_file(out_path),
        "rows": len(results),
        "status_counts": dict(sorted(counts.items())),
        "undetermined_cases": und,
        "contract_valid": not validation_errors,
        "validation_error_count": len(validation_errors),
        "final": False,
    }


def validate_output(ds, out_path):
    return validate_rows(out_path, expected_case_ids=[r.case_id for r in ds.requests],
                         audit_at_by_case={r.case_id: r.audit_at for r in ds.requests},
                         evidence_time=evidence_time_resolver(ds))


def gate(ds, results, out_path, manifest, allow_dirty=False, run_tests=True):
    """Return the list of reasons the output must NOT be exported (empty list = exportable)."""
    reasons = []
    errs = validate_output(ds, out_path)
    if errs:
        reasons.append(f"{len(errs)} contract validation errors (first: {errs[0]})")
    if manifest["undetermined_cases"]:
        reasons.append(f"{len(manifest['undetermined_cases'])} UNDETERMINED cases: the output cannot represent an unresolved obligation "
                       "(open decision P3); first: " + ", ".join(manifest["undetermined_cases"][:5]))
    if manifest["config"].get("unknown_policy") != "not_certified":
        reasons.append(f"unknown_policy is {manifest['config'].get('unknown_policy')!r}; only 'not_certified' may be exported")
    pending = [a for a in ds.manifest if a.file_path.endswith(".png")]
    if manifest["config"].get("png_extraction") != "complete" and pending:
        reasons.append(f"{len(pending)} PNG artifacts are not extracted yet (M5); the run cannot be final")
    if manifest["git"].get("dirty_code_files") and not allow_dirty:
        reasons.append(f"{len(manifest['git']['dirty_code_files'])} prediction-affecting files differ from the commit (first: {manifest['git']['dirty_code_files'][0]}); "
                       "commit the code first so the manifest's commit identifies the code that produced the output")
    if run_tests:
        r = subprocess.run([sys.executable, os.path.join(CODE, "evaluation", "main.py"), "all"], capture_output=True, text=True)
        if r.returncode != 0:
            reasons.append("the test and labeled-evaluation suite failed (python3 code/evaluation/main.py all)")
    return reasons


def write_manifest(manifest, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")


# --- best-effort review artifact ----------------------------------------------------------------------------------------------
# NOT a submission and NOT certified. Written only when the strict export gate cannot pass because evidence for some cases is
# genuinely missing. It carries the same rows the engine produced (unresolved obligations mapped by the non-certifying policy
# to INCOMPLETE, established steps only, nothing invented), plus a register that names the exact missing fact per case and
# every validation failure. It never writes the root output.csv.
BEST_EFFORT_NAMES = ("output_best_effort.csv", "output_best_effort.unresolved.json", "output_best_effort.manifest.json")


def _gap_text(res, ob, req):
    """The precise missing fact for one unresolved obligation (what evidence would settle it, and why the dataset cannot)."""
    where = f"between requested_at {req.requested_at} and audit_at {req.audit_at}"
    d = ob.detail or {}
    if ob.category == "USER_PROFILE" and ob.reason == "unresolved_link":
        pr = d.get("proof") or {}
        base = (f"no admissible capture of an account profile collection {where} establishes whether a profile for the subject remains "
                f"(proof status {pr.get('status', 'n/a')}: {pr.get('reason', 'no proof attempted')})")
        if d.get("window_candidates"):
            base += (f"; {len(d['window_candidates'])} deletion-worker activity rows in the request window name account resources, "
                     "but they are claims shared with other requests and carry no identifier, so none is linked to the subject")
        return base
    if ob.reason == "no_restore_flag_in_admissible_evidence":
        return (f"the restore permission of {ob.resource_id} at audit_at {req.audit_at} is not shown by any admissible evidence "
                "(screens that list the archive show no restore-allowed/blocked state; later logs and activity are after the cutoff)")
    if ob.reason == "conflicting_identity_evidence":
        return f"{ob.resource_id}: {d.get('conflict', 'admissible sources disagree about whose record this is')}; neither source supersedes the other"
    if ob.reason == "retained_record_not_found":
        return f"the latest admissible evidence does not show the retained record {ob.resource_id} present at audit_at {req.audit_at}"
    rid = ob.resource_id or ob.category
    if ob.reason == "no_enabled_flag_in_admissible_evidence":
        return f"whether the data flow {rid} is enabled at audit_at {req.audit_at} is not shown by any admissible evidence (no record of its enabled flag at or before the cutoff)"
    if ob.reason == "no_admissible_evidence":
        return f"no admissible evidence at or before audit_at {req.audit_at} shows the state of {rid} ({ob.category}): no capture covering its system and copy was available by the cutoff"
    if ob.reason == "shared_attachment":
        return f"{rid}: it cannot be established from the evidence whether the attachment belongs only to the subject ({d if isinstance(d, str) else 'shared or unclear ownership'}), which rule_06 requires before DELETE"
    if ob.reason == "record_absent_where_treatment_expected":
        return f"{rid} ({ob.category}) is absent although policy requires a treated record to remain; the evidence does not show whether it was retained elsewhere"
    if ob.reason.startswith("no_rule_for_category"):
        return f"{rid}: deletion_rules.csv has no rule for category {ob.category}, so no required state can be derived"
    return f"{rid}: unresolved ({ob.reason})"


def unresolved_register(ds, results, errors):
    """One entry per case with at least one UNKNOWN obligation. status_determined is True when an established violation already
    makes the case INCOMPLETE (the unknown item then only leaves part of the plan open); False when the status itself rests on
    an unresolved obligation."""
    reqs = {r.case_id: r for r in ds.requests}
    errs = {}
    for e in errors:
        errs.setdefault(e.split(":", 1)[0], []).append(e.split(":", 1)[1].strip() if ":" in e else e)
    out = []
    for r in results:
        unk = [o for o in r.obligations if o.verdict == "UNKNOWN"]
        if not unk:
            continue
        out.append({
            "case_id": r.case_id, "output_status": r.status, "internal_status": r.internal,
            "status_determined": r.internal == "INCOMPLETE",
            "unresolved": [{"system_id": o.system_id, "resource_id": o.resource_id, "category": o.category, "reason": o.reason,
                            "information_gap": _gap_text(r, o, reqs[r.case_id])} for o in unk],
            "emitted_steps": [{"phase": s["phase"], "system_id": s["system_id"], "resource_id": s["resource_id"], "operation": s["operation"],
                               "evidence_id": s["evidence_id"]} for s in r.steps],
            "validation_errors": errs.get(r.case_id, [])})
    return out


def write_best_effort(ds, results, errors, manifest, out_dir):
    """Writes the three best-effort files into out_dir and returns their paths. Marks the manifest certified=false."""
    from . import run as runner
    paths = {n: os.path.join(out_dir, n) for n in BEST_EFFORT_NAMES}
    runner.write_output(results, paths[BEST_EFFORT_NAMES[0]])
    reg = unresolved_register(ds, results, errors)
    with open(paths[BEST_EFFORT_NAMES[1]], "w", encoding="utf-8") as f:
        json.dump({"certified": False, "unresolved_cases": reg}, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    manifest = dict(manifest)
    manifest.update({
        "kind": "best_effort", "certified": False, "final": False,
        "output_sha256": sha256_file(paths[BEST_EFFORT_NAMES[0]]),
        "validation_errors": errors,
        "register_sha256": sha256_file(paths[BEST_EFFORT_NAMES[1]]),
        "disclosure": ("Review artifact, NOT a certified or contract-conforming submission. Cases listed in `undetermined_cases` rest on an "
                       "unresolved obligation: the non-certifying policy maps them to INCOMPLETE with only the steps the evidence supports, "
                       "which the contract validator rejects (INCOMPLETE needs a FINDING). No finding was fabricated to pass validation."),
    })
    write_manifest(manifest, paths[BEST_EFFORT_NAMES[2]])
    return paths, reg
