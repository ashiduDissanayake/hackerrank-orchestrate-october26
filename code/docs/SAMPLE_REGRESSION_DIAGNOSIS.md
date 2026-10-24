# Diagnosis: the nine public-sample cases that stopped being COMPLETE

Scope and rules. Public sample answers are read here for **diagnosis and evaluation only**; no expected resource id, label or step feeds prediction logic (`scripts/diagnose_sample_regressions.py` reads them, the engine never does). Cutoff rules are the user's U4/U11 (artifact availability **and** observation time must both be <= `audit_at`) and U12 (activity-window matches are candidates, never links). Evidence below is cited by `file_id` / `activity_id`.

Regeneration: `python3 scripts/diagnose_sample_regressions.py`. Cause measurements reuse M2b (`scripts/m2b_link_probe.py`) and `scripts/measure_anchored_window.py`.

## Why they regressed

Under the default policy `not_certified` an unresolved obligation makes a case INCOMPLETE instead of silently COMPLETE (review finding P1-1). All nine gold-COMPLETE cases contain an unresolved `USER_PROFILE` obligation, so all nine flipped.

## Per-case table

Policy for every row: `rule_01 USER_PROFILE DELETE (Always)`, and `rule_07 ANALYTICS_PROFILE ANONYMIZE (still attributable)` for analytics rows. "Admissible chain" = the evidence that links the resource to the subject; "state evidence" = evidence about the resource's state at `audit_at`.

| case | expected -> now | missing gold step(s) | admissible link chain | admissible state evidence | failure class | fix / what is missing |
|---|---|---|---|---|---|---|
| case_01 | COMPLETE -> INCOMPLETE | account_001 absent | **none**. The id appears in no artifact; only `activity_3342` (DELETE, claim) | evidence_54 (captured 2026-09-02T23:00Z <= audit) is a primary+failover account snapshot whose declared scope covers account_service and does not list account_001, so absence *would* be evidenced if the id were tied to the subject | identity linking, **dataset limitation** | no identifier ties account_001 to the subject |
| case_02 | COMPLETE -> INCOMPLETE | account_002 absent | none; only `activity_3376` (DELETE, PARTIAL claim) | same snapshot evidence_54 | identity linking, dataset limitation | as case_01 |
| case_04 | COMPLETE -> INCOMPLETE | account_004 absent; analytics_901 anonymized | account_004: none, **not even an activity row**. analytics_901: observed in evidence_56 (2026-09-07T09:45Z) with every identifier null | evidence_56 shows analytics_901 present with no identifier | identity linking, dataset limitation. An already-anonymized record has no identifier to link by, and under rule_07 an unattributable record needs no treatment, so the engine cannot derive it as an obligation | none recoverable |
| case_21 | COMPLETE -> INCOMPLETE | account_6440 absent; analytics_5335 anonymized | none for either | evidence_92 (service export, 2026-09-15T11:44Z): explicit lookup `account_6440` 404 / `profile: null`; `analytics_5335` present with null identifiers | identity linking: **state is evidenced, the link is not**. evidence_92 mixes six cases' accounts and seven analytics profiles in service-keyed lists with no per-case key | needs a per-case key; the only assignment routes are cross-case elimination (U5) or time ordering (U12) |
| case_25 | COMPLETE -> INCOMPLETE | account_3136 absent; analytics_1895 anonymized | none | evidence_92 (as case_21) | identity linking (as case_21) | as case_21 |
| case_26 | COMPLETE -> INCOMPLETE | account_5684 absent; analytics_4566 anonymized | none for these two (the case's audit record, backup, data flow and support record **are** linked and compliant) | evidence_92 | identity linking (as case_21) | as case_21 |
| case_27 | COMPLETE -> INCOMPLETE | account_3866 absent; analytics_4574 anonymized | none for these two | evidence_92 | identity linking (as case_21) | as case_21 |
| case_28 | COMPLETE -> INCOMPLETE | account_5482 absent; analytics_6077 anonymized | none for these two | evidence_92 | identity linking (as case_21) | as case_21 |
| case_31 | COMPLETE -> **COMPLETE** (fixed) | account_4857 absent (step only) | tombstone_440 is linked through the subject's audit/identity evidence | evidence_51 (2026-09-15T12:00Z, exactly `audit_at`): tombstone_440 with `account_status: DELETED` and no name, email, phone or hash | **specification-grounded fix**: a tombstone is state evidence that the account is deleted (rule_15's condition is "Account is deleted"). The account obligation is now COMPLIANT at subject level (reason `account_deleted_per_tombstone`) | the status is right; the *step* for account_4857 cannot be emitted because no evidence names that resource |

case_03 stayed COMPLETE throughout; it only lacks the analytics_9406 step (observed in evidence_94 with null identifiers: identity-linking dataset limitation, same class as case_04).

Result: 1 of the 9 resolved on evidence (case_31). **8 remain, all with one demonstrated cause: no identifier-bearing evidence links the account (and the anonymized analytics record) to the subject.**

## Is the account-gap obligation justified?

The engine adds `USER_PROFILE / UNKNOWN / unresolved_link` when no profile resource is linked. Per case it can be one of three things; they are now reported separately (`detail.gap_class`, `reason`).

