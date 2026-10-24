"""Subject -> resource links, accepted only with an explicit evidence chain.

Chains (all evidence read through CaseView, so every item is admissible under the dual-time cutoff):
  direct    an observation of the resource contains an exact identifier token of the subject (email, hash, phone,
            or the stable user id); identifiers must be verified and already belong to the user at the
            observation's time (Identifier.linkable_at)
  trace     a lookup whose key (same trace) equals a subject identifier returned this resource
  source    a linked record names another resource as its source (search document -> account)
  catalog   a data-catalog row dated <= audit_at ties the resource to the subject's email and user id
A resource linked by any chain stays linked for all of its admissible observations (anonymized or absent later).

Activity-window matches are NOT links. window_candidates() lists them for diagnostics only (user decision U12).
"""
import json
from dataclasses import dataclass, field

from .identity import KIND
from .observations import system_from_resource


@dataclass(frozen=True)
class Chain:
    kind: str            # direct | trace | source | catalog
    evidence_id: str
    locator: str
    field: str
    value: str
    time: str = ""       # observation time (or catalog event_time) the chain rests on
    available: str = ""  # when the evidence artifact itself became available (capture time); the chain is evidenced no earlier than this


# Fields that carry the QUESTION asked of a system (a lookup key), not an attribute of the record that came back.
# A match on one of these is a lookup chain, and the returned record can contradict it.
KEY_FIELDS = {"lookup_key", "match_key", "query", "subject_key", "scan_key", "owner_key", "trace_lookup_key", "correlation_key"}


@dataclass
class Link:
    resource_id: str
    system_id: str | None
    chains: list = field(default_factory=list)
    conflict: str | None = None     # set when the record's own identity contradicts a catalog link
    system_basis: str | None = None  # how system_id was resolved: observation | catalog | namespace_prefix (None = unresolved)

    def attribute_direct(self):
        """True if some chain rests on an attribute of the record itself (not a lookup key, catalog row or source ref)."""
        return any(c.kind == "direct" for c in self.chains)

    def since(self):
        """Earliest time any chain evidences the resource ITSELF. Absence older than this predates what we know of it.
        A source reference only tells us an id: a record naming account_X proves neither that X existed nor when it was
        created (a stale index document can name an account that was deleted long before), so it never sets the bound."""
        ts = [c.time for c in self.chains if c.time and c.kind != "source"]
        return min(ts) if ts else None


@dataclass
class LinkResult:
    links: dict = field(default_factory=dict)       # resource_id -> Link
    rejected: list = field(default_factory=list)    # (resource_id, reason, detail)
    candidates: list = field(default_factory=list)  # window candidates (diagnostics only)


def _fields_for(o, kind, value):
    src = o.f("ids_src")
    if not src:
        return ""
    try:
        return ",".join(json.loads(src).get(f"{kind}:{value}", []))
    except json.JSONDecodeError:
        return ""


def link_subject(cv, subj):
    res = LinkResult()
    if subj.user_id is None:
        return res

    def add(o, chain):
        if not o.resource_id:
            return
        ln = res.links.setdefault(o.resource_id, Link(o.resource_id, o.system_id, system_basis="observation" if o.system_id else None))
        if ln.system_id is None and o.system_id:
            ln.system_id, ln.system_basis = o.system_id, "observation"
        if chain not in ln.chains:
            ln.chains.append(chain)

    for ident in subj.identifiers:
        if not ident.verified:
            continue
        kind = KIND[ident.field]
        for o in cv.for_identifier(kind, ident.value):
            if not ident.linkable_at(o.observed_at):
                res.rejected.append((o.resource_id, "identifier_not_yet_valid", f"{kind}:{ident.value} valid_from {ident.valid_from} > {o.observed_at}"))
                continue
            flds = _fields_for(o, kind, ident.value)
            ck = "trace" if flds and set(flds.split(",")) <= KEY_FIELDS else "direct"
            add(o, Chain(ck, o.evidence_id, o.locator, flds, ident.value, o.observed_at, o.available_at))
        if ident.field == "phone":
            # phones written in free text (any common format); same rule as exposure checks and indexing
            for o, tok in cv.for_phone(ident.value):
                if not ident.linkable_at(o.observed_at):
                    res.rejected.append((o.resource_id, "identifier_not_yet_valid", f"phone {ident.value} valid_from {ident.valid_from} > {o.observed_at}"))
                    continue
                add(o, Chain("direct", o.evidence_id, o.locator, _fields_for(o, "phonetxt", tok), ident.value, o.observed_at, o.available_at))
        for o in cv.for_trace_key(ident.value):
            if not ident.linkable_at(o.observed_at):
                res.rejected.append((o.resource_id, "identifier_not_yet_valid", f"trace key {ident.value}"))
                continue
            add(o, Chain("trace", o.evidence_id, o.locator, o.f("trace_lookup_field") or "lookup_key", ident.value, o.observed_at, o.available_at))
    for o in cv.for_identifier("user", subj.user_id):
        flds = _fields_for(o, "user", subj.user_id)
        ck = "trace" if flds and set(flds.split(",")) <= KEY_FIELDS else "direct"
        add(o, Chain(ck, o.evidence_id, o.locator, flds, subj.user_id, o.observed_at, o.available_at))
    for o in cv.for_trace_key(subj.user_id):
        add(o, Chain("trace", o.evidence_id, o.locator, o.f("trace_lookup_field") or "lookup_key", subj.user_id, o.observed_at, o.available_at))

    # catalog links (activity rows): email AND user id must both match the subject
    emails = {i.value for i in subj.identifiers if i.field == "email" and i.verified}
    for c in cv.catalog_links():
        if c.user_ref == subj.user_id and c.email in emails:
            ln = res.links.setdefault(c.resource_id, Link(c.resource_id, c.system_id, system_basis="catalog" if c.system_id else None))
            ch = Chain("catalog", c.activity_id, c.activity_id, "details", c.user_ref, c.event_time, c.event_time)
            if ch not in ln.chains:
                ln.chains.append(ch)

    # structural: a linked record names another resource as its source. Followed to a fixed point (a visited set stops
    # cycles); every link keeps the chain that produced it, so provenance is the path of source references.
    _follow_sources(cv, res)
    for rid, ln in res.links.items():
        _resolve_system(cv, ln)
    _reconcile(cv, subj, res)
    _prune_orphans(res)
    return res


