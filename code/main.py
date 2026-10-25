"""Ghost Data audit CLI (M2 stage: extraction + coverage; the audit pipeline lands in M3).

  python3 code/main.py run [--data dataset] [--requests deletion_requests.csv] [--out runs/provisional/output.csv]   (provisional, never the submission path)
  python3 code/main.py export [--data dataset] [--allow-dirty] [--accept-plan-gaps]    (strict export; refuses unless every gate passes)
  python3 code/main.py candidate [--data dataset] [--artifact-dir DIR] (explicit uncertified output.csv + validation/uncertainty sidecars)
  python3 code/main.py best-effort [--data dataset]               (review artifact output_best_effort.* at the repo root; certified=false; never writes output.csv)
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
        from ghostaudit.workflow import WorkflowConfig
        ds, store, results = runner.run_dataset(os.path.join(REPO, cfg["data"]), cfg["requests"], cfg["unknown_policy"],
                                                workflow_mode=cfg.get("workflow_mode", "evidence"),
                                                workflow_config=WorkflowConfig(**cfg.get("workflow_config", {})),
                                                decision_policy=cfg.get("decision_policy", "strict"))
        tmp = os.path.join(REPO, "runs", "verify", "output.csv")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        runner.write_output(results, tmp)
        same_out = ex.sha256_file(tmp) == m["output_sha256"]
        same_in = ex.input_hashes(ds.root) == m["inputs_sha256"]
        same_code = ex.code_hash() == m["code_sha256"]
        print(f"output reproduces byte-for-byte: {same_out}\ninputs unchanged: {same_in}\ncode unchanged: {same_code}")
        if not same_code and "code_files_sha256" in m:
            now = {rel: ex.sha256_file(p) for rel, p in ex.code_files().items()}
            diff = sorted(k for k in set(now) | set(m["code_files_sha256"]) if now.get(k) != m["code_files_sha256"].get(k))
            print("  files that differ from the producing run:", ", ".join(diff[:10]))
        return 0 if (same_out and same_in and same_code) else 1
    if a.cmd == "run" and os.path.realpath(a.out) == os.path.realpath(os.path.join(REPO, "output.csv")):
        print("REFUSED: run writes provisional artifacts; only export (strict) or candidate (uncertified) may write repo-root output.csv.", file=sys.stderr)
        return 2
    from ghostaudit.workflow import WorkflowConfig
    workflow_config = WorkflowConfig(min_margin=a.workflow_min_margin, scoring=a.workflow_scoring)
    ds, store, results = runner.run_dataset(a.data, a.requests, a.unknown_policy,
                                           workflow_mode=a.workflow_mode, workflow_config=workflow_config, decision_policy=a.decision_policy)
    pngs = [r for r in store.artifacts.values() if r.fmt == "png"]
    from ghostaudit.engine import PROOF_DEFAULTS
    cfg = {"data": os.path.relpath(a.data, REPO), "requests": a.requests, "unknown_policy": a.unknown_policy, "account_proof": PROOF_DEFAULTS,
           "workflow_mode": a.workflow_mode, "workflow_config": workflow_config.to_dict(), "decision_policy": a.decision_policy,
           "png_extraction": "complete" if all(r.status == "ok" for r in pngs) else "pending",
           "png_method": "hand-authored visual transcription bound by sha256, cross-checked against local OCR (code/ghostaudit/image_transcriptions)"}
    out = a.out if a.cmd == "run" else os.path.join(REPO, "runs", "export_candidate", "output.csv")
    if a.cmd in ("best-effort", "candidate"):
        out = os.path.join(REPO, "runs", "best_effort", "output.csv")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    runner.write_output(results, out)
    errs = ex.validate_output(ds, out)
    manifest = ex.build_manifest(["python3", "code/main.py"] + sys.argv[1:], cfg, ds, results, out, errs)
    if a.cmd in ("best-effort", "candidate"):
        os.makedirs(a.artifact_dir, exist_ok=True)
        writer = ex.write_candidate if a.cmd == "candidate" else ex.write_best_effort
        try:
            paths, reg = writer(ds, results, errs, manifest, a.artifact_dir)
        except ValueError as error:
            print(f"REFUSED: {error}", file=sys.stderr)
            return 2
        print("UNCERTIFIED output.csv CANDIDATE (all unresolved rows and validation errors preserved):" if a.cmd == "candidate" else
              "BEST-EFFORT REVIEW ARTIFACT (certified=false; not a submission, root output.csv untouched):")
        for p_ in paths.values():
            print("  ", os.path.relpath(p_, REPO))
        print(f"rows={len(results)}  contract_valid={manifest['contract_valid']} ({len(errs)} validation errors)  unresolved-register cases={len(reg)}")
        return 1 if a.cmd == "candidate" and errs else 0
    if a.cmd == "run":
        runner.write_diagnostics(results, a.diagnostics)
        mpath = os.path.splitext(a.out)[0] + ".manifest.json"
        ex.write_manifest(manifest, mpath)
        print(f"PROVISIONAL: wrote {len(results)} rows to {a.out}; manifest -> {mpath}; diagnostics -> {a.diagnostics}")
        print(f"policy={a.unknown_policy}  contract_valid={manifest['contract_valid']} ({len(errs)} validation errors)  undetermined cases={len(manifest['undetermined_cases'])}")
        if a.workflow_mode != "evidence":
            print("INFERENCE PREVIEW: certified=false; workflow assignments are hypotheses, not proven ownership. See diagnostics and manifest.")
        for k, v in runner.diagnostics(results).items():
            print(f"  {k}: {v}")
        return 0
    reasons = ex.gate(ds, results, out, manifest, a.allow_dirty, run_tests=not a.skip_tests, allow_plan_gaps=a.accept_plan_gaps)
    if reasons:
        print("EXPORT REFUSED. output.csv was NOT written.")
        for r in reasons:
            print("  -", r)
        return 1
    final = os.path.join(REPO, "output.csv")
    manifest["final"] = True
    manifest["certified"] = not bool(a.accept_plan_gaps and manifest["plan_gap_cases"])
    manifest["plan_gaps_accepted"] = bool(a.accept_plan_gaps and manifest["plan_gap_cases"])
    import shutil
    shutil.copyfile(out, final)
    ex.write_manifest(manifest, os.path.join(REPO, "output.manifest.json"))
    print(f"EXPORTED {final} (sha256 {manifest['output_sha256'][:16]}...) with output.manifest.json")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("coverage", "dump", "run", "explain", "export", "verify", "best-effort", "candidate"):
        p = sub.add_parser(name)
        p.add_argument("--data", default=os.path.join(REPO, "dataset"))
        if name in ("run", "explain", "export", "best-effort", "candidate"):
            p.add_argument("--requests", default="deletion_requests.csv")
    r = sub.choices["run"]
    r.add_argument("--out", default=os.path.join(REPO, "runs", "provisional", "output.csv"))
    r.add_argument("--diagnostics", default=os.path.join(REPO, "runs", "provisional", "diagnostics.json"))
    ex = sub.choices["export"]
    ex.add_argument("--allow-dirty", action="store_true")
    ex.add_argument("--accept-plan-gaps", action="store_true", help="export although some INCOMPLETE cases carry unresolved obligations (disclosed in the manifest)")
    ex.add_argument("--skip-tests", action="store_true", help="NOT allowed for a final export; for debugging the gate only")
    sub.choices["best-effort"].add_argument("--artifact-dir", default=REPO,
                                         help="directory for the three uncertified artifacts (use a temporary directory when testing fixtures)")
    sub.choices["candidate"].add_argument("--artifact-dir", default=REPO,
                                        help="directory for output.csv and its explicit validation/uncertainty sidecars")
    sub.choices["verify"].add_argument("manifest")
    sub.choices["explain"].add_argument("case_id")
    for name in ("run", "explain", "export", "best-effort", "candidate"):
        sub.choices[name].add_argument("--decision-policy", default="strict", choices=["strict", "submission"],
                                       help="submission: explicit risk, catalog-owner and snapshot-persistence predictions; never strict certification")
        sub.choices[name].add_argument("--unknown-policy", default="not_certified", choices=["not_certified", "certify_established"],
                                       help="status for cases with unresolved obligations (open decision P3)")
        sub.choices[name].add_argument("--workflow-mode", default="evidence", choices=["evidence", "joint"],
                                       help="joint: opt-in inference preview; never certifiable or exportable")
        sub.choices[name].add_argument("--workflow-min-margin", type=float, default=0.0,
                                       help="minimum counterfactual assignment-score margin (not a probability)")
        sub.choices[name].add_argument("--workflow-scoring", default="contextual_v3", choices=["contextual", "contextual_v2", "contextual_v3", "anchor"],
                                       help="contextual/contextual_v2 retain earlier previews; anchor omits reported-outcome agreement")
    sub.choices["candidate"].set_defaults(workflow_mode="joint", decision_policy="submission")
    d = sub.choices["dump"]
    d.add_argument("--audit-at")
    d.add_argument("--resource")
    d.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()
    if a.cmd in ("run", "export", "verify", "best-effort", "candidate"):
        sys.exit(manifest_commands(a))
    if a.cmd in ("run", "explain"):
        import json
        from ghostaudit import run as runner
        from ghostaudit.workflow import WorkflowConfig
        ds, store, results = runner.run_dataset(a.data, a.requests, a.unknown_policy, workflow_mode=a.workflow_mode,
                                                workflow_config=WorkflowConfig(min_margin=a.workflow_min_margin, scoring=a.workflow_scoring),
                                                decision_policy=a.decision_policy)
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
