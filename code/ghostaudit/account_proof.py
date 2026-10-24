"""Subject-level proof that no account profile for the subject remains (or that one does).

Question answered: "does an authoritative account snapshot, queried by the SUBJECT's identifiers, contain a profile
for this subject, and can every copy that might hold one be accounted for?"  It does not need the original account
resource id, so it can hold when the id is unrecoverable.

What a snapshot may be taken to cover (all four must hold for it to SUPPORT absence)
  profile collection  the artifact evidences capture of a profile collection/table (ScopeDecl.captured), not merely of the
                      system: an empty declared `notification_preferences` collection under account_service says nothing
                      about profiles, and an inventory that declares account_service but lacks the profile table likewise
  strong scope        basis 'declared' or 'inferred_from_table'; 'inferred_from_rows' is weak and is ignored unless allow_weak
  complete source     the export's own completeness checks passed (ScopeDecl.complete: committed SQL, inventory completion
                      marker, declared record count equals the records held)
  after the request   the snapshot is available at/after requested_at and passes the dual-time cutoff
Rows: a row matches the subject if it carries any subject identifier that already belonged to the user at the row's time.
Only profile rows count (an explicit non-profile collection or record_type is not a profile). Every profile row of the copy
must carry an identifier, otherwise the copy is INDETERMINATE (an unattributable row could be the subject's); rows hidden by the
cutoff in the same artifact do the same. require_row (option, off) also demands a positive-control row.

Per-copy state. EVERY capture of every copy (strong or weak, before or after the request) contributes an event; the LATEST
event of a copy decides it (ties: present > indeterminate > absent). The proof is ABSENT only if:
  * the primary copy's latest event is a supporting post-request absence, and
  * no copy's latest event is a post-request presence, and
  * no copy is "unaccounted": its latest event is an indeterminate row, a pre-request presence (the replica held the subject and
    was not captured again), or a pre-request absence that lags a peer (another copy of the same capture, or an earlier
    admissible observation, shows the subject while this copy does not, so replication may still land).
A copy whose latest evidence shows attributable rows and no subject is EXCLUDED with that stated basis ("never evidenced to hold
the subject"). Copies observed only as other cases' captures contribute nothing about this subject and are listed as `uncovered`
for transparency, never asserted. The snapshot's own declaration of coverage remains the completeness claim for the profile
table; the snapshots hold 1-4 rows (case-focused extracts), so this is a stated assumption, validated on the public samples
against known account states and never used to name a resource.
"""
from dataclasses import dataclass, field

from .facts import COLLECTION_CATEGORY
from .identity import KIND
from .normalize import phone_matches
from .state import copy_of

STRONG = ("declared", "inferred_from_table")
RANK = {"present": 3, "indeterminate": 2, "absent": 1}
PROFILE = "USER_PROFILE"


@dataclass
class CopyEvent:
    copy: str
    status: str            # present | indeterminate | absent
    evidence_id: str
    time: str
    basis: str
    detail: str = ""
    supports: bool = False   # an absence that may discharge the obligation (profile collection, strong scope, complete source)
    pre: bool = False        # captured before the request


@dataclass
class AccountProof:
    status: str            # ABSENT | PRESENT | INDETERMINATE | NO_COVERAGE
    evidence_id: str = ""
    copies: dict = field(default_factory=dict)
    uncovered: list = field(default_factory=list)
    excluded: dict = field(default_factory=dict)
    reason: str = ""


def _row_matches(o, subj):
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


def _identifiable(o):
    return any(o.f(k) for k in ("ids_email", "ids_hash", "ids_user", "ids_phone", "ids_phonetxt", "user_ref", "email", "email_hash", "phone"))


def is_profile_row(o):
    """An explicit non-profile collection or record_type is not a profile; anything else under account_service is."""
    coll = o.f("collection")
    if coll:
        return COLLECTION_CATEGORY.get(coll) == PROFILE
    rt = o.f("record_type")
    return not rt or rt == PROFILE


def _profile_scope(sc):
    """The artifact evidences capture of a profile collection/table (not just of the system)."""
    return any(COLLECTION_CATEGORY.get(c) == PROFILE for c in sc.captured)


