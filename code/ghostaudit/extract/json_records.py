"""JSON evidence families -> Observations + ScopeDecls.

  snapshot bundle     {"snapshots":[{captured_at,data_store,collection,records}]}   scope: declared per (data_store, collection)
  service export      {"service_exports":{service:{list:[{resource_id,observed_at,...}]}}}   explicit lookups (no scope)
  lookup ledger       {"records":[{recorded_at,system,resource_id,record_type,result,subject_reference}]}
  collection file     {"captured_at","collection","records":[...]}                  (export jobs, analytics reports)
"""
import json

from ..observations import ScopeDecl, make_obs
from .common import normalize_fields

HISTORY = "operational_record_history"


def _later(a, b):
    return max(a, b) if a and b else (a or b)


def extract(evidence_id, path, available_at, store, report):
    d = json.load(open(path, encoding="utf-8"))
    header = d.get("exported_at") or d.get("captured_at")
    if header and header != available_at:
        report.notes.append(f"header time {header} differs from manifest {available_at}; using later")
    available_at = _later(available_at, header)

    if "snapshots" in d:
        for si, snap in enumerate(d["snapshots"]):
            cap = snap.get("captured_at") or available_at
            avail = _later(available_at, cap)
            ds, coll = snap["data_store"], snap["collection"]
            if coll != HISTORY:
                store.add_scope(ScopeDecl(evidence_id, avail, ds, "bundle", "declared", coll))
            for ri, rec in enumerate(snap["records"]):
                rec = dict(rec)
                t = rec.pop("recorded_at", None) or cap
                loc = f"/snapshots/{si}/records/{ri}"
                if coll == HISTORY:
                    rec_f = normalize_fields({**rec, "lookup_value": rec.get("lookup_value")})
                    present = rec.get("result") != "NOT_FOUND"
                    store.add_obs(make_obs(evidence_id, loc, avail, t, rec.get("system"), rec.get("resource_id"), "history", "record_lookup", present, rec_f))
                else:
                    rec_f = normalize_fields(rec)
                    rec_f["collection"] = coll
                    store.add_obs(make_obs(evidence_id, loc, avail, t, ds, rec.get("resource_id"), "bundle", "record", True, rec_f))
    elif "service_exports" in d:
        for svc, sections in d["service_exports"].items():
            for lname, items in sections.items():
                for i, it in enumerate(items):
                    it = dict(it)
                    t = it.pop("observed_at", None)
                    loc = f"/service_exports/{svc}/{lname}/{i}"
                    kind, present = "record", True
                    if lname == "profile_lookups":
                        prof = it.pop("profile", None) or {}
                        code = it.get("status_code")
                        present = code == 200 and bool(prof)
                        kind = "lookup"
                        it = {**it, **prof}
                    elif lname == "index_queries":
                        it["lookup_key"] = it.pop("query", None)
                        hits = it.pop("hits", None)
                        docs = hits.get("documents", []) if isinstance(hits, dict) else []
                        total = hits.get("total", len(docs)) if isinstance(hits, dict) else (hits or 0)
                        if docs:  # one observation per returned document; identifiers come from the document itself
                            for di, doc in enumerate(docs):
                                rec = {**it, **doc, "hit_total": total}
                                store.add_obs(make_obs(evidence_id, f"{loc}/hits/{di}", available_at, t, svc, doc.get("resource_id") or it.get("resource_id"),
                                                       "export", "lookup", True, normalize_fields(rec)))
                            continue
                        present = False
                        it["hit_total"] = total
                        kind = "lookup"
                    store.add_obs(make_obs(evidence_id, loc, available_at, t, svc, it.get("resource_id"), "export", kind, present, normalize_fields(it)))
    elif "records" in d and d["records"] and "record_type" in d["records"][0]:
        for i, rec in enumerate(d["records"]):
            rec = dict(rec)
            t = rec.pop("recorded_at", None)
            present = rec.get("result") != "NOT_FOUND"
            store.add_obs(make_obs(evidence_id, f"/records/{i}", available_at, t, rec.get("system"), rec.get("resource_id"), "ledger", "record_lookup", present, normalize_fields(rec)))
    elif "records" in d and "collection" in d:
        for i, rec in enumerate(d["records"]):
            rf = normalize_fields(rec)
            rf["collection"] = d["collection"]
            store.add_obs(make_obs(evidence_id, f"/records/{i}", available_at, None, None, rec.get("resource_id"), "snapshot", "record", True, rf))
    else:
        report.status = "failed"
        report.failures.append(f"unrecognized JSON shape: keys={sorted(d)}")
