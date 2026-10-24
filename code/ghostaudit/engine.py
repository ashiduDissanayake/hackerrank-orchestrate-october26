"""Per-case audit: intent -> subject -> links -> obligations -> status -> steps.

A deterministic function of the request, admissible evidence and explicitly supplied earlier-request context.
The optional workflow experiment additionally supplies competing-request hypotheses; it cannot be certified.
No inferred link is fed back into another case's evidence or candidate graph.

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
PROOF_DEFAULTS = {"allow_weak": False, "require_row": False, "pre_request_exclusion": True, "weak_promotion": True, "episode_scoping": True}


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
    carried_over: list = field(default_factory=list)    # resources scoped to an EARLIER request of the same subject (never silently dropped)
    workflow_inferences: list = field(default_factory=list)  # optional heuristic proposals, never certified evidence
    workflow_decisions: list = field(default_factory=list)


def carried_over_from(ln, req, earlier):
    """Earlier requests of the same subject whose investigation window explains ALL of this link's ownership evidence: every chain was
    captured (and observed) before this request was made and no later than that earlier request's audit. A resource with any chain at
    or after requested_at is part of this request's trail and is never carried over; neither is evidence that falls between the two
    requests, or any evidence of a subject with no earlier request."""
    if not ln.chains:
        return []
    last = max(max(c.time or "", c.available or "") for c in ln.chains)
    if last >= req.requested_at:
        return []
    return [e.case_id for e in earlier if e.audit_at <= req.requested_at and last <= e.audit_at
            and all(e.requested_at <= (c.available or c.time) <= e.audit_at for c in ln.chains)]


def audit_case(req, store, ident, rules, unknown_policy="not_certified", allow_weak=False, require_row=False, pre_request_exclusion=True, weak_promotion=True,
               earlier_requests=(), episode_scoping=True, view_cls=CaseView, workflow_inferences=(), workflow_decisions=()):
    intent = classify(req.request_text)
    if not intent.deletion:
        return CaseResult(req.case_id, "NOT_APPLICABLE", "NOT_APPLICABLE", [], intent)
    subj = ident.resolve(req.email, req.audit_at)
    cv = view_cls(store, req.audit_at)     # production: CaseView. Only measurement scripts pass a relaxed view (never the CLI)
    lr = link_subject(cv, subj)
    inferred = []
    if workflow_inferences:
        from .linking import Chain, Link
        for p in workflow_inferences:
            rid = p["resource_id"]
            if rid in lr.links or p["event_time"] > req.audit_at:
                continue
            lr.links[rid] = Link(rid, p["system_id"],
                                 [Chain("workflow_inference", p["activity_id"], p["activity_id"], "workflow_assignment",
                                        subj.user_id or "", p["event_time"], p["event_time"])],
                                 system_basis="workflow_target")
            inferred.append(dict(p))
    actions = action_table(rules)
    obs, carried = [], []
    for rid in sorted(lr.links):
        ln = lr.links[rid]
        ob = evaluate(cv, subj, ln, actions)
        if ob is None:
            continue
        if (rid in {p["resource_id"] for p in inferred} and ob.category == "USER_PROFILE" and ob.verdict == "COMPLIANT"):
            # Inferring a previously unknown id does not make an old, pre-request
            # empty snapshot evidence of this request's final state. Require the
            # same subject proof or timely explicit/per-copy absence evidence.
            from .state import copy_states
            states = copy_states(cv, rid, ln.system_id, None, subj, ob.category)
            timely = bool(states.latest) and all(e.kind == "absent" and e.time >= req.requested_at for e in states.latest.values())
            proof = account_proof(cv, subj, req.requested_at, allow_weak, require_row, pre_request_exclusion, weak_promotion)
            if not timely and proof.status != "ABSENT":
                ob = type(ob)(ob.system_id, rid, ob.category, ob.action, "UNKNOWN", "inferred_profile_state_not_established", "",
                              {"underlying_evidence": ob.evidence_id, "proof_status": proof.status, "proof_reason": proof.reason,
                               "missing": "post-request account state for the inferred profile id"})
        co = carried_over_from(ln, req, earlier_requests) if episode_scoping else []
        if co:
            # Evidence that only serves an earlier request's window. Resolved or unresolved items are scoped out with a record; a PRESENT
            # record is never hidden: it becomes an UNKNOWN (no step, no finding) that blocks certification.
            carried.append({"resource_id": rid, "system_id": ln.system_id, "category": ob.category, "earlier_requests": co,
                            "verdict": ob.verdict, "reason": ob.reason, "evidence_id": ob.evidence_id,
                            "chains": [(c.kind, c.evidence_id, c.time) for c in ln.chains]})
            if ob.verdict == "VIOLATION":
                obs.append(type(ob)(ob.system_id, rid, ob.category, ob.action, "UNKNOWN", "carried_over_present", "",
                                    {"earlier_requests": co, "underlying": f"{ob.reason}:{ob.evidence_id}",
                                     "missing": "this request's own trail contains no evidence of the record; its only ownership evidence belongs to an earlier request, "
                                                "so its state after this request is not evidenced"}))
            continue
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
                     [o for o in obs if o.verdict == "UNKNOWN"], list(subj.conditions), cands, carried)
    res.workflow_inferences = inferred
    res.workflow_decisions = list(workflow_decisions)
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
