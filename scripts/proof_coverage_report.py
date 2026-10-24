"""Per-case account-proof coverage report (diagnostic, not a label).

  python3 scripts/proof_coverage_report.py [--requests FILE] [--out PATH] [--case case_45 ...]

For every authorized-deletion case whose account obligation is discharged by account_proof, lists the proof status, the
evidence it rests on, per-copy events, and the copies the proof could not assert. Output is JSON so two code versions can be
diffed ("reopened" = was COMPLETE-by-proof, now not).
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))

from ghostaudit import run as runner  # noqa: E402


def main():
    args = sys.argv[1:]
    requests = args[args.index("--requests") + 1] if "--requests" in args else "deletion_requests.csv"
    out = args[args.index("--out") + 1] if "--out" in args else None
    only = set(args[args.index("--case") + 1:]) if "--case" in args else None
    ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"), requests)
    rep = {}
    for r in results:
        if only and r.case_id not in only:
            continue
        acct = [o for o in r.obligations if o.category == "USER_PROFILE"]
        rep[r.case_id] = {"status": r.status, "internal": r.internal,
                          "account": [{"resource": o.resource_id, "verdict": o.verdict, "reason": o.reason, "evidence": o.evidence_id,
                                       "copies": o.detail.get("copies"), "uncovered": o.detail.get("uncovered_copies"),
                                       "excluded": o.detail.get("excluded_copies")} for o in acct]}
    text = json.dumps(rep, indent=1, sort_keys=True, default=str)
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "w").write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
