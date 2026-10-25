"""Fills the AUTO blocks of code/evaluation/evaluation_report.md and usage_report.md from the actual evaluation and the
run manifest, so the reports can never drift from the run they describe.

  python3 scripts/write_reports.py            # re-run the provisional run and the best-effort artifact, then update both reports
  python3 scripts/write_reports.py --check    # exit 1 if the reports are out of date OR the cached run manifest is stale (used by the packaging check)

The reports must describe the run that produced the CSV, never a cached manifest from older code: in write mode the provisional run is ALWAYS
regenerated first; in check mode a manifest whose code or input hashes differ from the current tree is reported as stale.

A block looks like  <!--AUTO:name-->  ...  <!--/AUTO:name-->  and is replaced wholesale. Everything outside the blocks is
hand-written narrative. The reports are the single authoritative copies; scripts/package.py generates the packaging copy.
"""
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = os.path.join(REPO, "code")
sys.path.insert(0, CODE)
sys.path.insert(0, os.path.join(CODE, "evaluation"))

import labeled  # noqa: E402
import scoring  # noqa: E402
from ghostaudit import export as ex  # noqa: E402
from ghostaudit import run as runner  # noqa: E402

EVAL = os.path.join(CODE, "evaluation", "evaluation_report.md")
USAGE = os.path.join(CODE, "evaluation", "usage_report.md")
MANIFEST = os.path.join(REPO, "runs", "provisional", "output.manifest.json")
CANDIDATE_MANIFEST = os.path.join(REPO, "output.manifest.json")
REGISTER = os.path.join(REPO, "output_best_effort.unresolved.json")
FX = labeled.FX


def fmt_metrics(m):
    f = m["field_accuracy"]
    return "\n".join([
        "| metric | value |", "|---|---|",
        f"| cases | {m['cases']} |",
        f"| status accuracy | {m['status_accuracy']:.4f} ({round(m['status_accuracy'] * m['cases'])}/{m['cases']}) |",
        f"| step precision / recall / F1 (strict: all six fields incl. evidence_id) | {m['step_strict']['precision']:.4f} / {m['step_strict']['recall']:.4f} / {m['step_strict']['f1']:.4f} |",
        f"| step precision / recall / F1 (lenient: ignores evidence_id) | {m['step_lenient']['precision']:.4f} / {m['step_lenient']['recall']:.4f} / {m['step_lenient']['f1']:.4f} |",
        f"| alignment coverage (gold steps with a prediction on the same phase/system/resource/operation) | {m['alignment_coverage']:.4f} |",
        f"| field accuracy on aligned steps: state / evidence_id | {f['state']:.4f} / {f['evidence_id']:.4f} |",
        f"| evidence accuracy (gold steps that cite evidence and got the same citation) | {m['evidence_accuracy']:.4f} |",
        f"| sequence: exact-array match rate | {m['sequence_exact_rate']:.4f} |",
        f"| sequence: mean normalized LCS | {m['sequence_mean_lcs']:.4f} |",
        f"| status confusion (gold->predicted) | {', '.join(f'{k}: {v}' for k, v in m['confusion'].items())} |"])


def block_fixtures():
    m, n_fail, n, policy = labeled.run_fixtures(verbose=False)
    return (f"Fixture set `{os.path.basename(FX)}` (frozen, hash-guarded): {n - n_fail}/{n} cases pass all checks "
            f"({m['cases']} have a complete labeled answer scored below; the rest are labeled by internal expectations because their correct "
            f"output is an UNKNOWN state).\n\n" + fmt_metrics(m))


def sample_results(policy):
    ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"), "sample_deletion_requests.csv", policy)
    gold = scoring.load_output(os.path.join(REPO, "dataset", "sample_output.csv"))
    return scoring.score(gold, labeled.as_pred(results))


def block_samples():
    a, b = sample_results("not_certified"), sample_results("certify_established")
    ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"), "sample_deletion_requests.csv")
    und = [r.case_id for r in results if r.internal == "UNDETERMINED"]
    tail = ("With the subject-level account proof in place the two policies coincide on the public samples, because no public-sample case "
            "is left unresolved." if not und else f"{len(und)} public-sample cases are UNDETERMINED ({', '.join(und)}), which is where the two policies differ.")
    return ("Default policy `not_certified` (an unresolved obligation can never become COMPLETE):\n\n" + fmt_metrics(a) +
            "\n\nOpt-in ablation `certify_established` (NOT exportable; shown only to quantify what refusing to certify costs): "
            f"status accuracy {b['status_accuracy']:.4f}, strict step F1 {b['step_strict']['f1']:.4f}. " + tail)


def block_workflow():
    from evaluation.workflow_eval import measure, markdown
    return markdown(measure(os.path.join(REPO, "dataset")))


