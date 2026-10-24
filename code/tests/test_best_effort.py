"""The best-effort review artifact: always certified=false, never the submission path, never fabricated, fully registered.
Uses the frozen v3 fixtures (small, contains UNDETERMINED cases) plus one structural guard on the real run.
Run: python3 code/tests/test_best_effort.py"""
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
REPO = os.path.dirname(CODE)
sys.path.insert(0, CODE)

from ghostaudit import export as ex  # noqa: E402
from ghostaudit import run as runner  # noqa: E402

FX = os.path.join(CODE, "evaluation", "fixtures", "synth_v3")
MAIN = os.path.join(CODE, "main.py")


def build(root, out_dir):
    ds, store, results = runner.run_dataset(root)
    tmp = os.path.join(out_dir, "candidate.csv")
    runner.write_output(results, tmp)
    errs = ex.validate_output(ds, tmp)
    manifest = ex.build_manifest(["python3", "code/main.py", "best-effort"], {"data": root, "requests": "deletion_requests.csv",
                                                                               "unknown_policy": "not_certified"}, ds, results, tmp, errs)
    paths, reg = ex.write_best_effort(ds, results, errs, manifest, out_dir)
    return ds, results, errs, paths, reg


class BestEffort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ds, cls.results, cls.errs, cls.paths, cls.reg = build(FX, cls.tmp.name)
        cls.manifest = json.load(open(cls.paths["output_best_effort.manifest.json"]))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_writes_only_the_review_files_never_output_csv(self):
        self.assertEqual(sorted(os.listdir(self.tmp.name)), sorted(["candidate.csv", *ex.BEST_EFFORT_NAMES]))
        self.assertNotIn("output.csv", os.listdir(self.tmp.name))

    def test_manifest_is_never_certified_and_records_every_validation_error(self):
        m = self.manifest
        self.assertIs(m["certified"], False)
        self.assertIs(m["final"], False)
        self.assertEqual(m["kind"], "best_effort")
        self.assertEqual(m["validation_errors"], self.errs)
        self.assertEqual(m["validation_error_count"], len(self.errs))
        self.assertIn("NOT a certified", m["disclosure"])
        self.assertEqual(m["output_sha256"], ex.sha256_file(self.paths["output_best_effort.csv"]))

    def test_has_one_row_per_request(self):
        rows = list(csv.DictReader(open(self.paths["output_best_effort.csv"], encoding="utf-8")))
        self.assertEqual([r["case_id"] for r in rows], [r.case_id for r in self.results])
        self.assertEqual(len(rows), len(self.ds.requests))

    def test_register_covers_every_undetermined_case_with_a_precise_gap(self):
        und = {r.case_id for r in self.results if r.internal == "UNDETERMINED"}
        self.assertGreaterEqual(len(und), 3)
        by_case = {e["case_id"]: e for e in self.reg}
        self.assertTrue(und <= set(by_case))
        for cid in und:
            e = by_case[cid]
            self.assertFalse(e["status_determined"])
            self.assertTrue(e["unresolved"])
            for u in e["unresolved"]:
                self.assertTrue(len(u["information_gap"]) > 40, u)

    def test_nothing_is_fabricated_for_unresolved_obligations(self):
        by_id = {r.case_id: r for r in self.results}
        for e in self.reg:
            for s in by_id[e["case_id"]].steps:
                self.assertIsNotNone(s["resource_id"])
                self.assertFalse(s["phase"] == "FINDING" and not s["evidence_id"], "a finding without evidence")
            unresolved_resources = {u["resource_id"] for u in e["unresolved"] if u["resource_id"]}
            for s in by_id[e["case_id"]].steps:
                if s["resource_id"] in unresolved_resources:
                    self.fail(f"{e['case_id']}: step emitted for unresolved {s['resource_id']}")

    def test_validation_errors_are_exactly_the_undetermined_rows(self):
        und = {r.case_id for r in self.results if r.internal == "UNDETERMINED" and r.status == "INCOMPLETE" and not any(
            o.verdict == "VIOLATION" for o in r.obligations)}
        self.assertEqual({e.split(":")[0] for e in self.errs}, und)

    def test_cli_leaves_the_submission_path_alone(self):
        before = os.path.exists(os.path.join(REPO, "output.csv"))
        r = subprocess.run([sys.executable, MAIN, "best-effort", "--data", FX], capture_output=True, text=True, cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.exists(os.path.join(REPO, "output.csv")), before)
        self.assertIn("certified=false", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
