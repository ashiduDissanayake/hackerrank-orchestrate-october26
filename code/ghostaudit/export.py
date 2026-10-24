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


def code_hash():
    files = []
    for base in (os.path.join(CODE, "ghostaudit"),):
        for d, _, names in os.walk(base):
            if "__pycache__" in d:
                continue
            files += [os.path.relpath(os.path.join(d, n), CODE) for n in names if n.endswith((".py", ".md"))]
    return _tree_hash(files, CODE)


def git_state():
    def git(*a):
        r = subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    status = git("status", "--porcelain")
    dirty_files = [l[3:] for l in (status or "").splitlines() if not l[3:].startswith(("runs/", "output"))]
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(dirty_files), "dirty_files": dirty_files[:20]}


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
    if manifest["git"]["dirty"] and not allow_dirty:
        reasons.append(f"git working tree is dirty ({len(manifest['git']['dirty_files'])} files); commit first so the manifest's commit identifies the code")
    if run_tests:
        r = subprocess.run([sys.executable, os.path.join(CODE, "evaluation", "main.py"), "all"], capture_output=True, text=True)
        if r.returncode != 0:
            reasons.append("the test and labeled-evaluation suite failed (python3 code/evaluation/main.py all)")
    return reasons


def write_manifest(manifest, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
