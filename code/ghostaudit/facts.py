"""Observation -> data category and state facts.

Everything here reads one observation; reasoning across observations lives in state.py / obligations.py.
"""
import re
from dataclasses import dataclass, field

from .normalize import name_in_text, phone_matches, phone_tokens, text_fields

RECORD_TYPE_CATEGORY = {  # explicit record_type values found in handover / ledger / history records
    "USER_PROFILE": "USER_PROFILE", "SEARCH_INDEX_ENTRY": "SEARCH_INDEX_ENTRY", "ANALYTICS_PROFILE": "ANALYTICS_PROFILE",
    "SUPPORT_MESSAGE": "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT": "SUPPORT_ATTACHMENT", "USER_EXPORT": "USER_EXPORT",
    "DATA_FLOW": "DATA_FLOW", "BACKUP_ARCHIVE": "BACKUP_ARCHIVE", "SECURITY_AUDIT_LOG": "SECURITY_AUDIT_LOG",
    "LEGAL_HOLD_RECORD": "LEGAL_HOLD_RECORD", "ACCOUNT_TOMBSTONE": "ACCOUNT_TOMBSTONE",
    "SECONDARY_IDENTIFIER": "SECONDARY_IDENTIFIER", "MARKETING_PROFILE": "MARKETING_PROFILE", "CACHE_ENTRY": "CACHE_ENTRY",
    "EMAIL_DELIVERY_LOG": "EMAIL_DELIVERY_LOG", "PRODUCT_TELEMETRY": "PRODUCT_TELEMETRY",
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


COLLECTION_CATEGORY = {
    "deleted_customer_references": "ACCOUNT_TOMBSTONE", "retained_order_records": "LEGAL_HOLD_RECORD",
    "security_audit_events": "SECURITY_AUDIT_LOG", "ticket_attachments": "SUPPORT_ATTACHMENT",
    "support_conversations": "SUPPORT_MESSAGE", "customer_profiles": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY", "customer_analytics_reports": "ANALYTICS_PROFILE",
    "customer_export_jobs": "USER_EXPORT", "backup_catalog": "BACKUP_ARCHIVE", "connector_configurations": "DATA_FLOW",
}
# resource-id prefixes that identify ONE category unambiguously (account/search/analytics/support are ambiguous)
PREFIX_CATEGORY = {
    "tombstone": "ACCOUNT_TOMBSTONE", "legal_hold": "LEGAL_HOLD_RECORD", "audit_record": "SECURITY_AUDIT_LOG",
    "data_flow": "DATA_FLOW", "backup": "BACKUP_ARCHIVE", "export": "USER_EXPORT", "marketing": "MARKETING_PROFILE",
    "cache": "CACHE_ENTRY", "email_delivery": "EMAIL_DELIVERY_LOG",
}
# every category name that deletion_rules.csv or the data-flow obligation can use is also a valid explicit record_type
KNOWN_CATEGORIES = set(SYSTEM_CATEGORY.values()) | set(RECORD_TYPE_CATEGORY.values()) | {
    "ACCOUNT_TOMBSTONE", "SECONDARY_IDENTIFIER", "PRODUCT_TELEMETRY", "MARKETING_PROFILE", "CACHE_ENTRY", "EMAIL_DELIVERY_LOG"}
_PFX = re.compile(r"^([a-z_]+?)_[A-Za-z]?\d+[A-Za-z]*$")


def category_rank(o):
    """(category, rank). Precedence: explicit record_type (4) > collection (3) > unambiguous resource prefix (3)
    > event kind (2) > owning system default (1). The owning system never overrides explicit evidence: a tombstone
    reported by account_service is still a tombstone."""
    rt = o.f("record_type")
    if rt in KNOWN_CATEGORIES:
        return rt, 4
    coll = COLLECTION_CATEGORY.get(o.f("collection"))
    if coll:
        return coll, 3
    m = _PFX.match(o.resource_id or "")
    if m and m.group(1) in PREFIX_CATEGORY:
        return PREFIX_CATEGORY[m.group(1)], 3
    if (o.kind or "").startswith("contact_"):  # contact-index lookups: a secondary copy of contact identifiers (rule_02)
        return "SECONDARY_IDENTIFIER", 2
    cat = SYSTEM_CATEGORY.get(o.system_id)
    if o.system_id == "support_platform" and (o.store == "pdf" or (o.kind or "").startswith("attachment") or o.f("file_name")):
        return "SUPPORT_ATTACHMENT", 2
    if o.system_id == "analytics_platform" and o.f("email_opt_in") is not None:
        return "MARKETING_PROFILE", 2
    return cat, 1


def category_of(o):
    return category_rank(o)[0]


def _flag(v):
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    return None


def subject_text_exposure(o, subj):
    """Subject identifiers found inside ANY text field of the record: phone (any common written form, via
    normalize.phone_matches) and full name (whole phrase). Used only on records already linked to the subject."""
    found = set()
    if subj is None:
        return found
    phones = {i.value for i in subj.identifiers if i.field == "phone"}
    names = [n for n in subj.names if n]
    for k, v in text_fields(o.fields):
        if phones and any(phone_matches(d, p) for d in phone_tokens(v) for p in phones):
            found.add("text:phone")
        if any(name_in_text(n, v) for n in names):
            found.add("text:name")
    return found


def read(o, subj=None):
    cat = category_of(o)
    f = Facts(cat, o.present, result=o.f("result"))
    res = o.f("result")
    for k in DIRECT:
        if o.f(k):
            f.exposed.add(k)
    for kind in ("email", "hash", "phone"):  # identifiers embedded in free text (message_text, excerpts, scan hits)
        if o.f(f"ids_{kind}") and not f.exposed:
            f.exposed.add(f"embedded:{kind}")
    if cat in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY") and (o.f("user_ref") or o.f("ids_user")):
        f.exposed.add("user_ref")   # rule_07/08: still attributable to a user via ANY user-reference token
    f.exposed |= subject_text_exposure(o, subj)
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
