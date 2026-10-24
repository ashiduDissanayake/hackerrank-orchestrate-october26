"""Row-level diff of two output CSVs (status and step sets). Diagnostic helper for before/after measurements.
  python3 scripts/diff_outputs.py OLD.csv NEW.csv"""
import csv
import json
import sys

a = {r["case_id"]: r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8"))}
b = {r["case_id"]: r for r in csv.DictReader(open(sys.argv[2], encoding="utf-8"))}
changed = [c for c in a if c in b and a[c] != b[c]]
print(f"{len(changed)} changed rows of {len(a)}: {changed}")
for c in changed:
    sa = {(s["phase"], s["resource_id"], s["operation"], s["evidence_id"]) for s in json.loads(a[c]["steps_json"])}
    sb = {(s["phase"], s["resource_id"], s["operation"], s["evidence_id"]) for s in json.loads(b[c]["steps_json"])}
    print(f"  {c}: {a[c]['deletion_status']} -> {b[c]['deletion_status']}  removed {sorted(sa - sb)}  added {sorted(sb - sa)}")
