"""Per-case audit: intent -> subject -> links -> obligations -> status -> steps.

A pure function of (request, admissible evidence): no cross-case state, so a case yields the same result alone,
in a shuffled batch, or beside unrelated or later requests.

Internal status vs output status (user decision U8, review finding P1-1): UNKNOWN obligations are kept distinct
from violations, and an UNDETERMINED case is NEVER reported COMPLETE by default. The contract defines COMPLETE as
"only when every relevant copy has the required treatment ... and no active path can recreate prohibited data",
which an unresolved obligation does not satisfy, so the non-certifying default is INCOMPLETE. INCOMPLETE cannot
carry invented findings, so such rows are contract-INVALID by construction: they are listed as UNDETERMINED in the
run manifest and the final export gate refuses to export while any exist.
  not_certified        (default) UNDETERMINED -> INCOMPLETE, established steps only, flagged unresolved
  certify_established  UNDETERMINED -> COMPLETE when nothing established is violated. Opt-in only, for measuring the
                       cost of the default; never used for the final export
"""
from dataclasses import dataclass, field

from .account_proof import account_proof
from .caseview import CaseView
from .intent import classify
from .linking import link_subject, window_candidates
from .obligations import account_from_tombstone, account_gap, action_table, evaluate
from .planner import plan


def account_obligation_from_proof(p):
    """Subject-level absence of any account profile, from subject-keyed queries of account snapshots (account_proof.py).
    Records the proof internally like the tombstone proof: no resource id is invented, so no step is emitted."""
    from .obligations import Obligation
    if p.status != "ABSENT":
        return None
    return Obligation("account_service", None, "USER_PROFILE", "DELETE", "COMPLIANT", "no_profile_for_subject_in_snapshot", p.evidence_id,
                      {"no_step": True, "proof_reason": p.reason,
                       "copies": {c: (e.status, e.evidence_id, e.time, e.basis) for c, e in p.copies.items()}, "uncovered_copies": p.uncovered,
                       "excluded_copies": p.excluded})


def proof_summary(p):
    """What the proof found when it could NOT discharge the obligation: the precise information gap for the register."""
    return {"status": p.status, "reason": p.reason,
            "copies": {c: (e.status, e.evidence_id, e.time, e.basis, e.detail) for c, e in p.copies.items()}, "excluded_copies": p.excluded}


# The account-proof switches the engine uses by default (each measured in evaluation_report.md section 5); recorded in every run
# manifest so the configuration that produced an output is explicit rather than implied by code defaults.
PROOF_DEFAULTS = {"allow_weak": False, "require_row": False, "pre_request_exclusion": True, "weak_promotion": True}


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


def audit_case(req, store, ident, rules, unknown_policy="not_certified", allow_weak=False, require_row=False, pre_request_exclusion=True, weak_promotion=True):
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
        ob, proof = account_from_tombstone(cv, obs), None
        if ob is None:
            proof = account_proof(cv, subj, req.requested_at, allow_weak, require_row, pre_request_exclusion, weak_promotion)
            ob = account_obligation_from_proof(proof)
        if ob is None:
            ob = account_gap([c for c in cands if c[2] == "account_service"])
            if proof is not None:
                ob.detail["proof"] = proof_summary(proof)
        obs.append(ob)
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
        if unknown_policy == "not_certified":
            res.status = "INCOMPLETE"
        elif unknown_policy == "certify_established":
            res.status = "COMPLETE"
        else:
            raise ValueError(f"unknown policy {unknown_policy!r}")
    else:
        res.internal = res.status = "COMPLETE"
    res.steps = plan(obs, res.status)
    return res
