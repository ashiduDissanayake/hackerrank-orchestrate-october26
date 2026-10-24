"""Labeled evaluation: public samples (development/regression data) and frozen fixtures.

Only labeled data is scored here, so the numbers are accuracy figures. Fixture checks have two parts:
  output   exact match of status+steps for cases with a full label
  internal engine-agnostic expectations (links accepted/rejected, obligation verdicts, unresolved handling,
           forbidden citations); output-status expectations for UNDETERMINED cases are reported under 'policy'
           (open decision P3) instead of counting as engine failures.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)
sys.path.insert(0, HERE)
REPO = os.path.dirname(CODE)

import scoring  # noqa: E402
from ghostaudit import run as runner  # noqa: E402

FX = os.path.join(HERE, "fixtures", "synth_v1")


def as_pred(results):
    return {r.case_id: {"status": r.status, "steps": r.steps} for r in results}


def check_internal(res, exp):
    """Return (failures, policy_notes) for one fixture case."""
    fails, policy = [], []
    intent = exp.get("intent")
    if intent and (res.intent.deletion != (intent == "DELETION")):
        fails.append(f"intent {res.intent.deletion} expected {intent}")
    for rid in exp.get("links_accepted", []):
        if rid not in res.links:
            fails.append(f"link not accepted: {rid}")
    for rid in exp.get("links_rejected", []):
        if rid in res.links:
            fails.append(f"link wrongly accepted: {rid}")
    obs = {(o.resource_id or "subject_account"): o for o in res.obligations}
    for rid, want in exp.get("obligations", {}).items():
        o = obs.get(rid)
        verdict, _, reason = want.partition(":")
        if o is None:
            fails.append(f"no obligation for {rid}")
        elif o.verdict != verdict or (reason and o.reason != reason):
            fails.append(f"obligation {rid}: got {o.verdict}:{o.reason}, expected {want}")
    for u in exp.get("links_unresolved", []):
        got = [c[1] for ob in res.obligations for c in ob.detail.get("window_candidates", [])]
        if not set(u["candidates"]) <= set(got):
            fails.append(f"unresolved candidates {u['candidates']} not surfaced (got {got})")
    cited = {s["evidence_id"] for s in res.steps if s["evidence_id"]}
    for ev in exp.get("must_not_cite", []):
        if ev in cited:
            fails.append(f"cited forbidden evidence {ev}")
    if exp.get("status") == "UNDETERMINED":
        if res.internal != "UNDETERMINED":
            fails.append(f"internal status {res.internal}, expected UNDETERMINED")
        if res.status == "COMPLETE":
            policy.append("output status COMPLETE although obligations are unresolved (policy certify_established; never valid for export)")
        names = {o.resource_id for o in res.obligations if o.verdict == "UNKNOWN"} | {s["resource_id"] for s in res.steps}
        for bad in exp.get("must_not_emit", []):
            if bad.startswith("any step naming "):
                rid = bad.split()[-1]
                if rid in {s["resource_id"] for s in res.steps}:
                    fails.append(f"step emitted for unresolved {rid}")
    return fails, policy


POLICY = os.environ.get("UNKNOWN_POLICY", "not_certified")


def run_fixtures(verbose=True):
    ds, store, results = runner.run_dataset(FX, unknown_policy=POLICY)
    gold = {}
    for r in csv.DictReader(open(os.path.join(FX, "expected_output.csv"), encoding="utf-8")):
        gold[r["case_id"]] = {"status": r["deletion_status"], "steps": json.loads(r["steps_json"])}
    internal = json.load(open(os.path.join(FX, "expected_internal.json"), encoding="utf-8"))
    pred = as_pred(results)
    m = scoring.score(gold, pred)
    by_id = {r.case_id: r for r in results}
    n_fail = 0
    policy_notes = []
    for cid in sorted(internal):
        f, p = check_internal(by_id[cid], internal[cid])
        out_ok = (cid not in gold) or m["per_case"][cid]["exact"]
        ok = out_ok and not f
        n_fail += not ok
        policy_notes += [(cid, x) for x in p]
        if verbose:
            print(f"  {'PASS' if ok else 'FAIL'} {cid}" + ("" if out_ok else "  [output differs]") + "".join(f"\n        - {x}" for x in f))
    return m, n_fail, len(internal), policy_notes


def main():
    print(f"unresolved-obligation policy: {POLICY} (open decision P3)")
    print("== frozen fixtures (synth_v1) ==")
    m, n_fail, n, policy = run_fixtures()
    print(f"\ncases passing: {n - n_fail}/{n}  (labeled-output cases: {m['cases']})")
    print(scoring.summarize(m))
    for cid, p in policy:
        print(f"  policy note {cid}: {p}")
    print("\n== public samples (development/regression data, NOT an untouched holdout) ==")
    ds, store, results = runner.run_dataset(os.path.join(REPO, "dataset"), "sample_deletion_requests.csv", POLICY)
    gold = scoring.load_output(os.path.join(REPO, "dataset", "sample_output.csv"))
    ms = scoring.score(gold, as_pred(results))
    print(scoring.summarize(ms))
    gate_failures = n_fail
    if "--diff" in sys.argv:
        for cid, c in ms["per_case"].items():
            if c["exact"]:
                continue
            print(f"\n{cid}: gold={c['status_gold']} pred={c['status_pred']} lcs={c['lcs']}")
            for s in c["missing"]:
                print("  MISSING", s["phase"][:4], s["system_id"], s["resource_id"], s["operation"], s["evidence_id"])
            for s in c["extra"]:
                print("  EXTRA  ", s["phase"][:4], s["system_id"], s["resource_id"], s["operation"], s["evidence_id"])
            for s, f, v in c["wrong_fields"]:
                print(f"  WRONG {f}: gold={s[f]!r} pred={v!r} for {s['phase'][:4]} {s['system_id']} {s['resource_id']} {s['operation']}")
    # gate: every frozen fixture must pass; the samples are development data and report-only
    if gate_failures:
        print(f"\nGATE FAILED: {gate_failures} fixture case(s) failed")
        return 1
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(rc or 0)
