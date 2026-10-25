# Ghost Data Still Exists: deletion-audit agent

For every request in `dataset/deletion_requests.csv` this program decides whether the person asked for deletion, reconstructs what each system held about them at the case's `audit_at`, applies `deletion_rules.csv`, and returns `COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE` with the findings, an ordered remediation plan and the verification checks that must pass.

The design is **deterministic evidence code, not a model on the prediction path**. Nothing in `code/ghostaudit` calls a language model. A claim is only used as a claim; state comes from admissible evidence.

## Setup

Requirements: Python 3.10 or newer (developed and tested on 3.12), and the poppler `pdftotext` command (PDF evidence). The pipeline itself uses only the standard library.

```bash
python3 -m venv .venv && . .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r code/requirements.txt                     # pillow (OCR cross-check test) and anthropic (smoke-test script only)
# system tools:   macOS: brew install poppler tesseract    Debian/Ubuntu: apt-get install poppler-utils tesseract-ocr
```

`tesseract` and `pillow` are needed only for the OCR cross-check test; without them that one test is skipped and says so. No API key is needed for anything on the prediction path. The participant dataset is **not** part of the package: place it at `dataset/` next to `code/`.

## Run

```bash
python3 code/main.py run                      # provisional output + manifest + diagnostics under runs/provisional/
python3 code/main.py explain case_01 --data dataset --requests sample_deletion_requests.csv    # why a case came out as it did
python3 code/main.py coverage                 # per-artifact extraction coverage report
python3 code/main.py verify runs/provisional/output.manifest.json   # regenerate and compare: byte-identical output, unchanged inputs and code
python3 code/main.py export                   # the ONLY writer of ./output.csv (see below); --accept-plan-gaps discloses unresolved plan items
python3 code/main.py best-effort              # review artifact when export must refuse (see below); never writes output.csv
```

`run` never writes the submission path. `export` writes `./output.csv` and `./output.manifest.json` only if every gate passes: the output is contract-valid, no case is UNDETERMINED, the policy is the non-certifying default, all PNG evidence is transcribed, no prediction-affecting file differs from the commit recorded in the manifest (documentation and report changes do not matter: `code_sha256` identifies the exact code), and the complete test suite passes. A refused export lists every reason and writes nothing. Two separate readiness questions are checked: **status** (no case may be UNDETERMINED) and **material completeness** (an INCOMPLETE case on proven violations may still carry unresolved obligations, so its plan has gaps; `export` refuses those too unless `--accept-plan-gaps` is passed, which the manifest records as `plan_gaps_accepted`).

**When `export` refuses.** `best-effort` writes `output_best_effort.csv` (all 518 rows), `output_best_effort.unresolved.json` (per case: the exact missing fact, the steps actually emitted, every validation error) and `output_best_effort.manifest.json` (`certified: false`, `final: false`, the full validation-error list, code/input/output hashes). It uses the same non-certifying mapping as `run`: an unresolved obligation never becomes a finding, a remediation, a verification step or a certified COMPLETE, so those rows are contract-invalid by construction. It is a disclosed review artifact, not a submission and not a claim that the contract is satisfied.

The CLI requires a subcommand (`python3 code/main.py` alone prints usage).

## Requested output.csv candidate

```bash
python3 code/main.py candidate
python3 code/main.py verify output.manifest.json
```

This explicit command writes `output.csv` with all 518 requests, plus `output.manifest.json` and `output.unresolved.json`. It defaults to the joint context-v2 predictor. Unresolved rows, semantic validation errors and inference assumptions remain visible in the sidecars; no finding is fabricated to clear validation. The file is a prediction candidate and remains incomplete while those errors exist. The `certified` flag is local bookkeeping, not a HackerRank submission credential. An existing certified output is protected from replacement.

The CSV writer quotes the JSON cell correctly. For illustration only, a tiny file would look like this (the real output has 518 rows and real dataset IDs):

```csv
case_id,deletion_status,steps_json
case_000,COMPLETE,"[{""step_no"":1,""phase"":""VERIFICATION"",""system_id"":""security_service"",""resource_id"":""audit_record_demo"",""operation"":""VERIFY_RECORD_PRESENT"",""state"":""PRESENT"",""evidence_id"":""evidence_demo""}]"
case_001,NOT_APPLICABLE,[]
```

## Optional workflow-attribution preview

The default remains the evidence-only audit. An explicit experimental mode can propose otherwise unlinked account/analytics resources through a joint assignment of overlapping workflow requests. It preserves exact links, rejects contradictory identities, enforces the target audit cutoff for every competitor, leaves tied or low-margin assignments unresolved, and independently evaluates record state. It uses no model API.

