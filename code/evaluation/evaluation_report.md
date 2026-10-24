# Evaluation report: Ghost Data Still Exists

This is the single authoritative copy (`code/evaluation/evaluation_report.md`); `scripts/package.py` generates the packaging copy.
Numeric blocks between `AUTO` markers are regenerated from the actual evaluation by `python3 scripts/write_reports.py`, so they cannot drift from the code. Everything else is hand-written.

## 1. What was measured, and what the numbers do and do not establish

| data | labels | what it supports |
|---|---|---|
| frozen synthetic fixtures (`code/evaluation/fixtures/synth_v2`, v1 kept as history) | yes, written by the author from the contract before the engine ran against them | accuracy, precision/recall, field, evidence and sequence metrics |
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
Fixture set `synth_v2` (frozen, hash-guarded): 20/20 cases pass all checks (17 have a complete labeled answer scored below; the rest are labeled by internal expectations because their correct output is an UNKNOWN state).

| metric | value |
|---|---|
| cases | 17 |
| status accuracy | 1.0000 (17/17) |
| step precision / recall / F1 (strict: all six fields incl. evidence_id) | 1.0000 / 1.0000 / 1.0000 |
| step precision / recall / F1 (lenient: ignores evidence_id) | 1.0000 / 1.0000 / 1.0000 |
| alignment coverage (gold steps with a prediction on the same phase/system/resource/operation) | 1.0000 |
| field accuracy on aligned steps: state / evidence_id | 1.0000 / 1.0000 |
| evidence accuracy (gold steps that cite evidence and got the same citation) | 1.0000 |
| sequence: exact-array match rate | 1.0000 |
| sequence: mean normalized LCS | 1.0000 |
| status confusion (gold->predicted) | COMPLETE->COMPLETE: 8, INCOMPLETE->INCOMPLETE: 6, NOT_APPLICABLE->NOT_APPLICABLE: 3 |
<!--/AUTO:fixtures-->

### 2.2 Public samples (development data, not a holdout)

<!--AUTO:samples-->
Default policy `not_certified` (an unresolved obligation can never become COMPLETE):

| metric | value |
|---|---|
| cases | 32 |
| status accuracy | 1.0000 (32/32) |
| step precision / recall / F1 (strict: all six fields incl. evidence_id) | 0.9753 / 0.8187 / 0.8901 |
| step precision / recall / F1 (lenient: ignores evidence_id) | 0.9753 / 0.8187 / 0.8901 |
| alignment coverage (gold steps with a prediction on the same phase/system/resource/operation) | 0.8187 |
| field accuracy on aligned steps: state / evidence_id | 1.0000 / 1.0000 |
| evidence accuracy (gold steps that cite evidence and got the same citation) | 0.7867 |
| sequence: exact-array match rate | 0.2500 |
| sequence: mean normalized LCS | 0.7831 |
| status confusion (gold->predicted) | COMPLETE->COMPLETE: 10, INCOMPLETE->INCOMPLETE: 22 |

Opt-in ablation `certify_established` (NOT exportable; shown only to quantify what refusing to certify costs): status accuracy 1.0000, strict step F1 0.8901. With the subject-level account proof in place the two policies coincide on the public samples, because no public-sample case is left unresolved.
<!--/AUTO:samples-->

How to read the sample numbers: the lenient and strict scores coincide because every emitted step carries the right citation. Recall is below 1 because the gold answers contain steps for resource ids that no admissible evidence ties to the subject (an old account id that appears only in an activity *claim*, an anonymized analytics record with every identifier null). The engine proves the subject-level *state* (no profile remains) but, by design, never invents or guesses the resource id, so those steps are missing.

### 2.3 The 518 evaluation requests (diagnostics, not accuracy)

<!--AUTO:eval-->
Output statuses on the 518 evaluation requests (a diagnostic, NOT accuracy: there are no labels): COMPLETE 146, INCOMPLETE 362, NOT_APPLICABLE 10.
Internal states: COMPLETE 146, INCOMPLETE 353, NOT_APPLICABLE 10, UNDETERMINED 9.

Obligation verdicts by reason (counts of obligations, all cases):

| reason | count |
|---|---|
| record_present | 367 |
| retained_record_present | 311 |
| no_profile_for_subject_in_snapshot | 309 |
| identifiers_exposed | 214 |
| record_absent | 114 |
| data_flow_active | 113 |
| treated_record_present | 38 |
| restore_blocked | 33 |
| data_flow_disabled | 33 |
| unresolved_link | 25 |
| restore_allowed | 25 |
| account_deleted_per_tombstone | 8 |
| retained_record_not_found | 1 |
| no_restore_flag_in_admissible_evidence | 1 |
| conflicting_identity_evidence | 1 |

Cases that remain UNDETERMINED (no violation established, at least one obligation unresolved), grouped by the unresolved reason:

| unresolved reason | cases |
|---|---|
| conflicting_identity_evidence | case_63 |
| no_restore_flag_in_admissible_evidence | case_55 |
| unresolved_link | case_55, case_183, case_343, case_345, case_462, case_524, case_530, case_532 |
<!--/AUTO:eval-->

