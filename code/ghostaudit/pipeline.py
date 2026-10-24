"""Builds the unfiltered evidence Store from a data root (dataset/ or a fixture)."""
import os
import re

from .data import load_dataset
from .extract import handover, images, json_records, logs, pdf, sql_snapshots
from .observations import ArtifactReport, Store

CATALOG_RE = re.compile(r"linked (?P<res>\S+) \((?P<label>[^)]*)\) to (?P<email>\S+) and (?P<user>user_\w+)")
CATALOG_EXCL_RE = re.compile(r"confirmed (?P<res>\S+) \((?P<label>[^)]*)\) belongs only to (?P<email>\S+) and (?P<user>user_\w+)")

EXTRACTORS = {".sql": sql_snapshots.extract, ".json": json_records.extract, ".log": logs.extract,
              ".txt": handover.extract, ".pdf": pdf.extract, ".png": images.extract}
FORMAT = {".sql": "sql", ".json": "json", ".log": "log", ".txt": "txt", ".pdf": "pdf", ".png": "png"}


class CatalogLink:
    __slots__ = ("activity_id", "event_time", "system_id", "resource_id", "email", "user_ref", "exclusive")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def build_store(ds):
    store = Store()
    for m in ds.manifest:
        ext = os.path.splitext(m.file_path)[1].lower()
        rep = ArtifactReport(m.file_id, m.file_path, FORMAT.get(ext, ext), m.captured_at)
        store.artifacts[m.file_id] = rep
        fn = EXTRACTORS.get(ext)
        path = os.path.join(ds.root, m.file_path)
        if fn is None:
            rep.status = "failed"
            rep.failures.append(f"no extractor for {ext}")
            continue
        try:
            fn(m.file_id, path, m.captured_at, store, rep)
        except Exception as e:  # report, never swallow silently
            rep.status = "failed"
            rep.failures.append(f"{type(e).__name__}: {e}")
    store.activity = list(ds.activity)
    for a in ds.activity:
        if a.event_type != "LINK_RESOURCE_IDENTITY":
            continue
        mm = CATALOG_EXCL_RE.search(a.details)
        excl = bool(mm)
        mm = mm or CATALOG_RE.search(a.details)
        if mm:
            store.catalog_links.append(CatalogLink(activity_id=a.activity_id, event_time=a.event_time, system_id=a.target_system,
                                                   resource_id=mm.group("res"), email=mm.group("email").lower(),
                                                   user_ref=mm.group("user"), exclusive=excl))
    return store.finalize()


def build(root, requests_file="deletion_requests.csv"):
    ds = load_dataset(root, requests_file)
    return ds, build_store(ds)