```bash
# Sample preview and its scores (public development data):
python3 code/main.py run --requests sample_deletion_requests.csv --workflow-mode joint --out runs/workflow_samples/output.csv --diagnostics runs/workflow_samples/diagnostics.json
python3 code/evaluation/main.py score --pred runs/workflow_samples/output.csv --gold dataset/sample_output.csv

# All 518 requests; explicitly uncertified CSV + provenance manifest:
python3 code/main.py run --workflow-mode joint --out output_workflow_preview.csv --diagnostics runs/workflow_preview/diagnostics.json
python3 code/main.py verify output_workflow_preview.manifest.json
python3 scripts/evaluate_workflow.py
```

Context v2 improves the public result from the prior preview’s 17/32 to 19/32 exact answers and from 172 to 178 matching steps, with no extra sample steps. The evidence-only default remains 10/32 exact (159 matching steps). Context weights and thresholds were selected using public development data; this is not independent or hidden accuracy. A quarter-point margin floor gives 18/32 exact. Broader timing variants that assigned records to the wrong person were rejected. Full metrics and synthetic controls are in [workflow_report.md](code/evaluation/workflow_report.md); every remaining expected step and its exact evidence requirement is in [WORKFLOW_GAPS.md](code/docs/WORKFLOW_GAPS.md).

Every inferred link and run is marked `certified=false`. Margins measure a heuristic objective, not probabilities. The method assumes one additional orphan per system/request in a competing component; this is not a supplied data guarantee. It treats proximity and agreement of reported outcomes as attribution clues, never as proof that deletion succeeded. **Strict export always rejects inference mode**, including otherwise valid rows. No confirmed ownership or COMPLETE certification is claimed for these hypotheses.

`--workflow-min-margin` controls abstention (default 0: every accepted assignment must still have a strictly positive margin). Context v2 adds shared-file affinity, a post-report-operation penalty, independently compliant context and a clock estimated from at least three identity-linked policy resources. No fixed clock period or case-family rule is supplied. Initial account operations do not receive the clock feature. `--workflow-scoring contextual --workflow-min-margin 0.25` reproduces the previous preview, and `--workflow-scoring anchor --workflow-min-margin 0.25` is the result-free timing control. The mode never uses case-number priorities, sample answers, competitor predictions or post-cutoff artifacts. `best-effort --artifact-dir <directory>` can keep an alternative run's three review artifacts separate; fixture tests use this option rather than overwriting root predictions.

## Verify and test

```bash
python3 code/evaluation/main.py all           # every test suite + labeled evaluation; non-zero exit on any failure
python3 code/evaluation/main.py validate --pred runs/provisional/output.csv --requests dataset/deletion_requests.csv

# Scoring against the public samples needs predictions for the SAMPLE requests (the 518-case output has no labels):
python3 code/main.py run --requests sample_deletion_requests.csv --out runs/samples/output.csv --diagnostics runs/samples/diagnostics.json
python3 code/evaluation/main.py score --pred runs/samples/output.csv --gold dataset/sample_output.csv --diff

python3 scripts/write_reports.py              # re-run the producing run and refresh the numeric blocks of the two reports
```

Metric definitions, results, the synthetic evaluation cases, failures found and improvements made are in `code/evaluation/evaluation_report.md`; model/token/cost accounting (the final run uses no model) is in `code/evaluation/usage_report.md`; decisions, alternatives, measurements and limitations are in `code/docs/DECISIONS.md`; the diagnosis of the public-sample regressions is in `code/docs/SAMPLE_REGRESSION_DIAGNOSIS.md`.

## Package

```bash
python3 scripts/package.py                    # builds ./code.zip (README, code/, scripts/, a generated evaluation/ copy of the two reports)
python3 scripts/package.py --verify           # also extracts it to a temp dir, supplies the dataset separately, then runs the tests, run and verify there
```

The archive excludes `dataset/`, virtual environments, caches, `runs/`, secrets and nested archives, and the packager fails if it finds a secret-looking string or an archive inside.

## How it works

