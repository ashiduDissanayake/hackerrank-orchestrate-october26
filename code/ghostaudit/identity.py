"""Identity resolution as of a case's audit_at, with provenance.

What the contract supplies: user_identities.csv (current snapshot + updated_at) and user_audit_log.csv (dated
changes to email / email_hash / phone). Neither file has a capture time, so each identifier is dated by the
facts themselves:
  * a value that an audit change introduced is valid from that change's event_time;
  * the value before a user's first logged change has unknown start (valid_from=None: "since before the log");
  * a snapshot value with no logged change is in force unless the snapshot itself is dated after the cutoff AND no
    audit record accounts for that update, in which case it is kept but marked verified=False (it cannot create
    an accepted link).
Later audit events are used ONLY to exclude values introduced after audit_at (excluded_future); they are never
used to attach a later identifier to an earlier case. Identifier matching against an observation additionally
requires valid_from <= observation time, so a value cannot link evidence recorded before it belonged to the user.
Old values stay linkable after they are replaced (historical copies persist in downstream systems).
"""
from dataclasses import dataclass, field

from .extract.common import norm_email, norm_hash, norm_phone

FIELDS = ("email", "email_hash", "phone")
NORM = {"email": norm_email, "email_hash": norm_hash, "phone": norm_phone}
KIND = {"email": "email", "email_hash": "hash", "phone": "phone"}  # field -> ids_* kind


@dataclass(frozen=True)
class Identifier:
    field: str
    value: str
    valid_from: str | None
    valid_to: str | None
    source: str               # 'snapshot' or an audit_id
    verified: bool = True

    def linkable_at(self, t):
        return self.valid_from is None or self.valid_from <= t


@dataclass
class Subject:
    user_id: str | None
    request_email: str
    identifiers: list = field(default_factory=list)
    excluded_future: list = field(default_factory=list)
    names: list = field(default_factory=list)
    conditions: list = field(default_factory=list)
    audit_at: str = ""

    def by_kind(self, kind):
        return {i.value: i for i in self.identifiers if KIND[i.field] == kind}


class IdentityIndex:
    def __init__(self, identities, audit_log):
        self.users = {u.user_id: u for u in identities}
        self.changes = {}
        for c in sorted(audit_log, key=lambda c: (c.event_time, c.audit_id)):
            self.changes.setdefault(c.user_id, []).append(c)
        self.email_users = {}
        for u in identities:
            self.email_users.setdefault(norm_email(u.email), set()).add(u.user_id)
        for c in audit_log:
            if c.field_name == "email":
                for v in (c.old_value, c.new_value):
                    self.email_users.setdefault(norm_email(v), set()).add(c.user_id)

    def _timeline(self, user_id, fld):
        u = self.users[user_id]
        ch = [c for c in self.changes.get(user_id, []) if c.field_name == fld]
        norm = NORM[fld]
        out = []
        if not ch:
            out.append([norm(getattr(u, fld)), None, None, "snapshot"])
            return out, None
        out.append([norm(ch[0].old_value), None, ch[0].event_time, ch[0].audit_id])
        for i, c in enumerate(ch):
            nxt = ch[i + 1].event_time if i + 1 < len(ch) else None
            out.append([norm(c.new_value), c.event_time, nxt, c.audit_id])
        problem = None
        if out[-1][0] != norm(getattr(u, fld)):
            problem = f"audit chain for {fld} ends at a value different from the current snapshot"
        return out, problem

    def resolve(self, request_email, audit_at):
        e = norm_email(request_email)
        users = sorted(self.email_users.get(e, ()))
        subj = Subject(None, e or "", audit_at=audit_at)
        if not users:
            subj.conditions.append("request_email_unknown")
            return subj
        if len(users) > 1:
            subj.conditions.append(f"request_email_ambiguous:{','.join(users)}")
            return subj
        uid = subj.user_id = users[0]
        u = self.users[uid]
        subj.names.append(u.name)
        # A snapshot dated after the cutoff is only a problem when no audit record accounts for that update
        # (an audit change at/after updated_at explains it: the snapshot was bumped by that very change).
        explained = any(c.event_time >= u.updated_at for c in self.changes.get(uid, []))
        for fld in FIELDS:
            tl, problem = self._timeline(uid, fld)
            if problem:
                subj.conditions.append(problem)
            for value, vfrom, vto, src in tl:
                if value is None:
                    continue
                if vfrom is not None and vfrom > audit_at:
                    subj.excluded_future.append(Identifier(fld, value, vfrom, vto, src, True))
                    continue
                verified = True
                if src == "snapshot" and u.updated_at > audit_at and not explained:
                    verified = False
                    subj.conditions.append(f"snapshot_value_unverifiable:{fld} (snapshot updated_at {u.updated_at} is after audit_at, no audit record)")
                subj.identifiers.append(Identifier(fld, value, vfrom, vto, src, verified))
        req = [i for i in subj.identifiers if i.field == "email" and i.value == e]
        if not req:
            subj.conditions.append("request_email_not_valid_at_cutoff")
        return subj
