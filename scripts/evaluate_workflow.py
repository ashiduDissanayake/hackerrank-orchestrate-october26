"""Regenerate the workflow experiment's Markdown report and machine-readable development measurements."""
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "code"))
from evaluation.workflow_eval import measure, markdown  # noqa: E402


def main():
    records = measure(str(REPO / "dataset"))
    report = REPO / "code/evaluation/workflow_report.md"
    lines = ["# Workflow attribution experiment", "", markdown(records), "", "## Default-preview proposals", "",
             "The sources below support the candidate operation and the independently assessed state; the ownership relation remains an inference.", "",
             "| Case | Proposed resource | Activity | Assignment-score margin |", "|---|---|---|---:|"]
    for cid, props in records[1]["inferences"].items():
        for p in props:
            lines.append(f"| {cid} | {p['resource_id']} | {p['activity_id']} | {p['margin']:.6f} |")
    lines += ["", "## Remaining default-preview differences", "",
              "| Case | Missing resources | Extra resources |", "|---|---|---|"]
    for cid, d in records[1]["metrics"]["per_case"].items():
        if not d["exact"]:
            lines.append(f"| {cid} | {', '.join(s['resource_id'] for s in d['missing']) or 'none'} | {', '.join(s['resource_id'] for s in d['extra']) or 'none'} |")
    lines += ["", "## Independent synthetic controls", "",
              "These are fictional counterexamples in `code/tests/test_workflow.py`, not public-answer labels.", "",
              "1. **Ambiguous ownership:** Rui and Mina submit equally timed requests, and one anonymous account operation fits both equally. "
              "Expected: both abstain, including after request shuffling and case-ID renaming.", "",
              "2. **Global assignment:** request A scores resource X at 4 and Y at 3; request B scores X at 3.9 and has no Y edge. "
              "Expected: A gets Y and B gets X (total 6.9), with a real counterfactual margin; independent greedy assignment fails. "
              "The solver is also checked against exhaustive enumeration on 35 fixed-seed small graphs.", "",
              "3. **Claim without state:** a lone operation reports SUCCESS but there is no admissible account state or profile coverage. "
              "Expected: the ownership hypothesis may be recorded, the account remains UNKNOWN, and no absent-record verification is fabricated.", "",
              "4. **Temporal trap:** another person's account evidence is captured after the audit while its inner time is earlier. "
              "Expected: it cannot change the earlier assignment. Future requests and events are also excluded.", "",
              "5. **Export boundary:** a hypothesis plus an independent complete profile snapshot can produce a structurally valid candidate row. "
              "Expected: strict export still refuses it, even if its configuration is falsified as evidence-only. `run --out <repo>/output.csv` also refuses.", "",
              "## Other fixes in this pass", "",
              "- A source-reference cycle whose only identity root is rejected is removed by rooted reachability; a cycle with an independent valid root survives.",
              "- Evidence captured before an earlier request began cannot be assigned to that earlier request's investigation window.",
              "- The best-effort CLI accepts an artifact directory. Its fixture test uses a temporary directory and verifies that root prediction artifacts are unchanged.",
              "", "All runtime variants make zero model API calls. Coding-session usage is not available here and is not estimated.", ""]
    report.write_text("\n".join(lines), encoding="utf-8")
    output = REPO / "runs/workflow_evaluation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(markdown(records))
    print(f"Report: {report.relative_to(REPO)}; details: {output.relative_to(REPO)}")


if __name__ == "__main__":
    main()
