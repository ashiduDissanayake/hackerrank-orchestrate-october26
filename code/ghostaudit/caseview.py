"""CaseView: the ONLY way case logic reads evidence.

An observation is admissible for a case iff BOTH its artifact availability time and its observation time are
<= audit_at (inclusive). Activity rows and catalog links use event_time. Scope declarations use availability.
Nothing downstream (linking, state, policy, citations, investigator tools, excerpts, cached facts) may touch the
Store directly; `excluded_*` methods exist only so diagnostics can show what the cutoff removed.
"""


class CaseView:
    def __init__(self, store, audit_at):
        self._s = store
        self.audit_at = audit_at

    # --- admissibility -----------------------------------------------------------------------------------
    def _ok(self, o):
        return o.available_at <= self.audit_at and o.observed_at <= self.audit_at

    def admissible_evidence(self, evidence_id):
        """True for file_ids available by the cutoff and for activity_ids whose event_time is within it."""
        art = self._s.artifacts.get(evidence_id)
        if art is not None:
            return art.available_at <= self.audit_at
        return any(a.activity_id == evidence_id and a.event_time <= self.audit_at for a in self._s.activity)

    # --- observations ------------------------------------------------------------------------------------
    def _filter(self, obs, system, store_name, kind):
        for o in obs:
            if system and o.system_id != system:
                continue
            if store_name and o.store != store_name:
                continue
            if kind and o.kind != kind:
                continue
            yield o

    def for_resource(self, resource_id, system=None, store_name=None, kind=None):
        return [o for o in self._filter(self._s._by_resource.get(resource_id, ()), system, store_name, kind) if self._ok(o)]

    def for_identifier(self, kind, value, system=None):
        """Observations whose fields contain the exact identifier token (kind: email|hash|user|phone)."""
        return [o for o in self._filter(self._s._by_ident.get((kind, value), ()), system, None, None) if self._ok(o)]

    def for_trace_key(self, value):
        """Observations reached through a lookup whose key (from the same trace) equals `value`."""
        return [o for o in self._s._by_ident.get(("trace", value.strip().lower()), ()) if self._ok(o)]

    def artifact_mentions(self, resource_id, evidence_id):
        """True if the artifact contains ANY observation of the resource, admissible or not.
        Returns only a bool, so absence reasoning can refuse to claim 'not in this snapshot' when the snapshot
        does list the resource under a record time after the cutoff."""
        return any(o.evidence_id == evidence_id for o in self._s._by_resource.get(resource_id, ()))

    def all(self):
        return [o for o in self._s._obs if self._ok(o)]

    def scopes(self, system_id=None):
        return [sc for sc in self._s._scopes if sc.available_at <= self.audit_at and (system_id is None or sc.system_id == system_id)]

    # --- claims tables -----------------------------------------------------------------------------------
    def activity(self, resource_id=None, event_type=None, start=None, end=None):
        out = []
        for a in self._s.activity:
            if a.event_time > self.audit_at:
                continue
            if resource_id and a.resource_id != resource_id:
                continue
            if event_type and a.event_type != event_type:
                continue
            if start and a.event_time < start:
                continue
            if end and a.event_time > end:
                continue
            out.append(a)
        return out

    def catalog_links(self):
        return [c for c in self._s.catalog_links if c.event_time <= self.audit_at]

    # --- diagnostics only --------------------------------------------------------------------------------
    def excluded_for_identifier(self, kind, value):
        return [o for o in self._s._by_ident.get((kind, value), ()) if not self._ok(o)]

    def excluded_for_resource(self, resource_id):
        return [o for o in self._s._by_resource.get(resource_id, ()) if not self._ok(o)]