def block_eval():
    ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"))
    c = Counter(r.status for r in results)
    i = Counter(r.internal for r in results)
    reasons = Counter(o.reason for r in results for o in r.obligations)
    unresolved = {}
    for r in results:
        if r.internal == "UNDETERMINED":
            for o in r.obligations:
                if o.verdict == "UNKNOWN":
                    unresolved.setdefault(o.reason, []).append(r.case_id)
    lines = [f"Evidence-only default statuses on the {len(results)} evaluation requests (a diagnostic, NOT accuracy: there are no labels): "
             + ", ".join(f"{k} {v}" for k, v in sorted(c.items())) + ".",
             f"Internal states: " + ", ".join(f"{k} {v}" for k, v in sorted(i.items())) + ".", "",
             "Obligation verdicts by reason (counts of obligations, all cases):", "", "| reason | count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])]
    lines += ["", "Cases that remain UNDETERMINED (no violation established, at least one obligation unresolved), grouped by the unresolved reason:", "",
              "| unresolved reason | cases |", "|---|---|"]
    lines += [f"| {k} | {', '.join(v)} |" for k, v in sorted(unresolved.items())]
    return "\n".join(lines)


def block_manifest():
    path = CANDIDATE_MANIFEST if os.path.exists(CANDIDATE_MANIFEST) else MANIFEST
    m = json.load(open(path))
    g = m["git"]
    return "\n".join([
        "| field | value |", "|---|---|",
        f"| command | `{' '.join(m['command'])}` |",
        f"| configuration | `{json.dumps(m['config'], sort_keys=True)}` |",
        f"| producing commit (HEAD when the run was made) | `{(g['commit'] or 'none')[:12]}` |",
        f"| prediction-affecting files differing from that commit | {len(g.get('dirty_code_files', [])) or 'none'} (the code hash below identifies the exact code either way) |",
        f"| other uncommitted files at run time (reports, docs, tests, packaging; cannot change the output) | {len([f for f in g['dirty_files'] if f not in g.get('dirty_code_files', [])])} |",
        f"| output.csv sha256 | `{m['output_sha256']}` |",
        f"| code sha256 ({m.get('code_files', '?')} files: all of code/ghostaudit incl. image transcriptions, main.py, requirements) | `{m['code_sha256']}` |",
        f"| input files hashed | {len(m['inputs_sha256'])} (dataset csv + evidence); combined listing in the manifest |",
        f"| rows | {m['rows']} |", f"| statuses | {m['status_counts']} |",
        f"| contract-valid | {m['contract_valid']} ({m['validation_error_count']} validation errors) |",
        f"| UNDETERMINED cases | {len(m['undetermined_cases'])}: {', '.join(m['undetermined_cases'])} |",
        f"| runtime model calls | {m.get('runtime_model_calls', 'n/a')} |", f"| final (exported) | {m['final']} |"])


def block_candidate():
    m = json.load(open(CANDIDATE_MANIFEST))
    return (f"The explicit `candidate` command writes repository-root `output.csv`, `output.manifest.json` and `output.unresolved.json`. "
            f"The CSV contains {m['rows']} data rows and the required three columns. Its manifest records `kind=submission_candidate`, "
            f"`certified=false`, {m['validation_error_count']} semantic validation errors, {len(m['undetermined_cases'])} undetermined statuses "
            f"({', '.join(m['undetermined_cases'])}), and {len(m['plan_gap_cases'])} established INCOMPLETE cases with unresolved plan items. "
            "No unknown obligation was turned into a finding to clear validation. This file is a disclosed candidate and is not fully contract-conforming while those errors remain. "
            "The certification label belongs to this implementation; it is not a HackerRank credential. "
            "`code/docs/WORKFLOW_GAPS.md` lists every remaining public-sample discrepancy and its exact evidence requirement.")


def block_samples_validity():
    ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"), "sample_deletion_requests.csv")
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, "o.csv")
        runner.write_output(results, out)
        errs = ex.validate_output(ds, out)
    if not errs:
        return "The 32 public-sample rows all pass the contract validator."
    return (f"Contract validation of the 32 public-sample rows: {len(errs)} errors. "
            "Each is a COMPLETE row with zero steps: the subject's only gold steps are an account-absence verification (account resource id never linked to the "
            "subject) and an anonymized analytics record, and no retained audit record exists to cite, so the row has nothing the evidence lets the engine name. "
            "A COMPLETE row needs at least one verification step, so the contract validator rejects it.\n\n" + "\n".join(f"* {e}" for e in errs))


def block_best_effort():
    reg = json.load(open(REGISTER, encoding="utf-8"))["unresolved_cases"]
    det = [e for e in reg if not e["status_determined"]]
    part = [e for e in reg if e["status_determined"]]
    total = sum(json.load(open(MANIFEST))["status_counts"].values())
    lines = [f"`python3 code/main.py best-effort` writes `output_best_effort.csv` (all {total} rows), "
             "`output_best_effort.unresolved.json` and `output_best_effort.manifest.json` (`certified: false`, every validation error). It is a review artifact, never the submission.", "",
             f"**{len(det)} cases whose status rests on an unresolved obligation** (the row is contract-invalid by construction):", "",
             "| case | missing fact |", "|---|---|"]
    for e in det:
        for u in e["unresolved"]:
            lines.append(f"| {e['case_id']} | {u['information_gap'].replace('|', '/')} |")
    lines += ["", f"**{len(part)} cases that are INCOMPLETE on established violations** and also carry an unresolved obligation (the plan may be missing the unresolved items): "
              + ", ".join(e["case_id"] for e in part) + "."]
    return "\n".join(lines)


