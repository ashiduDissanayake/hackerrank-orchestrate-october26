# Evaluation report: Ghost Data Still Exists

This is the single authoritative copy (`code/evaluation/evaluation_report.md`); `scripts/package.py` generates the packaging copy.
Numeric blocks between `AUTO` markers are regenerated from the actual evaluation by `python3 scripts/write_reports.py`, so they cannot drift from the code. Everything else is hand-written.

## 1. What was measured, and what the numbers do and do not establish

| data | labels | what it supports |
|---|---|---|
| frozen synthetic fixtures (`code/evaluation/fixtures/synth_v4`; v1 to v3 kept unchanged as history) | yes, written by the author from the contract before the engine ran against them | accuracy, precision/recall, field, evidence and sequence metrics |
| 32 public samples (`dataset/sample_*.csv`) | yes (public answers) | **development / regression data only**. Several cases were inspected while building rules and guards, so this is *not* an untouched holdout |
| 518 evaluation requests | **none** | diagnostics only: status distribution, unresolved counts, evidence coverage. Never reported as accuracy |

Nothing here measures accuracy on the hidden answers. Public sample answers are read only by the scorer and by diagnosis scripts; no expected resource id, label or step feeds prediction logic (the engine never reads them).

### Metric definitions

* **Status accuracy**: predicted `deletion_status` equals the label, per case; plus the gold-to-predicted confusion matrix.
* **Step precision / recall / F1** (micro-averaged over cases, on the multiset of steps): *strict* matches all six fields `(phase, system_id, resource_id, operation, state, evidence_id)`; *lenient* drops `evidence_id`, which isolates citation errors from missing or wrong steps. A duplicate step counts as an extra prediction.
* **Alignment coverage**: share of gold steps for which the prediction has a step with the same `(phase, system_id, resource_id, operation)`.
* **Field accuracy**: over aligned steps, how often `state` and `evidence_id` equal the label.
* **Evidence accuracy**: over gold steps that cite evidence, how often the aligned prediction cites the same `file_id`/`activity_id`/`audit_id`.
* **Sequence**: *exact* = the whole `steps_json` array (including `step_no`) equals the label; *mean LCS* = mean over cases of `2*LCS/(len_gold+len_pred)` on step tuples (both empty counts as 1). Array order is significant in the official grader, so this is reported separately from set-style F1.
* **Contract validity** (`ghostaudit/validate.py`): exact columns, valid JSON, step schema, consecutive numbering, phase/operation/state consistency, canonical order (phase, operation table order, `system_id`, `resource_id`, lexicographic), no duplicates, status rules (COMPLETE = verification only with citations; INCOMPLETE = every finding has a matching remediation **and** verification, every remediation a finding, remediation/verification use an empty `evidence_id`), and every cited id exists and was available at or before the case's `audit_at`.

The scorer itself is tested with a corruption suite (`code/evaluation/test_scoring.py`): known mutations (dropped, extra, duplicated, mis-cited, wrong-field, reordered, renumbered steps, flipped status, missing case) are applied to the public answers and the exact metric effect is asserted; sabotaging the scorer makes those tests fail.

## 2. Results

### 2.1 Frozen fixtures

<!--AUTO:fixtures-->
Fixture set `synth_v4` (frozen, hash-guarded): 31/31 cases pass all checks (25 have a complete labeled answer scored below; the rest are labeled by internal expectations because their correct output is an UNKNOWN state).

| metric | value |
|---|---|
| cases | 25 |
| status accuracy | 1.0000 (25/25) |
| step precision / recall / F1 (strict: all six fields incl. evidence_id) | 1.0000 / 1.0000 / 1.0000 |
| step precision / recall / F1 (lenient: ignores evidence_id) | 1.0000 / 1.0000 / 1.0000 |
| alignment coverage (gold steps with a prediction on the same phase/system/resource/operation) | 1.0000 |
| field accuracy on aligned steps: state / evidence_id | 1.0000 / 1.0000 |
| evidence accuracy (gold steps that cite evidence and got the same citation) | 1.0000 |
| sequence: exact-array match rate | 1.0000 |
| sequence: mean normalized LCS | 1.0000 |
| status confusion (gold->predicted) | COMPLETE->COMPLETE: 11, INCOMPLETE->INCOMPLETE: 11, NOT_APPLICABLE->NOT_APPLICABLE: 3 |
<!--/AUTO:fixtures-->

### 2.2 Public samples (development data, not a holdout)

<!--AUTO:samples-->
Default policy `not_certified` (an unresolved obligation can never become COMPLETE):

| metric | value |
|---|---|
| cases | 32 |
| status accuracy | 1.0000 (32/32) |
| step precision / recall / F1 (strict: all six fields incl. evidence_id) | 1.0000 / 0.8238 / 0.9034 |
| step precision / recall / F1 (lenient: ignores evidence_id) | 1.0000 / 0.8238 / 0.9034 |
| alignment coverage (gold steps with a prediction on the same phase/system/resource/operation) | 0.8238 |
| field accuracy on aligned steps: state / evidence_id | 1.0000 / 1.0000 |
| evidence accuracy (gold steps that cite evidence and got the same citation) | 0.7867 |
| sequence: exact-array match rate | 0.3125 |
| sequence: mean normalized LCS | 0.7984 |
| status confusion (gold->predicted) | COMPLETE->COMPLETE: 10, INCOMPLETE->INCOMPLETE: 22 |

Opt-in ablation `certify_established` (NOT exportable; shown only to quantify what refusing to certify costs): status accuracy 1.0000, strict step F1 0.9034. With the subject-level account proof in place the two policies coincide on the public samples, because no public-sample case is left unresolved.
<!--/AUTO:samples-->

How to read the sample numbers: the lenient and strict scores coincide because every emitted step carries the right citation. Recall is below 1 because the gold answers contain steps for resource ids that no admissible evidence ties to the subject (an old account id that appears only in an activity *claim*, an anonymized analytics record with every identifier null). The engine proves the subject-level *state* (no profile remains) but, by design, never invents or guesses the resource id, so those steps are missing.

<!--AUTO:samples_validity-->
Contract validation of the 32 public-sample rows: 3 errors. Each is a COMPLETE row with zero steps: the subject's only gold steps are an account-absence verification (account resource id never linked to the subject) and an anonymized analytics record, and no retained audit record exists to cite, so the row has nothing the evidence lets the engine name. A COMPLETE row needs at least one verification step, so the contract validator rejects it.

* case_01: COMPLETE must have at least one step
* case_02: COMPLETE must have at least one step
* case_04: COMPLETE must have at least one step
<!--/AUTO:samples_validity-->

### 2.3 The 518 evaluation requests (diagnostics, not accuracy)

