"""Log line parsing for the log dialects found under evidence/logs/.

Dialects (all start with an ISO-8601 UTC timestamp):
  bracket   2026-.. [LEVEL] [service] [trace] event: k="v" ...
  cloud     2026-.. requestId=T level=L function=F message="k=\\"v\\" ..."      (escaped, nested)
  kv        2026-.. level=L service=S k=v ...                                   (also INFO service=S ...)
  pipe      2026-.. | LEVEL | service | trace | event | k="v" ...
  json      2026-.. {"severity":..,"service":..,"event":..,...}
  syslog    2026-.. <15>1 node service trace - - level=L k="v" ...

parse_line returns an Event or None (blank lines). Unparseable lines are returned with event=None so the
caller can count them as parsing failures instead of silently dropping them.
"""
import json
import re
from dataclasses import dataclass, field

TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+(.*)$")
KV = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)=("(?:[^"\\]|\\.)*"|[^\s"]+)')
TRACE = re.compile(r"\b((?:tr|rb)-[A-Za-z0-9-]+)\b")


@dataclass
class Event:
    ts: str
    dialect: str
    event: str | None
    service: str | None
    trace_id: str | None
    fields: dict = field(default_factory=dict)
    raw: str = ""


def _unquote(v):
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1].replace('\\"', '"')
    return v


def _kv(text):
    return {k: _unquote(v) for k, v in KV.findall(text)}


def _nullish(d):
    return {k: (None if v in ("null", "None") else v) for k, v in d.items()}


def parse_line(line):
    line = line.rstrip("\n")
    if not line.strip():
        return None
    m = TS.match(line)
    if not m:
        return Event("", "unknown", None, None, None, {}, line)
    ts, rest = m.groups()

    if rest.startswith("{"):
        try:
            d = json.loads(rest)
        except json.JSONDecodeError:
            return Event(ts, "json", None, None, None, {}, line)
        d = _nullish({k: (v if isinstance(v, str) else json.dumps(v)) for k, v in d.items()})
        return Event(ts, "json", d.get("event"), d.get("service"), d.get("trace_id"), d, line)

    if rest.startswith("["):  # bracket
        mm = re.match(r"\[(\w+)\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+(\w+):\s*(.*)$", rest)
        if mm:
            _, svc, trace, ev, tail = mm.groups()
            return Event(ts, "bracket", ev, svc, trace, _nullish(_kv(tail)), line)
        return Event(ts, "bracket", None, None, None, {}, line)

    if rest.startswith("requestId="):  # cloud: nested escaped message
        outer = _kv(rest.split(' message="', 1)[0])
        msg = rest.split(' message="', 1)[1].rsplit('"', 1)[0] if ' message="' in rest else ""
        inner = _nullish(_kv(msg.replace('\\"', '"')))
        d = {**{k: v for k, v in outer.items() if k not in ("requestId",)}, **inner}
        return Event(ts, "cloud", inner.get("event"), outer.get("function"), outer.get("requestId"), d, line)

    if rest.startswith("| ") or re.match(r"^\w+ \| ", rest):  # pipe (some lines omit the leading pipe)
        parts = [p.strip() for p in rest.lstrip("| ").split(" | ")]
        if len(parts) >= 5:
            return Event(ts, "pipe", parts[3], parts[1], parts[2], _nullish(_kv(" ".join(parts[4:]))), line)
        return Event(ts, "pipe", None, None, None, {}, line)

    if rest.startswith("<"):  # syslog
        mm = re.match(r"<\d+>1\s+(\S+)\s+(\S+)\s+(\S+)\s+-\s+-\s+(.*)$", rest)
        if mm:
            _, svc, trace, tail = mm.groups()
            d = _nullish(_kv(tail))
            return Event(ts, "syslog", d.get("event"), svc, trace if TRACE.match(trace) else d.get("trace_id"), d, line)
        return Event(ts, "syslog", None, None, None, {}, line)

    d = _nullish(_kv(rest))  # kv (includes "INFO service=..." variants)
    if "event" in d:
        return Event(ts, "kv", d["event"], d.get("service"), d.get("trace_id") or (TRACE.search(rest).group(1) if TRACE.search(rest) else None), d, line)
    return Event(ts, "kv", None, None, None, {}, line)


