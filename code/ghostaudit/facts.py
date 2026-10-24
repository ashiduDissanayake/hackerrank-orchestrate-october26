"""Observation -> data category and state facts.

Everything here reads one observation; reasoning across observations lives in state.py / obligations.py.
"""
from dataclasses import dataclass, field

RECORD_TYPE_CATEGORY = {  # explicit record_type values found in handover / ledger / history records
    "USER_PROFILE": "USER_PROFILE", "SEARCH_INDEX_ENTRY": "SEARCH_INDEX_ENTRY", "ANALYTICS_PROFILE": "ANALYTICS_PROFILE",
    "SUPPORT_MESSAGE": "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT": "SUPPORT_ATTACHMENT", "USER_EXPORT": "USER_EXPORT",
    "DATA_FLOW": "DATA_FLOW", "BACKUP_ARCHIVE": "BACKUP_ARCHIVE", "SECURITY_AUDIT_LOG": "SECURITY_AUDIT_LOG",
    "LEGAL_HOLD_RECORD": "LEGAL_HOLD_RECORD",
}
SYSTEM_CATEGORY = {
    "account_service": "USER_PROFILE", "search_service": "SEARCH_INDEX_ENTRY", "cache_service": "CACHE_ENTRY",
    "analytics_platform": "ANALYTICS_PROFILE", "marketing_platform": "MARKETING_PROFILE", "support_platform": "SUPPORT_MESSAGE",
    "export_service": "USER_EXPORT", "object_storage": "USER_EXPORT", "integration_service": "DATA_FLOW",
    "backup_service": "BACKUP_ARCHIVE", "security_service": "SECURITY_AUDIT_LOG", "legal_service": "LEGAL_HOLD_RECORD",
    "identity_service": "ACCOUNT_TOMBSTONE", "email_delivery_service": "EMAIL_DELIVERY_LOG",
}
DIRECT = ("name", "email", "phone", "email_hash")
TRUE, FALSE = {"1", "true", "True", "yes"}, {"0", "false", "False", "no"}


@dataclass
class Facts:
    category: str | None
    present: bool | None
    exposed: set = field(default_factory=set)      # which direct identifiers the record still carries
    enabled: bool | None = None                     # data flow / connector
    restore_allowed: bool | None = None             # backup archive
    retention_until: str | None = None
    result: str | None = None


def category_of(o):
    rt = o.f("record_type")
    if rt in RECORD_TYPE_CATEGORY:
        return RECORD_TYPE_CATEGORY[rt]
    if (o.kind or "").startswith("contact_"):  # contact-index lookups: a secondary copy of contact identifiers (rule_02)
        return "SECONDARY_IDENTIFIER"
    cat = SYSTEM_CATEGORY.get(o.system_id)
    if o.system_id == "support_platform" and (o.store == "pdf" or o.f("collection") == "ticket_attachments"
                                              or (o.kind or "").startswith("attachment") or o.f("file_name")):
        return "SUPPORT_ATTACHMENT"
    if o.system_id == "analytics_platform" and o.f("email_opt_in") is not None:
        return "MARKETING_PROFILE"
    return cat


def _flag(v):
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    return None


def read(o):
    cat = category_of(o)
    f = Facts(cat, o.present, result=o.f("result"))
    res = o.f("result")
    for k in DIRECT:
        if o.f(k):
            f.exposed.add(k)
    for kind in ("email", "hash", "phone"):  # identifiers embedded in free text (message_text, excerpts, scan hits)
        if o.f(f"ids_{kind}") and not f.exposed:
            f.exposed.add(f"embedded:{kind}")
    if cat == "ANALYTICS_PROFILE" and o.f("user_ref"):
        f.exposed.add("user_ref")
    if o.kind in ("record_lookup",) or o.store in ("handover", "ledger", "history"):
        # lookup records: the result word carries the treatment state, the lookup value carries the identifier
        if res in ("ANONYMIZED", "REDACTED"):
            f.exposed.clear()
        elif res in ("IDENTIFIABLE", "FOUND"):
            f.exposed.add("lookup_value")
        if cat == "DATA_FLOW":
            f.enabled = {"ACTIVE": True, "DISABLED": False}.get(res)
        if cat == "BACKUP_ARCHIVE":
            f.restore_allowed = {"ACTIVE": True, "BLOCKED": False}.get(res)
    if o.kind.endswith("_pii_scan") or o.kind == "analytics_identity_scan":
        f.exposed.add("scan_hit")   # a scan hit proves the record exists and still carries the identifier
        f.present = True
    en = _flag(o.f("enabled"))
    if en is not None:
        f.enabled = en
    ra = _flag(o.f("restore_allowed"))
    if ra is not None:
        f.restore_allowed = ra
    if o.kind == "restore_candidate_evaluated":      # eligible and not blocked by a deletion marker -> restorable
        elig, blk = _flag(o.f("eligible")), _flag(o.f("deletion_block"))
        if blk is True:
            f.restore_allowed = False
        elif elig is True and blk is False:
            f.restore_allowed = True
    if o.kind == "restore_authorization_completed":  # decision=deny under a privacy policy -> blocked
        f.restore_allowed = {"deny": False, "allow": True}.get(o.f("decision"))
    if o.kind == "export_download_check_completed" and o.f("available") == "true":
        f.present = True
    f.retention_until = o.f("retention_until") or o.f("retained_until")
    return f