<!--AUTO:eval-->
Evidence-only default statuses on the 518 evaluation requests (a diagnostic, NOT accuracy: there are no labels): COMPLETE 147, INCOMPLETE 361, NOT_APPLICABLE 10.
Internal states: COMPLETE 147, INCOMPLETE 353, NOT_APPLICABLE 10, UNDETERMINED 8.

Obligation verdicts by reason (counts of obligations, all cases):

| reason | count |
|---|---|
| record_present | 368 |
| retained_record_present | 311 |
| no_profile_for_subject_in_snapshot | 310 |
| identifiers_exposed | 214 |
| data_flow_active | 113 |
| record_absent | 112 |
| treated_record_present | 38 |
| restore_blocked | 33 |
| data_flow_disabled | 33 |
| restore_allowed | 25 |
| unresolved_link | 24 |
| account_deleted_per_tombstone | 8 |
| retained_record_not_found | 1 |
| no_restore_flag_in_admissible_evidence | 1 |
| conflicting_identity_evidence | 1 |

Cases that remain UNDETERMINED (no violation established, at least one obligation unresolved), grouped by the unresolved reason:

| unresolved reason | cases |
|---|---|
| conflicting_identity_evidence | case_63 |
| no_restore_flag_in_admissible_evidence | case_55 |
| unresolved_link | case_55, case_183, case_343, case_345, case_524, case_530, case_532 |
<!--/AUTO:eval-->

The UNDETERMINED cases are exactly the rows the contract validator rejects (an INCOMPLETE row with no finding, because the output format has no way to say "not determined"); they are why `export` refuses. Every other row passes the full contract validation.

## 3. Additional evaluation cases (independent, fully described)

The cases below are synthetic and fictional. They live in `code/evaluation/fixtures/synth_v4` (v4 = v3 + seven scenarios for relationships, absence, labels and request episodes; v3 = v2 + four proof-boundary scenarios; v2 = v1 + revised labels + four scenarios; every version is hash-frozen; `code/evaluation/test_fixtures_frozen.py` fails if any file changes). Their labels were written from the contract reasoning before the engine was run against them. Each also has an internal expectation file (accepted/rejected links, obligation verdicts, forbidden citations).

**Case A: `fx_case_05` temporal leakage (both halves of the cutoff).** Subject Nirmala Pereira (`user_f05`) asks for deletion; request 2026-06-01, `audit_at` 2026-06-15T12:00Z.
Evidence: `evidence_f01` (inventory, captured 06-01) lists her search entry `search_f05` under her email, so the resource is linked; `evidence_f02` (inventory, 06-14T10:00, scope covers search and security) no longer lists it; `evidence_f03` (account primary+failover snapshot, 06-14T11:00) has no row for her. Two traps: `evidence_f06` is captured on **06-20, after the audit**, and still contains the old `search_f05` row (its *record* time is 06-05); `evidence_f07` is captured **before** the audit but holds a record `search_f05b` observed on **06-16, after** the audit. An engine that filtered only on record time would cite `evidence_f06`; one that filtered only on artifact time would see `search_f05b`.
Expected output: COMPLETE with verification steps only, citing `evidence_f03` (account absent), `evidence_f02` (search absent, audit record present); neither trap artifact may be cited and `search_f05b` must not be linked. Result: passes.

