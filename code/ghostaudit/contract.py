"""Output contract constants (AGENTS.md section 6.3/6.4, problem_statement.md).

Single source of truth for phases, operations, states and the canonical step order.
Nothing here is derived from sample answers.
"""

STATUSES = ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE")
PHASES = ("FINDING", "REMEDIATION", "VERIFICATION")

# (phase, operation, state) in the order the problem statement's operation table lists them.
OPERATION_TABLE = (
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
)

OP_STATE = {op: state for _, op, state in OPERATION_TABLE}
OP_PHASE = {op: phase for phase, op, _ in OPERATION_TABLE}
OP_RANK = {op: i for i, (_, op, _) in enumerate(OPERATION_TABLE)}
PHASE_RANK = {p: i for i, p in enumerate(PHASES)}

STEP_FIELDS = ("step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id")
OUTPUT_COLUMNS = ("case_id", "deletion_status", "steps_json")


def sort_key(step):
    """Canonical order: phase, operation (table order), system_id, resource_id (lexicographic)."""
    return (
        PHASE_RANK[step["phase"]],
        OP_RANK[step["operation"]],
        step["system_id"],
        step["resource_id"],
    )


def canonical_sort(steps):
    """Sort steps canonically and renumber from 1. Pure function; input is not mutated."""
    ordered = sorted((dict(s) for s in steps), key=sort_key)
    for i, s in enumerate(ordered, start=1):
        s["step_no"] = i
    return ordered