def _events(cv, subj, requested_at, allow_weak, require_row, weak_promotion):
    rows_by_art = {}
    for o in cv.for_system("account_service"):
        if o.kind == "record" and is_profile_row(o):
            rows_by_art.setdefault((o.evidence_id, copy_of(o.store)), []).append(o)
    art_has_rows = {e for (e, _c) in rows_by_art}
    subject_copies = None      # (artifact, copy) pairs that hold ANY record about the subject; computed only if a weak scope needs it
    events, seen, seen_copies = [], set(), set()
    for sc in cv.scopes("account_service"):
        copy = copy_of(sc.store)
        seen_copies.add(copy)
        key = (sc.evidence_id, copy, sc.collection)
        if key in seen:
            continue
        seen.add(key)
        if sc.collection and COLLECTION_CATEGORY.get(sc.collection) != PROFILE:
            continue        # a declared non-profile collection says nothing about profiles, for or against
        rows = [o for o in rows_by_art.get((sc.evidence_id, copy), []) if not sc.collection or o.f("collection") == sc.collection]
        hidden = cv.hidden_in_artifact(sc.evidence_id, "account_service")
        promoted = False
        if weak_promotion and sc.basis == "inferred_from_rows" and sc.complete and sc.evidence_id in art_has_rows:
            # Per-source promotion: a document-table export is only a weak claim about WHICH collections a table covers. It is
            # taken as covering the profile collection for THIS subject when (a) the export demonstrably includes profile
            # rows (the collection is part of what it exports) and (b) this same copy holds records about the subject in
            # other collections (the subject's data was included in the extract, so a missing profile row is an omission
            # by the datastore, not by the extract). An export that never mentions the subject proves nothing about them.
            if subject_copies is None:
                subject_copies = {(o.evidence_id, copy_of(o.store)) for o in cv.all() if o.kind == "record" and _row_matches(o, subj)}
            promoted = (sc.evidence_id, copy) in subject_copies
        strong = sc.basis in STRONG or allow_weak or promoted
        supports = (_profile_scope(sc) or allow_weak or promoted) and strong and sc.complete
        if any(_row_matches(o, subj) for o in rows):
            status, detail = "present", "a row carries a subject identifier"
        elif hidden:
            status, detail = "indeterminate", f"{hidden} row(s) of this artifact are hidden by the cutoff"
        elif supports and require_row and sc.evidence_id not in art_has_rows:
            status, detail = "indeterminate", "the artifact shows no account row in any copy, so nothing shows the account collection was captured"
        elif any(not _identifiable(o) for o in rows):
            status, detail = "indeterminate", "an account row carries no identifier, so it could be the subject's"
        else:
            status, detail = "absent", f"{len(rows)} account row(s), none carries a subject identifier"
        if status == "absent" and not supports:
            continue        # a capture that does not evidence the profile table never supports (or excludes) anything
        events.append(CopyEvent(copy, status, sc.evidence_id, sc.available_at, sc.basis + ("+subject_in_source" if promoted else ""), detail,
                                supports and status == "absent", sc.available_at < requested_at))
    return events, seen_copies


def _earliest_subject_sighting(cv, subj):
    """Earliest admissible observation of a profile for the subject in any copy (snapshot row, lookup, log read)."""
    times = [o.observed_at for o in cv.for_system("account_service") if o.present and is_profile_row(o) and _row_matches(o, subj)]
    return min(times) if times else None


