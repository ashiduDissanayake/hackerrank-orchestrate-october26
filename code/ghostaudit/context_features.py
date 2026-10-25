"""Observable context for optional attribution hypotheses, never ownership/state proof.

No period, request family or case-number allocation is supplied. A candidate clock
is estimated from at least three independently linked policy resources. Several
clocks can fit a short trace: the largest fitting period is a modelling choice,
not an identification guarantee. The caller must retain alternatives and abstain.
"""
from datetime import datetime
from itertools import combinations
from math import exp

from .obligations import evaluate

POLICY_ACTIONS = {"ANONYMIZE_RECORD", "REDACT_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE"}


def _seconds(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def learned_cadence(anchors):
    anchors = [a for a in anchors if a.event_type in POLICY_ACTIONS and a.target_system != "account_service"]
    if len({a.resource_id for a in anchors}) < 3:
        return None
    times = sorted({round(_seconds(a.event_time)) for a in anchors})
    gaps = sorted({b - a for a, b in combinations(times, 2) if b > a})
    if len(times) < 3 or len(gaps) < 2:
        return None
    # Require at least three cycles between the closest observations; periods of
    # fewer than five seconds are too close to the trace's one-second resolution.
    for period in range(min(gaps) // 3, 4, -1):
        if all(min((t - times[0]) % period, period - (t - times[0]) % period) <= 1 for t in times):
            return {"period_seconds": period, "reference_epoch_seconds": times[0],
                    "anchor_activity_ids": sorted(a.activity_id for a in anchors),
                    "fit_tolerance_seconds": 1}
    return None


def ranking_context(cv, subject, links, request, anchors, actions):
    files = {o.evidence_id for rid in links.links for o in cv.for_resource(rid)
             if o.available_at >= request.requested_at}
    obligations = [evaluate(cv, subject, link, actions) for link in links.links.values()]
    obligations = [o for o in obligations if o is not None]
    return {"linked_files": sorted(files),
            "independently_compliant_context": bool(obligations) and all(o.verdict == "COMPLIANT" for o in obligations),
            "cadence": learned_cadence(anchors)}


def candidate_context(cv, proposal, request, context):
    common = sorted(set(context["linked_files"]) & {o.evidence_id for o in cv.for_resource(proposal["resource_id"])})
    cadence, distance, affinity = context["cadence"], None, 0.0
    # Initial profile deletion is not assumed to share the policy-action clock.
    if proposal["system_id"] == "analytics_platform" and cadence:
        period = cadence["period_seconds"]
        residue = (_seconds(proposal["event_time"]) - cadence["reference_epoch_seconds"]) % period
        distance = min(residue, period - residue)
        affinity = exp(-distance ** 2 / 8)  # smooth two-second scale; a feature, not a probability
    details = {"shared_file_ids": common,
               "operation_after_report": proposal["event_time"] > request.reported_at,
               "independently_compliant_context": context["independently_compliant_context"],
               "cadence": cadence, "cadence_distance_seconds": distance, "cadence_affinity": affinity}
    adjustment = (float(bool(common)) - 2 * details["operation_after_report"]
                  + 2 * details["independently_compliant_context"] + 2 * affinity)
    return adjustment, details


def account_context(cv, proposal, request, subject, anchors, context):
    """Account-only interactions for optional ranking, never proof of ownership.

    A clean case receives affinity only for a CURRENT explicit absent observation,
    rather than every account missing from a broad inventory. Three independently
    linked resources strengthen the existing anchor-distance feature. Both remain
    modelling assumptions; neither changes state or creates an evidence chain.
    """
    from .state import copy_states
    independent = len({a.resource_id for a in anchors})
    strong = independent >= 3
    states = copy_states(cv, proposal["resource_id"], "account_service", None, subject, "USER_PROFILE")
    explicit = sorted({e.evidence_id for e in states.latest.values()
                       if e.kind == "absent" and e.obs is not None and e.time >= request.requested_at})
    present = states.present_copies()
    affinity = bool(explicit) and not present and context["independently_compliant_context"]
    adjustment = float(affinity) - (proposal["features"]["anchor_distance_hours"] if strong else 0)
    return adjustment, {"independent_anchor_count": independent, "strong_anchor_context": strong,
                        "anchor_activity_ids": sorted(a.activity_id for a in anchors),
                        "explicit_absence_evidence_ids": explicit, "present_copies": present,
                        "state_affinity_applied": affinity, "ownership_proven": False}