1. **Extract** (`ghostaudit/extract/`): SQL snapshots (executed in an in-memory SQLite), JSON exports and bundles, six log dialects, the shift handover, PDFs (`pdftotext`) and the 11 PNG screenshots (hash-bound transcriptions in `ghostaudit/image_transcriptions/`, cross-checked against local OCR) become timestamped observations with two times each: when the artifact existed and when the record was observed. Snapshot scope declarations are kept, so "not captured" can be told from "absent".
2. **Cutoff** (`caseview.py`): the only way case logic reads evidence. An observation is visible only if **both** its artifact time and its observation time are at or before `audit_at`.
3. **Identity** (`identity.py`): current and historical emails, hashes and phones with the time each belonged to the user; identifiers introduced after the cutoff are excluded. Phones and names are normalized in one place (`normalize.py`); names never link.
4. **Link** (`linking.py`): in the default evidence mode, a record is linked to the subject only through an explicit evidence chain (a direct identifier, a lookup key, a source reference or a data-catalog row). Source references are followed to a fixed point (cycle-safe, provenance kept) and a referenced resource's system comes from its observations or the existing id namespace; learning an id through a reference does not date the resource. Activity-window matches remain candidates in this mode. The opt-in workflow preview can evaluate explicitly marked ownership hypotheses as described above. A link contradicted by the record it points at is rejected or reported as a conflict. A linked resource whose category cannot be resolved is an explicit UNKNOWN, never dropped.
5. **State and policy** (`state.py`, `coverage_rules.py`, `obligations.py`): per physical copy (primary and each replica) the latest evidence wins; absence counts only when a lookup or a snapshot supports it, under ONE standard shared with the account proof (the capture must hold records of the resource's category, come from a complete source and have a strong or per-source promoted scope; collection-scoped bundles are per-batch extracts and apply only to records known to belong to them); a REDACTED/ANONYMIZED result label discounts query metadata only, never identifiers in the returned payload; rule conditions (retention, legal hold, ownership, tombstone assessment) are evaluated, not looked up. When no account resource is linked, `account_proof.py` queries the account snapshots by the *subject's* identifiers to establish subject-level absence without naming a resource.
6. **Request scope** (`engine.py`): the subject's earlier requests (from every request file in the data root) define earlier investigation windows. A resource whose every ownership chain was captured inside such a window, before this request began, is carried over (recorded, no step; a PRESENT one becomes UNKNOWN); any evidence at or after the request keeps it in scope.
7. **Plan** (`planner.py`, `contract.py`): findings, remediation and verification in contract order, numbered consecutively; the validator rejects anything that is not a complete chain.

Uncertainty is kept honest: an obligation can be COMPLIANT, a VIOLATION or UNKNOWN, and an UNKNOWN is never turned into a finding, a remediation, a verification step or a certified COMPLETE. The three output statuses have no representation for "not determined", so a case that cannot be determined is reported by the manifest as UNDETERMINED and blocks `export` instead of being guessed.

## Layout

```text
code/main.py                 CLI: run | export | candidate | best-effort | verify | explain | coverage | dump
code/ghostaudit/             the engine (extract/, caseview, identity, linking, state, coverage_rules, obligations, account_proof, planner, validate, export, ...)
code/evaluation/             scorer, labeled evaluation, frozen fixtures (synth_v1..v3 history; synth_v4 current), the two reports
code/tests/                  unit, invariance, regression and cross-check tests
code/docs/                   DECISIONS.md, SAMPLE_DIFFERENCES.md (every public-sample difference) and the sample-regression diagnosis
code/requirements.txt        pinned dependencies (tests and scripts only)
scripts/                     package.py, write_reports.py, diagnosis and measurement scripts, the smoke test
```

## Known limitations

* The output format cannot express "not determined". Eight cases have an undetermined STATUS after all admissible evidence is used, and 18 more are INCOMPLETE on proven violations while carrying unresolved obligations (a plan with gaps) (each a missing fact, not a code gap: no profile-table capture after the request, no restore state for one backup, one irreconcilable marketing-record conflict). They are listed with the exact missing fact in `code/evaluation/evaluation_report.md` section 6 and in `output_best_effort.unresolved.json`; **no certified `output.csv` exists** while any remain, and `best-effort` output is explicitly not certified.
* The PNG transcriptions are hand-authored; they are hash-bound and OCR-cross-checked but not regenerated by code.
* The subject-level account proof rests on the snapshots' own declaration of coverage of a *profile* collection (they hold only 1 to 4 rows each); it is validated against known states, accounts for every copy that could hold the subject, and never names a resource. A copy never captured for the subject is not known to hold anything: a stated modelling assumption.
* The intent classifier is a deterministic heuristic.

---

# Challenge brief (from the starter README)

Build an AI agent that audits whether a user's personal data was actually deleted. A deletion workflow may report **Complete** while data still exists in databases, logs, support attachments, exports, search indexes, archives, or backups, and sync or restore processes may bring deleted data back. The full contract is in [`problem_statement.md`](./problem_statement.md) and [`AGENTS.md`](./AGENTS.md).

## Dataset

All participant-facing files are in `dataset/`:

| File | Contents |
| --- | --- |
| `deletion_requests.csv` | 518 requests |
| `sample_deletion_requests.csv` | 32 sample requests |
| `sample_output.csv` | Correct sample answers |
| `user_identities.csv` | Current user identities |
| `user_audit_log.csv` | Historical identity changes |
| `system_activity.csv` | Activity across services and data processes |
| `deletion_rules.csv` | Required treatment for each data category |
| `evidence_files.csv` | Manifest of supplied evidence files |
| `output.csv` | Blank output template |

Evidence is stored under `dataset/evidence/` and may include PDFs, images, logs, JSON, plain text, or SQL snapshot exports. SQL captures may contain a primary database, regional replicas, a reporting replica, or a failover replica so replication drift can be investigated directly. The `.sql` files are readable as text and executable with SQLite.

Only `deletion_requests.csv` requires answers. The other files provide evidence and context.

---

## Output

Create `output.csv` with these columns in this exact order:

```text
case_id,deletion_status,steps_json
```

Produce exactly one row per request. `deletion_status` is `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`. `steps_json` is an ordered JSON array containing findings, remediation actions, and verification checks. Use an empty array (`[]`) for `NOT_APPLICABLE`. Evidence references may be a `file_id`, `activity_id`, or `audit_id`. Determine the resource state at `audit_at` from the available evidence; reported workflow statuses and operation results are claims. Use `dataset/sample_output.csv` as the format reference.

The final file must contain 518 data rows sorted by `case_id` (plus the header row). The grader parses `steps_json` as JSON, so object-key order and whitespace do not matter; array order does. Order findings, remediation, and verification in that phase order. Within a phase, follow the operation order in the problem statement, then sort by `system_id` and `resource_id`.

---

## Evaluation

`output.csv` will be compared with hidden canonical answers. Scoring considers:

- deletion assessment accuracy;
- current and historical identity resolution;
- discovery of remaining data and recreation risks;
- correct policy application and evidence references; and
- completeness and ordering of remediation and verification steps.

Your `code.zip` must include:

```text
code/evaluation/evaluation_report.md
code/evaluation/usage_report.md
```

- `evaluation_report.md` must cover case, row, field, and sequence accuracy, at least three additional evaluation cases created by you, failures found, and improvements made.
- `usage_report.md` must cover the final full-dataset run, including model providers and names, model calls, input and output tokens, total and average tokens per request, and estimated total and per-request cost. Include per-model and overall totals when using multiple models.

**Important:** Place `evaluation_report.md` and `usage_report.md` inside `code/evaluation/` (matching `code/evaluation/main.py` in this starter layout), write your complete evaluation metrics, custom evaluation test cases, and token/cost breakdowns directly inside those Markdown files, and keep prompts in source code or Markdown files. Automated code evaluation ignores raw data files (`.csv`, `.tsv`, `.json`, `.jsonl`, `.sql`, `.log`), so content stored only in those formats will not be visible to the code judge or AI interviewer.

---

## Chat Transcript

This repository includes [`AGENTS.md`](./AGENTS.md), which instructs compatible AI coding tools to append conversation summaries to `log.txt` in the repository root:

| Platform | Path |
| --- | --- |
| macOS / Linux | `<repo root>/log.txt` |
| Windows | `<repo root>\log.txt` |

- Always launch your AI coding agent from the repository root (or explicitly ask it to read `./AGENTS.md` first) so every turn is logged to `log.txt` with the required `User Prompt`, `Agent Response Summary`, `Actions`, and `Context` sections.
- Upload `log.txt` directly as your `chat_transcript` submission on HackerRank.
- Do not include API keys, tokens, credentials, or secrets in prompts, code, configuration, or `log.txt`.

---

## Packaging `code.zip` and submission checklist

Use `python3 scripts/package.py` (see "Package" above); it replaces the starter's `zip -r code.zip README.md code ...` command, which still works and now also carries `code/requirements.txt`. Do not include `dataset/`, virtual environments, build caches or nested archives. Before submitting, confirm that:

- `output.csv` is the file written by `python3 code/main.py export` (never hand-edited), with the exact header `case_id,deletion_status,steps_json` and all 518 rows;
- every `steps_json` value is a valid JSON array with consecutive step numbers starting at `1`;
- findings cite valid evidence ids, `COMPLETE` verification steps cite evidence proving the current state, and remediation and future verification steps use an empty `evidence_id`;
- `code.zip` includes the runnable code, this `README.md`, `code/evaluation/evaluation_report.md` and `code/evaluation/usage_report.md`;
- `log.txt` is the unedited append-only log and is uploaded as the `chat_transcript`;
- no API keys, credentials, real personal data or sensitive configuration are included.
