"""Validates the subject-level account proof against the public samples. Gold answers are read ONLY to score it:
gold account state = 'present' if the answer reports a remaining account record, else 'absent'."""
import csv, json, os, sys
from collections import Counter
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
from ghostaudit.account_proof import account_proof  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402
from ghostaudit.data import load_dataset  # noqa: E402
from ghostaudit.identity import IdentityIndex  # noqa: E402
from ghostaudit.pipeline import build_store  # noqa: E402

allow_weak = "--weak" in sys.argv
ds = load_dataset(os.path.join(REPO, "dataset"), "sample_deletion_requests.csv")
store = build_store(ds)
ix = IdentityIndex(ds.identities, ds.audit_log)
gold = {r["case_id"]: json.loads(r["steps_json"]) for r in csv.DictReader(open(os.path.join(REPO, "dataset/sample_output.csv")))}
tab = Counter()
for r in ds.requests:
    subj = ix.resolve(r.email, r.audit_at)
    p = account_proof(CaseView(store, r.audit_at), subj, r.requested_at, allow_weak)
    g = "present" if any(s["system_id"] == "account_service" and s["operation"] == "REPORT_REMAINING_RECORD" for s in gold[r.case_id]) else "absent"
    tab[(g, p.status)] += 1
    if "-v" in sys.argv:
        print(r.case_id, "gold", g, "proof", p.status, p.evidence_id, {c: (e.status, e.evidence_id) for c, e in p.copies.items()})
print("weak scopes " + ("ALLOWED" if allow_weak else "ignored"), "| (gold account state, proof) -> count:", dict(sorted(tab.items())))
fa = sum(v for (g, p), v in tab.items() if g == "present" and p == "ABSENT")
print("FALSE ABSENCE (gold present, proof ABSENT):", fa)
