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


@dataclass(frozen=True)
class Chain:
    kind: str            # direct | trace | source | catalog
    evidence_id: str
    locator: str
    field: str
    value: str
    time: str = ""       # observation time (or catalog event_time) the chain rests on


@dataclass
class Link:
    resource_id: str
    system_id: str | None
    chains: list = field(default_factory=list)

    def since(self):
        """Earliest time any chain evidences the resource. Absence older than this predates what we know of it."""
        ts = [c.time for c in self.chains if c.time]
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
        ln = res.links.setdefault(o.resource_id, Link(o.resource_id, o.system_id))
        if ln.system_id is None:
            ln.system_id = o.system_id
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
            add(o, Chain("direct", o.evidence_id, o.locator, _fields_for(o, kind, ident.value), ident.value, o.observed_at))
        for o in cv.for_trace_key(ident.value):
            if not ident.linkable_at(o.observed_at):
                res.rejected.append((o.resource_id, "identifier_not_yet_valid", f"trace key {ident.value}"))
                continue
            add(o, Chain("trace", o.evidence_id, o.locator, o.f("trace_lookup_field") or "lookup_key", ident.value, o.observed_at))
    for o in cv.for_identifier("user", subj.user_id):
        add(o, Chain("direct", o.evidence_id, o.locator, _fields_for(o, "user", subj.user_id), subj.user_id, o.observed_at))
    for o in cv.for_trace_key(subj.user_id):
        add(o, Chain("trace", o.evidence_id, o.locator, o.f("trace_lookup_field") or "lookup_key", subj.user_id, o.observed_at))

    # catalog links (activity rows): email AND user id must both match the subject
    emails = {i.value for i in subj.identifiers if i.field == "email" and i.verified}
    for c in cv.catalog_links():
        if c.user_ref == subj.user_id and c.email in emails:
            ln = res.links.setdefault(c.resource_id, Link(c.resource_id, c.system_id))
            ch = Chain("catalog", c.activity_id, c.activity_id, "details", c.user_ref, c.event_time)
            if ch not in ln.chains:
                ln.chains.append(ch)

    # structural: a linked record naming another resource as its source
    for rid in list(res.links):
        for o in cv.for_resource(rid):
            src = o.f("source_resource_id")
            if src and src not in res.links:
                ln = res.links.setdefault(src, Link(src, None))
                ln.chains.append(Chain("source", o.evidence_id, o.locator, "source_resource_id", rid, o.observed_at))
    for rid, ln in res.links.items():
        if ln.system_id is None:
            for o in cv.for_resource(rid):
                if o.system_id:
                    ln.system_id = o.system_id
                    break
    return res


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
