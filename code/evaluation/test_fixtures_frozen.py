"""Guards the frozen labeled fixtures (synth_v1).

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
OUT = os.path.join(FX, "synth_v1")
MANIFEST = os.path.join(FX, "synth_v1.sha256")


def current_hashes():
    res = {}
    for root, _, names in os.walk(OUT):
        for nm in names:
            p = os.path.join(root, nm)
            res[os.path.relpath(p, OUT)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return res


def frozen_hashes():
    res = {}
    for line in open(MANIFEST):
        h, rel = line.rstrip("\n").split("  ", 1)
        res[rel] = h
    return res


class Frozen(unittest.TestCase):
    def test_hashes_match_manifest(self):
        self.assertEqual(current_hashes(), frozen_hashes(), "fixture files changed after the freeze")

    def test_build_is_deterministic(self):
        before = open(MANIFEST).read()
        subprocess.check_call([sys.executable, os.path.join(FX, "build_fixtures.py")], stdout=subprocess.DEVNULL)
        self.assertEqual(open(MANIFEST).read(), before, "rebuild produced a different fixture set")

    def test_labels_are_contract_valid(self):
        reqs = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(OUT, "deletion_requests.csv"), encoding="utf-8"))}
        ev = {r["file_id"]: r["captured_at"] for r in csv.DictReader(open(os.path.join(OUT, "evidence_files.csv")))}
        n = 0
        for r in csv.DictReader(open(os.path.join(OUT, "expected_output.csv"), encoding="utf-8")):
            errs = validate_row(r["case_id"], r["deletion_status"], r["steps_json"], audit_at=reqs[r["case_id"]]["audit_at"], evidence_time=ev.get)
            self.assertEqual(errs, [], r["case_id"])
            n += 1
        self.assertEqual(n, 13)

    def test_internal_references_exist(self):
        internal = json.load(open(os.path.join(OUT, "expected_internal.json"), encoding="utf-8"))
        corpus = ""
        for root, _, names in os.walk(OUT):
            for nm in names:
                if nm not in ("expected_internal.json", "expected_output.csv"):
                    corpus += open(os.path.join(root, nm), encoding="utf-8").read()
        for case, exp in internal.items():
            for key in ("links_accepted", "links_rejected"):
                for rid in exp.get(key, []):
                    self.assertIn(rid, corpus, f"{case}: {rid} not found in fixture inputs")
            for rid in exp.get("must_not_cite", []):
                self.assertIn(rid, corpus)
            for u in exp.get("links_unresolved", []):
                for rid in u["candidates"]:
                    self.assertIn(rid, corpus)

    def test_coverage_of_required_scenarios(self):
        reqs = list(csv.DictReader(open(os.path.join(OUT, "deletion_requests.csv"), encoding="utf-8")))
        internal = json.load(open(os.path.join(OUT, "expected_internal.json"), encoding="utf-8"))
        statuses = {r["deletion_status"] for r in csv.DictReader(open(os.path.join(OUT, "expected_output.csv"), encoding="utf-8"))}
        self.assertEqual(statuses, {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"})
        self.assertTrue(any(v.get("status") == "UNDETERMINED" for v in internal.values()))
        self.assertTrue(any(re_.encode("ascii", "ignore") != re_.encode() for re_ in (r["request_text"] for r in reqs)),
                        "needs non-ASCII (multilingual) request text")


if __name__ == "__main__":
    unittest.main(verbosity=2)
