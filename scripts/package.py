"""Builds code.zip and (optionally) proves the package works when extracted with the dataset supplied separately.

  python3 scripts/package.py               # build ./code.zip
  python3 scripts/package.py --verify      # build, extract to a temp dir, add dataset/ there, run tests + run + verify, compare output hashes

Contents: README.md, code/ (source, tests, evaluation incl. the two reports, fixtures, image transcriptions, docs, requirements),
scripts/, and a generated evaluation/ copy of the two reports (AGENTS.md names that path; code/evaluation/ is authoritative).
Excluded and enforced: dataset/, virtual environments, caches and bytecode, runs/, .git, .env, nested archives, output.csv/log.txt
(separate submission items), and any file containing a secret-looking string (the build fails instead of silently skipping it).
The zip is deterministic (sorted entries, fixed timestamps).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "code.zip")
FIXED = (2026, 10, 25, 0, 0, 0)
EXCLUDE_DIRS = {"__pycache__", ".venv", "venv", ".git", "node_modules", "runs", "cache", "dataset", "agent-trace", ".pytest_cache"}
EXCLUDE_FILES = {".DS_Store", ".env", "output.csv", "log.txt", "code.zip"}
ARCHIVE_EXT = (".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".bz2", ".xz")
SECRETS = [re.compile(p) for p in (
    r"sk-ant-[A-Za-z0-9_\-]{10,}", r"sk-[A-Za-z0-9]{32,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}",
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", r"(?i)ANTHROPIC_API_KEY\s*=\s*[^\s'\"$]+")]
REPORTS = ("evaluation_report.md", "usage_report.md")


def collect():
    files = {}
    for base in ("code", "scripts"):
        for d, dirs, names in os.walk(os.path.join(REPO, base)):
            dirs[:] = sorted(x for x in dirs if x not in EXCLUDE_DIRS)
            for n in sorted(names):
                if n in EXCLUDE_FILES or n.endswith((".pyc", ".pyo")):
                    continue
                p = os.path.join(d, n)
                files[os.path.relpath(p, REPO)] = p
    files["README.md"] = os.path.join(REPO, "README.md")
    for r in REPORTS:  # generated copies; the authoritative files stay in code/evaluation/
        files[f"evaluation/{r}"] = os.path.join(REPO, "code", "evaluation", r)
    return dict(sorted(files.items()))


def check(files):
    problems = []
    for rel, p in files.items():
        top = rel.split("/")[0]
        if top in EXCLUDE_DIRS or rel.endswith(ARCHIVE_EXT):
            problems.append(f"{rel}: forbidden path or nested archive")
        try:
            text = open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue  # binary (PNG-free package) files cannot hold text secrets we can scan
        for pat in SECRETS:
            m = pat.search(text)
            if m:
                problems.append(f"{rel}: secret-looking string ({pat.pattern[:30]}...) at offset {m.start()}")
    for need in ("README.md", "code/main.py", "code/requirements.txt", "code/evaluation/evaluation_report.md", "code/evaluation/usage_report.md",
                 "evaluation/evaluation_report.md", "evaluation/usage_report.md"):
        if need not in files:
            problems.append(f"missing required file {need}")
    return problems


def build(out=OUT):
    files = collect()
    problems = check(files)
    if problems:
        print("PACKAGE REFUSED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, p in files.items():
            zi = zipfile.ZipInfo(rel, FIXED)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o644 << 16)
            z.writestr(zi, open(p, "rb").read())
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print(f"built {os.path.relpath(out, REPO)}: {len(files)} files, {os.path.getsize(out)} bytes, sha256 {sha}")
    return files


def reports_current():
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "write_reports.py"), "--check"], capture_output=True, text=True, cwd=REPO)
    print(r.stdout.strip())
    return r.returncode == 0


def verify():
    prov = os.path.join(REPO, "runs", "provisional", "output.manifest.json")
    if not os.path.exists(prov):
        subprocess.check_call([sys.executable, os.path.join(REPO, "code", "main.py"), "run"], cwd=REPO, stdout=subprocess.DEVNULL)
    repo_out = json.load(open(prov))["output_sha256"]
    preview_path = os.path.join(REPO, "runs", "workflow_preview", "output.csv")
    subprocess.check_call([sys.executable, "code/main.py", "run", "--workflow-mode", "joint", "--out", preview_path,
                           "--diagnostics", "runs/workflow_preview/diagnostics.json"], cwd=REPO, stdout=subprocess.DEVNULL)
    preview_sha = hashlib.sha256(open(preview_path, "rb").read()).hexdigest()
    candidate_path = os.path.join(REPO, "runs", "package_candidate")
    subprocess.check_call([sys.executable, "code/main.py", "candidate", "--artifact-dir", candidate_path], cwd=REPO, stdout=subprocess.DEVNULL)
    candidate_expected = json.load(open(os.path.join(candidate_path, "output.manifest.json")))["output_sha256"]
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(OUT) as z:
            names = z.namelist()
            assert not any(n.startswith("dataset/") for n in names), "dataset must not be in the package"
            assert not any(n.endswith(ARCHIVE_EXT) for n in names), "nested archive in the package"
            z.extractall(tmp)
        shutil.copytree(os.path.join(REPO, "dataset"), os.path.join(tmp, "dataset"))   # the dataset is supplied separately
        env = dict(os.environ)
        steps = [("tests + labeled evaluation", [sys.executable, "code/evaluation/main.py", "all"]),
                 ("provisional run", [sys.executable, "code/main.py", "run"]),
                 ("verify manifest", [sys.executable, "code/main.py", "verify", "runs/provisional/output.manifest.json"]),
                 ("workflow preview", [sys.executable, "code/main.py", "run", "--workflow-mode", "joint",
                                       "--out", "runs/workflow_preview/output.csv", "--diagnostics", "runs/workflow_preview/diagnostics.json"]),
                 ("verify workflow manifest", [sys.executable, "code/main.py", "verify", "runs/workflow_preview/output.manifest.json"]),
                 ("submission candidate", [sys.executable, "code/main.py", "candidate", "--artifact-dir", "runs/candidate_release"]),
                 ("verify candidate manifest", [sys.executable, "code/main.py", "verify", "runs/candidate_release/output.manifest.json"]),
                 ("best-effort review artifact", [sys.executable, "code/main.py", "best-effort"])]
        for label, cmd in steps:
            r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, env=env)
            print(f"  [{'ok' if r.returncode == 0 else 'FAILED'}] extracted package: {label}")
            if r.returncode != 0:
                print((r.stdout + r.stderr)[-1500:])
                sys.exit(1)
        got = json.load(open(os.path.join(tmp, "runs", "provisional", "output.manifest.json")))["output_sha256"]
        print(f"  output sha256 in the extracted package {got[:16]}... == repository run {repo_out[:16]}...: {got == repo_out}")
        if got != repo_out:
            sys.exit(1)
        preview = json.load(open(os.path.join(tmp, "runs", "workflow_preview", "output.manifest.json")))
        assert preview["certified"] is False and preview["final"] is False
        assert preview["workflow_inferred_link_count"] > 0, "preview must exercise workflow attribution"
        assert preview["output_sha256"] == preview_sha, "packaged workflow preview differs from the repository run"
        candidate = json.load(open(os.path.join(tmp, "runs", "candidate_release", "output.manifest.json")))
        assert candidate["output_sha256"] == candidate_expected and candidate["certified"] is False and candidate["final"] is False
        assert candidate["validation_error_count"] == 0, "submission candidate failed validation"
        assert candidate["config"]["decision_policy"] == "submission"
        print(f"  workflow preview sha256 matches repository: {preview_sha[:16]}...")
        print(f"  submission candidate sha256 matches repository: {candidate_expected[:16]}...")
        # The extracted best-effort run must be uncertified and must never have produced the submission file.
        be = json.load(open(os.path.join(tmp, "output_best_effort.manifest.json")))
        assert be["certified"] is False and be["final"] is False, "best-effort output must be marked uncertified"
        assert not os.path.exists(os.path.join(tmp, "output.csv")), "the package run must not write output.csv"
    print("package verified: the CODE is runnable and reproduces the provisional output byte for byte.")
    root_final = os.path.join(REPO, "output.csv")
    man = os.path.join(REPO, "output.manifest.json")
    final_manifest = json.load(open(man)) if os.path.exists(man) else {}
    certified = (os.path.exists(root_final) and final_manifest.get("final") is True
                 and final_manifest.get("certified") is not False and not final_manifest.get("plan_gaps_accepted"))
    print("Strict evidence-only certification: " + ("yes" if certified else "no (submission predictions retain disclosed assumptions)."))
    print(f"Root candidate validation errors: {final_manifest.get('validation_error_count', 'not generated')}; "
          f"decision assumptions: {final_manifest.get('decision_inference_count', 0)}. Reproduction does not establish hidden accuracy.")


if __name__ == "__main__":
    if "--skip-report-check" not in sys.argv and not reports_current():
        print("PACKAGE REFUSED: the reports are out of date; run python3 scripts/write_reports.py")
        sys.exit(1)
    build()
    if "--verify" in sys.argv:
        verify()
