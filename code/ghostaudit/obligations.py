"""Obligations: the required final state of each linked resource under deletion_rules.csv, with a verdict.

Verdicts keep three things apart (user decision U8):
  COMPLIANT  supporting admissible evidence shows the required state
  VIOLATION  admissible evidence establishes a failure to meet the required state
  UNKNOWN    the evidence cannot establish either (reason says what is missing)

Rule conditions evaluated here (rule ids from deletion_rules.csv):
  rule_05 SUPPORT_MESSAGE      REDACT   assumed to apply to every support conversation record (shared context)   [A9]
  rule_06 SUPPORT_ATTACHMENT   DELETE   only if the attachment belongs only to the subject, else UNKNOWN
  rule_07/08 ANALYTICS/TELEMETRY ANONYMIZE only while the record is still attributable
  rule_11 EMAIL_DELIVERY_LOG   REDACT   only if the log contains a user email
  rule_12 SECURITY_AUDIT_LOG   RETAIN   only within retention_until (unknown retention is treated as within)    [A10]
  rule_13 LEGAL_HOLD_RECORD    RETAIN   only while the hold is active
  rule_14 BACKUP_ARCHIVE       RETAIN   archive stays; restore access must be blocked
  rule_15 ACCOUNT_TOMBSTONE    REDACT   activated by identifying the record as a tombstone; assessment checks for
                                        prohibited direct identifiers (only the stable user reference may remain)
Data flows have no rule row: "no active sync, import or restore path" (AGENTS.md 6.5) -> must be disabled.
"""
from collections import Counter
from dataclasses import dataclass, field

from .facts import read
from .state import copy_states, latest_fact

DELETE, REDACT, ANONYMIZE, RETAIN = "DELETE", "REDACT", "ANONYMIZE", "RETAIN"
EXTRA_ACTIONS = {"DATA_FLOW": "DISABLE", "BACKUP_ARCHIVE": "BLOCK_RESTORE"}


@dataclass
class Obligation:
    system_id: str | None
    resource_id: str | None
    category: str
    action: str
    verdict: str                     # COMPLIANT | VIOLATION | UNKNOWN
    reason: str
    evidence_id: str = ""
    detail: dict = field(default_factory=dict)


def action_table(rules):
    return {r["data_category"]: r["required_action"] for r in rules}


def category_of_resource(obs):
    """Highest-precedence category among the resource's observations (explicit evidence beats system defaults);
    ties go to the most frequent, then alphabetical."""
    from .facts import category_rank
    ranked = [category_rank(o) for o in obs]
    ranked = [(c, r) for c, r in ranked if c]
    if not ranked:
        return None
    top = max(r for _, r in ranked)
    cats = Counter(c for c, r in ranked if r == top)
    return sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _subject_only(cv, subj, rid, obs):
    """rule_06: does the attachment belong only to the subject?"""
    emails = {i.value for i in subj.identifiers if i.field == "email"}
    for c in cv.catalog_links():
        if c.resource_id == rid and c.exclusive and c.user_ref == subj.user_id:
            return True, "catalog confirms the attachment belongs only to the subject"
    others = set()
    for o in obs:
        others |= {e for e in (o.f("ids_email") or "").split("|") if e and e not in emails}
        others |= {u for u in (o.f("ids_user") or "").split("|") if u and u != subj.user_id}
    if others:
        return False, f"attachment also names {sorted(others)[:3]}"
    return True, "every identifier in the attachment belongs to the subject"


