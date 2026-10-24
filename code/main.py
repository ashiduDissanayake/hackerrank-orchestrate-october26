"""Ghost Data audit CLI (M2 stage: extraction + coverage; the audit pipeline lands in M3).

  python3 code/main.py run [--data dataset] [--requests deletion_requests.csv] [--out runs/provisional/output.csv]   (provisional, never the submission path)
  python3 code/main.py export [--data dataset] [--allow-dirty]    (the ONLY writer of repo-root output.csv; refuses unless every gate passes)
  python3 code/main.py verify MANIFEST.json                       (regenerates from a manifest and compares the output hash)
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


def manifest_commands(a):
    import json
    from ghostaudit import export as ex
    from ghostaudit import run as runner
    if a.cmd == "verify":
        m = json.load(open(a.manifest))
        cfg = m["config"]
        ds, store, results = runner.run_dataset(os.path.join(REPO, cfg["data"]), cfg["requests"], cfg["unknown_policy"])
        tmp = os.path.join(REPO, "runs", "verify", "output.csv")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        runner.write_output(results, tmp)
        same_out = ex.sha256_file(tmp) == m["output_sha256"]
        same_in = ex.input_hashes(ds.root) == m["inputs_sha256"]
        same_code = ex.code_hash() == m["code_sha256"]
        print(f"output reproduces byte-for-byte: {same_out}\ninputs unchanged: {same_in}\ncode unchanged: {same_code}")
        return 0 if (same_out and same_in and same_code) else 1
    cfg = {"data": os.path.relpath(a.data, REPO), "requests": a.requests, "unknown_policy": a.unknown_policy, "png_extraction": "pending"}
    ds, store, results = runner.run_dataset(a.data, a.requests, a.unknown_policy)
    out = a.out if a.cmd == "run" else os.path.join(REPO, "runs", "export_candidate", "output.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    runner.write_output(results, out)
    errs = ex.validate_output(ds, out)
    manifest = ex.build_manifest(["python3", "code/main.py"] + sys.argv[1:], cfg, ds, results, out, errs)
    if a.cmd == "run":
        runner.write_diagnostics(results, a.diagnostics)
        mpath = os.path.splitext(a.out)[0] + ".manifest.json"
        ex.write_manifest(manifest, mpath)
        print(f"PROVISIONAL: wrote {len(results)} rows to {a.out}; manifest -> {mpath}; diagnostics -> {a.diagnostics}")
        print(f"policy={a.unknown_policy}  contract_valid={manifest['contract_valid']} ({len(errs)} validation errors)  undetermined cases={len(manifest['undetermined_cases'])}")
        for k, v in runner.diagnostics(results).items():
            print(f"  {k}: {v}")
        return 0
    reasons = ex.gate(ds, results, out, manifest, a.allow_dirty, run_tests=not a.skip_tests)
    if reasons:
        print("EXPORT REFUSED. output.csv was NOT written.")
        for r in reasons:
            print("  -", r)
        return 1
    final = os.path.join(REPO, "output.csv")
    manifest["final"] = True
    import shutil
    shutil.copyfile(out, final)
    ex.write_manifest(manifest, os.path.join(REPO, "output.manifest.json"))
    print(f"EXPORTED {final} (sha256 {manifest['output_sha256'][:16]}...) with output.manifest.json")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("coverage", "dump", "run", "explain", "export", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--data", default=os.path.join(REPO, "dataset"))
        if name in ("run", "explain", "export"):
            p.add_argument("--requests", default="deletion_requests.csv")
    r = sub.choices["run"]
    r.add_argument("--out", default=os.path.join(REPO, "runs", "provisional", "output.csv"))
    r.add_argument("--diagnostics", default=os.path.join(REPO, "runs", "provisional", "diagnostics.json"))
    ex = sub.choices["export"]
    ex.add_argument("--allow-dirty", action="store_true")
    ex.add_argument("--skip-tests", action="store_true", help="NOT allowed for a final export; for debugging the gate only")
    sub.choices["verify"].add_argument("manifest")
    sub.choices["explain"].add_argument("case_id")
    for name in ("run", "explain", "export"):
        sub.choices[name].add_argument("--unknown-policy", default="not_certified", choices=["not_certified", "certify_established"],
                                       help="status for cases with unresolved obligations (open decision P3)")
    d = sub.choices["dump"]
    d.add_argument("--audit-at")
    d.add_argument("--resource")
    d.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()
    if a.cmd in ("run", "export", "verify"):
        sys.exit(manifest_commands(a))
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
