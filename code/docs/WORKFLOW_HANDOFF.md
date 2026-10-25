# Workflow follow-up: current output and remaining evidence requirements

Producing code: `488c0e78fadb349701093b3ad6baf0fde6f20775`. The current repository-root `output.csv` was generated with the explicit `candidate` command. It is a 518-row prediction candidate with `certified=false`; three rows still fail semantic validation. The certification label is local bookkeeping, not a HackerRank credential.

## Public development results

| Measure | Previous joint preview | Current context v2 |
|---|---:|---:|
| Correct statuses | 32/32 | 32/32 |
| Exact full answers | 17/32 | 19/32 |
| Matching / extra / missing steps | 172 / 0 / 21 | 178 / 0 / 15 |
| Step F1 | 0.9425 | 0.9596 |
| Sample semantic validation errors | 0 | 0 |

This closes two additional full public answers and recovers six additional steps. The 13 differing answers contain 15 missing steps: three IDs have no participant occurrence, five audit records appear only in captures after the audit cutoff, and seven account IDs have unresolved ownership among competing workflows. Every resource, source and timestamp is listed in [WORKFLOW_GAPS.md](WORKFLOW_GAPS.md).

The public samples were used for development and threshold/feature selection; these figures are not an independent test or a hidden challenge score. Broader timing variants that introduced wrong-person assignments were rejected. The evidence-only default remains unchanged at 10/32 exact, 159 matching steps and zero extra steps.

## Full 518-request output

| Measure | Current candidate |
|---|---:|
| COMPLETE / INCOMPLETE / NOT_APPLICABLE | 152 / 356 / 10 |
| Internally undetermined statuses | 3 |
| Established INCOMPLETE rows with unresolved plan items | 18 |
| Cases with unresolved obligations | 21 |
| Semantic validation errors | 3 |
| Inferred workflow links | 286 |

These are diagnostics, not hidden accuracy. Undetermined cases: case_55, case_63, case_345. Their missing facts are:

- case_55: a post-request account/profile state and the restore-allowed or blocked state of backup_9287 at or before 2026-04-30T11:00Z.
- case_63: an association or precedence rule resolving the conflicting subject identities for marketing_001.
- case_345: a subject/request-to-account link or a complete profile-table capture between its request and audit.

No missing finding was invented to clear validation. The root CSV therefore exists, but it is not fully contract-conforming while these three errors remain. Eighteen further plans have open items; `output.unresolved.json` names every missing fact. The evidence-only mode still has eight undetermined statuses and 18 plan gaps.

## Artifacts and reproduction

- `output.csv`: requested filename, 518 data rows, exact columns `case_id,deletion_status,steps_json`; SHA-256 `9b3bdef08b89931dd98b18e5424eacb2688f02e426d0d0bf0a09e189d8a27421`.
- `output.manifest.json`: producing code/input/output hashes, mode, all inferred links, all validation errors; `kind=submission_candidate`, `certified=false`, `final=false`.
- `output.unresolved.json`: exact unknown obligations, emitted steps and validation errors.
- `output_workflow_preview.*`: the same candidate bytes under the earlier review filename.
- `output_best_effort.*`: unchanged evidence-only prediction bytes, with refreshed provenance.

```bash
python3 code/main.py candidate
python3 code/main.py verify output.manifest.json
python3 scripts/evaluate_workflow.py
python3 scripts/diagnose_sample_differences.py --workflow-mode joint --markdown code/docs/WORKFLOW_GAPS.md
python3 code/evaluation/main.py all
python3 scripts/write_reports.py
python3 scripts/package.py --verify
```

Context v2 uses shared-file affinity, a penalty for operations after the reported claim, independently assessed compliant context, and a policy clock estimated from at least three identity-linked resources. No period or case family is supplied. Account initiation events do not get the clock feature. Anonymous policy candidates require a currently present record; old presence followed by an absent lookup cannot supply one. Every accepted assignment must have a strictly positive counterfactual score margin, and every inference stays uncertified. These are modelling assumptions, not proof of ownership.

Nine independent synthetic controls supplement the unchanged frozen fixtures. They include a different learned clock period, ambiguous equal clocks, future anchors, absent-only lookups, later absence, and candidate-artifact disclosures/overwrite protection. Python 3.12 was used; no new Python 3.14 validation is claimed. No paid model API call was made.
