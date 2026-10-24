"""Subject-level proof that no account profile for the subject remains (or that one does).

Question answered: "does an authoritative account snapshot, queried by the SUBJECT's identifiers, contain a profile
for this subject?"  It does not need the original account resource id, so it can hold when the id is unrecoverable.

A snapshot event (artifact, physical copy) is evaluated at the cutoff under explicit gates:
  scope        an admissible ScopeDecl for account_service on that copy. basis 'declared' or 'inferred_from_table' is
               strong; 'inferred_from_rows' is weak and ignored unless allow_weak (measured separately)
  timing       the snapshot is available at/after requested_at (state AFTER the request) and passes the dual-time cutoff
  query        a row matches the subject if it carries any subject identifier (user id, email, hash, phone) that already
               belonged to the user at the row's time (identity.Identifier.linkable_at)
  attribution  every account row of that copy in the artifact carries at least one identifier; an unidentifiable row
               could be the subject's, so the copy is INDETERMINATE
  hidden rows  rows the cutoff hides in the same artifact make the copy INDETERMINATE
  require_row  (option, off) also demand that the artifact shows >= 1 account row in some copy, i.e. a positive control
               that the account collection was captured; declared-empty tables then give no proof
Per copy the LATEST event wins (ties: present > indeterminate > absent). The proof is ABSENT only if the primary copy's
latest event is a strong absence and no copy's latest event is present or indeterminate. Copies with no post-request
coverage are listed but not asserted. The snapshot's own declaration of coverage is the completeness claim; the
snapshots hold 1-4 rows (case-focused extracts), so this remains a stated assumption, validated on the public samples
against known account states (see DECISIONS.md) and never used to name a resource.
"""
from dataclasses import dataclass, field

from .identity import KIND
from .normalize import phone_matches
from .state import copy_of

STRONG = ("declared", "inferred_from_table")
RANK = {"present": 3, "indeterminate": 2, "absent": 1}


@dataclass
class CopyEvent:
    copy: str
    status: str            # present | indeterminate | absent
    evidence_id: str
    time: str
    basis: str
    detail: str = ""


@dataclass
class AccountProof:
    status: str            # ABSENT | PRESENT | INDETERMINATE | NO_COVERAGE
    evidence_id: str = ""
    copies: dict = field(default_factory=dict)
    uncovered: list = field(default_factory=list)
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


def account_proof(cv, subj, requested_at, allow_weak=False, require_row=False):
    events = {}
    covered_pre = set()
    rows_by_art = {}
    for o in cv.for_system("account_service"):
        if o.kind == "record":
            rows_by_art.setdefault((o.evidence_id, copy_of(o.store)), []).append(o)
    seen = set()
    evaluated = set()          # every artifact that produced a snapshot event (latest or superseded)
    for sc in cv.scopes("account_service"):
        copy = copy_of(sc.store)
        key = (sc.evidence_id, copy, sc.collection)
        if key in seen:
            continue
        seen.add(key)
        if sc.available_at < requested_at:
            covered_pre.add(copy)
            continue
        evaluated.add(sc.evidence_id)
        rows = [o for o in rows_by_art.get((sc.evidence_id, copy), []) if not sc.collection or o.f("collection") == sc.collection]
        hidden = cv.hidden_in_artifact(sc.evidence_id, "account_service")
        if any(_row_matches(o, subj) for o in rows):
            status, detail = "present", "a row carries a subject identifier"
        elif hidden:
            status, detail = "indeterminate", f"{hidden} row(s) of this artifact are hidden by the cutoff"
        elif require_row and not any(o.evidence_id == sc.evidence_id for o in cv.for_system("account_service") if o.kind == "record"):
            status, detail = "indeterminate", "the artifact shows no account row in any copy, so nothing shows the account collection was captured"
        elif any(not _identifiable(o) for o in rows):
            status, detail = "indeterminate", "an account row carries no identifier, so it could be the subject's"
        else:
            status, detail = "absent", f"{len(rows)} account row(s), none carries a subject identifier"
        if status != "present" and sc.basis not in STRONG and not allow_weak:
            continue   # weak scope may never SUPPORT absence, but it must never hide presence
        ev = CopyEvent(copy, status, sc.evidence_id, sc.available_at, sc.basis, detail)
        cur = events.get(copy)
        if cur is None or (ev.time, RANK[ev.status]) > (cur.time, RANK[cur.status]):
            events[copy] = ev
    uncovered = sorted(covered_pre - set(events))
    # Direct evidence of a profile for the subject that is not a snapshot row (explicit lookups, log reads, screens): a
    # population-level snapshot cannot overrule subject-level evidence, because declared snapshots are case-focused
    # extracts (a public sample has a lookup returning the profile and a later declared-empty snapshot).
    # Only evidence at/after the request counts (the account was expected to exist before it), and rows of artifacts already
    # evaluated as snapshots (including superseded ones) are handled by the per-copy latest-event logic, not here.
    direct = [o for o in cv.for_system("account_service")
              if o.present and o.observed_at >= requested_at and o.evidence_id not in evaluated and _row_matches(o, subj)]
    if direct:
        return AccountProof("PRESENT", copies=events, uncovered=uncovered,
                            reason=f"profile for the subject evidenced directly ({direct[0].evidence_id} {direct[0].locator}); resource-level state applies")
    if not events:
        return AccountProof("NO_COVERAGE", reason="no admissible account snapshot at or after requested_at", uncovered=uncovered)
    if any(e.status == "present" for e in events.values()):
        return AccountProof("PRESENT", copies=events, uncovered=uncovered, reason="a snapshot row carries a subject identifier")
    if any(e.status == "indeterminate" for e in events.values()):
        return AccountProof("INDETERMINATE", copies=events, uncovered=uncovered, reason="; ".join(f"{c}: {e.detail}" for c, e in events.items() if e.status == "indeterminate"))
    prim = events.get("primary")
    if prim is None or prim.status != "absent":
        return AccountProof("NO_COVERAGE", copies=events, uncovered=uncovered, reason="the primary copy has no post-request snapshot")
    return AccountProof("ABSENT", evidence_id=prim.evidence_id, copies=events, uncovered=uncovered,
                        reason=f"no profile for the subject in {', '.join(sorted(events))} (latest snapshot per copy)")
