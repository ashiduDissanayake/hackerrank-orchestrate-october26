"""One standard for "this capture shows the record absent", used by BOTH reasoning paths: the subject-level account proof
(account_proof.py) and the state of an already linked resource (state.copy_states). A capture may be used as absence
evidence only if, for the record's category:
  collection/table  the artifact evidences capture of a collection/table that holds records of that category
                    (ScopeDecl.captured); a declared empty `notification_preferences` says nothing about profiles
  source            the export's own completeness checks passed (ScopeDecl.complete). COMMIT or a matching row count prove
                    the file is whole, NOT that it is unfiltered or authoritative for every subject: that is the scope claim
  scope             declared, or the table itself (strong); or a weak document export promoted for THIS subject (below)
  copy/time         handled by the callers (physical copy, latest event per copy, dual-time cutoff)
Weak document exports (scope inferred from the systems seen in rows) are promoted per source: the export holds profile rows
of the record's category (that collection is part of what it exports) AND the same copy holds records about the subject in
other collections (the subject's data was included in the extract, so a missing row is an omission by the datastore, not by
the extract). An export that never mentions the subject proves nothing about them.
"""
from .facts import COLLECTION_CATEGORY, category_rank
from .identity import KIND
from .normalize import phone_matches
from .copies import copy_of

STRONG = ("declared", "inferred_from_table")

# typed-inventory table names (sql_snapshots.TYPED_SYSTEM) -> the categories whose records they hold.
# support_records rows carry message_excerpt and requester fields (messages), never attachments: verified on all 33 rows of the dataset.
TABLE_CATEGORIES = {
    "customer_profiles": {"USER_PROFILE"}, "customer_search_documents": {"SEARCH_INDEX_ENTRY"},
    "customer_analytics_profiles": {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY", "MARKETING_PROFILE"},
    "support_records": {"SUPPORT_MESSAGE"}, "customer_exports": {"USER_EXPORT"},
    "connector_subscriptions": {"DATA_FLOW"}, "backup_restore_entries": {"BACKUP_ARCHIVE"},
    "security_audit_records": {"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"},
}


def categories_of(name):
    cats = set(TABLE_CATEGORIES.get(name, ()))
    if name in COLLECTION_CATEGORY:
        cats.add(COLLECTION_CATEGORY[name])
    return cats


def covers_category(sc, category):
    """True/False when the scope names what it captured; None when it does not (document-table exports)."""
    if not sc.captured:
        return None
    return any(category in categories_of(n) for n in sc.captured)


def row_matches(o, subj):
    """Same identifier semantics as linking: exact email/hash/user-id tokens, and phones by normalize.phone_matches
    (international, 00-prefixed or >= 9-digit national form, in a phone field or free text)."""
    for ident in subj.identifiers:
        if not ident.verified or not ident.linkable_at(o.observed_at):
            continue
        if ident.field == "phone":
            toks = (o.f("ids_phonetxt") or "").split("|") + (o.f("ids_phone") or "").split("|")
            if any(t and phone_matches(t, ident.value) for t in toks):
                return True
            continue
        if ident.value in (o.f(f"ids_{KIND[ident.field]}") or "").split("|"):
            return True
    return bool(subj.user_id and subj.user_id in (o.f("ids_user") or "").split("|"))


def _subject_copies(cv, subj):
    """(artifact, copy) pairs holding ANY record about the subject; memoized per case view."""
    key = ("subject_copies", subj.user_id)
    if key not in cv.memo:
        cv.memo[key] = {(o.evidence_id, copy_of(o.store)) for o in cv.all() if o.kind == "record" and row_matches(o, subj)}
    return cv.memo[key]


def _artifact_has_category(cv, evidence_id, category):
    key = ("artifact_categories", evidence_id)
    if key not in cv.memo:
        cv.memo[key] = {category_rank(o)[0] for o in cv.all() if o.evidence_id == evidence_id and o.kind == "record"}
    return category in cv.memo[key]


def promoted_weak(cv, subj, sc, category):
    return (subj is not None and sc.basis == "inferred_from_rows" and sc.complete and _artifact_has_category(cv, sc.evidence_id, category)
            and (sc.evidence_id, copy_of(sc.store)) in _subject_copies(cv, subj))


def absence_support(cv, subj, sc, category, allow_weak=False):
    """(supports, basis_label). Whether this scope may support absence of a record of `category` for `subj`."""
    if not sc.complete:
        return False, sc.basis
    cov = covers_category(sc, category)
    if cov is False:
        return False, sc.basis
    if sc.basis in STRONG:
        return (cov is True or allow_weak), sc.basis
    if promoted_weak(cv, subj, sc, category):
        return True, sc.basis + "+subject_in_source"
    return allow_weak, sc.basis
