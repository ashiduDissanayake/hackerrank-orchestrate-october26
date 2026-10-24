"""Guards the frozen labeled fixtures (synth_v1, synth_v2, synth_v3).

1. Every fixture file hashes to the value in synth_v1.sha256 (any edit after the freeze fails the test).
2. The build is deterministic (rebuilding yields the identical manifest).
3. Every labeled answer passes the output validator, including the evidence-time rule.
4. Internal expectations reference only resources/evidence that exist in the fixture.
Run: python3 code/evaluation/test_fixtures_frozen.py
"""
import csv
import hashlib
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from ghostaudit.validate import validate_row  # noqa: E402

FX = os.path.join(HERE, "fixtures")
# version -> (builder script, number of fully labeled output rows)
VERSIONS = {"synth_v1": ("build_fixtures.py", 13), "synth_v2": ("build_fixtures_v2.py", 17), "synth_v3": ("build_fixtures_v3.py", 18)}


def paths(version):
    return os.path.join(FX, version), os.path.join(FX, f"{version}.sha256")


def current_hashes(out):
    res = {}
    for root, _, names in os.walk(out):
        for nm in names:
            p = os.path.join(root, nm)
            res[os.path.relpath(p, out)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return res


def frozen_hashes(manifest):
    res = {}
    for line in open(manifest):
        h, rel = line.rstrip("\n").split("  ", 1)
        res[rel] = h
    return res


class Frozen(unittest.TestCase):
    def test_hashes_match_manifest(self):
        for v in VERSIONS:
            out, man = paths(v)
            self.assertEqual(current_hashes(out), frozen_hashes(man), f"{v}: fixture files changed after the freeze")

    def test_build_is_deterministic(self):
        for v, (script, _) in VERSIONS.items():
            out, man = paths(v)
            before = open(man).read()
            subprocess.check_call([sys.executable, os.path.join(FX, script)], stdout=subprocess.DEVNULL)
            self.assertEqual(open(man).read(), before, f"{v}: rebuild produced a different fixture set")
        # building a later version must never touch an earlier one
        for v in VERSIONS:
            self.assertEqual(current_hashes(paths(v)[0]), frozen_hashes(paths(v)[1]), f"{v} changed while rebuilding")

    def test_labels_are_contract_valid(self):
        for v, (_, expected_rows) in VERSIONS.items():
            out, _ = paths(v)
            reqs = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(out, "deletion_requests.csv"), encoding="utf-8"))}
            ev = {r["file_id"]: r["captured_at"] for r in csv.DictReader(open(os.path.join(out, "evidence_files.csv")))}
            ev.update({r["activity_id"]: r["event_time"] for r in csv.DictReader(open(os.path.join(out, "system_activity.csv")))})
            n = 0
            for r in csv.DictReader(open(os.path.join(out, "expected_output.csv"), encoding="utf-8")):
                errs = validate_row(r["case_id"], r["deletion_status"], r["steps_json"], audit_at=reqs[r["case_id"]]["audit_at"], evidence_time=ev.get)
                self.assertEqual(errs, [], f"{v} {r['case_id']}")
                n += 1
            self.assertEqual(n, expected_rows, v)

    def test_internal_references_exist(self):
        for v in VERSIONS:
            out, _ = paths(v)
            internal = json.load(open(os.path.join(out, "expected_internal.json"), encoding="utf-8"))
            corpus = ""
            for root, _, names in os.walk(out):
                for nm in names:
                    if nm not in ("expected_internal.json", "expected_output.csv"):
                        corpus += open(os.path.join(root, nm), encoding="utf-8").read()
            for case, exp in internal.items():
                for key in ("links_accepted", "links_rejected", "must_not_cite"):
                    for rid in exp.get(key, []):
                        self.assertIn(rid, corpus, f"{v} {case}: {rid} not found in fixture inputs")
                for u in exp.get("links_unresolved", []):
                    for rid in u["candidates"]:
                        self.assertIn(rid, corpus)

    def test_coverage_of_required_scenarios(self):
        out, _ = paths("synth_v3")
        reqs = list(csv.DictReader(open(os.path.join(out, "deletion_requests.csv"), encoding="utf-8")))
        internal = json.load(open(os.path.join(out, "expected_internal.json"), encoding="utf-8"))
        statuses = {r["deletion_status"] for r in csv.DictReader(open(os.path.join(out, "expected_output.csv"), encoding="utf-8"))}
        self.assertEqual(statuses, {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"})
        self.assertGreaterEqual(sum(1 for v in internal.values() if v.get("status") == "UNDETERMINED"), 3)
        self.assertTrue(any(re_.encode("ascii", "ignore") != re_.encode() for re_ in (r["request_text"] for r in reqs)),
                        "needs non-ASCII (multilingual) request text")


if __name__ == "__main__":
    unittest.main(verbosity=2)
