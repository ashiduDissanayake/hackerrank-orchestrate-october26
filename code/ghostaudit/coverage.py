"""Extraction coverage report.

'ok' only means the extractor did not raise, so each text artifact is also checked independently: every
resource id that appears in the raw file must appear in some observation extracted from it (log noise events
and headers are expected to contribute nothing, so the check is on resource ids, not lines).
"""
import os
import re
import subprocess
from collections import Counter

from .extract.pdf import RES_RE

RAW_ID = re.compile(r"\b((?:account|analytics|audit_record|backup|data_flow|export|legal_hold|marketing|search|support|tombstone|object|email_delivery)_[A-Za-z]?\d+[A-Za-z]*)\b")


def raw_resource_ids(path):
    if path.endswith(".png"):
        return None
    if path.endswith(".pdf"):
        text = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    else:
        text = open(path, encoding="utf-8", errors="replace").read()
    return set(RAW_ID.findall(text))


def report(ds, store):
    rows = []
    obs_by_art = {}
    for o in store._obs:
        got = obs_by_art.setdefault(o.evidence_id, set())
        got.add(o.resource_id)
        for _, v in o.fields:  # ids referenced inside records (e.g. source_resource_id) count as captured, not lost
            if v:
                got.update(RAW_ID.findall(v))
    for eid, rep in sorted(store.artifacts.items(), key=lambda kv: int(kv[0].split("_")[-1])):
        raw = raw_resource_ids(os.path.join(ds.root, rep.path))
        got = obs_by_art.get(eid, set())
        missing = sorted(raw - got) if raw is not None else None
        rows.append((rep, missing, len(raw) if raw is not None else None))
    return rows


def render(ds, store):
    rows = report(ds, store)
    out = []
    out.append(f"{'file_id':<13}{'fmt':<5}{'status':<9}{'obs':>6}{'res':>6}{'scopes':>7}{'rawIDs':>7}{'missing':>8}{'unparsed':>9}  path")
    tot = Counter()
    gaps = []
    for rep, missing, nraw in rows:
        out.append(f"{rep.evidence_id:<13}{rep.fmt:<5}{rep.status:<9}{rep.observations:>6}{rep.resources:>6}{rep.scopes:>7}"
                   f"{(nraw if nraw is not None else '-'):>7}{(len(missing) if missing is not None else '-'):>8}{rep.unparsed:>9}  {rep.path}")
        tot[rep.status] += 1
        tot["obs"] += rep.observations
        tot["unparsed"] += rep.unparsed
        if missing:
            gaps.append((rep.evidence_id, missing))
        for n in rep.notes:
            if "differs" in n or "later than" in n or "Snapshot" in n:
                tot["time_disagreements"] += 1
    out.append("")
    out.append(f"artifacts by status: { {k: v for k, v in tot.items() if k in ('ok', 'pending', 'failed')} }")
    out.append(f"observations: {tot['obs']}   scopes: {len(store._scopes)}   catalog links: {len(store.catalog_links)}   unparsed lines/rows: {tot['unparsed']}")
    out.append(f"manifest-vs-content time disagreements noted: {tot['time_disagreements']}")
    later = [o for o in store._obs if o.observed_at > o.available_at]
    out.append(f"observations with observed_at later than their artifact's availability: {len(later)}"
               + (f" e.g. {later[0].evidence_id} {later[0].locator}" if later else ""))
    if gaps:
        out.append(f"\nEXTRACTION GAPS (raw resource ids with no observation), {len(gaps)} files:")
        for eid, miss in gaps:
            out.append(f"  {eid}: {len(miss)} e.g. {miss[:6]}")
    else:
        out.append("no extraction gaps by the resource-id check")
    fails = [(r.evidence_id, f) for r, _, _ in rows for f in r.failures]
    out.append(f"extractor failures recorded: {len(fails)}")
    for eid, f in fails[:20]:
        out.append(f"  {eid}: {f}")
    return "\n".join(out)
