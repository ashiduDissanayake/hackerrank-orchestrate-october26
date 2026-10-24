# Every difference between the sample predictions and `dataset/sample_output.csv`

Diagnosis only. The public answers are read to learn which resource ids to look up; nothing in the engine reads them. Regenerate with
`python3 scripts/diagnose_sample_differences.py` (it greps every participant file for each id: SQL/JSON/log/txt, PDFs through `pdftotext`, the
hash-bound image transcriptions, `system_activity.csv`, `user_audit_log.csv`, and records the production link chain and the admissibility of every
hit under the dual-time cutoff).

## Before and after this round (public samples, development data, not a holdout)

| | before (`485f684`) | after (`e2e991e` + this round) |
|---|---|---|
| status accuracy | 32/32 | 32/32 |
| strict steps TP / FP / FN (193 expected) | 158 / 4 / 35 | **159 / 0 / 34** |
| strict precision / recall / F1 | 0.9753 / 0.8187 / 0.8901 | **1.0000 / 0.8238 / 0.9034** |
| aligned-field accuracy (state / evidence_id) | 1.000 / 1.000 | 1.000 / 1.000 |
| exact full answers | 8/32 | **10/32** |
| sequence exact rate / mean LCS | 0.250 / 0.7831 | 0.3125 / 0.7984 |
| contract-invalid rows | 3 (case_01, 02, 04: COMPLETE with zero steps) | 3 (same) |

"Aligned-field accuracy" is measured only over steps that were matched on (phase, system, resource, operation); it says nothing about the 34 missing steps.
The remaining 34 gaps are listed below. The two fixes that moved these numbers were found by the diagnosis (the user's hint for `case_06`; the repeated-request
structure for the extras), so their gain is development evidence, not an independent measurement.

## What was recovered, and why the earlier diagnosis was wrong

* **case_06 / `account_006`**: `evidence_57` (search SQL snapshot, capture 2026-09-10T08:45Z) holds `search_001` with `email = jonas.berg@outlook.com` and
  `source_resource_id = account_006` (indexed 2026-09-09T22:12Z, before the audit 2026-09-10T09:15Z). Chain: subject email -> `search_001` (direct) -> `account_006`
  (source reference). The linker already found it but created `Link(src, None)`: no observation of the account supplies a system, so policy evaluation returned `None` and
  silently dropped it. Fixed in `linking.py` (system from observations, then the existing id namespace; `Link.system_basis`; fixed point with a visited set; orphan pruning),
  `obligations.py` (an unresolvable category is an explicit UNKNOWN) and `Link.since()` (a source reference proves neither existence nor creation time, so the
  declared-empty inventory `evidence_90`, captured 2026-09-05T07:18:01Z, **before** the document was indexed, still shows the account gone). The state proof
  is separate from the link: `account_006` absent in `evidence_90` (primary) and `evidence_54` (failover, 2026-09-02T23:00Z). Step recovered: `VERIFICATION account_006 VERIFY_RECORD_ABSENT` with an empty `evidence_id` (future check). The earlier statement that every missing sample step lacks usable linking evidence was wrong for this case.
  The only three `source_resource_id` values in the dataset are in `evidence_57`; the other two (`search_4203`, `search_8814`) belong to other identities.
* **case_07 / `object_19` (extra), case_17 / `account_6523` (extra)**: not errors of state or linkage but of episode scope. The same person made an earlier request in each
  case (`case_61`: 2026-02-11..02-14; `case_46`: 2026-03-08..03-11). Every ownership chain of `object_19` (catalog `activity_4007` 2026-02-13T08:07:01Z, screenshot
  `evidence_46` 2026-02-13T08:00Z) and of `account_6523` (trace lookup `evidence_67` 2026-03-10T06:18:01Z, 404) was captured inside the earlier request's window and before the later
  request began (2026-08-31 and 2026-08-19). They are now carried over (`res.carried_over`): not steps; a PRESENT carried-over record would become UNKNOWN, never hidden.
  This is a documented inference from the subject's own request history, not a first-request rule and not a case-number rule: any chain at or after `requested_at`, or evidence
  between the two requests, keeps a resource in scope (tests in `code/tests/test_episode_scope.py`). The eval run has the same shape once: `case_33` / `export_1260` (earlier `case_52`, window 2026-06-16..06-19).
  The data's repeated-request subjects are exactly three (`user_07`, `user_17`, `user_18`).