The UNDETERMINED cases are exactly the rows the contract validator rejects (an INCOMPLETE row with no finding, because the output format has no way to say "not determined"); they are why `export` refuses. Every other row passes the full contract validation.

## 3. Additional evaluation cases (independent, fully described)

The cases below are synthetic and fictional. They live in `code/evaluation/fixtures/synth_v2` (hash-frozen; `code/evaluation/test_fixtures_frozen.py` fails if any file changes). Their labels were written from the contract reasoning before the engine was run against them. Each also has an internal expectation file (accepted/rejected links, obligation verdicts, forbidden citations).

**Case A: `fx_case_05` temporal leakage (both halves of the cutoff).** Subject Nirmala Pereira (`user_f05`) asks for deletion; request 2026-06-01, `audit_at` 2026-06-15T12:00Z.
Evidence: `evidence_f01` (inventory, captured 06-01) lists her search entry `search_f05` under her email, so the resource is linked; `evidence_f02` (inventory, 06-14T10:00, scope covers search and security) no longer lists it; `evidence_f03` (account primary+failover snapshot, 06-14T11:00) has no row for her. Two traps: `evidence_f06` is captured on **06-20, after the audit**, and still contains the old `search_f05` row (its *record* time is 06-05); `evidence_f07` is captured **before** the audit but holds a record `search_f05b` observed on **06-16, after** the audit. An engine that filtered only on record time would cite `evidence_f06`; one that filtered only on artifact time would see `search_f05b`.
Expected output: COMPLETE with verification steps only, citing `evidence_f03` (account absent), `evidence_f02` (search absent, audit record present); neither trap artifact may be cited and `search_f05b` must not be linked. Result: passes.

