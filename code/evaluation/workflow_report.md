# Workflow attribution experiment

Public samples are development data. The context features, weights and margin were selected after examining public development results. These figures do not establish hidden accuracy or calibrated confidence.

| Variant | Status | Exact full answers | TP / FP / FN | Step P / R / F1 | Validation errors |
|---|---:|---:|---|---|---:|
| Evidence baseline | 32/32 | 10/32 | 159 / 0 / 34 | 1.0000 / 0.8238 / 0.9034 | 3 |
| Joint preview (default margin) | 32/32 | 22/32 | 182 / 0 / 11 | 1.0000 / 0.9430 / 0.9707 | 0 |
| Joint preview (quarter-point floor) | 32/32 | 21/32 | 181 / 0 / 12 | 1.0000 / 0.9378 / 0.9679 | 0 |
| Anchor-only control | 32/32 | 15/32 | 166 / 0 / 27 | 1.0000 / 0.8601 / 0.9248 | 0 |
| Previous context v2 | 32/32 | 19/32 | 178 / 0 / 15 | 1.0000 / 0.9223 / 0.9596 | 0 |
| Previous workflow context | 32/32 | 17/32 | 172 / 0 / 21 | 1.0000 / 0.8912 / 0.9425 | 0 |

The joint mode proposes ownership from a partial maximum-weight assignment. It never uses workflow results as record-state proof. All such runs and their links are marked uncertified, retain alternative candidates and margins, and cannot pass `export`. Schema validity does not establish evidence validity. The evidence baseline remains the default.

Default settings: 90 minutes before / 10 minutes after reported_at; a strictly positive counterfactual score margin (ties abstain); one additional orphan per system/request and one request per orphan within a competing component. These are modelling assumptions, not supplied guarantees. A score margin is not a probability. The v2 context adds shared-file affinity (+1), a post-report-operation penalty (-2), independently compliant linked context (+2), and an anonymous-policy cadence feature (up to +2). A cadence is estimated from at least three distinct identity-linked policy resources; no period or case family is supplied. The largest period fitting the observed timestamps within one second is a modelling choice and may be aliased. These features rank hypotheses and never supply record-state evidence. Initial account deletions do not receive the cadence feature.

Context v3 additionally gives +1 account affinity when independently linked context is compliant AND a current explicit absent observation exists with no known present copy. Three distinct independently linked resources add one further anchor-distance term. Missing, stale, future and inventory-only absence supplies no affinity. These interactions were selected using public development data; ownership remains inferred and strict export continues to refuse it.

## Default-preview proposals

The sources below support the candidate operation and the independently assessed state; the ownership relation remains an inference.

| Case | Proposed resource | Activity | Assignment-score margin |
|---|---|---|---:|
| case_01 | account_001 | activity_3342 | 3.990556 |
| case_02 | account_002 | activity_3376 | 1.831667 |
| case_03 | analytics_9406 | activity_3852 | 0.008333 |
| case_04 | analytics_901 | activity_3463 | 3.789444 |
| case_07 | account_007 | activity_3590 | 3.955000 |
| case_08 | account_008 | activity_3554 | 0.910556 |
| case_09 | account_3960 | activity_3703 | 1.843333 |
| case_10 | account_010 | activity_3595 | 1.983056 |
| case_18 | account_5521 | activity_3732 | 0.747778 |
| case_20 | account_5037 | activity_3734 | 0.497222 |
| case_21 | account_6440 | activity_3661 | 3.000000 |
| case_21 | analytics_5335 | activity_3665 | 3.000000 |
| case_22 | account_4990 | activity_3573 | 2.000000 |
| case_25 | account_3136 | activity_3597 | 0.337778 |
| case_25 | analytics_1895 | activity_3602 | 1.043056 |
| case_26 | account_5684 | activity_3600 | 0.337778 |
| case_26 | analytics_4566 | activity_3603 | 1.764994 |
| case_27 | account_3866 | activity_3530 | 2.000000 |
| case_27 | analytics_4574 | activity_3533 | 2.978055 |
| case_28 | account_5482 | activity_3529 | 0.654444 |
| case_28 | analytics_6077 | activity_3534 | 2.978055 |
| case_29 | account_7012 | activity_3532 | 0.654444 |
| case_30 | account_4163 | activity_3465 | 1.856667 |

## Remaining default-preview differences

| Case | Missing resources | Extra resources |
|---|---|---|
| case_04 | account_004 | none |
| case_09 | audit_record_4902 | none |
| case_18 | audit_record_6645 | none |
| case_20 | audit_record_5569 | none |
| case_23 | account_410, audit_record_4128 | none |
| case_24 | audit_record_7095 | none |
| case_29 | audit_record_3954 | none |
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
- Context v2 learns a candidate policy cadence from at least three identity-linked resources, adds shared-capture and observed-compliance features, and penalizes operations after the workflow report. These are explicitly uncertain attribution features.
- The cadence feature is restricted to anonymous policy records; extending it to initial account operations produced wrong sample assignments and was rejected.
- Independent context tests use a different inferred period, retain same-clock ambiguity, exclude future anchors and verify candidate-file uncertainty and overwrite protections.

All runtime variants make zero model API calls. Coding-session usage is not available here and is not estimated.
