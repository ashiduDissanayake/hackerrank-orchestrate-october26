"""Ghost Data audit CLI (M2 stage: extraction + coverage; the audit pipeline lands in M3).

  python3 code/main.py run [--data dataset] [--requests deletion_requests.csv] [--out output.csv] [--diagnostics runs/last/diagnostics.json]
  python3 code/main.py explain CASE_ID [--data dataset] [--requests deletion_requests.csv]
  python3 code/main.py coverage [--data dataset]
  python3 code/main.py dump [--data dataset] [--audit-at TS] [--resource ID] [--limit N]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.dirname(HERE)

from ghostaudit import coverage  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.pipeline import build  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("coverage", "dump", "run", "explain"):
        p = sub.add_parser(name)
        p.add_argument("--data", default=os.path.join(REPO, "dataset"))
        if name in ("run", "explain"):
            p.add_argument("--requests", default="deletion_requests.csv")
    r = sub.choices["run"]
    r.add_argument("--out", default=os.path.join(REPO, "output.csv"))
    r.add_argument("--diagnostics", default=os.path.join(REPO, "runs", "last", "diagnostics.json"))
    sub.choices["explain"].add_argument("case_id")
    for name in ("run", "explain"):
        sub.choices[name].add_argument("--unknown-policy", default="established_only", choices=["established_only", "unknown_is_incomplete"],
                                       help="status for cases with unresolved obligations (open decision P3)")
    d = sub.choices["dump"]
    d.add_argument("--audit-at")
    d.add_argument("--resource")
    d.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()
    if a.cmd in ("run", "explain"):
        import json
        from ghostaudit import run as runner
        ds, store, results = runner.run_dataset(a.data, a.requests, a.unknown_policy)
        if a.cmd == "run":
            runner.write_output(results, a.out)
            runner.write_diagnostics(results, a.diagnostics)
            print(f"wrote {len(results)} rows to {a.out}; diagnostics -> {a.diagnostics}")
            print(f"UNRESOLVED-OBLIGATION POLICY: '{a.unknown_policy}' (open decision P3).")
            for k, v in runner.diagnostics(results).items():
                print(f"  {k}: {v}")
        else:
            r = next(x for x in results if x.case_id == a.case_id)
            print(json.dumps(runner.case_detail(r), indent=1, ensure_ascii=False, default=str))
            print("steps:")
            for s_ in r.steps:
                print("  ", s_["step_no"], s_["phase"], s_["system_id"], s_["resource_id"], s_["operation"], s_["evidence_id"])
        return
    ds, store = build(a.data)
    if a.cmd == "coverage":
        print(coverage.render(ds, store))
    else:
        obs = CaseView(store, a.audit_at).all() if a.audit_at else store._obs
        if a.resource:
            obs = [o for o in obs if o.resource_id == a.resource]
        for o in obs[: a.limit]:
            print(o.evidence_id, o.locator, o.available_at, o.observed_at, o.system_id, o.resource_id, o.store, o.kind, o.present)


if __name__ == "__main__":
    main()
