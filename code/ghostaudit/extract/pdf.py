"""PDF documents via pdftotext -layout. One observation per resource id mentioned (or one id-less document
observation). Embedded dates are not parsed (the text rendering loses time separators); the manifest time is used."""
import re
import shutil
import subprocess

from ..observations import make_obs
from .common import normalize_fields

RES_RE = re.compile(r"\b(?:account|analytics|audit_record|backup|data_flow|export|legal_hold|marketing|search|support|tombstone|object|email_delivery)_[A-Za-z]?\d+\b")


def pdf_text(path):
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext (poppler) not found; install poppler-utils")
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout


def extract(evidence_id, path, available_at, store, report):
    text = pdf_text(path)
    flat = re.sub(r"[ \t]+", " ", text)
    base = normalize_fields({"document_text": flat})
    base["text_excerpt"] = flat.strip()[:400].replace("\n", " ")
    base["orders"] = "|".join(sorted(set(re.findall(r"\bORD-\d+\b", text))))
    rids = sorted(set(RES_RE.findall(text)))
    if not rids:
        report.notes.append("no resource ids in document; emitted one id-less document observation")
        store.add_obs(make_obs(evidence_id, "doc", available_at, None, None, None, "pdf", "document", None, base))
    for rid in rids:
        store.add_obs(make_obs(evidence_id, f"doc:{rid}", available_at, None, None, rid, "pdf", "document", True, dict(base)))
