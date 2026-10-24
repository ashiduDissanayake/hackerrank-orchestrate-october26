"""Evaluation CLI.

  python3 code/evaluation/main.py all          # every test suite + labeled evaluation
  python3 code/evaluation/main.py selftest
  python3 code/evaluation/main.py score --pred output.csv --gold dataset/sample_output.csv [--diff]
  python3 code/evaluation/main.py validate --pred output.csv --requests dataset/deletion_requests.csv

`score` is only meaningful on labeled data (public samples, labeled fixtures); it reports accuracy.
"""
import argparse
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import scoring  # noqa: E402
from ghostaudit.validate import validate_rows  # noqa: E402


def cmd_selftest(_):
    sys.exit(subprocess.call([sys.executable, os.path.join(HERE, "test_scoring.py")]))


def cmd_all(_):
    """Every test suite, then the labeled evaluation. Exit code is non-zero if any suite fails."""
    code_dir = os.path.dirname(HERE)
    suites = [os.path.join(HERE, "test_scoring.py"), os.path.join(HERE, "test_fixtures_frozen.py"),
              os.path.join(code_dir, "tests", "test_core.py"), os.path.join(code_dir, "tests", "test_intent.py"),
              os.path.join(code_dir, "tests", "test_invariance.py"),
              os.path.join(code_dir, "tests", "test_review_findings.py"),
              os.path.join(code_dir, "tests", "test_export.py"),
              os.path.join(code_dir, "tests", "test_account_gap.py"), os.path.join(code_dir, "tests", "test_phone_linking.py"),
              os.path.join(code_dir, "tests", "test_identity_conflicts.py"), os.path.join(code_dir, "tests", "test_image_transcriptions.py"),
              os.path.join(code_dir, "tests", "test_account_proof.py")]
    failed = []
    for sfile in suites:
        r = subprocess.run([sys.executable, sfile], capture_output=True, text=True)
        tail = [l for l in r.stderr.splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
        print(f"{'PASS' if r.returncode == 0 else 'FAIL'}  {os.path.relpath(sfile, os.path.dirname(code_dir))}  {' '.join(tail)}", flush=True)
        if r.returncode:
            failed.append(sfile)
    print(flush=True)
    rc = subprocess.call([sys.executable, os.path.join(HERE, "labeled.py")])
    if rc != 0:
        print(f"FAIL  labeled evaluation exited with status {rc}", flush=True)
        failed.append("labeled.py")
    print(f"\n{'ALL CHECKS PASSED' if not failed else 'FAILED: ' + ', '.join(os.path.basename(f) for f in failed)}")
    sys.exit(1 if failed else 0)


def cmd_score(a):
    gold = scoring.load_output(a.gold)
    pred = scoring.load_output(a.pred)
    m = scoring.score(gold, pred)
    print(scoring.summarize(m))
    if a.diff:
        for cid, c in m["per_case"].items():
            if c["exact"]:
                continue
            print(f"\n{cid}: gold={c['status_gold']} pred={c['status_pred']} lcs={c['lcs']}")
            for s in c["missing"]:
                print("  MISSING", json.dumps(s, sort_keys=True))
            for s in c["extra"]:
                print("  EXTRA  ", json.dumps(s, sort_keys=True))
            for s, f, v in c["wrong_fields"]:
                print(f"  WRONG {f}: gold={s[f]!r} pred={v!r} for {s['phase']} {s['system_id']} {s['resource_id']} {s['operation']}")


def cmd_validate(a):
    """Contract validation incl. finding/remediation/verification chains and evidence-time checks for file, activity
    and audit ids (the same checks the export gate applies)."""
    from ghostaudit import export as ex
    from ghostaudit.data import load_dataset
    ds = load_dataset(os.path.dirname(os.path.abspath(a.requests)), os.path.basename(a.requests))
    errs = ex.validate_output(ds, a.pred)
    print(f"{len(errs)} validation errors")
    for e in errs[:50]:
        print(" ", e)
    sys.exit(1 if errs else 0)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest").set_defaults(fn=cmd_selftest)
    sub.add_parser("all").set_defaults(fn=cmd_all)
    s = sub.add_parser("score")
    s.add_argument("--pred", required=True)
    s.add_argument("--gold", required=True)
    s.add_argument("--diff", action="store_true")
    s.set_defaults(fn=cmd_score)
    v = sub.add_parser("validate")
    v.add_argument("--pred", required=True)
    v.add_argument("--requests", required=True)
    v.set_defaults(fn=cmd_validate)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
