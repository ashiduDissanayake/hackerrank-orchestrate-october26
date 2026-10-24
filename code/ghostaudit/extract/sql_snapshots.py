"""SQLite-compatible SQL snapshot exports -> Observations + ScopeDecls.

Families handled (by table shape, not by file name):
  typed inventory       tables + snapshot_scope(origin_system, captured_at)      scope: declared
  document tables       (resource_id, origin_system, collection_name, record_json, updated_at)
                        one table per physical copy (primary / replica_* / read_replica / ...)
                        scope: systems seen in ANY table of the file, applied to EVERY table  (inferred_from_rows)
  account replicas      customer_profiles_primary / customer_profiles_failover_replica        (inferred_from_table)
  search primary        search_documents_primary                                               (inferred_from_table)
Files are executed in an in-memory SQLite database only.
"""
import json
import re
import sqlite3

from ..observations import ScopeDecl, make_obs
from .common import normalize_fields

TYPED_SYSTEM = {
    "customer_profiles": "account_service",
    "customer_search_documents": "search_service",
    "customer_analytics_profiles": "analytics_platform",
    "support_records": "support_platform",
    "customer_exports": "export_service",
    "connector_subscriptions": "integration_service",
    "backup_restore_entries": "backup_service",
    "security_audit_records": "security_service",
}
DOC_COLS = {"resource_id", "origin_system", "collection_name", "record_json", "updated_at"}
ACCT_COLS = {"resource_id", "user_id", "full_name", "email", "phone", "account_status", "updated_at"}
SEARCH_COLS = {"resource_id", "display_name", "email", "source_resource_id", "indexed_at"}


def _header(text):
    cap = re.search(r"^-- Captured at:\s*(\S+)", text, re.M)
    topo = re.search(r"^-- Database topology:\s*(\S+)", text, re.M)
    done = re.search(r"snapshot_completed_at=(\S+)", text)
    return (cap.group(1) if cap else None), (topo.group(1) if topo else None), (done.group(1) if done else None)


def _store_name(table):
    t = re.sub(r"^customer_data_", "", table)
    t = re.sub(r"^customer_profiles_", "", t)
    return t


def extract(evidence_id, path, available_at, store, report):
    text = open(path, encoding="utf-8").read()
    cap, topo, done = _header(text)
    header_time = cap or done
    if header_time and header_time > available_at:
        available_at = header_time  # later of manifest and header
    if header_time and header_time != report.available_at:
        report.notes.append(f"header time {header_time} differs from manifest {report.available_at}; using later")
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(text)
    except sqlite3.Error as e:
        report.status = "failed"
        report.failures.append(f"sqlite load error: {e}")
        return
    db.row_factory = sqlite3.Row
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    cols = {t: [c[1] for c in db.execute(f'PRAGMA table_info("{t}")')] for t in tables}

    # Source completeness: the export closed its transaction, and a typed inventory carries its completion marker.
    committed = re.search(r"^\s*COMMIT\s*;", text, re.M) is not None
    complete = committed and (done is not None or "snapshot_scope" not in tables)
    if not complete:
        report.notes.append("source completeness not established (no COMMIT, or inventory without snapshot_completed_at)")

    # scope for typed inventory: the declared origin system is covered for the tables of that system present in the file
    if "snapshot_scope" in tables:
        for r in db.execute("SELECT origin_system, captured_at FROM snapshot_scope"):
            captured = tuple(sorted(t for t in tables if TYPED_SYSTEM.get(t) == r["origin_system"]))
            store.add_scope(ScopeDecl(evidence_id, max(available_at, r["captured_at"]), r["origin_system"], "inventory", "declared", None, captured, complete))

    doc_tables = [t for t in tables if DOC_COLS <= set(cols[t])]
    doc_systems = set()
    for t in doc_tables:
        doc_systems |= {r[0] for r in db.execute(f'SELECT DISTINCT origin_system FROM "{t}"')}
    for t in doc_tables:
        for sysid in sorted(doc_systems):
            store.add_scope(ScopeDecl(evidence_id, available_at, sysid, _store_name(t), "inferred_from_rows", None, (), complete))

    for t in tables:
        if t == "snapshot_scope":
            continue
        cset = set(cols[t])
        if t in TYPED_SYSTEM:
            sysid = TYPED_SYSTEM[t]
            for r in db.execute(f'SELECT * FROM "{t}"'):
                d = dict(r)
                rid = d.pop("resource_id")
                obs_t = d.pop("updated_at", None)
                rec = normalize_fields(d)
                store.add_obs(make_obs(evidence_id, f"{t}:{rid}", available_at, obs_t, sysid, rid, "inventory", "record", True, rec))
        elif DOC_COLS <= cset:
            for r in db.execute(f'SELECT * FROM "{t}"'):
                try:
                    raw = json.loads(r["record_json"])
                except json.JSONDecodeError:
                    report.unparsed += 1
                    report.failures.append(f"{t}:{r['resource_id']} record_json invalid")
                    continue
                rec = normalize_fields(raw)
                rec["collection"] = r["collection_name"]
                store.add_obs(make_obs(evidence_id, f"{t}:{r['resource_id']}", available_at, r["updated_at"], r["origin_system"],
                                       r["resource_id"], _store_name(t), "record", True, rec))
        elif ACCT_COLS <= cset:
            sysid = "account_service"
            store.add_scope(ScopeDecl(evidence_id, available_at, sysid, _store_name(t), "inferred_from_table", None, ("customer_profiles",), complete))
            for r in db.execute(f'SELECT * FROM "{t}"'):
                d = dict(r)
                rid = d.pop("resource_id")
                obs_t = d.pop("updated_at")
                store.add_obs(make_obs(evidence_id, f"{t}:{rid}", available_at, obs_t, sysid, rid, _store_name(t), "record", True, normalize_fields(d)))
        elif SEARCH_COLS <= cset:
            store.add_scope(ScopeDecl(evidence_id, available_at, "search_service", _store_name(t), "inferred_from_table", None, ("customer_search_documents",), complete))
            for r in db.execute(f'SELECT * FROM "{t}"'):
                d = dict(r)
                rid = d.pop("resource_id")
                obs_t = d.pop("indexed_at")
                store.add_obs(make_obs(evidence_id, f"{t}:{rid}", available_at, obs_t, "search_service", rid, _store_name(t), "record", True, normalize_fields(d)))
        else:
            report.skipped += 1
            report.failures.append(f"table {t} has unrecognized shape {sorted(cset)}")
