"""Scoring of predicted output against labeled answers.

Only labeled data (public samples, labeled fixtures) may be scored with this module; the
numbers it produces are accuracy figures. Unlabeled cases get diagnostics elsewhere.

Metrics
  status          accuracy + confusion matrix
  step P/R/F1     micro-averaged over cases on the multiset of full step tuples
                  (phase, system_id, resource_id, operation, state, evidence_id); the
                  lenient variant drops evidence_id to isolate citation errors
  fields          for steps aligned on (phase, system_id, resource_id, operation) within a
                  case: accuracy of state and evidence_id; alignment coverage is reported
  evidence        among gold steps with a non-empty evidence_id: fraction whose aligned
                  prediction carries the same evidence_id
  sequence        exact-array match rate (all fields incl. step_no) and mean normalized LCS
                  over step tuples, 2*LCS/(len_gold+len_pred); both-empty counts as 1
"""
import csv
import json
from collections import Counter, defaultdict

FULL = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")
LENIENT = ("phase", "system_id", "resource_id", "operation", "state")
ALIGN = ("phase", "system_id", "resource_id", "operation")


def load_output(path):
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                steps = json.loads(r["steps_json"])
            except json.JSONDecodeError:
                steps = None
            out[r["case_id"]] = {"status": r["deletion_status"], "steps": steps}
    return out


def _t(step, fields):
    return tuple(step.get(f) for f in fields)


def _lcs(a, b):
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, start=1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn}


def score(gold, pred):
    """gold/pred: {case_id: {"status":..., "steps":[...]}}. Missing/invalid predictions count as empty."""
    cases = sorted(gold)
    confusion = Counter()
    strict = Counter()
    lenient = Counter()
    aligned = 0
    gold_steps = 0
    field_ok = Counter()
    ev_total = 0
    ev_ok = 0
    exact = 0
    lcs_sum = 0.0
    per_case = {}

    for cid in cases:
        g = gold[cid]
        p = pred.get(cid) or {"status": "MISSING", "steps": []}
        psteps = p["steps"] if isinstance(p["steps"], list) else []
        gsteps = g["steps"]
        confusion[(g["status"], p["status"])] += 1

        for counter, fields in ((strict, FULL), (lenient, LENIENT)):
            gc = Counter(_t(s, fields) for s in gsteps)
            pc = Counter(_t(s, fields) for s in psteps)
            tp = sum((gc & pc).values())
            counter["tp"] += tp
            counter["fp"] += sum(pc.values()) - tp
            counter["fn"] += sum(gc.values()) - tp

        pmap = defaultdict(list)
        for s in psteps:
            pmap[_t(s, ALIGN)].append(s)
        missing_steps = []
        wrong = []
        for s in gsteps:
            gold_steps += 1
            cand = pmap.get(_t(s, ALIGN))
            if s["evidence_id"]:
                ev_total += 1
            if not cand:
                missing_steps.append(s)
                continue
            q = cand.pop(0)
            aligned += 1
            for f in ("state", "evidence_id"):
                if q.get(f) == s.get(f):
                    field_ok[f] += 1
                else:
                    wrong.append((s, f, q.get(f)))
            if s["evidence_id"] and q.get("evidence_id") == s["evidence_id"]:
                ev_ok += 1
        extra_steps = [s for lst in pmap.values() for s in lst]

        is_exact = g["status"] == p["status"] and gsteps == psteps
        exact += is_exact
        gt = [_t(s, FULL) for s in gsteps]
        pt = [_t(s, FULL) for s in psteps]
        if not gt and not pt:
            lcs_ratio = 1.0
        else:
            lcs_ratio = 2 * _lcs(gt, pt) / (len(gt) + len(pt))
        lcs_sum += lcs_ratio
        per_case[cid] = {
            "status_gold": g["status"], "status_pred": p["status"], "exact": is_exact,
            "lcs": round(lcs_ratio, 4), "missing": missing_steps, "extra": extra_steps,
            "wrong_fields": wrong,
        }

    n = len(cases)
    return {
        "cases": n,
        "status_accuracy": sum(v for (a, b), v in confusion.items() if a == b) / n if n else 1.0,
        "confusion": {f"{a}->{b}": v for (a, b), v in sorted(confusion.items())},
        "step_strict": _prf(strict["tp"], strict["fp"], strict["fn"]),
        "step_lenient": _prf(lenient["tp"], lenient["fp"], lenient["fn"]),
        "alignment_coverage": aligned / gold_steps if gold_steps else 1.0,
        "field_accuracy": {f: field_ok[f] / aligned if aligned else 1.0 for f in ("state", "evidence_id")},
        "evidence_accuracy": ev_ok / ev_total if ev_total else 1.0,
        "sequence_exact_rate": exact / n if n else 1.0,
        "sequence_mean_lcs": lcs_sum / n if n else 1.0,
        "per_case": per_case,
    }


def summarize(m):
    lines = [
        f"cases                 {m['cases']}",
        f"status accuracy       {m['status_accuracy']:.4f}",
        f"step strict  P/R/F1   {m['step_strict']['precision']:.4f} / {m['step_strict']['recall']:.4f} / {m['step_strict']['f1']:.4f}",
        f"step lenient P/R/F1   {m['step_lenient']['precision']:.4f} / {m['step_lenient']['recall']:.4f} / {m['step_lenient']['f1']:.4f}",
        f"alignment coverage    {m['alignment_coverage']:.4f}",
        f"field accuracy        state {m['field_accuracy']['state']:.4f}  evidence_id {m['field_accuracy']['evidence_id']:.4f}",
        f"evidence accuracy     {m['evidence_accuracy']:.4f}",
        f"sequence exact rate   {m['sequence_exact_rate']:.4f}",
        f"sequence mean LCS     {m['sequence_mean_lcs']:.4f}",
        f"confusion             {m['confusion']}",
    ]
    return "\n".join(lines)