1. **An established relevant resource whose state is unknown.** Not applicable to the gap itself: no profile resource is established. (Where a profile *is* linked, its state is evaluated normally: COMPLIANT absent / VIOLATION present.)
2. **A resource that exists but is not linked.** Demonstrated for cases 21, 25-28: evidence_92 evidences accounts 404 but gives no subject key. For cases 01, 02, 31 the resource is named only by a deletion-worker activity row (a claim, not state).
3. **An obligation assumed by the implementation.** Case_04 is the clearest: no artifact and no activity row mentions an account for the subject at all.

Grounding in the contract. The obligation is **not** invented to lower scores: `rule_01` applies "Always", the task definition makes the user's profile a relevant copy of every authorized deletion, and COMPLETE is defined "only when every relevant copy has the required treatment". Equally, a missing profile does **not** prove an unresolved deletion, so the engine never turns the gap into a finding, a remediation, or a verification step. Two evidence-grounded ways the obligation is discharged:

* a linked profile resource whose latest evidence is absence (existing behaviour);
* **new:** a linked `ACCOUNT_TOMBSTONE` with `account_status == DELETED` (all 18 tombstone records from SQL/JSON carry it; the one from a screenshot, tombstone_17, shows only "Retained reference" and no status, so it does **not** discharge the obligation). Effect: sample case_31 and **8 eval cases** no longer carry the gap (counted from the run: reason `account_deleted_per_tombstone`). Tests: `tests/test_account_gap.py` (a non-DELETED tombstone does not discharge it; a tombstone with exposed PII still violates).

Distribution on the 518 eval cases (unlabeled diagnostic, not accuracy): 96 unresolved accounts have window candidates only (class 2 by construction, the candidates are unlinked claims); the rest of the UNDETERMINED set is listed under "Remaining unresolved cases" in `DECISIONS.md`.

## Why the window cannot link them (evidence, not assumption)

* M2b: the activity window holds a unique account candidate for 37 of 550 requests; the true account is inside the window in 31/32 samples but ambiguous in 23 of those.
* `scripts/measure_anchored_window.py` (new): anchoring the window on the case's own evidence-linked resources does **not** fix it. Samples: 13 scorable cases; 3 give a unique candidate containing the right account, 4 contain it among several, **6 do not contain it at all**. Eval: of 248 cases with a non-empty candidate set only 29 are unique (127 have none).
* Note on the specification text: `AGENTS.md` 6.6 lists "timestamps" among the handles for matching evidence. The measurements show timestamps alone are not identity proof in this dataset; accepting them as evidence is the user's decision (U12) and is not adopted.

## Minimal reproducible example (dataset limitation)

```
python3 code/main.py explain case_01 --data dataset --requests sample_deletion_requests.csv
```
Case_01 needs `account_001` verified absent. `grep -rn account_001 dataset/` returns only `activity_3342` (a DELETE *claim*) and the sample answer. evidence_54 would prove absence if the id were known to belong to the subject, but nothing in any artifact, at any capture time, links that id to `amina.elmasri@gmail.com`. This is a dataset property, not an implementation gap.


## Update (2026-10-25): the two questions are different

The analysis above conflated two questions, and the closeout review separated them:

1. Can the SUBJECT's account state be established (no profile for the subject remains in an authoritative snapshot)?
2. Can the original account RESOURCE ID be recovered (needed to emit the canonical verification step)?

For the eight remaining cases (01, 02, 04, 21, 25, 26, 27, 28) question 2 is still **no** (unchanged: no identifier ties `account_001` ... `account_5482` to the subject), but question 1 is answerable from `evidence_54` / `evidence_51` / `evidence_90` etc.: a subject-keyed query returns no row. `ghostaudit/account_proof.py` records that as a subject-level obligation (`USER_PROFILE`, `no_profile_for_subject_in_snapshot`) **without a resource id and without a step**. Effect on the public samples: all 8 are no longer unresolved; sample status accuracy is 32/32 under the default non-certifying policy. Their gold answers still contain an account step that cannot be produced, so step recall stays below 1 (0.8187); the missing steps are a recall limitation, not an uncertainty about the state.

How the proof was kept from over-claiming (details and tests in `code/tests/test_account_proof.py`, `code/evaluation/evaluation_report.md` section 5):

* validated against the samples' known account states: all 3 genuinely present accounts (cases 05, 16, 24) are violations and none was claimed absent; this validation found two flaws that are fixed (weak-scope replicas must never hide presence; a profile lookup must outrank a later declared-empty bundle: case_24's lookup at 09:41 versus a declared-empty `customer_profiles` bundle at 12:00);
* the snapshots hold only 1 to 4 rows each, so "the snapshot declares coverage" is an assumption, not a proof; two stricter switches (weak scopes, required positive-control row) are measured and left off.

The real data splits as: 309 eval cases discharged by the proof (86 of them rest only on declared-empty account tables, 219 on artifacts that also show at least one account row), 8 by a `DELETED` tombstone, and **9 remain UNDETERMINED**: `case_524`, `case_530`, `case_532` (audit 2026-01-29, before any account artifact), `case_55` (also no restore state), `case_183`, `case_343`, `case_345`, `case_462` (weak scope only) and `case_63` (source conflict).
