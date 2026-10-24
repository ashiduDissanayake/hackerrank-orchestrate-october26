"""Output validation against the contract (AGENTS.md 6.3-6.6, problem_statement.md).

validate_row  -> list of error strings for one output row.
validate_rows -> errors for a whole file (row count, ordering, duplicates, per-row checks).

Evidence admissibility (evidence captured/created after audit_at) is checked when an
`evidence_time` resolver is supplied: evidence_time(evidence_id) -> ISO timestamp or None.
"""
import csv
import json
import re

from .contract import (
    OP_PHASE,
    OP_STATE,
    OUTPUT_COLUMNS,
    STATUSES,
    STEP_FIELDS,
    sort_key,
)


# An incomplete deletion must be a complete plan: every finding is remediated and then verified, and nothing is
# remediated or verified without a finding that justifies it (AGENTS.md 6.3: findings, the COMPLETE remediation
# plan, and the checks that must pass afterwards).
FINDING_REMEDIATIONS = {
    "REPORT_REMAINING_RECORD": ("DELETE_RECORD",),
    "REPORT_EXPOSED_PII": ("REDACT_RECORD", "ANONYMIZE_RECORD"),
    "REPORT_ACTIVE_DATA_FLOW": ("DISABLE_DATA_FLOW",),
    "REPORT_RESTORE_RISK": ("BLOCK_RESTORE",),
}
REMEDIATION_VERIFICATION = {
    "DELETE_RECORD": "VERIFY_RECORD_ABSENT", "REDACT_RECORD": "VERIFY_RECORD_REDACTED",
    "ANONYMIZE_RECORD": "VERIFY_RECORD_ANONYMIZED", "DISABLE_DATA_FLOW": "VERIFY_DATA_FLOW_DISABLED",
    "BLOCK_RESTORE": "VERIFY_RESTORE_BLOCKED",
}


def _chain_errors(case_id, steps):
    errs = []
    by = {}
    for s in steps:
        by.setdefault((s["system_id"], s["resource_id"]), []).append(s["operation"])
    for (system, rid), ops in sorted(by.items()):
        findings = [o for o in ops if o in FINDING_REMEDIATIONS]
        rems = [o for o in ops if o in REMEDIATION_VERIFICATION]
        for f in findings:
            if not any(r in ops for r in FINDING_REMEDIATIONS[f]):
                errs.append(f"{case_id}: {f} on {system}/{rid} has no matching remediation ({'/'.join(FINDING_REMEDIATIONS[f])})")
            need = {REMEDIATION_VERIFICATION[r] for r in FINDING_REMEDIATIONS[f]}
            if not need & set(ops):
                errs.append(f"{case_id}: {f} on {system}/{rid} has no matching verification ({'/'.join(sorted(need))})")
        for r in rems:
            if not any(r in FINDING_REMEDIATIONS[f] for f in findings):
                errs.append(f"{case_id}: {r} on {system}/{rid} has no finding that justifies it")
            if REMEDIATION_VERIFICATION[r] not in ops:
                errs.append(f"{case_id}: {r} on {system}/{rid} has no matching verification ({REMEDIATION_VERIFICATION[r]})")
    return errs