**Case B: `fx_case_16` identity change after the cutoff, plus a lookalike.** Anouk Visser requests deletion with her *old* email. Her audit log shows an email change on **2026-06-20, after `audit_at`**, and the identity snapshot already shows the new email.
Evidence: `evidence_f02` holds `search_f16` under the old email (linked: that address already belonged to her) and `search_f16b` under the **new** email (not hers yet at the evidence's record time, so it must not link). Expected: INCOMPLETE with a finding/remediation/verification chain on `search_f16` only, plus account-absent and audit-present verification. Result: passes. This is what prevents later identifiers from being attached to earlier cases.

**Case C: `fx_case_22` a populated replica is not discharged by a clean primary.** Tobias Eriksen, request 2026-07-01, audit 2026-07-15. `evidence_g04` (July 10) is a primary+failover account snapshot: the primary lists only an unrelated person, but the failover replica also lists a row carrying his user id and email. Expected INCOMPLETE: finding `REPORT_REMAINING_RECORD` on `account_f22` citing `evidence_g04`, delete, verify absent, plus the audit-record verification. This is the replication-drift control for the subject-level account proof: a clean primary must never prove absence while a covered replica holds the subject. Result: passes.

**Case D: `fx_case_23` an unattributable row blocks the proof.** Nadine Okafor, request 2026-04-01, audit 2026-04-15. The only account snapshot (`evidence_g06`, a declared bundle) lists one unrelated person **and** an account row with every identifier null. That row could be hers, so the snapshot cannot exclude it. Expected: internal state UNDETERMINED (account obligation UNKNOWN), never COMPLETE, and no step may name `account_g23x`. Result: passes.

Further synthetic cases in the same set: a tombstone that still exposes email/hash versus one holding only the stable user id (`fx_case_08`, `fx_case_09`), a historical email_hash link (`fx_case_13`), a near-miss lookalike email (`fx_case_12`), a legal hold present in a replica (`fx_case_15`), a snapshot that predates the request (`fx_case_24`), a scope that excludes the system so absence is not evidenced (`fx_case_07`), and non-deletion requests in English, Spanish and Japanese (`fx_case_01..03`).

Expected outputs and expectations for the four cases above, regenerated from the frozen files:

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
| `fx_case_14/17` labels encoded "unlinkable id means unresolved obligation" | closeout review | v2 fixtures with revised labels written before running the engine; v1 retained |

Hypotheses that were measured and **not** adopted, because the measurements did not support them: accepting activity-window candidates as links (unique candidate for only 37 of 550 requests; anchoring the window on the case's own resources leaves the right account absent from the candidates in 6 of 13 samples), and scoping out already-absent pre-request resources (one supporting case, no contradiction, too thin).

## 5. Subject-level account proof: sensitivity

The proof answers "does an authoritative account snapshot, queried by the subject's identifiers, contain a profile for this subject?" without needing the original account resource id. Its gates, per physical copy: a declared (or table-name-inferred) account scope; capture at or after the request; every account row in the copy carries some identifier; no rows hidden by the cutoff; latest event per copy wins; the primary copy must be affirmatively absent. It is consulted only when no account resource is linked, and it never emits a step (no resource id is evidenced).

Two optional switches change how much weight is placed on the snapshots. Results (sample counts are development data; eval counts are diagnostics; "false-absence" compares against the public answers' known account state):

<!--AUTO:sensitivity-->
```text
== samples (development data)
   default (strong scopes, empty tables allowed)    {'COMPLETE': 10, 'INCOMPLETE': 22}  false-absence vs gold: 0
   + weak scopes (inferred_from_rows)               {'COMPLETE': 10, 'INCOMPLETE': 22}  false-absence vs gold: 0
   + require an account row in the artifact         {'COMPLETE': 4, 'INCOMPLETE': 22, 'UNDETERMINED': 6}  false-absence vs gold: 0
   weak + require_row                               {'COMPLETE': 4, 'INCOMPLETE': 22, 'UNDETERMINED': 6}  false-absence vs gold: 0
== eval (unlabeled diagnostics)
   default (strong scopes, empty tables allowed)    {'COMPLETE': 146, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 9}
   + weak scopes (inferred_from_rows)               {'COMPLETE': 150, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 5}
   + require an account row in the artifact         {'COMPLETE': 120, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 35}
   weak + require_row                               {'COMPLETE': 128, 'INCOMPLETE': 353, 'NOT_APPLICABLE': 10, 'UNDETERMINED': 27}
```
<!--/AUTO:sensitivity-->

The default keeps strong scopes only and allows declared-empty tables. Requiring a positive-control row would flip 6 correct sample COMPLETEs to unresolved. Snapshots hold 1 to 4 rows each (case-focused extracts, not full tables), so "the snapshot declares coverage of the account service" is a stated assumption, not something the data proves. The public samples contain one counterexample to trusting an empty declared snapshot over direct evidence (a profile lookup at 09:41 followed by a declared-empty bundle at 12:00), which is why direct evidence outranks it.

## 6. Remaining unresolved cases and limitations

The cases in section 2.3 that remain UNDETERMINED are *internal* states; the output has no status for them. Each is a documented, reproducible case:

* **No account snapshot covers the subject after the request**: `case_524`, `case_530`, `case_532` (audit 2026-01-29, before any account artifact exists) and `case_55`. Example: `python3 code/main.py explain case_524`.
* **Only document-style replica files cover the account collection** (scope inferred from rows, weak): `case_183`, `case_343`, `case_345`, `case_462`. They resolve under the optional weak-scope switch; whether that inference is acceptable is a decision, not a fact.
* **Restore state not shown** (`case_55`, `backup_9287`): the recovery console shows the archive, its account email, path, checksum and retention, and restore entries for *other* archives; it shows no permission or block for this one. Inferring restorability from the console context would be an interpretation, so the obligation stays UNKNOWN.
* **Source conflict** (`case_63`, `marketing_001`): the screenshot shows Soo-jin Park (`sj.park@naver.com`), while the data catalog ties the same resource to another subject. No supplied rule says which source wins, so the contradiction is preserved (UNKNOWN), never resolved by assumption.

Other limitations: the PNG transcriptions are hand-authored (hash-bound and OCR-cross-checked, not regenerated by code); the intent classifier is a deterministic clause-level heuristic with no labeled non-deletion examples to measure its precision; phone matching by a 9-digit national suffix could in principle collide with an unrelated number; step recall is limited by resource ids the data never links to the subject; and a COMPLETE row with no citable verification step cannot be valid, so such a row would still need an accepted representation.

## 7. Reproducing

```text
python3 code/evaluation/main.py all            # all test suites + labeled evaluation; non-zero exit on any failure
python3 code/main.py run                       # provisional output + manifest under runs/provisional/
python3 code/main.py verify runs/provisional/output.manifest.json   # byte-identical regeneration, unchanged inputs and code
python3 code/main.py export                    # the only writer of ./output.csv; refuses unless every gate passes
python3 scripts/write_reports.py               # refresh the numeric blocks in this file and usage_report.md
```

The run these numbers describe:

<!--AUTO:manifest-->
| field | value |
|---|---|
| command | `python3 code/main.py run` |
| configuration | `{"data": "dataset", "png_extraction": "complete", "png_method": "hand-authored visual transcription bound by sha256, cross-checked against local OCR (code/ghostaudit/image_transcriptions)", "requests": "deletion_requests.csv", "unknown_policy": "not_certified"}` |
| git commit / working tree | `462a85fbc2fb` / DIRTY (uncommitted changes) |
| output.csv sha256 | `97993dfc44ea55ec1b007380f0e9923e593e6019a15e8c099d3b8837b1ff9be9` |
| code sha256 (41 files: all of code/ghostaudit incl. image transcriptions, main.py, requirements) | `30fd78b4b48091164d2c02c1eb25270e14f2c4be713061334daf4ee4dd83c86b` |
| input files hashed | 103 (dataset csv + evidence); combined listing in the manifest |
| rows | 518 |
| statuses | {'COMPLETE': 146, 'INCOMPLETE': 362, 'NOT_APPLICABLE': 10} |
| contract-valid | False (9 validation errors) |
| UNDETERMINED cases | 9: case_55, case_63, case_183, case_343, case_345, case_462, case_524, case_530, case_532 |
| runtime model calls | 0 |
| final (exported) | False |
<!--/AUTO:manifest-->
