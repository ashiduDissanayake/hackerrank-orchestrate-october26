"""Resource state at the cutoff, per physical copy, with scope-aware absence.

Physical copies: 'primary' (every view of the live system: inventory, bundle, export, log, handover, ledger,
history, snapshot, pdf) and each named replica (*_replica*, replica_*). A copy's state is its LATEST admissible
evidence; ties go to presence (conservative).

Evidence kinds per copy:
  present   an observation of the resource with present=True (time = observed_at)
  absent    an explicit lookup/observation with present=False, or a snapshot whose scope covers the resource's
            system and that copy and does not list the resource (time = snapshot availability).
            A snapshot that lists the resource under a record time after the cutoff is NOT absence evidence.
Scope basis (declared vs inferred_from_*) is kept on the event so reports can tell strong from weak absence.
"""
from dataclasses import dataclass, field

from .copies import copy_of  # noqa: F401  (re-exported)
from .coverage_rules import absence_support
from .facts import read




@dataclass(frozen=True)
class Event:
    time: str
    copy: str
    kind: str                # present | absent
    evidence_id: str
    locator: str
    basis: str               # observation | explicit_lookup | declared | inferred_from_rows | inferred_from_table
    obs: object = None


@dataclass
class CopyStates:
    latest: dict = field(default_factory=dict)       # copy -> Event
    events: list = field(default_factory=list)

    def present_copies(self):
        return sorted(c for c, e in self.latest.items() if e.kind == "present")

    def newest(self, kind, copies=None):
        evs = [e for c, e in self.latest.items() if e.kind == kind and (copies is None or c in copies)]
        return max(evs, key=lambda e: (e.time, e.evidence_id)) if evs else None


def copy_states(cv, resource_id, system_id, since=None, subj=None, category=None):
    """since: earliest time the resource itself is evidenced for this subject. Absence evidence older than `since` is
    ignored: not seeing a record before we know it exists says nothing about its state at the cutoff.
    A scope-based absence is accepted only under the shared standard (coverage_rules.absence_support): the capture must
    evidence a collection/table of the record's `category`, come from a complete source, and have a strong scope (or be a
    weak document export promoted for `subj`). Explicit lookups (404, not-found) are unaffected."""
    cs = CopyStates()
    obs = cv.for_resource(resource_id)
    collections = {o.f("collection") for o in obs if o.f("collection")}
    for o in obs:
        pres = read(o).present   # facts refine the raw flag (scan hits, download checks)
        if pres is None:
            continue
        kind = "present" if pres else "absent"
        if kind == "absent" and since and o.observed_at < since:
            continue
        basis = "explicit_lookup" if (kind == "absent") else "observation"
        cs.events.append(Event(o.observed_at, copy_of(o.store), kind, o.evidence_id, o.locator, basis, o))
    for sc in cv.scopes(system_id):
        if sc.collection and collections and sc.collection not in collections:
            continue
        if sc.collection and not collections:
            continue
        if cv.artifact_mentions(resource_id, sc.evidence_id):
            continue
        if since and sc.available_at < since:
            continue
        supports, basis = absence_support(cv, subj, sc, category)
        if not supports:
            continue
        cs.events.append(Event(sc.available_at, copy_of(sc.store), "absent", sc.evidence_id, "scope", basis, None))
    for e in cs.events:
        cur = cs.latest.get(e.copy)
        if cur is None or (e.time, e.kind == "present", e.evidence_id) > (cur.time, cur.kind == "present", cur.evidence_id):
            cs.latest[e.copy] = e
    return cs


def latest_fact(cv, resource_id, attr):
    """Newest admissible observation whose facts carry a non-None `attr`; returns (value, obs) or (None, None)."""
    best = None
    for o in cv.for_resource(resource_id):
        v = getattr(read(o), attr)
        if v is not None and (best is None or (o.observed_at, o.evidence_id) > (best[1].observed_at, best[1].evidence_id)):
            best = (v, o)
    return best if best else (None, None)