def block_proof_stats():
    ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"))
    proofs = [(r, o) for r in results for o in r.obligations if o.reason == "no_profile_for_subject_in_snapshot"]
    promoted = [r.case_id for r, o in proofs if any("subject_in_source" in v[3] for v in o.detail["copies"].values())]
    excl = [(r, o) for r, o in proofs if o.detail.get("excluded_copies")]
    declared_only = [r.case_id for r, o in proofs if all(v[3] == "declared" for v in o.detail["copies"].values())]
    lines = [f"Subject-level discharges in the real run: {len(proofs)} of {len(results)} requests (plus {sum(1 for r in results for o in r.obligations if o.reason == 'account_deleted_per_tombstone')} by a DELETED tombstone).",
             f"* proofs whose latest primary or replica capture is a **weakly scoped document export promoted per source** (it holds the subject's own records and exports profile rows): {len(promoted)}",
             f"* proofs that exclude at least one replica whose latest capture predates the request and shows attributable rows without the subject: {len(excl)}"
             + (f" ({', '.join(r.case_id for r, _ in excl)}); of these COMPLETE: {', '.join(r.case_id for r, _ in excl if r.internal == 'COMPLETE') or 'none'}" if excl else ""),
             f"* proofs of which every copy used is a declared capture: {len(declared_only)}"]
    return "\n".join(lines)


def block_sensitivity():
    r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "sensitivity_account_proof.py")], capture_output=True, text=True, cwd=REPO)
    return "```text\n" + r.stdout.strip() + "\n```"


def block_fixture_cases():
    exp = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(FX, "expected_output.csv"), encoding="utf-8"))}
    internal = json.load(open(os.path.join(FX, "expected_internal.json"), encoding="utf-8"))
    out = []
    for cid in ("fx_case_05", "fx_case_16", "fx_case_22", "fx_case_23", "fx_case_25", "fx_case_26", "fx_case_28", "fx_case_29", "fx_case_30", "fx_case_32", "fx_case_34"):
        out.append(f"**{cid}** expected: `{exp[cid]['deletion_status'] if cid in exp else 'UNDETERMINED (internal expectation only)'}`")
        if cid in exp:
            out += ["", "```json", json.dumps(json.loads(exp[cid]["steps_json"]), indent=1, sort_keys=True), "```"]
        else:
            out += ["", "```json", json.dumps(internal[cid], indent=1, sort_keys=True, ensure_ascii=False), "```"]
        out.append("")
    return "\n".join(out)


BLOCKS = {"fixtures": block_fixtures, "samples": block_samples, "workflow": block_workflow, "candidate": block_candidate, "samples_validity": block_samples_validity, "eval": block_eval,
          "manifest": block_manifest, "best_effort": block_best_effort, "proof_stats": block_proof_stats, "sensitivity": block_sensitivity, "fixture_cases": block_fixture_cases}


def fill(path, text_blocks):
    s = open(path, encoding="utf-8").read()
    for name, text in text_blocks.items():
        pat = re.compile(rf"(<!--AUTO:{name}-->)(.*?)(<!--/AUTO:{name}-->)", re.S)
        if not pat.search(s):
            continue
        s = pat.sub(lambda m: f"{m.group(1)}\n{text}\n{m.group(3)}", s)
    return s


def manifest_stale():
    """True if the cached provisional manifest does not describe the current code and inputs."""
    if not os.path.exists(MANIFEST) or not os.path.exists(REGISTER):
        return True
    paths = [MANIFEST, CANDIDATE_MANIFEST]
    code, inputs = ex.code_hash(), ex.input_hashes(os.path.join(REPO, "dataset"))
    return any(not os.path.exists(path) or (lambda m: m.get("code_sha256") != code or m.get("inputs_sha256") != inputs)(json.load(open(path))) for path in paths)


def main():
    check = "--check" in sys.argv
    if check and manifest_stale():
        print("STALE: runs/provisional/output.manifest.json (or the best-effort register) does not describe the current code/inputs; run python3 scripts/write_reports.py")
        sys.exit(1)
    if not check:    # the reports must describe the run that produced the CSV: always regenerate it
        for cmd in ("run", "best-effort", "candidate"):
            subprocess.check_call([sys.executable, os.path.join(CODE, "main.py"), cmd], cwd=REPO, stdout=subprocess.DEVNULL)
    blocks = {k: f() for k, f in BLOCKS.items()}
    stale = []
    for path in (EVAL, USAGE):
        new = fill(path, blocks)
        old = open(path, encoding="utf-8").read()
        if new != old:
            stale.append(os.path.relpath(path, REPO))
            if not check:
                open(path, "w", encoding="utf-8").write(new)
    if check:
        print("reports up to date" if not stale else f"STALE: {stale}")
        sys.exit(1 if stale else 0)
    print("updated:", stale or "nothing changed")


if __name__ == "__main__":
    main()