**Case B: `fx_case_16` identity change after the cutoff, plus a lookalike.** Anouk Visser requests deletion with her *old* email. Her audit log shows an email change on **2026-06-20, after `audit_at`**, and the identity snapshot already shows the new email.
Evidence: `evidence_f02` holds `search_f16` under the old email (linked: that address already belonged to her) and `search_f16b` under the **new** email (not hers yet at the evidence's record time, so it must not link). Expected: INCOMPLETE with a finding/remediation/verification chain on `search_f16` only, plus account-absent and audit-present verification. Result: passes. This is what prevents later identifiers from being attached to earlier cases.

**Case C: `fx_case_22` a populated replica is not discharged by a clean primary.** Tobias Eriksen, request 2026-07-01, audit 2026-07-15. `evidence_g04` (July 10) is a primary+failover account snapshot: the primary lists only an unrelated person, but the failover replica also lists a row carrying his user id and email. Expected INCOMPLETE: finding `REPORT_REMAINING_RECORD` on `account_f22` citing `evidence_g04`, delete, verify absent, plus the audit-record verification. This is the replication-drift control for the subject-level account proof: a clean primary must never prove absence while a covered replica holds the subject. Result: passes.

**Case D: `fx_case_23` an unattributable row blocks the proof.** Nadine Okafor, request 2026-04-01, audit 2026-04-15. The only account snapshot (`evidence_g06`, a declared bundle) lists one unrelated person **and** an account row with every identifier null. That row could be hers, so the snapshot cannot exclude it. Expected: internal state UNDETERMINED (account obligation UNKNOWN), never COMPLETE, and no step may name `account_g23x`. Result: passes.

**Case E: `fx_case_25` an empty collection that is not a profile collection.** Ingrid Solberg, request 2026-08-01, audit 2026-08-25. The only account_service capture after the request is a declared bundle for the collection `notification_preferences`, with no records. A system name alone says nothing about which collection was captured, so no profile table was covered. Expected: internal UNDETERMINED, never COMPLETE (the retained audit record is linked and compliant, which is exactly the shape that used to be certified). Result: passes; sabotaging the code to accept any account_service collection flips it to COMPLETE (`scripts/sabotage_account_proof.py`).

**Case F: `fx_case_26` / `fx_case_27` a weakly scoped document export is trusted only for a subject it demonstrably covers.** The export is a primary + reporting-replica document-table capture (scope inferred from rows, weak). In `fx_case_26` (Lucia Ferraro) it holds her audit record in both copies and another user's profile row, so profiles are part of what it exports and her data was included, yet no profile row is hers: expected COMPLETE citing the export for the audit record. In `fx_case_27` (Dmitri Volkov) the same export shape holds nothing about the subject: expected UNDETERMINED, because an export that never mentions someone proves nothing about them. Result: both pass; disabling the per-source promotion flips `fx_case_26` to UNDETERMINED.

**Case G: `fx_case_28` a replica last seen before the request with a row nobody can attribute.** Kofi Boateng, request 2026-11-10, audit 2026-11-25. A clean post-request primary snapshot exists, but the failover replica was last captured on 11-05 with an account row that carries no identifier. It could be his, and nothing shows the replica afterwards. Expected UNDETERMINED, never COMPLETE, and no step may name that row. Result: passes; ignoring pre-request captures (the earlier behaviour) flips it to COMPLETE. This scenario sits in the last month on purpose: an unattributable row is correctly visible to every later case, so it must not leak into the others.

**Case H: `fx_case_29` a source reference reaches an account that nothing else observes.** Astrid Lindqvist, request 2026-01-05, audit 2026-01-25. A search SQL snapshot (`evidence_i01`, 01-10) holds `search_f29` with her email and `source_resource_id = account_f29`; no artifact contains an account row named `account_f29`. A declared inventory (`evidence_i02`, 01-08) with another person's profile row shows the account gone, and it is *older* than the document's indexing time (01-09T22:00): a reference proves neither existence nor creation time. A second document names `account_f29z` and belongs to someone else. Expected INCOMPLETE: finding/remediation/verification for `search_f29`, plus a future `VERIFY_RECORD_ABSENT account_f29` with an empty citation and the audit-record check. This is the public-sample `case_06` pattern. Result: passes; if a referenced resource gets no system, it is silently dropped and the account step disappears (`scripts/sabotage_v4.py`).

**Case I: `fx_case_31` and `fx_case_30` one person, two requests.** Rhea Kapoor asked twice: `fx_case_31` (Dec 1-5, 2025) and `fx_case_30` (Feb 10-25, 2026). The December inventory (`evidence_i03`, 12-03) lists `search_f31` and `audit_record_f31`; the February inventory (`evidence_i04`, 02-15) lists `search_f30` and `audit_record_f30` and not the December records. For the later request the December records are linked only by evidence captured inside the earlier request's window, so they are carried over (no step; `search_f31` is absent in the February snapshot anyway): expected INCOMPLETE with steps for `search_f30` and `audit_record_f30` only, and no citation of `evidence_i03`. The earlier request keeps its own evidence. Result: passes; with episode scoping off, `fx_case_30` gains steps for the earlier episode's resources.

**Case J: `fx_case_32` / `fx_case_33` a treatment label is not a payload.** Both subjects have a tombstone lookup in a ledger with `result: REDACTED`. In `fx_case_32` (Teodor Marin) the returned record carries his email and full name next to the stable user id: expected INCOMPLETE with `REPORT_EXPOSED_PII`, `REDACT_RECORD`, `VERIFY_RECORD_REDACTED`. In `fx_case_33` (Sana Qureshi) the email appears only as the lookup key (`lookup_value`) and the record returns the stable user id only: expected COMPLETE with a redaction verification citing the ledger. Result: both pass; letting the label clear every exposure flips `fx_case_32` to COMPLETE.

**Case K: `fx_case_34` / `fx_case_35` what a later empty capture may and may not erase.** Both subjects have a profile returned with HTTP 200 after the request. In `fx_case_34` (Bruno Teixeira) a later declared-empty `notification_preferences` bundle and a later inventory that names account_service but has no profile table follow: neither captured a profile collection, so the profile stays present (expected INCOMPLETE with finding, `DELETE_RECORD`, absence check). In `fx_case_35` (Mina Abe) the later evidence is an explicit lookup returning 404: valid absence, expected COMPLETE citing that lookup. Result: both pass; accepting any scope as absence evidence flips `fx_case_34`. *Authoring correction before the freeze:* `fx_case_35` was first labeled with a later declared-empty `customer_profiles` bundle as the valid absence; the public sample `case_24` (profile lookup, later declared-empty bundle, answer: present) contradicted that label, and the engine's membership rule was right, so the label, not the engine, was changed.

Further synthetic cases in the same set: a tombstone that still exposes email/hash versus one holding only the stable user id (`fx_case_08`, `fx_case_09`), a historical email_hash link (`fx_case_13`), a near-miss lookalike email (`fx_case_12`), a legal hold present in a replica (`fx_case_15`), a snapshot that predates the request (`fx_case_24`), a scope that excludes the system so absence is not evidenced (`fx_case_07`), and non-deletion requests in English, Spanish and Japanese (`fx_case_01..03`).

Expected outputs and expectations for the cases above (A to K, a representative subset below), regenerated from the frozen files:

<!--AUTO:fixture_cases-->
**fx_case_05** expected: `COMPLETE`

```json
[
 {
  "evidence_id": "evidence_f03",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "account_f05",
  "state": "ABSENT",
  "step_no": 1,
  "system_id": "account_service"
 },
 {
  "evidence_id": "evidence_f02",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "search_f05",
  "state": "ABSENT",
  "step_no": 2,
  "system_id": "search_service"
 },
 {
  "evidence_id": "evidence_f02",
  "operation": "VERIFY_RECORD_PRESENT",
  "phase": "VERIFICATION",
  "resource_id": "audit_record_f05",
  "state": "PRESENT",
  "step_no": 3,
  "system_id": "security_service"
 }
]
```

**fx_case_16** expected: `INCOMPLETE`

```json
[
 {
  "evidence_id": "evidence_f02",
  "operation": "REPORT_REMAINING_RECORD",
  "phase": "FINDING",
  "resource_id": "search_f16",
  "state": "PRESENT",
  "step_no": 1,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "DELETE_RECORD",
  "phase": "REMEDIATION",
  "resource_id": "search_f16",
  "state": "ABSENT",
  "step_no": 2,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "account_f16",
  "state": "ABSENT",
  "step_no": 3,
  "system_id": "account_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "search_f16",
  "state": "ABSENT",
  "step_no": 4,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_PRESENT",
  "phase": "VERIFICATION",
  "resource_id": "audit_record_f16",
  "state": "PRESENT",
  "step_no": 5,
  "system_id": "security_service"
 }
]
```

**fx_case_22** expected: `INCOMPLETE`

```json
[
 {
  "evidence_id": "evidence_g04",
  "operation": "REPORT_REMAINING_RECORD",
  "phase": "FINDING",
  "resource_id": "account_f22",
  "state": "PRESENT",
  "step_no": 1,
  "system_id": "account_service"
 },
 {
  "evidence_id": "",
  "operation": "DELETE_RECORD",
  "phase": "REMEDIATION",
  "resource_id": "account_f22",
  "state": "ABSENT",
  "step_no": 2,
  "system_id": "account_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "account_f22",
  "state": "ABSENT",
  "step_no": 3,
  "system_id": "account_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_PRESENT",
  "phase": "VERIFICATION",
  "resource_id": "audit_record_f22",
  "state": "PRESENT",
  "step_no": 4,
  "system_id": "security_service"
 }
]
```

**fx_case_23** expected: `UNDETERMINED (internal expectation only)`

```json
{
 "intent": "DELETION",
 "links_accepted": [
  "audit_record_f23"
 ],
 "must_not_emit": [
  "any step naming account_g23x",
  "status COMPLETE"
 ],
 "note": "account_g23x carries no identifier, so it could be the subject's: the snapshot cannot exclude it and absence is not proven",
 "obligations": {
  "audit_record_f23": "COMPLIANT",
  "subject_account": "UNKNOWN:unresolved_link"
 },
 "status": "UNDETERMINED"
}
```

**fx_case_25** expected: `UNDETERMINED (internal expectation only)`

```json
{
 "intent": "DELETION",
 "links_accepted": [
  "audit_record_f25"
 ],
 "must_not_emit": [
  "status COMPLETE"
 ],
 "note": "evidence_h02 declares an EMPTY account_service collection, but the collection is notification_preferences: no profile collection was captured",
 "obligations": {
  "audit_record_f25": "COMPLIANT",
  "subject_account": "UNKNOWN:unresolved_link"
 },
 "status": "UNDETERMINED"
}
```

**fx_case_26** expected: `COMPLETE`

```json
[
 {
  "evidence_id": "evidence_h05",
  "operation": "VERIFY_RECORD_PRESENT",
  "phase": "VERIFICATION",
  "resource_id": "audit_record_f26",
  "state": "PRESENT",
  "step_no": 1,
  "system_id": "security_service"
 }
]
```

**fx_case_28** expected: `UNDETERMINED (internal expectation only)`

```json
{
 "intent": "DELETION",
 "links_accepted": [
  "audit_record_f28"
 ],
 "must_not_emit": [
  "any step naming account_g28x",
  "status COMPLETE"
 ],
 "note": "evidence_h04 is a clean post-request primary snapshot, but the failover replica was last captured before the request (evidence_h03) with a row that carries no identifier: it could be the subject's and nothing shows its state afterwards",
 "obligations": {
  "audit_record_f28": "COMPLIANT",
  "subject_account": "UNKNOWN:unresolved_link"
 },
 "status": "UNDETERMINED"
}
```

**fx_case_29** expected: `INCOMPLETE`

```json
[
 {
  "evidence_id": "evidence_i01",
  "operation": "REPORT_REMAINING_RECORD",
  "phase": "FINDING",
  "resource_id": "search_f29",
  "state": "PRESENT",
  "step_no": 1,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "DELETE_RECORD",
  "phase": "REMEDIATION",
  "resource_id": "search_f29",
  "state": "ABSENT",
  "step_no": 2,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "account_f29",
  "state": "ABSENT",
  "step_no": 3,
  "system_id": "account_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "search_f29",
  "state": "ABSENT",
  "step_no": 4,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_PRESENT",
  "phase": "VERIFICATION",
  "resource_id": "audit_record_f29",
  "state": "PRESENT",
  "step_no": 5,
  "system_id": "security_service"
 }
]
```

**fx_case_30** expected: `INCOMPLETE`

```json
[
 {
  "evidence_id": "evidence_i04",
  "operation": "REPORT_REMAINING_RECORD",
  "phase": "FINDING",
  "resource_id": "search_f30",
  "state": "PRESENT",
  "step_no": 1,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "DELETE_RECORD",
  "phase": "REMEDIATION",
  "resource_id": "search_f30",
  "state": "ABSENT",
  "step_no": 2,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "search_f30",
  "state": "ABSENT",
  "step_no": 3,
  "system_id": "search_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_PRESENT",
  "phase": "VERIFICATION",
  "resource_id": "audit_record_f30",
  "state": "PRESENT",
  "step_no": 4,
  "system_id": "security_service"
 }
]
```

**fx_case_32** expected: `INCOMPLETE`

```json
[
 {
  "evidence_id": "evidence_i05",
  "operation": "REPORT_EXPOSED_PII",
  "phase": "FINDING",
  "resource_id": "tombstone_f32",
  "state": "PRESENT",
  "step_no": 1,
  "system_id": "identity_service"
 },
 {
  "evidence_id": "",
  "operation": "REDACT_RECORD",
  "phase": "REMEDIATION",
  "resource_id": "tombstone_f32",
  "state": "REDACTED",
  "step_no": 2,
  "system_id": "identity_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_PRESENT",
  "phase": "VERIFICATION",
  "resource_id": "audit_record_f32",
  "state": "PRESENT",
  "step_no": 3,
  "system_id": "security_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_REDACTED",
  "phase": "VERIFICATION",
  "resource_id": "tombstone_f32",
  "state": "REDACTED",
  "step_no": 4,
  "system_id": "identity_service"
 }
]
```

**fx_case_34** expected: `INCOMPLETE`

```json
[
 {
  "evidence_id": "evidence_i09",
  "operation": "REPORT_REMAINING_RECORD",
  "phase": "FINDING",
  "resource_id": "account_f34",
  "state": "PRESENT",
  "step_no": 1,
  "system_id": "account_service"
 },
 {
  "evidence_id": "",
  "operation": "DELETE_RECORD",
  "phase": "REMEDIATION",
  "resource_id": "account_f34",
  "state": "ABSENT",
  "step_no": 2,
  "system_id": "account_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_ABSENT",
  "phase": "VERIFICATION",
  "resource_id": "account_f34",
  "state": "ABSENT",
  "step_no": 3,
  "system_id": "account_service"
 },
 {
  "evidence_id": "",
  "operation": "VERIFY_RECORD_PRESENT",
  "phase": "VERIFICATION",
  "resource_id": "audit_record_f34",
  "state": "PRESENT",
  "step_no": 4,
  "system_id": "security_service"
 }
]
```

<!--/AUTO:fixture_cases-->

## 4. Failures found and improvements made

Every row was found by a test, a measurement or a review, and has a regression test. Full reasoning is in `code/docs/DECISIONS.md`.

| failure found | how it was found | improvement |
|---|---|---|
| Unknown obligations were reported COMPLETE under the default policy (112 cases) | external review, reproduced as a counterexample | default policy never certifies; certifying kept only as an opt-in ablation; export gate refuses |
| Committed CSV did not regenerate from the committed defaults | external review | run manifests (command, config, input and code hashes, commit), `verify`, and an export gate that is the only writer of the submission path |
| Phone in message text and an analytics record with `subject_reference` passed as redacted/anonymized | external review | exposure checks use one shared normalization over any text field, and any user-reference token makes analytics attributable |
| Tombstone classified as an ordinary profile (deleted its stable reference) | external review | category precedence: explicit record type, then collection, resource prefix, event kind, and only last the owning system |
| Intent: mixed instructions misread ("delete my account but keep records the policy requires", "remove me from the newsletter and keep my account") | external review | clause-level classification (action, negation, object class) |
| Evaluator exit code ignored the labeled run; INCOMPLETE rows with only a finding validated | external review | `all` fails on any suite or fixture failure; chain validation of finding/remediation/verification |
| Stale absence counted as evidence | fixture `fx_case_07` | absence older than the earliest link evidence is ignored |
| A fixture was mis-authored (activity row outside the chosen window) | first engine run | corrected openly with a new frozen manifest; v1 kept; the same run found a real engine flaw |
| Provenance text (screen title, notes) created identifier links | OCR/transcription work | provenance fields are never scanned |
| Lookup-key matches linked near-miss records | transcription work | a key-only link is rejected if the returned record shows another identity; a catalog link contradicted by the record is an explicit conflict |
| A statement PDF printing a catalog label had no resource id | case_33 diagnosis | catalog-label join, with availability raised to the catalog row's time |
| Phones written in free text could be checked but not linked | review follow-up | one normalization module used by indexing, linking and exposure, with guards against order numbers and names |
| Subject-level account proof: row matching compared phones by exact equality and counted superseded snapshot rows as direct presence | the proof's own regression tests | shared phone rule; only evidence after the request and outside evaluated snapshots counts as direct presence |
| Two public samples showed the proof could claim absence while the account existed | validation against known account states | weak scope may never support absence but never hides presence; direct profile evidence outranks a population-level snapshot; the proof is consulted only when no account resource is linked |
| A resource named only by a linked record's `source_resource_id` (sample case_06 / `account_006`) was linked with no system, so policy evaluation returned nothing and the account was silently dropped; the M2b diagnostic made the same mistake and called it unreachable | independent review, reproduced with failing regressions | source references followed to a fixed point (cycle-safe, provenance kept); system from observations then the id namespace (`Link.system_basis`); `Link.since()` ignores source references; an unresolvable category is an explicit UNKNOWN; the diagnostic runs the production linker |
| Scope-based absence of an already linked resource ignored the completeness, collection and coverage checks that the account proof applies (a later empty `notification_preferences` scope, an incomplete export or a weak export could erase a present linked profile and the case came out COMPLETE) | independent review, reproduced | one shared standard (`coverage_rules.py`) for both paths: category-holding table, complete source, strong or per-source promoted scope. Inventory `support_records` holds messages only (all 33 rows), so it no longer erases an attachment (eval `case_34` / `support_9538`) |
| A REDACTED / ANONYMIZED label cleared every detected exposure, including identifiers in the returned payload | independent review, reproduced | the label discounts query metadata only (`QUERY_FIELDS`); real-data effect: none of the 17 treatment-result observations changes (stated, not claimed as an accuracy gain) |
| Evidence of an earlier request leaked into a later request by the same person (sample `object_19`, `account_6523`; eval `export_1260`) | sample diagnosis, repeated-request structure | request-episode scoping from the subject's own request history; a present carried-over record becomes UNKNOWN, never hidden |
| A relaxation of the collection-membership rule (to let a declared-empty profile bundle erase a looked-up profile) | tried and measured | rejected: 5 public-sample COMPLETE cases became INCOMPLETE and `case_24`'s profile was erased; the fixture label that assumed it was corrected before the freeze |
| Readiness conflated status with completeness: 18 cases are INCOMPLETE on proven violations yet carry unresolved obligations | independent review | manifest `plan_gap_cases` / `cases_with_unresolved_obligations`; `export` refuses plan gaps unless `--accept-plan-gaps`; the register lists both groups |
| `fx_case_14/17` labels encoded "unlinkable id means unresolved obligation" | closeout review | v2 fixtures with revised labels written before running the engine; v1 retained |
| A declared-EMPTY non-profile collection (`notification_preferences`) discharged the profile obligation, so a retained audit record then yielded COMPLETE | independent review, reproduced as unit and file-level fixtures | a snapshot supports absence only if it evidences a profile collection (`ScopeDecl.captured`), a strong scope and a complete source; non-profile rows neither prove nor disprove anything |
| A clean post-request primary hid a failover replica last captured with an unattributable row (COMPLETE with the replica listed as "uncovered") | independent review, reproduced | every capture of every copy contributes an event; a copy whose latest evidence is an unattributable row, a pre-request presence, or a lagging absence is unaccounted and blocks the proof; a copy with attributable rows and no subject is excluded with a stated basis |
| README sample-scoring example compared the 518-case output with the 32 labeled samples | independent review | README commands fixed; `score` now fails when the case sets are disjoint and warns on partial overlap (tested) |
| The export gate required a clean whole tree, mixing documentation with producing code; reports could describe a cached manifest of older code | closeout review | the manifest records `dirty_code_files` and per-file code hashes; the gate refuses only when a prediction-affecting file differs from the commit; `write_reports.py` always regenerates the run and `--check` flags a stale manifest |

Hypotheses that were measured and **not** adopted, because the measurements did not support them: accepting activity-window candidates as links (unique candidate for only 37 of 550 requests; anchoring the window on the case's own resources leaves the right account absent from the candidates in 6 of 13 samples), and scoping out already-absent pre-request resources (one supporting case, no contradiction, too thin).

## 5. Subject-level account proof: gates, boundaries and sensitivity

The proof answers "does an authoritative account snapshot, queried by the subject's identifiers, contain a profile for this subject, and can every copy that might hold one be accounted for?" without needing the original account resource id. It is consulted only when no account resource is linked, and it never emits a step (no resource id is evidenced).

**What a capture must be to support absence** (all must hold): it evidences a *profile collection or table* (an inventory that declares account_service but lacks the profile table, or a declared empty `notification_preferences`, does not count), its scope is strong (declared, or the account table itself) or promoted per source (below), its source is complete (SQL transaction committed and the inventory completion marker present; a declared record count must equal the records held), and it was captured at or after the request. Only profile rows count; every profile row of the copy must carry an identifier, otherwise the copy is indeterminate (an unattributable row could be the subject's); rows hidden by the cutoff do the same.

**Per-copy accounting.** Every capture of every copy contributes an event; the latest event of a copy decides it. The proof is ABSENT only if the primary's latest event is a supporting post-request absence, no copy's latest event is a post-request presence, and no copy is *unaccounted*: a copy is unaccounted if its latest evidence is an unattributable row, a presence before the request that was never captured again, or an absence that lags a peer (another copy of the same capture, or an earlier sighting, shows the subject while this copy does not, so replication may still land). A copy whose latest capture shows attributable rows and none for the subject is *excluded* with that stated basis ("never evidenced to hold the subject"). Copies seen only in other cases' captures contribute nothing about this subject: they are listed as `uncovered` for transparency and never asserted. That is a modelling assumption (a replica that was never captured for the subject is not known to hold anything), recorded as such.

**One standard for both reasoning paths (2026-10-25).** The state of an already linked resource and the subject-level proof now use the same absence rule (`coverage_rules.absence_support`). Valid explicit 404s and authoritative complete snapshots are preserved (an empty profile *table* is valid absence; no positive-control row is required). COMMIT or a matching row count prove only that a file is whole, not that it is unfiltered or authoritative for every subject, so they gate nothing beyond completeness. Collection-scoped bundles are per-batch extracts and apply only to records known to belong to them; that membership rule was measured against its relaxation (see section 4).

**Per-source promotion of weak document exports.** A document-table export declares no collection list; its scope is inferred from the systems seen in its rows, so it is a weak claim. It is promoted to a supporting capture for *this subject* only when (a) the export demonstrably includes profile rows (the collection is part of what it exports) and (b) the same copy holds records about the subject in other collections (the subject's data was included in the extract, so a missing profile row is an omission by the datastore, not by the extract), and the source is complete. An export that never mentions the subject proves nothing about them (`fx_case_27`). The switch is never enabled globally: the optional global "weak scopes" setting remains off.

Measured effect of the 2026-10-25 boundary fixes, comparing the full 518-row output of the previously reviewed commit (it reproduces `97993dfc…`) with the current code, row by row:

* the two review findings alone reopened **no** case: every previously discharged proof already rested on a profile collection and had no unattributable or lagging copy in the real data (the new behaviour is exercised by unit tests and fixtures `fx_case_25` and `fx_case_28`, and the sabotage check shows those fail under the old rules);
* per-source promotion changed exactly **one** row: `case_462` went from INCOMPLETE (no finding, contract-invalid) to COMPLETE with one verification step. Its post-request document export (`evidence_43`, captured exactly at `audit_at`) holds the subject's own audit record in both copies and exports profile rows of other users, with no profile row for the subject;
* every other row is byte-identical.

**Inspected cases.** `case_45` and `case_64` list a failover replica whose last capture (`evidence_54`, 2026-09-02T23:00Z) predates their requests. That capture has four attributable rows, none for the subject, and the subject was never evidenced in any copy before it, so the replica is excluded with the stated basis rather than blocking. This is the one judgment call that the data cannot settle: if pre-request captures were never allowed to exclude a replica, `case_45` and `case_64` would become unresolved, and so would one *public sample* (`case_21`) whose public answer is COMPLETE with exactly this pattern. That sample is development data, not independent proof, but it agrees with the default.

**Effect of the relationship, absence, label and episode fixes**, comparing the full 518-row output of the previously reviewed commit `485f684` (hash `443edff0…`) with the current code, row by row:

* two rows change, both in a stated direction: `case_33` loses the `export_1260` absence verification (carried over to the earlier request `case_52`), and `case_34` gains a finding and remediation for the attachment `support_9538` (an inventory that only captures messages no longer erases it; the latest evidence is a PII scan hit on 2026-09-15 and a UI reference listing it on 2026-09-26);
* no status changes; all 8 undetermined statuses are unchanged, and the REDACTED/ANONYMIZED-label fix changes no real row (none of the 17 treatment-result observations carries a contradicting payload);
* public samples: strict steps TP/FP/FN 158/4/35 -> 159/0/34, exact answers 8 -> 10 of 32, status 32/32 (the case_06 link and the episode scoping were found through the sample diagnosis, so this is development evidence).

<!--AUTO:proof_stats-->
Subject-level discharges in the real run: 310 of 518 requests (plus 8 by a DELETED tombstone).
* proofs whose latest primary or replica capture is a **weakly scoped document export promoted per source** (it holds the subject's own records and exports profile rows): 86
* proofs that exclude at least one replica whose latest capture predates the request and shows attributable rows without the subject: 8 (case_45, case_47, case_48, case_49, case_62, case_63, case_64, case_65); of these COMPLETE: case_45, case_64
* proofs of which every copy used is a declared capture: 207
<!--/AUTO:proof_stats-->

Optional switches, measured (sample counts are development data; eval counts are diagnostics; "false-absence" compares against the public answers' known account state; **no variant claims an absent account where a sample shows one**):

<!--AUTO:sensitivity-->
```text
== samples (development data)
   default (strong scopes, empty tables allowed)    {'COMPLETE': 10, 'INCOMPLETE': 22}  false-absence vs gold: 0; strict TP/FP/FN 159/0/34, exact 10/32
   + weak scopes (inferred_from_rows)               {'COMPLETE': 10, 'INCOMPLETE': 22}  false-absence vs gold: 0; strict TP/FP/FN 159/0/34, exact 10/32
   + require an account row in the artifact         {'COMPLETE': 4, 'INCOMPLETE': 22, 'UNDETERMINED': 6}  false-absence vs gold: 0; strict TP/FP/FN 145/14/48, exact 10/32
   weak + require_row                               {'COMPLETE': 4, 'INCOMPLETE': 22, 'UNDETERMINED': 6}  false-absence vs gold: 0; strict TP/FP/FN 145/14/48, exact 10/32
   no exclusion on pre-request-only copy captures   {'COMPLETE': 9, 'INCOMPLETE': 22, 'UNDETERMINED': 1}  false-absence vs gold: 0; strict TP/FP/FN 158/1/35, exact 10/32
   no per-source promotion of weak document exports {'COMPLETE': 10, 'INCOMPLETE': 22}  false-absence vs gold: 0; strict TP/FP/FN 159/0/34, exact 10/32
   no request-episode scoping (carried-over evidence stays in scope) {'COMPLETE': 10, 'INCOMPLETE': 22}  false-absence vs gold: 0; strict TP/FP/FN 159/4/34, exact 9/32
== eval (unlabeled diagnostics)
   default (strong scopes, empty tables allowed)    {'COMPLETE': 147, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 8}
   + weak scopes (inferred_from_rows)               {'COMPLETE': 150, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 5}
   + require an account row in the artifact         {'COMPLETE': 123, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 32}
   weak + require_row                               {'COMPLETE': 128, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 27}
   no exclusion on pre-request-only copy captures   {'COMPLETE': 145, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 10}
   no per-source promotion of weak document exports {'COMPLETE': 146, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 9}
   no request-episode scoping (carried-over evidence stays in scope) {'COMPLETE': 147, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 8}
```
<!--/AUTO:sensitivity-->

The default keeps strong or per-source promoted scopes only and allows declared-empty profile tables. Requiring a positive-control row would flip 6 correct sample COMPLETEs to unresolved. Snapshots hold 1 to 4 rows each (case-focused extracts, not full tables), so "the snapshot declares coverage of the profile table" is a stated assumption, not something the data proves. The public samples contain one counterexample to trusting an empty declared snapshot over direct evidence (a profile lookup at 09:41 followed by a declared-empty bundle at 12:00), which is why direct evidence outranks it.

## 6. Remaining unresolved cases and limitations

Eight cases have an undetermined *status* (internal UNDETERMINED; the output has no status for them) and 18 more are INCOMPLETE on proven violations but carry unresolved obligations, so their investigation or plan has gaps; the register below lists both groups apart. There is **no certified root `output.csv`**: the strict export refuses while any remain. Each is a documented, reproducible gap in the supplied evidence, not an implementation gap; every one was re-investigated from the original evidence after the boundary fixes (`python3 code/main.py explain case_524`, and the register below).

* **No profile-table capture after the request** (`case_183`, `case_343`, `case_345`; the latest supporting capture predates the request by hours to days, and the later document exports in the window contain nothing about the subject): a capture before the request cannot show the post-request state, and an export that never mentions the subject says nothing about them. `case_524`, `case_530`, `case_532` (audit 2026-01-29T12:00Z) have no admissible capture of any copy at the cutoff. The one bundle that covers that period (`evidence_49`) is captured and exported on 2026-01-31T15:00Z according to both the manifest and its own header, two days after the audit, although the snapshot times inside it equal the audit time. The contract excludes evidence captured after `audit_at`, and the strict dual-time rule (user decision U11) treats the artifact time as binding, so it is not used; reading the inner record time instead would be a relaxation of that rule and is recorded as an open decision, not adopted. `case_55` has no profile-table capture after its request either (the latest, `evidence_35`, is from 2026-04-16, before the 2026-04-27 request).
* **Restore state not shown** (`case_55`, `backup_9287`): the only admissible evidence is the recovery-console screenshot (`evidence_32`, 2026-04-29), which shows the archive, its account email, path, checksum, retention and last drill, and no restore-allowed or restore-blocked state for any archive. A log line stating that the archive is restore-eligible and an activity row for a later restore both post-date the audit cutoff, and a restore of another archive says nothing about this one. Inferring restorability from the console would be an interpretation, so the obligation stays UNKNOWN.
* **Source conflict** (`case_63`, `marketing_001`): the screenshot (`evidence_60`, captured 2026-09-16T07:20Z) shows Soo-jin Park, `sj.park@naver.com`, `+82 10-5837-9451`; the catalog row `activity_4008` (07:27:01Z, itself an activity claim) links the same resource to Kwame Mensah / `user_09`. Soo-jin Park appears in no identity, audit-log or activity row, and no admissible evidence shows the record changing between the two times, so neither a temporal explanation (an overwrite after the screenshot) nor an identity explanation (an alias or a prior email of the subject) is supported. No supplied rule gives either source precedence, so the contradiction is preserved. If the record is the subject's, rule_10 (MARKETING_PROFILE, DELETE) makes the case INCOMPLETE with a finding on `marketing_001`; if it is not, no marketing obligation exists. The evidence cannot tell which.

<!--AUTO:best_effort-->
`python3 code/main.py best-effort` writes `output_best_effort.csv` (all 518 rows), `output_best_effort.unresolved.json` and `output_best_effort.manifest.json` (`certified: false`, every validation error). It is a review artifact, never the submission.

**8 cases whose status rests on an unresolved obligation** (the row is contract-invalid by construction):

| case | missing fact |
|---|---|
| case_55 | the restore permission of backup_9287 at audit_at 2026-04-30T11:00:00Z is not shown by any admissible evidence (screens that list the archive show no restore-allowed/blocked state; later logs and activity are after the cutoff) |
| case_55 | no admissible capture of an account profile collection between requested_at 2026-04-27T06:00:00Z and audit_at 2026-04-30T11:00:00Z establishes whether a profile for the subject remains (proof status NO_COVERAGE: the primary copy's latest supporting profile-table capture (evidence_35, 2026-04-16T06:00:00Z) predates the request) |
| case_63 | marketing_001: record shows email=sj.park@naver.com, phone=821058379451 but the data catalog ties the resource to the subject; neither source supersedes the other |
| case_183 | no admissible capture of an account profile collection between requested_at 2026-07-07T11:00:00Z and audit_at 2026-07-18T11:00:00Z establishes whether a profile for the subject remains (proof status NO_COVERAGE: the primary copy's latest supporting profile-table capture (evidence_81, 2026-07-03T07:43:56Z) predates the request); 2 deletion-worker activity rows in the request window name account resources, but they are claims shared with other requests and carry no identifier, so none is linked to the subject |
| case_343 | no admissible capture of an account profile collection between requested_at 2026-04-18T09:00:00Z and audit_at 2026-04-29T09:00:00Z establishes whether a profile for the subject remains (proof status NO_COVERAGE: the primary copy's latest supporting profile-table capture (evidence_35, 2026-04-16T06:00:00Z) predates the request); 1 deletion-worker activity rows in the request window name account resources, but they are claims shared with other requests and carry no identifier, so none is linked to the subject |
| case_345 | no admissible capture of an account profile collection between requested_at 2026-04-16T09:00:00Z and audit_at 2026-04-29T09:00:00Z establishes whether a profile for the subject remains (proof status NO_COVERAGE: the primary copy's latest supporting profile-table capture (evidence_35, 2026-04-16T06:00:00Z) predates the request); 3 deletion-worker activity rows in the request window name account resources, but they are claims shared with other requests and carry no identifier, so none is linked to the subject |
| case_524 | no admissible capture of an account profile collection between requested_at 2026-01-17T12:00:00Z and audit_at 2026-01-29T12:00:00Z establishes whether a profile for the subject remains (proof status NO_COVERAGE: no admissible profile-table capture of any copy exists at the audit cutoff); 3 deletion-worker activity rows in the request window name account resources, but they are claims shared with other requests and carry no identifier, so none is linked to the subject |
| case_530 | no admissible capture of an account profile collection between requested_at 2026-01-11T12:00:00Z and audit_at 2026-01-29T12:00:00Z establishes whether a profile for the subject remains (proof status NO_COVERAGE: no admissible profile-table capture of any copy exists at the audit cutoff); 3 deletion-worker activity rows in the request window name account resources, but they are claims shared with other requests and carry no identifier, so none is linked to the subject |
| case_532 | no admissible capture of an account profile collection between requested_at 2026-01-09T12:00:00Z and audit_at 2026-01-29T12:00:00Z establishes whether a profile for the subject remains (proof status NO_COVERAGE: no admissible profile-table capture of any copy exists at the audit cutoff); 3 deletion-worker activity rows in the request window name account resources, but they are claims shared with other requests and carry no identifier, so none is linked to the subject |

**18 cases that are INCOMPLETE on established violations** and also carry an unresolved obligation (the plan may be missing the unresolved items): case_33, case_34, case_35, case_39, case_50, case_102, case_143, case_144, case_184, case_185, case_186, case_282, case_344, case_526, case_527, case_528, case_529, case_531.
<!--/AUTO:best_effort-->

Other limitations: the PNG transcriptions are hand-authored (hash-bound and OCR-cross-checked, not regenerated by code); the intent classifier is a deterministic clause-level heuristic with no labeled non-deletion examples to measure its precision; phone matching by a 9-digit national suffix could in principle collide with an unrelated number; step recall is limited by resource ids the data never links to the subject; and a COMPLETE row with no citable verification step cannot be valid (three public samples are in that position, section 2.2). Official issue #11 (missing provenance and ambiguous timestamps) was withdrawn by its author on 2026-10-24 with no organizer reply, so no clarification of these gaps exists.

## 7. Reproducing

```text
python3 code/evaluation/main.py all            # all test suites + labeled evaluation; non-zero exit on any failure
python3 code/main.py run                       # provisional output + manifest under runs/provisional/
python3 code/main.py verify runs/provisional/output.manifest.json   # byte-identical regeneration, unchanged inputs and code
python3 code/main.py export                    # the only writer of ./output.csv; refuses unless every gate passes
python3 code/main.py best-effort               # review artifact output_best_effort.* (certified=false) when export must refuse
python3 code/main.py run --requests sample_deletion_requests.csv --out runs/samples/output.csv
python3 code/evaluation/main.py score --pred runs/samples/output.csv --gold dataset/sample_output.csv   # public samples only
python3 scripts/write_reports.py               # refresh the numeric blocks in this file and usage_report.md
```

The run these numbers describe:

<!--AUTO:manifest-->
| field | value |
|---|---|
| command | `python3 code/main.py candidate` |
| configuration | `{"account_proof": {"allow_weak": false, "episode_scoping": true, "pre_request_exclusion": true, "require_row": false, "weak_promotion": true}, "data": "dataset", "png_extraction": "complete", "png_method": "hand-authored visual transcription bound by sha256, cross-checked against local OCR (code/ghostaudit/image_transcriptions)", "requests": "deletion_requests.csv", "unknown_policy": "not_certified", "workflow_config": {"after_seconds": 600, "before_seconds": 5400, "min_margin": 0.0, "scoring": "contextual_v3"}, "workflow_mode": "joint"}` |
| producing commit (HEAD when the run was made) | `2edab59a72b8` |
| prediction-affecting files differing from that commit | none (the code hash below identifies the exact code either way) |
| other uncommitted files at run time (reports, docs, tests, packaging; cannot change the output) | 6 |
| output.csv sha256 | `f32fd414316b4511da8d2744fbdb1f6e7ddb7dbb115dac3c0a208506aa6f2ae9` |
| code sha256 (45 files: all of code/ghostaudit incl. image transcriptions, main.py, requirements) | `0918ae6d02fda055dfe2b4087823f953025525a5e66c1c880bb805cb2012a642` |
| input files hashed | 103 (dataset csv + evidence); combined listing in the manifest |
| rows | 518 |
| statuses | {'COMPLETE': 152, 'INCOMPLETE': 356, 'NOT_APPLICABLE': 10} |
| contract-valid | False (3 validation errors) |
| UNDETERMINED cases | 3: case_55, case_63, case_345 |
| runtime model calls | 0 |
| final (exported) | False |
<!--/AUTO:manifest-->

## 8. Optional workflow-attribution experiment

<!--AUTO:workflow-->
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
<!--/AUTO:workflow-->

Details and at least three independent synthetic controls are recorded directly in `code/evaluation/workflow_report.md`; regenerate them with `python3 scripts/evaluate_workflow.py`.

The new inference experiment is opt-in and cannot pass strict export. Its development gain comes from candidate attribution, not from changing the evidence-time rule. Two additional source/episode regressions were fixed: source cycles must remain reachable from an accepted identity root, and evidence from before an earlier request cannot be assigned to its investigation window. The fixture best-effort CLI test now uses a temporary artifact directory and asserts that root artifacts remain unchanged.

## 9. Requested prediction candidate and exact remaining requirements

<!--AUTO:candidate-->
The explicit `candidate` command writes repository-root `output.csv`, `output.manifest.json` and `output.unresolved.json`. The CSV contains 518 data rows and the required three columns. Its manifest records `kind=submission_candidate`, `certified=false`, 3 semantic validation errors, 3 undetermined statuses (case_55, case_63, case_345), and 18 established INCOMPLETE cases with unresolved plan items. No unknown obligation was turned into a finding to clear validation. This file is a disclosed candidate and is not fully contract-conforming while those errors remain. The certification label belongs to this implementation; it is not a HackerRank credential. `code/docs/WORKFLOW_GAPS.md` lists every remaining public-sample discrepancy and its exact evidence requirement.
<!--/AUTO:candidate-->

Context v2 adds independent synthetic controls directly in `code/tests/test_workflow_context.py`: a scheduler whose period must be inferred as 17 seconds from three fictional operations; two subjects with distinct clock phases that distinguish anonymous policy records; same-clock ambiguity that must remain unresolved; and post-cutoff identity anchors that must remain invisible. A further artifact control verifies that `output.csv` retains all unresolved rows/errors and cannot overwrite an existing certified file. These cases supplement the earlier frozen fixtures; they do not use public labels.

## 10. Phase 1 account-link interactions

The label-free investigation and equally optimal assignment witnesses are recorded in `code/docs/ACCOUNT_LINK_PHASE1.md` and reproduced by `python3 scripts/audit_account_links.py`. Four of seven previously ambiguous account matches are accepted as inferences under context v3. This closes three full public answers and adds four matching steps; the public-development gain is 19/32 -> 22/32 exact and 178/0/15 -> 182/0/11 matching/extra/missing steps. No hidden accuracy or proven ownership is claimed. Cases 23, 31 and 32 retain multiple score-optimal alternatives.

Additional fictional controls are implemented in `code/tests/test_account_ranking.py`:

- **Joint state affinity:** two equally timed requests and two unowned profile operations are tied in v2. One case has independently compliant linked records and one profile has a current explicit absent lookup. V3 ranks that pair while the unobserved profile remains an ownership hypothesis; claims do not become state evidence.
- **Independent anchors:** two unowned profiles are both observed absent. Three stable-reference-linked policy resources support one request. V3 uses that independent context to distinguish the assignments, including after request renaming and input shuffling.
- **Temporal and replica controls:** a lookup captured after the cutoff, one predating the request, a broad inventory omission, later presence and a populated replica supply no absence affinity. Four retries of one resource do not count as three independent anchors.
- **Ambiguity witnesses:** equal global assignments publish both alternatives; a weaker assignment is not marked equally optimal; a null assignment remains available when every proposed edge is worse.

Queue-order calibration uses only explicit account ownership and in-window operations visible by the target cutoff: 72 FIFO and 70 reverse-order pairs across 125 batches (overlapping descriptive pairs, not independent trials). No queue-order rule was adopted. Alternate numeric references were inspected and belonged to other namespaces or unrelated subjects/activities, so no suffix-based ownership rule was added.
