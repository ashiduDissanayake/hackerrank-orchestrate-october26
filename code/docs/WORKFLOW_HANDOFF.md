# Submission closeout

Producing code: `7f307e866962792d1997138539730454f027523e`. Repository-root `output.csv` contains 518 predictions and passes the existing validator with zero errors. It uses joint context-v3 workflow attribution plus `decision_policy=submission`. This is a prediction release with disclosed assumptions, not an evidence-only certificate or a claim of hidden accuracy.

## Reproduce and package

```bash
python3 code/main.py candidate
python3 code/main.py verify output.manifest.json
python3 scripts/write_reports.py
python3 scripts/package.py --verify
```

The separate submission files are `output.csv`, `code.zip`, and the authentic root `log.txt`. The ZIP excludes the participant corpus, credentials, caches, nested archives and transcript. It includes runnable sources, setup instructions and the required evaluation and usage reports.

## Results

| Measure | Submission predictor |
|---|---:|
| Rows | 518 |
| COMPLETE / INCOMPLETE / NOT_APPLICABLE | 153 / 355 / 10 |
| Validator errors | 0 |
| Internally undetermined predictions | 0 |
| Explicit decision assumptions | 16 across 15 cases |
| INCOMPLETE cases with unresolved plan facts | 6 |
| Workflow ownership inferences | 307 |
| Public statuses | 32/32 |
| Public exact full answers | 22/32 |
| Public matching / extra / missing steps | 182 / 0 / 11 |
| Public step precision / recall / F1 | 1.0000 / 0.9430 / 0.9707 |

The public samples were reused for development, not held out. The new decision assumptions do not change any public answer, so public results provide no direct validation of those assumptions. The fifteen independent fictional controls exercise positive decisions and temporal, ownership, scope and certification counterexamples. All 22 suites and the unchanged 31 frozen fixtures pass under Python 3.12. No paid API call was made.

## Submission decisions

| Rule | Evidence used | Explicit assumption |
|---|---|---|
| recoverable_archive_risk | Present archive, storage path, verified checksum, drill history, unexpired retention | A usable archive remains a recreation risk unless blocking is evidenced; restore permission itself is not observed |
| later_catalog_owner | Later mapping matching stable user_id and verified email, earlier present resource | The later owner association outranks earlier foreign contact fields when no competing stable owner or newer contact evidence is shown; identities are not merged |
| clean_snapshot_persistence | Complete clean primary/profile capture and accounted-for copies, no admissible subject profile ever observed | Absence persists to audit_at even when the capture predates the request; no account ID is invented |

Case_55 predicts INCOMPLETE using the archive risk and snapshot-persistence assumptions. Case_63 predicts INCOMPLETE using later catalog ownership. Case_345 predicts COMPLETE using snapshot persistence and its evidence-backed retained audit record. Every affected case, original unknown reason, evidence ID and assumption is included in `output.manifest.json` and `output.unresolved.json`. No post-audit artifact, case-number rule, peer prediction or organizer-only truth is used.

## Remaining evidence limits

Six established-INCOMPLETE cases retain open plan facts: case_34 (audit_record_3753 is not currently observed), and cases 526, 527, 528, 529 and 531 (account evidence is insufficient at their cutoffs). Future checks are included for known IDs; missing IDs are not invented. The status is already INCOMPLETE because other violations are established. Zero validation errors does not prove these plans match every hidden canonical step.

The public residual remains eleven missing steps across ten cases: three IDs have no participant occurrence, five audit IDs occur only after the cutoff, and three account associations have equally optimal alternatives. `WORKFLOW_GAPS.md` and `ACCOUNT_LINK_PHASE1.md` give the exact sources and witnesses. Official main was rechecked at `0eddbbd33f682eae0a2770d67412af8a3cf4af20`; no participant dataset update was found.

## Comparison and provenance

Plain `run` preserves evidence-only decisions. `run --workflow-mode joint --decision-policy strict` reproduces the previous workflow preview. `candidate --decision-policy strict` can also generate that comparison, but correctly exits non-zero because three rows remain invalid under abstention. The strict export gate rejects every submission assumption even if configuration is falsified; an internal certification flag is not a HackerRank credential.

Candidate SHA-256: `8dc3ae5f75d4fb5a3237a1214f9896ded7c66ebe7da8dc26850c8e21afafaef1`. Code SHA-256: `5a7b08771c8bd95065b682d03925f8d3830c01ae1118dcb817e5c04addc1c60d` across 46 prediction-affecting files. Both evidence upper cutoffs remain enforced. Runtime model calls, input/output tokens and model cost are all zero; coding-assistant session usage is unavailable and is not estimated.
