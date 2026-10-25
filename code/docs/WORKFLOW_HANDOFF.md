# Workflow follow-up: current output and remaining evidence requirements

Producing code: `a4fad4354e310f3d30c7d8ac27e4f93d6fbca833`. The current repository-root `output.csv` was generated with the explicit `candidate` command. It is a 518-row prediction candidate with `certified=false`; three rows still fail semantic validation. The certification label is local bookkeeping, not a HackerRank credential.

## Public development results

| Measure | Previous context v2 | Current context v3 |
|---|---:|---:|
| Correct statuses | 32/32 | 32/32 |
| Exact full answers | 19/32 | 22/32 |
| Matching / extra / missing steps | 178 / 0 / 15 | 182 / 0 / 11 |
| Step F1 | 0.9596 | 0.9707 |
| Sample semantic validation errors | 0 | 0 |

This phase recovers four account matches (cases 25, 26, 28 and 29), closing three additional full public answers. The remaining 10 differing answers contain 11 missing steps: three IDs have no participant occurrence, five audit records appear only in captures after the audit cutoff, and three account associations remain ambiguous (cases 23, 31 and 32). The new matches remain ownership inferences. Exact alternative-assignment witnesses and the label-free audit are in [ACCOUNT_LINK_PHASE1.md](ACCOUNT_LINK_PHASE1.md). Every resource, source and timestamp is listed in [WORKFLOW_GAPS.md](WORKFLOW_GAPS.md).

The public samples were used for development and threshold/feature selection; these figures are not an independent test or a hidden challenge score. Broader timing variants that introduced wrong-person assignments were rejected. The evidence-only default remains unchanged at 10/32 exact, 159 matching steps and zero extra steps.

## Full 518-request output

| Measure | Current candidate |
|---|---:|
| COMPLETE / INCOMPLETE / NOT_APPLICABLE | 152 / 356 / 10 |
| Internally undetermined statuses | 3 |
| Established INCOMPLETE rows with unresolved plan items | 18 |
| Cases with unresolved obligations | 21 |
| Semantic validation errors | 3 |
| Inferred workflow links | 307 |

These are diagnostics, not hidden accuracy. Undetermined cases: case_55, case_63, case_345. Their missing facts are:

- case_55: a post-request account/profile state and the restore-allowed or blocked state of backup_9287 at or before 2026-04-30T11:00Z.
- case_63: an association or precedence rule resolving the conflicting subject identities for marketing_001.
- case_345: a subject/request-to-account link or a complete profile-table capture between its request and audit.

No missing finding was invented to clear validation. The root CSV therefore exists, but it is not fully contract-conforming while these three errors remain. Eighteen further plans have open items; `output.unresolved.json` names every missing fact. The evidence-only mode still has eight undetermined statuses and 18 plan gaps.

## Artifacts and reproduction

- `output.csv`: requested filename, 518 data rows, exact columns `case_id,deletion_status,steps_json`; SHA-256 `9cf7a9c704dc0fa96e70ae0d0cf74ad21cb767614445a8744efa3a6ea5154fce`.
- `output.manifest.json`: producing code/input/output hashes, mode, all inferred links, all validation errors; `kind=submission_candidate`, `certified=false`, `final=false`.
- `output.unresolved.json`: exact unknown obligations, emitted steps and validation errors.
- `output_workflow_preview.*`: the same candidate bytes under the earlier review filename.
- `output_best_effort.*`: evidence-only predictions, including the future-check coverage fix, with refreshed provenance.

```bash
python3 code/main.py candidate
python3 code/main.py verify output.manifest.json
python3 scripts/evaluate_workflow.py
python3 scripts/diagnose_sample_differences.py --workflow-mode joint --markdown code/docs/WORKFLOW_GAPS.md
python3 code/evaluation/main.py all
python3 scripts/write_reports.py
python3 scripts/package.py --verify
```

Context v2 uses shared-file affinity, a penalty for operations after the reported claim, independently assessed compliant context, and a policy clock estimated from at least three identity-linked resources. No period or case family is supplied. Account initiation events do not get the clock feature. Anonymous policy candidates require a currently present record; old presence followed by an absent lookup cannot supply one. Context v3 adds account-state affinity only when independently linked context is compliant and a current explicit absence is observed with no known present copy; three distinct linked resources add anchor-distance weight. Every accepted assignment must have a strictly positive counterfactual score margin, and every inference stays uncertified. These are modelling assumptions, not proof of ownership.

Twelve additional account-ranking, temporal, replica and ambiguity-witness controls supplement the previous context tests and unchanged frozen fixtures. All 21 suites and 31 frozen fixtures pass, including seven new future-verification controls and an updated source-reference integration expectation. They include a different learned clock period, ambiguous equal clocks, future anchors, absent-only lookups, later absence, and candidate-artifact disclosures/overwrite protection. Python 3.12 was used; no new Python 3.14 validation is claimed. No paid model API call was made.

## Future-verification coverage fix

The planner previously discarded every UNKNOWN obligation. For an already INCOMPLETE case with an established finding, a known resource, and a known policy target, the contract permits a future verification check with an empty evidence ID. That check does not establish the current state and does not authorize inventing a finding or destructive remediation.

The candidate adds exactly nine such checks: an audit-retention check in case_34 and account-absence checks in cases 102, 144, 184, 282, 344, 526, 528 and 531. No existing step is removed and no status changes. Ownership conflicts, missing IDs/categories and excluded obligations still emit no check. The 18 open plans remain open because the current facts are still unknown. Public sample metrics stay 22/32 exact and 182/0/11 matching/extra/missing steps; this is a coverage improvement on the unlabeled requests, not a measured hidden-score gain.
