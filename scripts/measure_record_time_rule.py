"""Measurement ONLY (open decision P9, never the default): what would the strict dual-time rule cost if admissibility used only the
record's own observation time (observed_at <= audit_at) and ignored the artifact capture time?  The contract forbids evidence
captured after audit_at, and user decision U11 keeps the strict rule; this quantifies the cost so the decision is informed.
Public sample answers are used only to score. Scopes (which carry artifact time) are left strict, so this is a lower bound.
  python3 scripts/measure_record_time_rule.py"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "code"))
sys.path.insert(0, os.path.join(REPO, "code", "evaluation"))
import scoring  # noqa: E402
from ghostaudit import run as runner  # noqa: E402
from ghostaudit.caseview import CaseView  # noqa: E402


class RecordTimeView(CaseView):
    def _ok(self, o):
        return o.observed_at <= self.audit_at


DS = os.path.join(REPO, "dataset")
gold = scoring.load_output(os.path.join(DS, "sample_output.csv"))
for label, kw in (("strict dual-time (production)", {}), ("record time only (P9, measurement)", {"view_cls": RecordTimeView})):
    _, _, res = runner.run_dataset(DS, "sample_deletion_requests.csv", **kw)
    m = scoring.score(gold, {r.case_id: {"status": r.status, "steps": r.steps} for r in res})
    s = m["step_strict"]
    print(f"{label:<40} status {m['status_accuracy']:.4f}  TP/FP/FN {s['tp']}/{s['fp']}/{s['fn']}  P/R/F1 {s['precision']:.4f}/{s['recall']:.4f}/{s['f1']:.4f}  exact {sum(c['exact'] for c in m['per_case'].values())}/32")
for label, kw in (("strict dual-time (production)", {}), ("record time only (P9, measurement)", {"view_cls": RecordTimeView})):
    _, _, res = runner.run_dataset(DS, "deletion_requests.csv", **kw)
    from collections import Counter
    print(f"eval {label:<36} internal {dict(sorted(Counter(r.internal for r in res).items()))}")
