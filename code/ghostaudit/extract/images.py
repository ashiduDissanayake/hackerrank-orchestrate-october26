"""PNG screenshots -> Observations from hash-bound transcriptions.

The transcriptions (code/ghostaudit/image_transcriptions/*.json) are hand-authored (see
scripts/build_image_transcriptions.py) and bound to the PNG bytes by sha256: if the image changes the transcription is
rejected and the artifact is reported failed. An image without a transcription stays `pending`, so coverage numbers
never overstate. Provenance (method, transcriber, per-record notes, the catalog row a resource id came from) is kept
in the observation fields.
"""
import hashlib
import json
import os

from ..observations import make_obs
from .common import normalize_fields

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image_transcriptions")


def extract(evidence_id, path, available_at, store, report):
    tpath = os.path.join(DIR, f"{evidence_id}.json")
    if not os.path.exists(tpath):
        report.status = "pending"
        report.notes.append("no transcription for this image")
        return
    doc = json.load(open(tpath, encoding="utf-8"))
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if doc["source_sha256"] != sha:
        report.status = "failed"
        report.failures.append(f"transcription is bound to a different image (sha256 {doc['source_sha256'][:12]} != {sha[:12]})")
        return
    base_avail = max(available_at, doc.get("header_time") or "")
    report.notes.append(f"transcription: {doc['method']}; {len(doc['records'])} records")
    for i, r in enumerate(doc["records"]):
        avail = max(base_avail, r.get("available_at_override") or "")
        f = dict(r["fields"])
        f["source_screen"] = doc["screen"]
        f["transcription_method"] = "agent_visual_transcription"
        for k in ("note", "resource_id_source"):
            if r.get(k):
                f[f"provenance_{k}"] = r[k]
        store.add_obs(make_obs(evidence_id, f"/records/{i}", avail, r["observed_at"], r["system_id"], r["resource_id"], "ui",
                               r["kind"], r["present"], normalize_fields(f)))