## The 34 steps still missing (each with the provenance that is missing)

| case | missing step | status | subject-level state proof | participant occurrences of the id (file @ capture time; admissible at audit) | what blocks it |
|---|---|---|---|---|---|
| case_01 | account_001 ABSENT | COMPLETE | no profile for subject, `evidence_54` | `activity_3342` 2026-08-20T16:41Z (deletion-worker claim) | no ownership chain: the activity row names the id and no identity |
| case_02 | account_002 ABSENT | COMPLETE | `evidence_54` | `activity_3376` 2026-08-22T07:30Z | as case_01 |
| case_03 | analytics_9406 ANONYMIZED | COMPLETE | n/a | `evidence_94` L42-43 (read log, 2026-09-26T10:38Z: every identifier null, `lookup_key=null`), `activity_3852` | the record is already anonymous: no identifier to chain through |
| case_04 | account_004 ABSENT | COMPLETE | `evidence_90` | **none anywhere** (not even an activity row; re-searched all participant text) | the id appears only in the public answer |
| case_04 | analytics_901 ANONYMIZED | COMPLETE | n/a | `evidence_56` L7 (2026-09-07T09:45Z, identifiers null), `activity_3463` | already anonymous |
| case_07 | account_007 ABSENT | INCOMPLETE | `evidence_90` | `activity_3590` | as case_01; future check, needs only the id |
| case_08 | account_008 ABSENT | INCOMPLETE | `evidence_07` | `activity_3554` | as case_01 |
| case_09 | account_3960 ABSENT | INCOMPLETE | `evidence_93` | `activity_3703`; **LATE** `evidence_06` L86 (log, captured 2026-09-18T11:55Z, record time 2026-09-16T08:57Z) | the only artifact naming it was captured after the audit (2026-09-16T09:00Z) |
| case_09 | audit_record_4902 PRESENT | INCOMPLETE | n/a | **LATE** `evidence_06` L28 (record time 2026-09-16T08:52Z) | as above |
| case_10 | account_010 ABSENT | INCOMPLETE | `evidence_02` | `activity_3595` | as case_01 |
| case_18 | account_5521 ABSENT | INCOMPLETE | `evidence_02` | `activity_3732` | as case_01 |
| case_18 | audit_record_6645 PRESENT | INCOMPLETE | n/a | **none anywhere** | the id appears only in the public answer |
| case_20 | account_5037 ABSENT | INCOMPLETE | `evidence_02` | `activity_3734` | as case_01 |
| case_20 | audit_record_5569 PRESENT | INCOMPLETE | n/a | **none anywhere** | the id appears only in the public answer |
| case_21 | account_6440 ABSENT | COMPLETE | `evidence_51` | `evidence_92` L46 (404 lookup 2026-09-15T09:31:19Z, **no per-case key**), `activity_3661` | `evidence_92` is one service export covering several subjects' lookups; its list items carry no key |
| case_21 | analytics_5335 ANONYMIZED | COMPLETE | n/a | `evidence_92` L105 (null identifiers), `activity_3665`; **LATE** `evidence_02` | already anonymous, unkeyed list |
| case_22 | account_4990 ABSENT | INCOMPLETE | `evidence_05` | `activity_3573` | as case_01 |
| case_23 | account_410 ABSENT | INCOMPLETE | `evidence_51` | `activity_3662` | as case_01 |
| case_23 | audit_record_4128 PRESENT | INCOMPLETE | n/a | **LATE** `evidence_02` L412 (captured 2026-09-17T12:00Z, snapshot time 2026-09-15T12:00Z = audit time) | artifact captured after the audit |
| case_24 | audit_record_7095 PRESENT | INCOMPLETE | n/a | **LATE** `evidence_02` L419 | as case_23 |
| case_25 | account_3136 ABSENT | COMPLETE | `evidence_51` | `evidence_92` L10 (404, unkeyed), `activity_3597` | as case_21 |
| case_25 | analytics_1895 ANONYMIZED | COMPLETE | n/a | `evidence_92` L60, `activity_3602`; **LATE** `evidence_02` L83 | as case_21 |
| case_26 | account_5684 ABSENT | COMPLETE | `evidence_51` | `evidence_92` L40, `activity_3600`; **LATE** `evidence_02` L11 | as case_21 |
| case_26 | analytics_4566 ANONYMIZED | COMPLETE | n/a | `evidence_92` L78, `activity_3603`; **LATE** `evidence_02` L107 | as case_21 |
| case_27 | account_3866 ABSENT | COMPLETE | `evidence_51` | `evidence_92` L16, `activity_3530`; **LATE** `evidence_02` L524 | as case_21 |
| case_27 | analytics_4574 ANONYMIZED | COMPLETE | n/a | `evidence_92` L87, `activity_3533`; **LATE** `evidence_02` L132 | as case_21 |
| case_28 | account_5482 ABSENT | COMPLETE | `evidence_51` | `evidence_92` L34, `activity_3529` | as case_21 |
| case_28 | analytics_6077 ANONYMIZED | COMPLETE | n/a | `evidence_92` L114, `activity_3534`; **LATE** `evidence_02` L161 | as case_21 |
| case_29 | account_7012 ABSENT | INCOMPLETE | `evidence_51` | `activity_3532` | as case_01 |
| case_29 | audit_record_3954 PRESENT | INCOMPLETE | n/a | **LATE** `evidence_02` L454 | as case_23 |
| case_30 | account_4163 ABSENT | INCOMPLETE | `evidence_51` | `activity_3465` | as case_01 |
| case_30 | audit_record_1707 PRESENT | INCOMPLETE | n/a | **LATE** `evidence_02` L461 | as case_23 |
| case_31 | account_4857 ABSENT | COMPLETE | tombstone `tombstone_440` DELETED, `evidence_51` (2026-09-15T12:00Z) | `activity_3682` | the tombstone proves the account state, not which resource id it was |
| case_32 | account_8858 ABSENT | INCOMPLETE | tombstone, `evidence_51` | `activity_3685` | as case_31 |

