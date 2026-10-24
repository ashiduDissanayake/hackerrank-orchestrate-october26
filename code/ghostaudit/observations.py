"""Timestamped evidence model.

Every fact extracted from evidence is an Observation with TWO times:
  available_at  when the artifact existed (manifest captured_at, or the later of manifest/header time)
  observed_at   when the fact was observed (record-level time if the artifact has one, else available_at)
Case logic must only see observations through CaseView, which requires BOTH to be <= audit_at.

ScopeDecl records which (system, store) an artifact claims to cover, so absence can be told apart from
"not captured". scope_basis says how the scope is known: declared | inferred_from_table | inferred_from_rows.
"""
import re
from dataclasses import dataclass, field

# Resource-ID prefix -> owning system. Fallback only: evidence-provided system/origin wins.
PREFIX_SYSTEM = {
    "account": "account_service",
    "analytics": "analytics_platform",
    "audit_record": "security_service",
    "backup": "backup_service",
    "cache": "cache_service",
    "data_flow": "integration_service",
    "email_delivery": "email_delivery_service",
    "export": "export_service",
    "legal_hold": "legal_service",
    "marketing": "marketing_platform",
    "object": "object_storage",
    "search": "search_service",
    "support": "support_platform",
    "tombstone": "identity_service",
}
_PREFIX_RE = re.compile(r"^([a-z_]+?)_[A-Za-z]?\d+[A-Za-z]*$")


def system_from_resource(resource_id):
    if not resource_id:
        return None
    m = _PREFIX_RE.match(resource_id)
    return PREFIX_SYSTEM.get(m.group(1)) if m else None


@dataclass(frozen=True)
class Observation:
    evidence_id: str          # file_id (activity_id/audit_id are used by the activity and identity stores)
    locator: str              # where inside the artifact (line number, table:key, json path)
    available_at: str
    observed_at: str
    system_id: str | None
    resource_id: str | None
    store: str                # physical copy: primary, failover_replica, replica_ap_south, snapshot, log, export, ...
    kind: str                 # record | lookup | event-name | document | ...
    present: bool | None      # True/False when the observation establishes existence; None when not stateful
    fields: tuple = ()        # sorted (key, value) pairs; values are str or None

    def f(self, key, default=None):
        for k, v in self.fields:
            if k == key:
                return v
        return default

    def fdict(self):
        return dict(self.fields)


def make_obs(evidence_id, locator, available_at, observed_at, system_id, resource_id, store, kind, present, fields):
    clean = tuple(sorted((k, v if v is None else str(v)) for k, v in fields.items()))
    if system_id is None:
        system_id = system_from_resource(resource_id)
    return Observation(evidence_id, locator, available_at, observed_at or available_at, system_id, resource_id,
                       store, kind, present, clean)


@dataclass(frozen=True)
class ScopeDecl:
    evidence_id: str
    available_at: str
    system_id: str
    store: str
    basis: str                # declared | inferred_from_table | inferred_from_rows
    collection: str | None = None
    captured: tuple = ()      # collections/tables whose capture this artifact evidences (a profile proof needs a profile collection)
    complete: bool = True     # source-completeness checks passed (SQL transaction committed, inventory completion marker, counts)


@dataclass
class ArtifactReport:
    """Per-file extraction accounting used for the coverage report."""
    evidence_id: str
    path: str
    fmt: str
    available_at: str
    observations: int = 0
    resources: int = 0
    scopes: int = 0
    unparsed: int = 0
    skipped: int = 0
    status: str = "ok"        # ok | pending (needs VLM) | failed
    notes: list = field(default_factory=list)
    failures: list = field(default_factory=list)


class Store:
    """Unfiltered evidence. Not for use by case logic: go through CaseView."""

    def __init__(self):
        self._obs = []
        self._scopes = []
        self.artifacts = {}
        self.activity = []
        self.catalog_links = []

    def add_obs(self, o):
        self._obs.append(o)

    def add_scope(self, s):
        self._scopes.append(s)

    def finalize(self):
        self._obs.sort(key=lambda o: (o.evidence_id, o.locator))
        self._by_resource, self._by_ident, self._by_system = {}, {}, {}
        for o in self._obs:
            if o.resource_id:
                self._by_resource.setdefault(o.resource_id, []).append(o)
            if o.system_id:
                self._by_system.setdefault(o.system_id, []).append(o)
            tk = o.f("trace_lookup_key")
            if tk:
                self._by_ident.setdefault(("trace", tk.strip().lower()), []).append(o)
            for tok in (o.f("ids_phonetxt") or "").split("|"):
                if tok:
                    self._by_ident.setdefault(("phonekey", tok.lstrip("0")[-9:]), []).append(o)
            for kind in ("email", "hash", "user", "phone"):
                for v in (o.f(f"ids_{kind}") or "").split("|"):
                    if v:
                        self._by_ident.setdefault((kind, v), []).append(o)
        self._scopes.sort(key=lambda s: (s.evidence_id, s.system_id, s.store, s.collection or ""))
        for rep in self.artifacts.values():
            mine = [o for o in self._obs if o.evidence_id == rep.evidence_id]
            rep.observations = len(mine)
            rep.resources = len({o.resource_id for o in mine if o.resource_id})
            rep.scopes = sum(1 for s in self._scopes if s.evidence_id == rep.evidence_id)
        return self