def validate_row(case_id, status, steps_json, audit_at=None, evidence_time=None):
    errs = []

    def err(msg):
        errs.append(f"{case_id}: {msg}")

    if status not in STATUSES:
        err(f"invalid deletion_status {status!r}")
        return errs
    try:
        steps = json.loads(steps_json)
    except (TypeError, json.JSONDecodeError) as e:
        err(f"steps_json is not valid JSON ({e})")
        return errs
    if not isinstance(steps, list):
        err("steps_json is not a JSON array")
        return errs

    if status == "NOT_APPLICABLE":
        if steps:
            err("NOT_APPLICABLE must have steps_json == []")
        return errs

    if not steps:
        err(f"{status} must have at least one step")
        return errs

    keys = set()
    for i, s in enumerate(steps, start=1):
        if not isinstance(s, dict) or set(s) != set(STEP_FIELDS):
            err(f"step {i}: fields must be exactly {list(STEP_FIELDS)}")
            return errs
        if s["step_no"] != i:
            err(f"step {i}: step_no is {s['step_no']!r}, expected consecutive numbering from 1")
        op = s["operation"]
        if op not in OP_PHASE:
            err(f"step {i}: unknown operation {op!r}")
            continue
        if s["phase"] != OP_PHASE[op]:
            err(f"step {i}: operation {op} belongs to phase {OP_PHASE[op]}, got {s['phase']}")
        if s["state"] != OP_STATE[op]:
            err(f"step {i}: operation {op} requires state {OP_STATE[op]}, got {s['state']}")
        if not s["system_id"] or not s["resource_id"]:
            err(f"step {i}: empty system_id or resource_id")
        k = (s["phase"], s["system_id"], s["resource_id"], op)
        if k in keys:
            err(f"step {i}: duplicate step for {k}")
        keys.add(k)

    if errs:
        return errs

    # canonical order (phase, operation table order, system_id, resource_id)
    for a, b in zip(steps, steps[1:]):
        if sort_key(a) > sort_key(b):
            err(f"steps {a['step_no']}->{b['step_no']} are out of canonical order")
            break

    phases = {s["phase"] for s in steps}
    if status == "COMPLETE":
        if phases != {"VERIFICATION"}:
            err("COMPLETE must contain only VERIFICATION steps")
        for s in steps:
            if not s["evidence_id"]:
                err(f"step {s['step_no']}: COMPLETE verification must cite evidence")
    else:  # INCOMPLETE
        if "FINDING" not in phases:
            err("INCOMPLETE must contain at least one FINDING step")
        for s in steps:
            if s["phase"] == "FINDING" and not s["evidence_id"]:
                err(f"step {s['step_no']}: finding must cite evidence")
            if s["phase"] != "FINDING" and s["evidence_id"] != "":
                err(f"step {s['step_no']}: {s['phase']} step must use empty evidence_id")

    if status == "INCOMPLETE":
        errs += _chain_errors(case_id, steps)

    if audit_at and evidence_time:
        for s in steps:
            eid = s["evidence_id"]
            if not eid:
                continue
            t = evidence_time(eid)
            if t is None:
                err(f"step {s['step_no']}: evidence_id {eid!r} does not exist")
            elif t > audit_at:
                err(f"step {s['step_no']}: evidence {eid} dated {t} is after audit_at {audit_at}")
    return errs


def case_sort_key(case_id):
    """Natural order (case_2 < case_10 < case_100): the order of dataset/deletion_requests.csv.
    The contract says only 'sorted by case_id'; plain string order would put case_100 before case_33.
    Recorded as an open ambiguity in code/docs/DECISIONS.md (A9)."""
    m = re.match(r"^(.*?)(\d+)$", case_id)
    return (m.group(1), int(m.group(2))) if m else (case_id, -1)


def read_output(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = list(reader)
    return header, rows


def validate_rows(path, expected_case_ids=None, audit_at_by_case=None, evidence_time=None):
    errs = []
    header, rows = read_output(path)
    if tuple(header or ()) != OUTPUT_COLUMNS:
        errs.append(f"header must be {','.join(OUTPUT_COLUMNS)}, got {header}")
        return errs
    ids = []
    for r in rows:
        if len(r) != 3:
            errs.append(f"row has {len(r)} columns: {r[:1]}")
            continue
        ids.append(r[0])
        at = (audit_at_by_case or {}).get(r[0])
        errs += validate_row(r[0], r[1], r[2], audit_at=at, evidence_time=evidence_time)
    if len(set(ids)) != len(ids):
        errs.append("duplicate case_id rows")
    if ids != sorted(ids, key=case_sort_key):
        errs.append("rows are not in natural case_id order (see validate.case_sort_key)")
    if expected_case_ids is not None:
        missing = set(expected_case_ids) - set(ids)
        extra = set(ids) - set(expected_case_ids)
        if missing:
            errs.append(f"{len(missing)} case_ids missing, e.g. {sorted(missing)[:3]}")
        if extra:
            errs.append(f"{len(extra)} unexpected case_ids, e.g. {sorted(extra)[:3]}")
    return errs