Where does the pipeline lose available evidence? Nowhere in these 34: for each id the table is the complete set of participant occurrences, and none is an explicit ownership chain
under the contract's time rule (activity rows are claims without identity; null-identifier records cannot chain; unkeyed multi-subject exports carry no key; artifacts captured after the
audit are excluded; three ids occur nowhere). Extraction, propagation, system resolution, policy and planning were checked for each by the production-linker diagnostic
(`scripts/m2b_link_probe.py`, now run on the real relationship graph).

## Alternatives measured, not adopted

* **Record-time-only admissibility (open decision P9)**: artifact capture time ignored, only `observed_at <= audit_at`. `scripts/measure_record_time_rule.py`: public samples fall to
  TP/FP/FN 138/28/55 (P 0.831, R 0.715) versus 159/0/34 under the strict dual-time rule, because later artifacts also show later states. About 8 of the 34 gaps
  (`audit_record_*` and some accounts in `evidence_02`/`evidence_06`) become reachable, at a net loss. The contract prohibits evidence captured after `audit_at`; the strict rule stays.
* **Activity-window candidates as links**: unique candidate for 37 of 550 requests; the anchored window contains the right account for only 3 of 13 scorable samples and misses it in 6
  (`scripts/measure_anchored_window.py`). Timing alone is not ownership; candidates stay diagnostic.
