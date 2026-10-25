"""Explicit, auditable submission assumptions; never evidence-only certification.

The CSV requires a prediction, while the strict audit can abstain internally.
These rules use only the case view and never supply invented resource IDs,
permission flags, identity aliases, or observations. Their inputs and original
unknowns are retained separately from established evidence.
"""
from dataclasses import replace
from urllib.parse import urlsplit

from .account_proof import account_proof, is_profile_row
from .coverage_rules import row_matches
from .obligations import evaluate
from .state import copy_states


def _record(ob, rule, sources, assumption):
    return {"rule": rule, "system_id": ob.system_id, "resource_id": ob.resource_id,
            "original_verdict": ob.verdict, "original_reason": ob.reason,
            "source_evidence_ids": sorted(set(sources)), "assumption": assumption,
            "certified": False}


def _recoverable_archive(cv, subj, ob):
    """A usable retained archive supplies a restore-risk prediction, not a permission observation."""
    cs = copy_states(cv, ob.resource_id, ob.system_id, subj=subj, category=ob.category)
    for e in sorted(cs.latest.values(), key=lambda e: (e.time, e.evidence_id), reverse=True):
        o = e.obs
        if e.kind != "present" or o is None:
            continue
        path, end, drill = o.f("archive_path"), o.f("retention_end"), o.f("last_drill")
        if (not path or not urlsplit(path).scheme or (o.f("checksum") or "").lower() != "verified"
                or not end or end[:10] < cv.audit_at[:10]
                or not drill or drill[:10] > o.observed_at[:10]):
            continue
        return o
    return None


def _later_catalog_owner(cv, subj, link):
    """A later stable-owner mapping may outrank earlier contact fields, never another stable owner."""
    rows = cv.for_resource(link.resource_id)
    if not rows:
        return None
    for o in rows:
        owners = set((o.f("ids_user") or "").split("|")) - {"", subj.user_id}
        if owners:
            return None
    mappings = [c for c in cv.catalog_links() if c.resource_id == link.resource_id and c.system_id == link.system_id]
    if not mappings:
        return None
    latest = max(c.event_time for c in mappings)
    winners = [c for c in mappings if c.event_time == latest]
    valid_emails = {i.value for i in subj.identifiers if i.field == "email" and i.verified and i.linkable_at(latest)}
    if any(c.user_ref != subj.user_id or c.email not in valid_emails for c in winners):
        return None
    # Later contact fields, even without a user_id, keep the conflict unresolved.
    if any(o.present and o.observed_at >= latest for o in rows):
        return None
    return min(winners, key=lambda c: c.activity_id)


def _persisted_subject_absence(cv, subj):
    """Forecast persistence of a clean complete snapshot only for a never-observed profile.

    The empty lower bound removes only the request-time freshness requirement;
    completeness, category, identity, physical-copy and BOTH upper cutoffs remain.
    No known past/present profile, hidden row or lagging replica can be erased.
    """
    if subj.conditions or any(o.present and is_profile_row(o) and row_matches(o, subj)
                              for o in cv.for_system("account_service")):
        return None
    p = account_proof(cv, subj, "")
    return p if p.status == "ABSENT" else None


def resolve(req, cv, subj, obligations, links, actions):
    """Return predicted obligations and their separately disclosed assumptions."""
    if subj.user_id is None or subj.conditions:
        return list(obligations), []
    out, decisions = [], []
    absence = None
    absence_checked = False
    for original in obligations:
        ob, decision = original, None
        if ob.verdict != "UNKNOWN":
            out.append(ob)
            continue
        if ob.reason == "no_restore_flag_in_admissible_evidence" and ob.category == "BACKUP_ARCHIVE":
            o = _recoverable_archive(cv, subj, ob)
            if o:
                decision = _record(ob, "recoverable_archive_risk", [o.evidence_id],
                                   "A present, checksum-verified archive with a storage path, drill history and unexpired retention is treated as a recreation risk unless restore blocking is evidenced. Permission itself is not observed.")
                ob = replace(ob, verdict="VIOLATION", reason="predicted_recoverable_archive_risk", evidence_id=o.evidence_id)
        elif (ob.reason == "conflicting_identity_evidence" and ob.action == "DELETE"
              and ob.category != "SUPPORT_ATTACHMENT" and ob.resource_id in links):
            link = links[ob.resource_id]
            owner = _later_catalog_owner(cv, subj, link)
            if owner:
                assessed = evaluate(cv, subj, replace(link, conflict=None), actions)
                if assessed and assessed.verdict != "UNKNOWN":
                    decision = _record(ob, "later_catalog_owner", [owner.activity_id, assessed.evidence_id],
                                       "A later catalog association matching stable user_id and verified email outranks earlier contact fields with no competing stable owner. This does not merge the two people's identities.")
                    ob = assessed
        elif (ob.category == "USER_PROFILE" and ob.reason in ("unresolved_link", "inferred_profile_state_not_established")):
            if not absence_checked:
                absence, absence_checked = _persisted_subject_absence(cv, subj), True
            if absence:
                decision = _record(ob, "clean_snapshot_persistence", [e.evidence_id for e in absence.copies.values()],
                                   "A latest complete clean profile snapshot is assumed to persist to audit_at when no admissible observation ever shows this subject's profile. The capture may predate the request; no account ID is invented.")
                ob = replace(ob, verdict="COMPLIANT", reason="predicted_profile_absence_persistence", evidence_id=absence.evidence_id,
                             detail={**ob.detail, "no_step": ob.resource_id is None, "snapshot_reason": absence.reason})
        if decision:
            decision["predicted_verdict"] = ob.verdict
            ob.detail = {**ob.detail, "prediction_assumption": decision}
            decisions.append(decision)
        out.append(ob)
    return out, decisions
