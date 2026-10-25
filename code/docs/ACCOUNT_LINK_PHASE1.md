# Phase 1: account-link investigation

This audit does not read sample_output.csv, peer predictions or organizer data. It compares the two ranking modes on participant inputs. An accepted assignment remains an uncertified ownership inference, not a newly discovered identity chain.

Context v3 accepts 4 of 7 previously ambiguous account assignments.

| Case | New proposal | Margin | Equally score-optimal alternatives |
|---|---|---:|---|
| case_23 | abstain | 0.000000 | account_410, account_7015, account_9155 |
| case_25 | account_3136 | 0.337778 | account_3136 |
| case_26 | account_5684 | 0.337778 | account_5684 |
| case_28 | account_5482 | 0.654444 | account_5482 |
| case_29 | account_7012 | 0.654444 | account_7012 |
| case_31 | abstain | 0.000000 | account_1810, account_3677, account_4857 |
| case_32 | abstain | 0.000000 | account_2381, account_8858 |

## What changed

- Current explicit absence interacts with an independently compliant case context. A broad inventory omission, stale lookup or future capture supplies no affinity; a known present copy blocks it.
- Three distinct identity-linked policy resources strengthen the existing anchor-distance feature. Repeated operations on one resource do not count as independent anchors.
- Both signals remain ranking assumptions. State is assessed separately, and original evidence-only predictions and the strict export gate are unchanged.

## Why the remaining assignments abstain

Each witness below is a feasible global assignment with the same objective score. The ambiguity is in the admissible account-to-subject association. This establishes ambiguity under the current model; it is not a claim that all possible inference methods are equivalent.

### case_23 at 2026-09-15T12:00:00Z

Best score: 14.653333333. Distinct equally optimal targets: account_410, account_7015, account_9155.

```json
[
 {
  "assignment": {
   "case_21": "account_6440",
   "case_23": "account_410",
   "case_546": "account_8832",
   "case_547": "account_9155",
   "case_548": "account_7015"
  },
  "resource_id": "account_410",
  "score": 14.65333333333333
 },
 {
  "assignment": {
   "case_21": "account_6440",
   "case_23": "account_7015",
   "case_546": "account_8832",
   "case_547": "account_9155",
   "case_548": "account_410"
  },
  "resource_id": "account_7015",
  "score": 14.653333333333332
 }
]
```

Candidate evidence visible by the cutoff:

| Resource | Observations | Capture IDs | Nonempty join fields |
|---|---:|---|---|
| account_294 | 0 | none | none |
| account_410 | 0 | none | none |
| account_6440 | 1 | evidence_92 | none |
| account_7015 | 0 | none | none |
| account_8832 | 0 | none | none |
| account_9155 | 0 | none | none |

### case_31 at 2026-09-15T12:00:00Z

Best score: 12.282500000. Distinct equally optimal targets: account_1810, account_3677, account_4857.

```json
[
 {
  "assignment": {
   "case_14": "account_3677",
   "case_31": "account_1810",
   "case_32": "account_8858",
   "case_38": "account_2381",
   "case_40": "account_4857"
  },
  "resource_id": "account_1810",
  "score": 12.282499999999999
 },
 {
  "assignment": {
   "case_14": "account_1810",
   "case_31": "account_3677",
   "case_32": "account_8858",
   "case_38": "account_2381",
   "case_40": "account_4857"
  },
  "resource_id": "account_3677",
  "score": 12.282499999999999
 }
]
```

Candidate evidence visible by the cutoff:

| Resource | Observations | Capture IDs | Nonempty join fields |
|---|---:|---|---|
| account_1810 | 0 | none | none |
| account_2381 | 0 | none | none |
| account_3677 | 0 | none | none |
| account_4857 | 0 | none | none |
| account_8858 | 0 | none | none |

### case_32 at 2026-09-15T12:00:00Z

Best score: 12.282500000. Distinct equally optimal targets: account_2381, account_8858.

```json
[
 {
  "assignment": {
   "case_14": "account_1810",
   "case_31": "account_3677",
   "case_32": "account_2381",
   "case_38": "account_8858",
   "case_40": "account_4857"
  },
  "resource_id": "account_2381",
  "score": 12.282499999999999
 },
 {
  "assignment": {
   "case_14": "account_1810",
   "case_31": "account_3677",
   "case_32": "account_8858",
   "case_38": "account_2381",
   "case_40": "account_4857"
  },
  "resource_id": "account_8858",
  "score": 12.282499999999999
 }
]
```

Candidate evidence visible by the cutoff:

| Resource | Observations | Capture IDs | Nonempty join fields |
|---|---:|---|---|
| account_1810 | 0 | none | none |
| account_2381 | 0 | none | none |
| account_3677 | 0 | none | none |
| account_4857 | 0 | none | none |
| account_8858 | 0 | none | none |

## Queue-order calibration

Calibration uses accounts with explicit subject links and operations in their request windows, available by the target cutoff. It does not use the public answer file. Pairs overlap and the counts are descriptive, not independent accuracy trials.

At 2026-09-15T12:00:00Z: {"FIFO": 72, "LIFO": 70, "same_result_FIFO": 25, "same_result_LIFO": 26} across 125 batches.

Neither first-in-first-out nor reverse request order is established by these observations, so neither was added as a tie-break. The raw alias pass found no additional account association; numeric suffix matches referred to other resource namespaces, unrelated subjects or unrelated activity IDs.

To establish the remaining ownership links, supply a participant-visible request/job/subject correlation key or a source reference tying each account ID to its subject by audit_at. No case-number allocation or later capture was used to fill the missing association.

Reproduce: `python3 scripts/audit_account_links.py`. Public sample accuracy is measured separately by `python3 scripts/evaluate_workflow.py`.
