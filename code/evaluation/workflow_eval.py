"""Evaluation only: public-label comparison of the optional workflow experiment.

Prediction code never imports this module. All variants are development/sensitivity
measurements; no hidden-set accuracy or calibrated confidence is claimed.
"""
import os
import tempfile

from ghostaudit import export, run
from ghostaudit.workflow import WorkflowConfig
from .scoring import load_output, score

VARIANTS = (
    ("Evidence baseline", "evidence", WorkflowConfig()),
    ("Joint preview (default margin)", "joint", WorkflowConfig()),
    ("Joint preview (no positive margin floor)", "joint", WorkflowConfig(min_margin=0)),
    ("Anchor-only control", "joint", WorkflowConfig(scoring="anchor")),
)


def measure(root):
    records = []
    for name, mode, cfg in VARIANTS:
        ds, store, results = run.run_dataset(root, "sample_deletion_requests.csv", workflow_mode=mode, workflow_config=cfg)
        # Labels are consulted only after candidate selection and state evaluation finish.
        metrics = score(load_output(os.path.join(root, "sample_output.csv")),
                        {r.case_id: {"status": r.status, "steps": r.steps} for r in results})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "output.csv")
            run.write_output(results, path)
            errors = export.validate_output(ds, path)
        records.append({"name": name, "mode": mode, "config": cfg.to_dict(), "metrics": metrics,
                        "validation_errors": errors,
                        "inferences": {r.case_id: r.workflow_inferences for r in results if r.workflow_inferences}})
    return records


def markdown(records):
    lines = ["Public samples are development data. The margin was selected after examining public development results. "
             "These figures do not establish hidden accuracy or calibrated confidence.", "",
             "| Variant | Status | Exact full answers | TP / FP / FN | Step P / R / F1 | Validation errors |",
             "|---|---:|---:|---|---|---:|"]
    for r in records:
        m, s = r["metrics"], r["metrics"]["step_strict"]
        n = m["cases"]
        lines.append(f"| {r['name']} | {round(m['status_accuracy']*n)}/{n} | {sum(d['exact'] for d in m['per_case'].values())}/{n} | "
                     f"{s['tp']} / {s['fp']} / {s['fn']} | {s['precision']:.4f} / {s['recall']:.4f} / {s['f1']:.4f} | {len(r['validation_errors'])} |")
    lines += ["", "The joint mode proposes ownership from a partial maximum-weight assignment. It never uses workflow results as record-state proof. "
              "All such runs and their links are marked uncertified, retain alternative candidates and margins, and cannot pass `export`. "
              "Schema validity does not establish evidence validity. The evidence baseline remains the default.", "",
              "Default settings: 90 minutes before / 10 minutes after reported_at; minimum counterfactual score margin 0.25; "
              "one additional orphan per system/request and one request per orphan within a competing component. These are modelling assumptions, not supplied guarantees. "
              "A score margin is not a probability."]
    return "\n".join(lines)
