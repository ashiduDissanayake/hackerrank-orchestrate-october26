# Usage report: model providers, calls, tokens and cost

Single authoritative copy (`code/evaluation/usage_report.md`); `scripts/package.py` generates the packaging copy. The run block is regenerated from the run manifest by `python3 scripts/write_reports.py`.

## 1. The final full-dataset run

The pipeline that produces the provisional predictions is deterministic code (Python standard library plus the poppler `pdftotext` command). No certified root `output.csv` exists. **It calls no language model at run time**: no provider, no API key, no network access. The optional workflow preview also makes zero model calls, uses zero API input/output tokens, and has $0.00 model cost over all 518 requests ($0.00 per request). Its CSV is explicitly uncertified.

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

| item | value |
|---|---|
| model providers used by the final run | none |
| model names | none |
| model calls | 0 |
| input tokens / output tokens | 0 / 0 |
| total tokens; average tokens per request (518 requests) | 0; 0 |
| estimated cost; per-request cost | $0.00; $0.00 |
| per-model totals | not applicable (no models) |

The manifest field `runtime_model_calls` is written by the code itself and is 0 by construction; there is no model client on the prediction path (`code/ghostaudit` never imports an LLM SDK; the `anthropic` package in `requirements.txt` is used only by `scripts/api_smoke_test.py`).

## 2. Where model use did happen (development only, not part of the final run)

### 2.1 Paid API calls made by project scripts

`scripts/api_smoke_test.py`, run once on 2026-10-24 to check model availability, structured output and a tool-use round trip before any integration was considered. Provider: Anthropic. Per model: 1 structured-output request and a tool-use round trip of 2 requests (3 calls). Token counts are the `usage` fields returned by the API. Prices are the first-party rates from the claude-api reference (cached 2026-10-06; Haiku 5.5 rate applies to prompts up to 100K tokens), so the cost column is an estimate.

| provider | model id | calls | input tokens | output tokens | total tokens | avg tokens / call | est. cost (USD) |
|---|---|---:|---:|---:|---:|---:|---:|
| Anthropic | claude-haiku-5-5 | 3 | 1,168 | 142 | 1,310 | 437 | 0.000188 |
| Anthropic | claude-sonnet-5-5 | 3 | 1,168 | 142 | 1,310 | 437 | 0.003756 |
| Anthropic | claude-opus-5-5 | 3 | 1,168 | 238 | 1,406 | 469 | 0.009432 |
| **overall** | | **9** | **3,504** | **522** | **4,026** | **447** | **0.013376** |

Not counted: the `models.list()` requests (no tokens), and any silent SDK retry (none was observed; the SDK does not expose a retry count in the usage fields). No other script has called a paid API. No cache was used, so there are no cache hits or misses to report.

### 2.2 Coding-agent sessions (not measurable here)

The workflow-attribution follow-up was implemented in Codex. This runtime exposes no authoritative exact model identifier or session token/cost totals, so no identifier, token count or cost is guessed. No project script made a paid API call during this follow-up. Historical Claude session details below describe earlier work.

The code, tests and documents were developed in Claude Code sessions (models `claude-opus-5-5`, then `claude-sonnet-5-5`). The agent has no access to the token counts or cost of its own session, so **no figure is given and none is estimated**; the authoritative record of what was done is the root `log.txt`. This includes the visual inspection of the 11 PNG screenshots: the agent viewed each image with the session's image viewer and typed the visible records into `code/ghostaudit/image_transcriptions/*.json`. That is development-time preprocessing, not a call made by the project's code. Each transcription is bound to its image by sha256 and is cross-checked against local OCR (tesseract) in `code/tests/test_image_transcriptions.py`; a fresh install needs no model to reproduce the output because the transcriptions are part of the package.

### 2.3 Proposed but not run

A small intent-classification pilot (398 distinct request texts, `claude-haiku-5-5` with adjudication on `claude-sonnet-5-5`, estimated about $0.05, hard cap $0.50) was proposed in `code/docs/DECISIONS.md` (P8). It has **not** been approved or run, so it contributes nothing to this report. Any future use would be logged here with actual usage.

## 3. Reproducibility versus model behavior

Because the final run uses no model, two kinds of reproduction both apply and are checked: `python3 code/main.py verify <manifest>` regenerates the output byte for byte from the same inputs and code; and a fresh checkout or the extracted `code.zip` regenerates the same output with the dataset supplied separately (`scripts/package.py --verify`). There is no cache of model responses to replay and no fresh-call variance to measure.
