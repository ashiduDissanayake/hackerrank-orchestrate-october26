# DECISIONS ledger

Three sections, kept separate on purpose. Every entry records: setting, alternatives, measured before/after, limitation, code location.

## A. User decisions (explicit choices made by the user)

| # | Decision | Source |
|---|---|---|
| U1 | Hybrid design: deterministic ingestion, identity linking, temporal filtering, policy enforcement and serialization; targeted LLM/VLM interpretation; a small bounded tool-using investigator, kept only on measured merit | answers to the LLM-posture question |
| U2 | Working budget under 24h, scheduled against the actual time remaining | time-budget answer + plan feedback round 2 |
| U3 | Reproducibility is tested both with fresh model calls and cached reruns; costs come from actual workloads | LLM-posture answer |
| U4 | Evidence cutoff requires BOTH artifact availability time and observation time <= audit_at | feedback round 1 (1) |
| U5 | Window matching is candidate discovery only; accepted links need an explicit evidence chain; no cross-case elimination | feedback round 1 (2) |
| U6 | COMPLETE requires supporting evidence for every applicable obligation; absence is evidence only with an explicit lookup or a scope-covering snapshot | feedback round 1 (3) |
| U7 | Policy conditions are evaluated (retention, legal hold, ownership); tombstone: identify first, then assess prohibited identifiers | feedback rounds 1 (4) and 2 (1) |
| U8 | UNKNOWN is distinct from INCOMPLETE; no automatic mapping; output policy to be resolved against the contract before the final run | feedback round 2 (2) |
| U9 | Labeled accuracy (samples + labeled fixtures) kept separate from unlabeled diagnostics | feedback round 2 (4) |
| U11 | Time rule for identity links stays STRICT (U4): no artifact captured after audit_at is ever used, not even to establish a stable resource-to-subject link. Accepted cost, measured in M2b: 8 of 111 sample resources (7%) stay unlinked. Closes P5 | answer to M2b checkpoint question 1 (2026-10-24) |
| U12 | Activity-window candidates are reported as UNRESOLVED only: never accepted as links, never emitted as steps; the exact missing link and the candidate list are reported. Closes P4 | answer to M2b checkpoint question 2 (2026-10-24) |
| U10 | Lexicographic resource_id ordering; single authoritative report location code/evaluation/ with generated packaging copies; model choices configurable | feedback round 2 (7) |

## B. Agent proposals awaiting a user decision

