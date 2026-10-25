# Workflow follow-up: measured gain and remaining boundaries

Producing code: `ab3bd22d53e878adec5da2f4b7c56bf7da2ca8a9` (following `f342c2181f27dd3c1710da175f03c915b72e00b1`). No paid model API calls were made. The evidence-only default and its prediction CSV are unchanged.

## Public development results

| Measure | Evidence default | Optional joint preview |
|---|---:|---:|
| Correct statuses | 32/32 | 32/32 |
| Exact complete answers | 10/32 | 17/32 |
| Matching / extra / missing steps | 159 / 0 / 34 | 172 / 0 / 21 |
| Step precision / recall / F1 | 1.0000 / 0.8238 / 0.9034 | 1.0000 / 0.8912 / 0.9425 |
| Schema validation errors | 3 | 0 |

These are public examples used for development and threshold selection, not an independent test or hidden challenge accuracy. A zero-margin variant gives 18 exact answers but adds an incorrect step, so it is not the default. The result comes from inferred ownership, not newly discovered proof. It cannot pass strict export.

## Full 518-request artifacts

| Measure | Evidence default | Optional joint preview |
|---|---:|---:|
| Output COMPLETE / INCOMPLETE / NOT_APPLICABLE | 147 / 361 / 10 | 152 / 356 / 10 |
| Status undetermined internally | 8 | 3 |
| Established INCOMPLETE with unresolved plan items | 18 | 19 |
| Cases with unresolved obligations | 26 | 22 |
| Schema validation errors | 8 | 3 |
| Certified | false | false |

These counts are diagnostics, not accuracy. The preview records 225 inferred links across 204 cases and changes 197 CSV rows. Its five output-status changes are case_183, case_343, case_524, case_530 and case_532, conditionally COMPLETE under inferred ownership. That inference remains unproven. The three undetermined cases are case_55 (account and restore state), case_63 (marketing identity conflict), and case_345 (account coverage). Other unknown obligations still leave 19 remediation plans open. No post-audit evidence or arbitrary source precedence was introduced.

Root artifacts:

- `output_best_effort.csv` and its manifest/register: unchanged evidence-mode predictions; uncertified.
- `output_workflow_preview.csv`: 518 experimental rows; SHA-256 `6b4b15bc3f9b37ef369a52b9e22c39e228deca09f9b027a4b950ff4a819c9897`.
- `output_workflow_preview.manifest.json`: mode, assumptions, all inferred links and margins, producing commit and input/code/output hashes; `certified=false`.
- `output_workflow_preview.unresolved.json`: exact missing facts and validation errors for the preview's 22 unresolved cases.

No certified root `output.csv` exists. Neither review CSV is a claim that the required evidence-backed submission is complete.

## Reproduce and investigate

```bash
python3 code/main.py run
python3 code/main.py best-effort
python3 code/main.py run --workflow-mode joint --out output_workflow_preview.csv --diagnostics runs/workflow_preview/diagnostics.json
python3 code/main.py verify output_workflow_preview.manifest.json
python3 code/main.py explain case_345 --workflow-mode joint
python3 scripts/evaluate_workflow.py
python3 code/evaluation/main.py all
python3 scripts/write_reports.py
python3 scripts/package.py --verify
```

The explain output retains candidate rankings, competitor requests, alternative assignment scores and rejected low-margin matches. Margins are heuristic score differences, not calibrated probabilities. Additional independent controls cover assignment versus greedy matching, ties, identity conflicts, future evidence, unsupported success claims, stale profile snapshots and export boundaries. Existing frozen fixtures remain untouched. Python 3.12 was used for this follow-up; no new Python 3.14 validation is claimed.

Remaining work is evidentiary: establish ownership with an admissible identifier, lookup, catalog or source-reference chain for inferred resources; resolve the three undetermined cases and the 19 plan gaps with actual evidence; and obtain organizer clarification where the supplied artifacts cannot support an answer. Do not convert a preview hypothesis into certified evidence to clear a gate.