def _follow_sources(cv, res):
    queue, seen = list(res.links), set()
    while queue:
        rid = queue.pop(0)
        if rid in seen:
            continue
        seen.add(rid)
        for o in cv.for_resource(rid):
            src = o.f("source_resource_id")
            if not src or src == rid:
                continue
            new = src not in res.links
            ln = res.links.setdefault(src, Link(src, None))
            ch = Chain("source", o.evidence_id, o.locator, "source_resource_id", rid, o.observed_at, o.available_at)
            if ch not in ln.chains:
                ln.chains.append(ch)
            if new:
                queue.append(src)


def _resolve_system(cv, ln):
    """System of a linked resource: its own observations first, then the existing justified id namespace
    (system_from_resource: account_* is account_service, ...). A link keeps which basis was used."""
    if ln.system_id is None:
        for o in cv.for_resource(ln.resource_id):
            if o.system_id:
                ln.system_id, ln.system_basis = o.system_id, "observation"
                break
    if ln.system_id is None:
        sysid = system_from_resource(ln.resource_id)
        if sysid:
            ln.system_id, ln.system_basis = sysid, "namespace_prefix"


def _prune_orphans(res):
    """A link that rests only on source references from resources that are no longer linked (rejected by reconciliation)
    is dropped too, with the reason recorded."""
    changed = True
    while changed:
        changed = False
        for rid, ln in list(res.links.items()):
            ln.chains = [c for c in ln.chains if c.kind != "source" or c.value in res.links]
            if not ln.chains:
                del res.links[rid]
                res.rejected.append((rid, "source_resource_not_linked", "every source reference to it came from a rejected link"))
                changed = True



def foreign_identifiers(cv, subj, rid):
    """Direct identifiers (email / phone / hash FIELDS of the record itself) that none of the subject's identifiers
    explains. Empty when the record shows no identifier at all (404 lookups, anonymized records) or only the subject's."""
    mine = {(i.field, i.value) for i in subj.identifiers}
    mine |= {(i.field, i.value) for i in subj.excluded_future}
    foreign = set()
    for o in cv.for_resource(rid):
        if not o.present:
            continue
        for fld, key in (("email", "email"), ("phone", "phone"), ("email_hash", "email_hash")):
            v = o.f(key)
            if v and (fld, v) not in mine:
                foreign.add((fld, v))
    return foreign


def _reconcile(cv, subj, res):
    """A link must not be contradicted by the record it points at.
      * lookup-key / source links (no attribute of the record matched): if the returned record shows a different
        identity, it is another person's record (e.g. a near-miss search hit) -> the link is REJECTED;
      * catalog links: the catalog is an explicit statement, so a contradicting record is a CONFLICT between two
        sources -> the link is kept but flagged, and the obligation becomes UNKNOWN (never a violation).
    A record that shows no identifier at all contradicts nothing."""
    for rid, ln in list(res.links.items()):
        if ln.attribute_direct():
            continue
        foreign = foreign_identifiers(cv, subj, rid)
        if not foreign:
            continue
        detail = "record shows " + ", ".join(sorted(f"{f}={v}" for f, v in foreign))
        if any(c.kind == "catalog" for c in ln.chains):
            ln.conflict = detail + " but the data catalog ties the resource to the subject"
        else:
            del res.links[rid]
            res.rejected.append((rid, "record_identity_contradicts_lookup_key", detail))


def window_candidates(cv, request, linked, before_minutes=90, after_minutes=10):
    """Deletion-worker activity in [reported_at - before, reported_at + after] on resources not already linked.
    Window measured in M2b (code/docs/DECISIONS.md). DIAGNOSTIC ONLY: the window is shared by concurrent requests
    (a unique candidate exists for only 37 of 550 requests), so it never evidences ownership."""
    import datetime as dt
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    rep = dt.datetime.strptime(request.reported_at, fmt)
    start = (rep - dt.timedelta(minutes=before_minutes)).strftime(fmt)
    end = (rep + dt.timedelta(minutes=after_minutes)).strftime(fmt)
    out = []
    for a in cv.activity(start=start, end=end):
        if a.source_system == "deletion_worker" and a.event_type in ("DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "BLOCK_RESTORE", "DISABLE_DATA_FLOW") and a.resource_id not in linked:
            out.append((a.activity_id, a.resource_id, a.target_system, a.event_type, a.reported_result, a.event_time))
    return out
