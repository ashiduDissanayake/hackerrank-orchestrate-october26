"""Per-case audit: intent -> subject -> links -> obligations -> status -> steps.

A pure function of (request, admissible evidence): no cross-case state, so a case yields the same result alone,
in a shuffled batch, or beside unrelated or later requests.

Internal status vs output status (user decision U8): UNKNOWN obligations are kept distinct from violations.
The CSV needs one of three statuses, and the output policy for unresolved obligations is still an OPEN decision
(P3/P6). Two switchable policies exist (see DECISIONS.md for the measured effect of each):
  established_only       status/steps reflect only what the evidence establishes; unresolved items are listed in
                         diagnostics (default, announced in every run report)
  unknown_is_incomplete  any unresolved obligation makes the case INCOMPLETE
"""
from dataclasses import dataclass, field

from .caseview import CaseView
from .intent import classify
from .linking import link_subject, window_candidates
from .obligations import account_gap, action_table, evaluate
from .planner import plan


@dataclass
class CaseResult:
    case_id: str
    status: str                      # output status
    internal: str                    # COMPLETE | INCOMPLETE | NOT_APPLICABLE | UNDETERMINED
    steps: list
    intent: object = None
    subject: object = None
    links: dict = field(default_factory=dict)
    rejected: list = field(default_factory=list)
    obligations: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    conditions: list = field(default_factory=list)
    candidates: list = field(default_factory=list)


def audit_case(req, store, ident, rules, unknown_policy="established_only"):
    intent = classify(req.request_text)
    if not intent.deletion:
        return CaseResult(req.case_id, "NOT_APPLICABLE", "NOT_APPLICABLE", [], intent)
    subj = ident.resolve(req.email, req.audit_at)
    cv = CaseView(store, req.audit_at)
    lr = link_subject(cv, subj)
    actions = action_table(rules)
    obs = []
    for rid in sorted(lr.links):
        ob = evaluate(cv, subj, lr.links[rid], actions)
        if ob is not None:
            obs.append(ob)
    cands = window_candidates(cv, req, set(lr.links))
    if not any(o.category == "USER_PROFILE" for o in obs):
        obs.append(account_gap([c for c in cands if c[2] == "account_service"]))
    res = CaseResult(req.case_id, "", "", [], intent, subj, lr.links, lr.rejected, obs,
                     [o for o in obs if o.verdict == "UNKNOWN"], list(subj.conditions), cands)
    violations = [o for o in obs if o.verdict == "VIOLATION"]
    if subj.user_id is None:
        res.internal, res.status, res.steps = "UNDETERMINED", "INCOMPLETE", []
        return res
    if violations:
        res.internal = res.status = "INCOMPLETE"
    elif res.unresolved or res.conditions:
        res.internal = "UNDETERMINED"
        if unknown_policy == "established_only":
            res.status = "COMPLETE"      # nothing established as violated; unresolved items are listed, never turned into steps
        elif unknown_policy == "unknown_is_incomplete":
            res.status = "INCOMPLETE"    # not shown complete -> INCOMPLETE (may have no finding: contract-invalid, flagged)
        else:
            raise ValueError(f"unknown policy {unknown_policy!r}")
    else:
        res.internal = res.status = "COMPLETE"
    res.steps = plan(obs, res.status)
    return res