def parse_file(path):
    with open(path, encoding="utf-8") as f:
        return [e for e in (parse_line(l) for l in f) if e is not None]


# ---------------------------------------------------------------------------------------------------------------
# Observation extraction
# ---------------------------------------------------------------------------------------------------------------
from ..observations import make_obs, system_from_resource  # noqa: E402
from .common import normalize_fields  # noqa: E402

LOOKUP_KEYS = ("lookup_key", "match_key", "subject_ref", "subject_key", "scan_key", "owner_key")
# Infrastructure noise: carries no resource state. Counted, never silently dropped.
NOISE = {
    "export_started", "export_completed", "cache_lookup", "cache_refresh", "connection_acquired", "connection_pool_pressure",
    "dependency_recovered", "dependency_retry", "certificate_checked", "consumer_lag", "disk_latency", "flag_snapshot_loaded",
    "lease_extended", "lease_renewed", "pool_sample", "properties_reloaded", "slow_call_rate", "telemetry_flushed",
    "timer_tick", "batch_started", "checkpoint_saved", "delivery_abandoned",
}


def _present(ev):
    f = ev.fields
    e = ev.event
    rows, code = f.get("rows"), f.get("http_status")
    if e in ("profile_lookup_completed", "audit_record_read_completed", "contact_lookup_completed", "contact_query_completed"):
        if rows is not None:
            return rows not in ("0", "00")
        return code == "200" if code else None
    if e == "index_query_completed":
        return {"hit": True, "miss": False}.get(f.get("result"))
    if e == "restore_policy_read_completed":
        return {"true": True, "false": False}.get(f.get("archive_present"))
    if e == "record_lookup":
        return f.get("result") != "NOT_FOUND"
    if e in ("analytics_profile_read_completed", "analytics_profile_read", "connector_config_read_completed",
             "connector_config_loaded", "connector_heartbeat", "support_ticket_read_completed", "export_metadata_read_completed",
             "message_read", "retained_order_loaded"):
        return True
    return None


def extract(evidence_id, path, available_at, store, report):
    events = parse_file(path)
    last_ts = max((e.ts for e in events if e.ts), default=None)
    if last_ts and last_ts > available_at:
        report.notes.append(f"log line time {last_ts} is later than manifest {available_at}; using later as availability")
        available_at = last_ts
    trace_key = {}
    for e in events:
        if e.event is None:
            report.unparsed += 1
            report.failures.append(f"unparsed line: {e.raw[:100]}")
            continue
        if e.trace_id:
            for k in LOOKUP_KEYS:
                if e.fields.get(k):
                    trace_key.setdefault(e.trace_id, (k, e.fields[k]))
    counts = {"noise": 0, "no_resource": 0}
    for n, e in enumerate(events, start=1):
        if e.event is None:
            continue
        if e.event in NOISE:
            counts["noise"] += 1
            continue
        f = dict(e.fields)
        rid = f.get("resource_id")
        if e.event == "record_lookup":  # notification / search diagnostic: record_type/result/subject_reference
            f["lookup_value"] = f.pop("subject_reference", None)
        if not rid:
            counts["no_resource"] += 1
            continue
        for drop in ("instance", "pod", "region", "level", "severity", "logger", "function", "service", "event", "trace_id", "seq", "duration_ms", "took_ms", "shard"):
            f.pop(drop, None)
        if e.trace_id and e.trace_id in trace_key:
            k, v = trace_key[e.trace_id]
            f["trace_lookup_key"] = v
            f["trace_lookup_field"] = k
        if e.trace_id:
            f["trace_id"] = e.trace_id
        sysid = f.pop("system", None) or system_from_resource(rid) or e.service
        store.add_obs(make_obs(evidence_id, f"L{n}", available_at, e.ts, sysid, rid, "log", e.event, _present(e), normalize_fields(f)))
    report.notes.append(f"events={len(events)} noise={counts['noise']} no_resource_id={counts['no_resource']}")
