"""Obligations -> ordered steps. The only producer of steps; ordering via contract.canonical_sort."""
from .contract import canonical_sort

FIND = {"DELETE": ("REPORT_REMAINING_RECORD",), "REDACT": ("REPORT_EXPOSED_PII",), "ANONYMIZE": ("REPORT_EXPOSED_PII",),
        "DISABLE": ("REPORT_ACTIVE_DATA_FLOW",), "BLOCK_RESTORE": ("REPORT_RESTORE_RISK",)}
REMEDIATE = {"DELETE": "DELETE_RECORD", "REDACT": "REDACT_RECORD", "ANONYMIZE": "ANONYMIZE_RECORD",
             "DISABLE": "DISABLE_DATA_FLOW", "BLOCK_RESTORE": "BLOCK_RESTORE"}
VERIFY = {"DELETE": "VERIFY_RECORD_ABSENT", "REDACT": "VERIFY_RECORD_REDACTED", "ANONYMIZE": "VERIFY_RECORD_ANONYMIZED",
          "DISABLE": "VERIFY_DATA_FLOW_DISABLED", "BLOCK_RESTORE": "VERIFY_RESTORE_BLOCKED", "RETAIN": "VERIFY_RECORD_PRESENT"}


def _step(phase, ob, op, evidence):
    from .contract import OP_STATE
    return {"step_no": 0, "phase": phase, "system_id": ob.system_id, "resource_id": ob.resource_id, "operation": op,
            "state": OP_STATE[op], "evidence_id": evidence}


def plan(obligations, status):
    """status is COMPLETE or INCOMPLETE. Resolved obligations only (UNKNOWN ones never produce steps)."""
    steps = []
    for ob in obligations:
        if ob.verdict == "UNKNOWN" or ob.resource_id is None or ob.system_id is None:
            continue
        if ob.detail.get("no_obligation"):
            continue
        key = ob.action
        if status == "COMPLETE":
            if ob.verdict == "COMPLIANT":
                steps.append(_step("VERIFICATION", ob, VERIFY[key], ob.evidence_id))
            continue
        if ob.verdict == "VIOLATION":
            steps.append(_step("FINDING", ob, FIND[key][0], ob.evidence_id))
            steps.append(_step("REMEDIATION", ob, REMEDIATE[key], ""))
        steps.append(_step("VERIFICATION", ob, VERIFY[key], ""))
    return canonical_sort(_dedupe(steps))


def _dedupe(steps):
    seen, out = set(), []
    for s in steps:
        k = (s["phase"], s["system_id"], s["resource_id"], s["operation"])
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out
