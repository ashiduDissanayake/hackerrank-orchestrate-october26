"""CSV loaders. A data root is any directory shaped like `dataset/` (the real dataset or a fixture)."""
import csv
import os
from dataclasses import dataclass


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass(frozen=True)
class Request:
    case_id: str
    email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str


@dataclass(frozen=True)
class ActivityRow:
    activity_id: str
    event_time: str
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


@dataclass(frozen=True)
class AuditChange:
    audit_id: str
    user_id: str
    event_time: str
    field_name: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class IdentityRow:
    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: str


@dataclass(frozen=True)
class ManifestEntry:
    file_id: str
    file_path: str
    origin: str
    captured_at: str


@dataclass
class Dataset:
    root: str
    requests: list
    identities: list
    audit_log: list
    activity: list
    rules: list
    manifest: list

    def manifest_by_id(self):
        return {m.file_id: m for m in self.manifest}


def load_dataset(root, requests_file="deletion_requests.csv"):
    p = lambda n: os.path.join(root, n)  # noqa: E731
    return Dataset(
        root=root,
        requests=[Request(**r) for r in _read(p(requests_file))],
        identities=[IdentityRow(**r) for r in _read(p("user_identities.csv"))],
        audit_log=[AuditChange(**r) for r in _read(p("user_audit_log.csv"))],
        activity=[ActivityRow(**r) for r in _read(p("system_activity.csv"))],
        rules=_read(p("deletion_rules.csv")),
        manifest=[ManifestEntry(**r) for r in _read(p("evidence_files.csv"))],
    )


REQUEST_FILES = ("deletion_requests.csv", "sample_deletion_requests.csv")


def load_request_history(root):
    """Every request in the data root's request files (the evaluation and the public sample files when present), deduplicated by
    case_id. It is the subject's REQUEST HISTORY: context about other requests by the same person, never labels."""
    seen, out = set(), []
    for fn in REQUEST_FILES:
        path = os.path.join(root, fn)
        if not os.path.exists(path):
            continue
        for r in _read(path):
            if r["case_id"] not in seen:
                seen.add(r["case_id"])
                out.append(Request(**r))
    return out