def evaluate(cv, subj, link, actions):
    rid, sysid = link.resource_id, link.system_id
    obs = cv.for_resource(rid)
    cat = category_of_resource(obs)
    if cat is None and sysid:  # linked only by a catalog row: no observation yet, the owning system decides the category
        from .facts import SYSTEM_CATEGORY
        cat = SYSTEM_CATEGORY.get(sysid)
    if cat is None:   # a linked resource whose category cannot be resolved is an explicit gap, never a silent drop
        return Obligation(sysid, rid, "UNRESOLVED_CATEGORY", "NONE", "UNKNOWN", "category_unresolved", "",
                          {"missing": "no observation, owning system or id namespace identifies what kind of record this is",
                           "chains": [(c.kind, c.evidence_id) for c in link.chains]})
    act = EXTRA_ACTIONS.get(cat) or actions.get(cat)  # data flows / backups: the obligation is DISABLE / BLOCK_RESTORE, not the table's RETAIN
    o_ = lambda verdict, reason, ev="", **d: Obligation(sysid, rid, cat, act or "NONE", verdict, reason, ev, d)  # noqa: E731

    if link.conflict:
        return o_("UNKNOWN", "conflicting_identity_evidence", "", conflict=link.conflict,
                  chains=[(c.kind, c.evidence_id) for c in link.chains])

    if cat == "DATA_FLOW":
        val, o = latest_fact(cv, rid, "enabled")
        if val is None:
            return o_("UNKNOWN", "no_enabled_flag_in_admissible_evidence")
        return o_("VIOLATION", "data_flow_active", o.evidence_id) if val else o_("COMPLIANT", "data_flow_disabled", o.evidence_id)
    if cat == "BACKUP_ARCHIVE":
        val, o = latest_fact(cv, rid, "restore_allowed")
        if val is None:
            return o_("UNKNOWN", "no_restore_flag_in_admissible_evidence")
        return o_("VIOLATION", "restore_allowed", o.evidence_id) if val else o_("COMPLIANT", "restore_blocked", o.evidence_id)

    cs = copy_states(cv, rid, sysid, link.since(), subj, cat)
    present = cs.present_copies()

    if act == DELETE:
        if cat == "SUPPORT_ATTACHMENT":
            ok, why = _subject_only(cv, subj, rid, obs)
            if not ok:
                return o_("UNKNOWN", "shared_attachment", detail=why)
        if present:
            e = cs.newest("present", present)
            return o_("VIOLATION", "record_present", e.evidence_id, copies=present)
        e = cs.newest("absent")
        if e is None:
            return o_("UNKNOWN", "no_admissible_evidence")
        return o_("COMPLIANT", "record_absent", e.evidence_id, basis=e.basis)

    if act in (REDACT, ANONYMIZE):
        if cat == "EMAIL_DELIVERY_LOG" and not any(read(o, subj).exposed for o in obs):
            return o_("COMPLIANT", "log_has_no_email", cs.newest("present").evidence_id if present else "")
        exposed_events = [e for c, e in cs.latest.items() if e.kind == "present" and read(e.obs, subj).exposed]
        if exposed_events:
            e = max(exposed_events, key=lambda x: (x.time, x.evidence_id))
            return o_("VIOLATION", "identifiers_exposed", e.evidence_id, exposed=sorted(read(e.obs, subj).exposed), copies=present)
        if present:
            e = cs.newest("present", present)
            return o_("COMPLIANT", "treated_record_present", e.evidence_id)
        return o_("UNKNOWN", "record_absent_where_treatment_expected")

    if act == RETAIN:
        if not present:
            return o_("UNKNOWN", "retained_record_not_found")
        e = cs.newest("present", present)
        ret = [read(o).retention_until for o in obs if read(o).retention_until]
        if ret and max(ret) < cv.audit_at:
            return o_("COMPLIANT", "retention_expired_no_obligation", e.evidence_id, retention_until=max(ret), no_obligation=True)
        return o_("COMPLIANT", "retained_record_present", e.evidence_id)

    return o_("UNKNOWN", f"no_rule_for_category:{cat}")


def account_from_tombstone(cv, obligations):
    """Subject-level evidence that the account profile is deleted: a linked ACCOUNT_TOMBSTONE whose own record says
    account_status == DELETED (rule_15's condition is "Account is deleted"). It establishes the STATE of the
    subject's profile without naming a profile resource, so the obligation carries no resource id and the planner
    emits no step for it (a step needs a resource id, and none is evidenced)."""
    best = None
    for ob in obligations:
        if ob.category != "ACCOUNT_TOMBSTONE" or ob.resource_id is None:
            continue
        for o in cv.for_resource(ob.resource_id):
            if o.present and o.f("account_status") == "DELETED":
                if best is None or (o.observed_at, o.evidence_id) > (best[0].observed_at, best[0].evidence_id):
                    best = (o, ob)
    if best is None:
        return None
    o, ob = best
    return Obligation("account_service", None, "USER_PROFILE", DELETE, "COMPLIANT", "account_deleted_per_tombstone", o.evidence_id,
                      {"no_step": True, "tombstone": ob.resource_id, "locator": o.locator})


def account_gap(cands):
    """No profile resource is linked and no tombstone evidences deletion. The obligation exists because rule_01 applies
    to every authorized deletion ("USER_PROFILE ... Always"); its STATE is unknown. gap_class says what is known:
      resource_candidates  deletion-worker activity in the window names account resources (claims; unlinked, shared by
                           concurrent requests, so never accepted as links)
      no_evidence          nothing in the dataset points at an account for this subject"""
    return Obligation("account_service", None, "USER_PROFILE", DELETE, "UNKNOWN", "unresolved_link", "",
                      {"gap_class": "resource_candidates" if cands else "no_evidence",
                       "missing": "no evidence chain links any account_service resource to the subject",
                       "window_candidates": cands})
