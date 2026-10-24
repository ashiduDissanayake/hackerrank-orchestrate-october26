"""Plain-text shift handover: '<ts> | <system> | <resource> | <CATEGORY> | <STATE> | <identifier>' rows."""
import re

from ..observations import make_obs
from .common import normalize_fields

ROW = re.compile(r"^-\s*(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(.*)$")


def extract(evidence_id, path, available_at, store, report):
    for n, line in enumerate(open(path, encoding="utf-8"), start=1):
        s = line.rstrip("\n")
        snap = re.match(r"Snapshot:\s*(\S+)", s)
        if snap and snap.group(1) > available_at:
            report.notes.append(f"header Snapshot {snap.group(1)} later than manifest; using later")
            available_at = snap.group(1)
        if not s.startswith("-"):
            continue
        m = ROW.match(s)
        if not m:
            report.unparsed += 1
            report.failures.append(f"line {n}: {s[:100]}")
            continue
        ts, system, rid, cat, state, ident = m.groups()
        present = state != "NOT_FOUND"
        rec = normalize_fields({"record_type": cat, "result": state, "lookup_value": ident.strip()})
        store.add_obs(make_obs(evidence_id, f"L{n}", available_at, ts, system, rid, "handover", "record_lookup", present, rec))
