"""Sensitivity of the subject-level account proof to its optional switches. Prints counts only; the default
(strong scopes only, empty tables allowed) is what the engine uses. Gold answers are used to score the samples only."""
import csv, json, os, sys
from collections import Counter
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
sys.path.insert(0, os.path.join(REPO, "code", "evaluation"))
import scoring  # noqa: E402
from ghostaudit.data import load_dataset  # noqa: E402
from ghostaudit.engine import audit_case  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.pipeline import build_store  # noqa: E402
from ghostaudit.run import earlier_requests_by_case  # noqa: E402

VARIANTS = [("default (strong scopes, empty tables allowed)", dict()), ("+ weak scopes (inferred_from_rows)", dict(allow_weak=True)),
            ("+ require an account row in the artifact", dict(require_row=True)), ("weak + require_row", dict(allow_weak=True, require_row=True)),
            ("no exclusion on pre-request-only copy captures", dict(pre_request_exclusion=False)),
            ("no per-source promotion of weak document exports", dict(weak_promotion=False)),
            ("no request-episode scoping (carried-over evidence stays in scope)", dict(episode_scoping=False))]
for reqfile, label in (("sample_deletion_requests.csv", "samples (development data)"), ("deletion_requests.csv", "eval (unlabeled diagnostics)")):
    ds = load_dataset(os.path.join(REPO, "dataset"), reqfile)
    store = build_store(ds)
    ix = IdentityIndex(ds.identities, ds.audit_log)
    earlier = earlier_requests_by_case(ds, ix)
    gold = {}
    if "sample" in reqfile:
        gold = {r["case_id"]: json.loads(r["steps_json"]) for r in csv.DictReader(open(os.path.join(REPO, "dataset/sample_output.csv")))}
    print(f"== {label}")
    for name, kw in VARIANTS:
        c = Counter(); fa = 0; preds = {}
        for r in ds.requests:
            res = audit_case(r, store, ix, ds.rules, earlier_requests=earlier[r.case_id], **kw)
            c[res.internal] += 1
            preds[r.case_id] = {"status": res.status, "steps": res.steps}
            if gold:
                present = any(s["system_id"] == "account_service" and s["operation"] == "REPORT_REMAINING_RECORD" for s in gold[r.case_id])
                fa += present and any(o.category == "USER_PROFILE" and o.verdict == "COMPLIANT" for o in res.obligations)
        extra = ""
        if gold:
            m = scoring.score(scoring.load_output(os.path.join(REPO, "dataset/sample_output.csv")), preds)
            st = m["step_strict"]
            extra = f"  false-absence vs gold: {fa}; strict TP/FP/FN {st['tp']}/{st['fp']}/{st['fn']}, exact {sum(x['exact'] for x in m['per_case'].values())}/32"
        print(f"   {name:<48} {dict(sorted(c.items()))}" + extra)
