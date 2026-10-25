# Workflow attribution experiment

Public samples are development data. The margin was selected after examining public development results. These figures do not establish hidden accuracy or calibrated confidence.

| Variant | Status | Exact full answers | TP / FP / FN | Step P / R / F1 | Validation errors |
|---|---:|---:|---|---|---:|
| Evidence baseline | 32/32 | 10/32 | 159 / 0 / 34 | 1.0000 / 0.8238 / 0.9034 | 3 |
| Joint preview (default margin) | 32/32 | 17/32 | 172 / 0 / 21 | 1.0000 / 0.8912 / 0.9425 | 0 |
| Joint preview (no positive margin floor) | 32/32 | 18/32 | 173 / 1 / 20 | 0.9943 / 0.8964 / 0.9428 | 0 |
| Anchor-only control | 32/32 | 15/32 | 166 / 0 / 27 | 1.0000 / 0.8601 / 0.9248 | 0 |

The joint mode proposes ownership from a partial maximum-weight assignment. It never uses workflow results as record-state proof. All such runs and their links are marked uncertified, retain alternative candidates and margins, and cannot pass `export`. Schema validity does not establish evidence validity. The evidence baseline remains the default.

Default settings: 90 minutes before / 10 minutes after reported_at; minimum counterfactual score margin 0.25; one additional orphan per system/request and one request per orphan within a competing component. These are modelling assumptions, not supplied guarantees. A score margin is not a probability.

## Default-preview proposals

The sources below support the candidate operation and the independently assessed state; the ownership relation remains an inference.

| Case | Proposed resource | Activity | Assignment-score margin |
|---|---|---|---:|
| case_01 | account_001 | activity_3342 | 3.990556 |
| case_02 | account_002 | activity_3376 | 3.831667 |
| case_04 | analytics_901 | activity_3463 | 3.789444 |
| case_07 | account_007 | activity_3590 | 3.955000 |
| case_08 | account_008 | activity_3554 | 2.910556 |
| case_09 | account_3960 | activity_3703 | 1.843333 |
| case_10 | account_010 | activity_3595 | 3.983056 |
| case_20 | account_5037 | activity_3734 | 0.497222 |
| case_21 | account_6440 | activity_3661 | 1.390556 |
| case_21 | analytics_5335 | activity_3665 | 1.000000 |
| case_22 | account_4990 | activity_3573 | 2.000000 |
| case_27 | account_3866 | activity_3530 | 2.000000 |
| case_30 | account_4163 | activity_3465 | 1.856667 |

## Remaining default-preview differences

| Case | Missing resources | Extra resources |
|---|---|---|
| case_03 | analytics_9406 | none |
| case_04 | account_004 | none |
| case_09 | audit_record_4902 | none |
| case_18 | account_5521, audit_record_6645 | none |
| case_20 | audit_record_5569 | none |
| case_23 | account_410, audit_record_4128 | none |
| case_24 | audit_record_7095 | none |
| case_25 | account_3136, analytics_1895 | none |
| case_26 | account_5684, analytics_4566 | none |
| case_27 | analytics_4574 | none |
| case_28 | account_5482, analytics_6077 | none |
| case_29 | account_7012, audit_record_3954 | none |
| case_30 | audit_record_1707 | none |
| case_31 | account_4857 | none |
| case_32 | account_8858 | none |

## Independent synthetic controls

These are fictional counterexamples in `code/tests/test_workflow.py`, not public-answer labels.

1. **Ambiguous ownership:** Rui and Mina submit equally timed requests, and one anonymous account operation fits both equally. Expected: both abstain, including after request shuffling and case-ID renaming.

2. **Global assignment:** request A scores resource X at 4 and Y at 3; request B scores X at 3.9 and has no Y edge. Expected: A gets Y and B gets X (total 6.9), with a real counterfactual margin; independent greedy assignment fails. The solver is also checked against exhaustive enumeration on 35 fixed-seed small graphs.

3. **Claim without state:** a lone operation reports SUCCESS but there is no admissible account state or profile coverage. Expected: the ownership hypothesis may be recorded, the account remains UNKNOWN, and no absent-record verification is fabricated.

4. **Temporal trap:** another person's account evidence is captured after the audit while its inner time is earlier. Expected: it cannot change the earlier assignment. Future requests and events are also excluded.

5. **Export boundary:** a hypothesis plus an independent complete profile snapshot can produce a structurally valid candidate row. Expected: strict export still refuses it, even if its configuration is falsified as evidence-only. `run --out <repo>/output.csv` also refuses.

## Other fixes in this pass

- A source-reference cycle whose only identity root is rejected is removed by rooted reachability; a cycle with an independent valid root survives.
- Evidence captured before an earlier request began cannot be assigned to that earlier request's investigation window.
- The best-effort CLI accepts an artifact directory. Its fixture test uses a temporary directory and verifies that root prediction artifacts are unchanged.

All runtime variants make zero model API calls. Coding-session usage is not available here and is not estimated.