| # | Proposal | Status |
|---|---|---|
| P1 | Development cost ceiling of about $40 | **UNAPPROVED** (user must choose explicitly) |
| P2 | Model per task (intent, VLM, investigator); smoke test shows haiku-5-5, sonnet-5-5, opus-5-5 all available | open |
| P3 | Output policy for obligations that remain UNKNOWN after investigation | **OPEN, resolve before M8. Measured (see D): `established_only` (default, provisional) keeps sample status accuracy at 32/32 and yields 8 contract-invalid eval rows; `unknown_is_incomplete` drops sample status accuracy to 23/32 (71.9%) and yields 112 contract-invalid rows (INCOMPLETE without a finding)** |
| ~~P4~~ | RESOLVED by U12. (was: Whether any window-based rule may ever count as evidence | **open; M2b measured (section D): window finds the right account in 31/32 samples but is ambiguous in 23 of them; unique in only 37/550 requests.** Baseline stays strict (candidates are reported, never accepted) ) |
| ~~P5~~ | RESOLVED by U11. (was: Time rule for IDENTITY linking: keep U4 (artifact availability AND observation time <= audit_at) or allow an artifact captured after audit_at to establish a stable resource-to-subject link when the record's own observed_at <= audit_at (state still taken only from admissible evidence) | **open; M2b measured: strict loses 8 of the 111 sample resources (7%), 7 reachable under observation-time-only, 1 only with any-time identity.** Baseline stays strict (U4)) |
| P7 | Scoping rule "a linked resource whose own latest observation is an absence dated before requested_at is outside this request" (would drop case_17's account_6523, which belongs to the same user's earlier case_46) | **NOT adopted.** Evidence is thin: fires on 1 of 9 sample absent-obligations (the motivating case) and 1 of 114 eval ones (case_34 account_5762), 0 contradictions in the samples. Costs one extra step in case_17 (precision) until decided |
| P6 | Output policy when an expected-type resource cannot be linked by any evidence under any time rule (27/111 = 24% of sample resources) | open; ties to P3 |

## C. Autonomous choices (agent defaults, reversible)

| # | Choice | Alternative | Notes |
|---|---|---|---|
| A1 | Python 3.12 venv in .venv, anthropic pinned to 2.3.0 (requirements.txt) | system Python 3.14 | 3.14 is the system default; 3.12 chosen for dependency stability. Documented in README at M9 |
| A2 | Work branch dev/baseline | commit on main | |
| A3 | Sampling params (temperature/top_p/top_k) never sent | send temperature=0 | API rejects them from 2026-10-21 (claude-api reference) |
| A4 | Schedule clock anchored at first session message, 2026-10-24T14:28:45Z (first timestamp in the session transcript) | anchor at plan approval | Deadline-equivalent for under 24h: about 2026-10-25T14:28Z. This anchor is an ASSUMPTION about what the user meant by "under 24 hours" |

| A5 | Document-style replica files (customer_data_primary / replica_* ...) carry no scope table: covered systems are inferred as the origin_systems seen in ANY table of the file, applied to EVERY table (basis=inferred_from_rows). Declared scopes (snapshot_scope, snapshot-bundle collections) are kept distinct by `basis` | treat such files as having unknown scope | Needed for replica-drift detection (a replica missing a row its primary has). Absence rules (M3) must treat inferred scope as weaker than declared; code: extract/sql_snapshots.py |
| A6 | System of a record comes from the evidence (SQL origin_system, JSON data_store/system, handover/ledger system) and falls back to a resource-ID prefix map (observations.PREFIX_SYSTEM). The activity table's target_system is NOT used as the owner | use activity target_system | measured: audit_record_* targets archive_service (196/197 rows), support_* targets search_service (232), export_* targets object_store (155), so activity targets are not owners |
| A7 | Every record is scanned for exact identifier tokens (full email, 64-hex hash, user_<id>, and phone only from phone-named fields) and the source field names are kept (ids_*, ids_src). subject_reference / subject_selector / lookup_value are NOT treated as user ids because they hold emails in some record types | alias them to a user reference | measured: backup catalog subject_reference and connector subject_selector hold emails, security records hold user ids. Code: extract/common.py |
| A8 | A snapshot dated after the cutoff makes its unchanged values unverifiable (verified=False, cannot create an accepted link) only when no audit record accounts for that update | flag whenever updated_at > audit_at | a failing test showed the snapshot's updated_at is bumped by the very audit change that postdates the cutoff; code: identity.py |

| A9 | Output rows are ordered by NATURAL case_id order (case_2 < case_10 < case_100), the order of dataset/deletion_requests.csv. The contract only says "sorted by case_id"; lexicographic order would put case_100 before case_33 | lexicographic | OPEN AMBIGUITY worth confirming (a grader keyed by case_id is unaffected; an order-sensitive one would not be). validate.case_sort_key |
| A10 | Rule assumptions in the baseline engine (obligations.py header): every support conversation record is REDACT (rule_05 shared context assumed); a security audit record with no retention_until is treated as within retention; analytics counts customer_reference as attributable; a support attachment is subject-only if the catalog says so or every identifier in it belongs to the subject | evaluate per-record free text | to be revisited with measured sample errors in M6 |

| A11 | Absence evidence older than the earliest evidence linking the resource to the subject is ignored (state.copy_states `since`) | accept any older absence | found by fixture fx_case_07: a 06-01 snapshot "absence" predates the 06-02 catalog link, so it says nothing about the cutoff state. General logic, not sample-driven |
| A12 | Presence from facts, not only the raw flag: PII-scan hits and download checks prove existence; contact_* lookups are category SECONDARY_IDENTIFIER (DELETE); restore state from restore_candidate_evaluated (eligible & no deletion_block = restorable) and restore_authorization_completed (deny = blocked) | leave those events as UNKNOWN | sample-motivated (case_10/12/17/19) but each mapping is a direct reading of the event fields; revisit in M6 |
| A13 | Physical copies: 'primary' = every view of the live system (inventory, bundle, export, log, handover, ledger, history, snapshot, pdf); named replicas (*_replica*, replica_*) are separate copies; a record present in ANY copy's latest evidence is present | each store separate | avoids false drift from comparing a view with itself |
| A14 | Window candidates use [reported_at - 90 min, reported_at + 10 min] (measured in M2b), deletion_worker activity only, diagnostic only | wider windows | wider windows did not reduce ambiguity |
| A15 | Intent baseline is a lexicon heuristic with negation patterns; manual review of all 398 distinct request texts shows all 9 non-deletion classifications are genuinely non-deletion; 3 were low-confidence (2 French lexicon gaps, 1 phone-update misread, both fixed). Replaced/augmented by the LLM classifier in M5 | LLM now | NOT tuned to any expected NOT_APPLICABLE count |

## D. Measurements

### M0 API smoke test (2026-10-24T16:25Z, scripts/api_smoke_test.py, anthropic 2.3.0)
All three models found in models.list and passed both checks (structured output with json_schema, tool-use round trip with strict tool and tool_choice auto).
Tokens per model (structured / tool-use round trip): haiku-5-5 260in/25out, 908in/117out; sonnet-5-5 260in/25out, 908in/117out; opus-5-5 260in/76out, 908in/162out.
Observation: haiku and sonnet report identical token counts on both calls; this was not investigated. Cost of the smoke test is negligible (under $0.01).

### M1 evaluator and frozen fixtures (2026-10-24)
* Scorer + validator: validator reports 0 errors on all 32 public sample answers (sort rule, per-status constraints, and evidence captured_at <= audit_at hold on every cited file_id: the inclusive boundary is confirmed on all samples).
* Corruption suite: 16 tests, all pass; sabotage check: breaking the precision formula fails 4 tests, breaking evidence-field comparison fails 2 (tests can fail). code/evaluation/test_scoring.py
* Frozen fixtures synth_v1: 16 cases (13 with full labels, 3 labeled only by internal expectations because their correct output is UNKNOWN-typed), 15 files, sha256 manifest code/evaluation/fixtures/synth_v1.sha256, guarded by test_fixtures_frozen.py (hash, determinism, label validity, coverage of NOT_APPLICABLE/COMPLETE/INCOMPLETE/UNDETERMINED and non-ASCII text).
* LIMITATION of the fixtures: labels were authored by the same agent that writes the engine (from the contract), they follow two sample-derived conventions the contract does not state: (1) citation = latest admissible artifact whose scope covers the resource's system and store, (2) a deletion verification covers the account-absent and retained-audit-record resources. They are not independent of that understanding. Expired-retention audit records and email-delivery/marketing/cache categories are NOT covered (policy gap).

### M2 extraction coverage on the real dataset (code/main.py coverage)
* 94 artifacts: 83 ok, 11 pending (PNG, vision extraction is M5), 0 extractor failures.
* 3,162 observations, 369 scope declarations, 12 catalog links, 0 unparsed lines or rows (logs: 2,211 lines across 26 files in 6 dialects).
* Independent completeness check (raw resource ids vs observations per file): 0 gaps after counting ids referenced inside records (the first run flagged evidence_57, where search documents reference account ids via source_resource_id; they are references, kept in fields).
* Concrete parsing failure found and fixed during M2: 11 service_resource_export files failed on index_queries because `hits` is {documents, total}, not an integer.
* Time findings: manifest-vs-content availability disagreements: 0. Observations whose observed_at is later than their artifact's capture time: 2 (evidence_13 record 38 and evidence_36 record 45), both for requests whose audit_at equals the artifact capture time (case_135 account_1417, case_383 account_5043): an earlier record in the same artifact shows the account NOT_FOUND and a later-dated record shows it FOUND (recreated). The observation-time check is therefore not hypothetical; test: tests/test_core.py DualTimeRealData.
* Identity: all 518 requests resolve to exactly one user with no conditions; 0 cases have an identity snapshot update or audit change after audit_at (so the post-cutoff logic is exercised by tests and fixtures only).
* Tests: test_core.py 12, test_scoring.py 16, test_fixtures_frozen.py 5, all pass. test_core includes a guard that case logic never reads the raw Store (only caseview/observations/pipeline/coverage may).

### M2b window-only linkage investigation (scripts/m2b_link_probe.py; labels used ONLY to measure coverage)
Population: 111 distinct (case, resource) pairs in the 32 public sample answers, reachable by strict evidence chains under U4 (dual-time):
* 76 reachable (49 via a direct identifier in an observation of the resource, 27 via the subject's user id).
* 35 not reachable. Breakdown: 15 account_* seen only as deletion-worker activity rows (claims), 12 resources observed but carrying no identifier (404 lookups, anonymized analytics), 8 with no observation and no activity at all (audit_record_*).
Competing time rules for the 35:
* observation-time-only (ignore artifact availability): +7 (audit_record_4902 and account_3960 via a log exported 2026-09-18 for an audit at 2026-09-16T09:15; audit_record_4128/7095/3954/1707 and account_5684 via the 2026-09-17 bundle for audits at 2026-09-15T12:00).
* any-time identity: +1 (account_3866).
* unreachable under EVERY time rule: 27 of 111 (24%): all other accounts, anonymized analytics, and audit_record_6645 / audit_record_5569 which appear nowhere in the dataset except the sample answers.
Window rule (deletion_worker DELETE_RECORD on account_service within [reported_at-90min, reported_at+10min]): 539 such rows; the sample's expected account is inside the window in 31/32 cases, but the window holds more than one candidate in 23 of those 31; across all 550 requests: 0 candidates 18, exactly 1 candidate 37, 2: 54, 3: 294, 4+: 147. Widening to 180 or 360 minutes does not help. The nearest-activity assignment is unique for only 35 of 174 requests. case_04 account_004 has no activity row at all.
Interpretation (competing hypotheses, none validated): (H1) the generator emits the account deletion near reported_at, so the window contains the truth plus unrelated concurrent deletions; with 3+ candidates typical, picking one is not identity evidence. (H2) hero-case ID patterns (account_00N with user_0N for cases 1 to 8) correlate with user numbering, but that is naming, not evidence. (H3) cross-case elimination is order-dependent and was excluded by U5. No additional structural or causal link between the unreachable resources and the subject was found in any artifact, at any capture time.
Consequence: strict-chain linking cannot reproduce about a quarter of the expected sample resources, mostly account_* and anonymized analytics, and no rule validated on this data closes that gap without accepting ambiguous candidates. Decision needed on P3/P4/P5/P6.

### Fixture correction (found at the first engine run)
synth_v1 had an authoring defect: the activity row fxact_001 was dated 2026-06-01T13:00Z, about 20 h before the reported_at of the two cases that share it (window = reported_at -90/+10 min, chosen earlier from the M2b measurements), so the "window-only candidate" expectation could never be met. This was a fixture error, not engine tuning. Corrected to 2026-06-02T07:45Z (inside both cases' windows), rebuilt, manifest re-frozen. Manifest sha256 before: dbbb2001d2f3caa218d68060a3921fb9e6b0263f84b9d2209059a8446b292589; after: 61062d66dab3f0d33770763925f54226cc882c75154147c7ebe1e11549b052e9. The same run also exposed a genuine ENGINE flaw (stale absence, A11) and a catalog-only category bug, both fixed in the engine, not the fixture.

### M3 baseline (first end-to-end run, 2026-10-24)
Engine: intent -> identity as of cutoff -> evidence-chain links -> per-copy state -> rule-condition obligations -> planner -> canonical sort. Output: full 518 rows.
Labeled (development/regression data, NOT an untouched holdout), policy established_only:
* fixtures synth_v1: 16/16 cases pass (13 exact-output cases at 1.000 on every metric; internal expectations all met; fx_case_07/14/17 carry an output-status policy note because obligations are unresolved, see P3).
* public samples (32): status accuracy 1.0000; step strict P/R/F1 0.9937 / 0.8187 / 0.8977; field accuracy on aligned steps: state 1.0000, evidence_id 1.0000; evidence accuracy 0.7867; exact-sequence rate 0.25; mean LCS 0.79. The recall gap is the structurally unreachable set from M2b (accounts, anonymized analytics, two audit records) plus one extra step (case_17 account_6523, P7). Every remaining MISSING step in the sample diff is such an unreachable resource.
* Sample errors found and fixed during M3 (each a general mapping, A12): case_10 category (contact index -> DELETE), case_17 restore state (backup missed), case_19 PII-scan presence.
Unlabeled diagnostics on the 518 eval cases (NOT accuracy): status COMPLETE 163 / INCOMPLETE 345 / NOT_APPLICABLE 10; 346 deletion cases have no linked account (account obligation UNKNOWN: unresolved_link); 8 deletion cases have no admissible evidence at all (verified: 7 only have evidence captured after audit_at, 1 only a PNG pending M5) and are contract-invalid rows under any policy until P3 is decided; 13 intent decisions were low-confidence before the lexicon fixes.
Provisional unresolved-obligation policy comparison (labeled samples / eval):
| policy | sample status accuracy | sample step F1 | eval COMPLETE / INCOMPLETE / NA | contract-invalid eval rows |
|---|---|---|---|---|
| established_only (default) | 32/32 = 1.000 | 0.898 | 163 / 345 / 10 | 8 |
| unknown_is_incomplete | 23/32 = 0.719 | 0.807 | 51 / 457 / 10 | 112 |
A first attempt that special-cased "nothing established -> INCOMPLETE" dropped sample status accuracy to 0.906 (case_01, 02, 04 are COMPLETE in the gold with an unreachable account); it was reverted into the explicit policy switch above instead of being kept as a silent choice.

### Test discipline (all pass: python3 code/evaluation/main.py all)
test_scoring 16, test_fixtures_frozen 5, test_core 12, test_intent 3, test_invariance 7 (alone vs batch, shuffled, extra later requests, unrelated evidence, future evidence of both kinds, post-cutoff identity change; plus a 60-case shuffled slice of the real dataset).
Sabotage checks (tests must be able to fail): an order-dependent engine fails 6/7 invariance tests; dropping either half of the dual-time cutoff fails the future-evidence test and the matching fixture/real-data tests; a planted raw-store read fails the bypass guard. Two defects found IN the tests themselves while doing this: a vacuous "extra requests" test (copy.replace missing on Python 3.12) and a bypass-guard regex that flagged the sanctioned CaseView method; both fixed.
