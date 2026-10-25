# Remaining public sample differences and evidence requirements

Diagnosis only: labels identify the expected resource to search for after predictions are complete. Neither this report nor the labels feed predictions. These are public development results, not a hidden-set score.

Mode `joint`, scoring `contextual_v2`, margin floor `0.0`: 19/32 exact full answers; 13 differing rows; 15 missing steps; 0 extra steps.

| Case | Expected resource | Cause | Participant occurrences | Audit cutoff |
|---|---|---|---|---|
| case_04 | account_004 | NO_PARTICIPANT_OCCURRENCE | none | 2026-09-07T10:20:00Z |
| case_09 | audit_record_4902 | CAPTURED_AFTER_AUDIT | evidence_06 @ 2026-09-18T11:55:24Z | 2026-09-16T09:00:00Z |
| case_18 | audit_record_6645 | NO_PARTICIPANT_OCCURRENCE | none | 2026-09-26T11:00:00Z |
| case_20 | audit_record_5569 | NO_PARTICIPANT_OCCURRENCE | none | 2026-09-26T11:00:00Z |
| case_23 | account_410 | OWNERSHIP_UNRESOLVED | activity_3662 @ 2026-09-05T11:10:55Z | 2026-09-15T12:00:00Z |
| case_23 | audit_record_4128 | CAPTURED_AFTER_AUDIT | evidence_02 @ 2026-09-17T12:00:00Z | 2026-09-15T12:00:00Z |
| case_24 | audit_record_7095 | CAPTURED_AFTER_AUDIT | evidence_02 @ 2026-09-17T12:00:00Z | 2026-09-15T12:00:00Z |
| case_25 | account_3136 | OWNERSHIP_UNRESOLVED | evidence_92 @ 2026-09-15T11:44:55Z; activity_3597 @ 2026-09-02T10:48:27Z | 2026-09-15T12:00:00Z |
| case_26 | account_5684 | OWNERSHIP_UNRESOLVED | evidence_02 @ 2026-09-17T12:00:00Z; evidence_92 @ 2026-09-15T11:44:55Z; activity_3600 @ 2026-09-02T11:08:43Z | 2026-09-15T12:00:00Z |
| case_28 | account_5482 | OWNERSHIP_UNRESOLVED | evidence_92 @ 2026-09-15T11:44:55Z; activity_3529 @ 2026-08-30T10:46:13Z | 2026-09-15T12:00:00Z |
| case_29 | account_7012 | OWNERSHIP_UNRESOLVED | activity_3532 @ 2026-08-30T11:06:57Z | 2026-09-15T12:00:00Z |
| case_29 | audit_record_3954 | CAPTURED_AFTER_AUDIT | evidence_02 @ 2026-09-17T12:00:00Z | 2026-09-15T12:00:00Z |
| case_30 | audit_record_1707 | CAPTURED_AFTER_AUDIT | evidence_02 @ 2026-09-17T12:00:00Z | 2026-09-15T12:00:00Z |
| case_31 | account_4857 | OWNERSHIP_UNRESOLVED | activity_3682 @ 2026-09-06T10:45:58Z | 2026-09-15T12:00:00Z |
| case_32 | account_8858 | OWNERSHIP_UNRESOLVED | activity_3685 @ 2026-09-06T11:05:15Z | 2026-09-15T12:00:00Z |

Counts by missing-step cause: CAPTURED_AFTER_AUDIT=5, NO_PARTICIPANT_OCCURRENCE=3, OWNERSHIP_UNRESOLVED=7.

Required input to close these differences:

- For an ID with no participant occurrence: a participant-visible record or activity naming the ID and connecting it to the subject, available by audit_at.
- For later-captured evidence: an admissible earlier capture, or explicit organizer clarification changing the stated time contract. A later capture cannot be used under the current rule.
- For unresolved ownership: a request/subject correlation key, source reference or other grounded association that distinguishes the competing workflows. Request-number ordering does not prove ownership.

The output schema itself is clear. These requirements concern facts needed to reproduce specific canonical steps without inserting labels into prediction code.