def account_proof(cv, subj, requested_at, allow_weak=False, require_row=False, pre_request_exclusion=True, weak_promotion=True):
    events, seen_copies = _events(cv, subj, requested_at, allow_weak, require_row, weak_promotion)
    evaluated = {e.evidence_id for e in events} | {sc.evidence_id for sc in cv.scopes("account_service")}

    # Peer drift inside one capture: another copy of the same artifact shows the subject while this copy does not.
    by_art = {}
    for e in events:
        by_art.setdefault(e.evidence_id, []).append(e)
    for evs in by_art.values():
        if any(e.status == "present" for e in evs):
            for e in evs:
                if e.status == "absent":
                    e.status, e.supports = "indeterminate", False
                    e.detail = "another copy captured in the same artifact holds the subject while this copy does not (replication drift)"
    # Drift across artifacts: the subject was already seen in some copy when this copy was captured clean.
    first_seen = _earliest_subject_sighting(cv, subj)
    latest = {}
    for e in events:
        cur = latest.get(e.copy)
        if cur is None or (e.time, RANK[e.status]) > (cur.time, RANK[cur.status]):
            latest[e.copy] = e
    for e in latest.values():
        if e.status == "absent" and e.pre and first_seen and first_seen <= e.time:
            e.status, e.supports = "indeterminate", False
            e.detail = f"the subject was already evidenced ({first_seen}) when this copy was captured without it; replication state afterwards is unknown"

    # Direct evidence of a profile for the subject that is not a snapshot row (explicit lookups, log reads, screens): a
    # population-level snapshot cannot overrule subject-level evidence, because declared snapshots are case-focused
    # extracts (a public sample has a lookup returning the profile and a later declared-empty snapshot).
    # Only evidence at/after the request counts (the account was expected to exist before it), and rows of artifacts already
    # evaluated as snapshots (including superseded ones) are handled by the per-copy latest-event logic, not here.
    direct = [o for o in cv.for_system("account_service")
              if o.present and is_profile_row(o) and o.observed_at >= requested_at and o.evidence_id not in evaluated and _row_matches(o, subj)]
    uncovered = sorted(seen_copies - set(latest))
    excluded = {c: (f"latest capture {e.evidence_id} ({e.time}) shows attributable rows and none for the subject; the subject was never evidenced in this copy")
                for c, e in latest.items() if e.pre and e.status == "absent" and e.supports}
    if direct:
        return AccountProof("PRESENT", copies=latest, uncovered=uncovered, excluded=excluded,
                            reason=f"profile for the subject evidenced directly ({direct[0].evidence_id} {direct[0].locator}); resource-level state applies")
    if not latest:
        return AccountProof("NO_COVERAGE", reason="no admissible profile-table capture of any copy exists at the audit cutoff", uncovered=uncovered)
    if any(e.status == "present" and not e.pre for e in latest.values()):
        return AccountProof("PRESENT", copies=latest, uncovered=uncovered, excluded=excluded, reason="a snapshot row carries a subject identifier")
    unaccounted = {c: e for c, e in latest.items() if e.status == "indeterminate" or (e.status == "present" and e.pre)}
    if not pre_request_exclusion:      # option (off): a copy captured only BEFORE the request is never excluded, whatever it showed
        for c, e in latest.items():
            if c not in unaccounted and e.pre and e.status == "absent" and c != "primary":
                e.detail = f"captured only before the request ({e.evidence_id}); its state afterwards is not evidenced"
                unaccounted[c] = e
        excluded = {}
    if unaccounted:
        why = "; ".join(f"{c}: {e.detail if e.status in ('indeterminate', 'absent') else f'held the subject at {e.time} ({e.evidence_id}) and was not captured again after the request'}"
                        for c, e in sorted(unaccounted.items()))
        return AccountProof("INDETERMINATE", copies=latest, uncovered=uncovered, excluded=excluded, reason=why)
    prim = latest.get("primary")
    if prim is None or prim.status != "absent" or prim.pre or not prim.supports:
        why = ("the primary copy has no profile-table capture at all" if prim is None else
               f"the primary copy's latest supporting profile-table capture ({prim.evidence_id}, {prim.time}) predates the request" if prim.pre and prim.supports else
               "the primary copy has no supporting post-request profile-table capture")
        return AccountProof("NO_COVERAGE", copies=latest, uncovered=uncovered, excluded=excluded, reason=why)
    asserted = sorted(c for c, e in latest.items() if not e.pre)
    return AccountProof("ABSENT", evidence_id=prim.evidence_id, copies=latest, uncovered=uncovered, excluded=excluded,
                        reason=f"no profile for the subject in {', '.join(asserted)} (latest capture per copy)")
