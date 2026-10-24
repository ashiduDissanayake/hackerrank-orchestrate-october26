"""Run manifest, reproducibility and export-gate tests. Uses the frozen fixtures only and never touches the
repo-root output.csv. Run: python3 code/tests/test_export.py"""
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
REPO = os.path.dirname(CODE)
sys.path.insert(0, CODE)

from ghostaudit import export as ex  # noqa: E402
from ghostaudit import run as runner  # noqa: E402

FX = os.path.join(CODE, "evaluation", "fixtures", "synth_v1")
MAIN = os.path.join(CODE, "main.py")


def run_cli(*args):
    return subprocess.run([sys.executable, MAIN, *args], capture_output=True, text=True, cwd=REPO)


class Reproducibility(unittest.TestCase):
    def test_two_runs_are_byte_identical_and_verify_passes(self):
        with tempfile.TemporaryDirectory(dir=os.path.join(REPO, "runs")) as t1, tempfile.TemporaryDirectory(dir=os.path.join(REPO, "runs")) as t2:
            outs = []
            for t in (t1, t2):
                out = os.path.join(t, "output.csv")
                r = run_cli("run", "--data", FX, "--out", out, "--diagnostics", os.path.join(t, "d.json"))
                self.assertEqual(r.returncode, 0, r.stderr)
                outs.append(out)
            self.assertEqual(ex.sha256_file(outs[0]), ex.sha256_file(outs[1]))
            m1 = json.load(open(os.path.splitext(outs[0])[0] + ".manifest.json"))
            m2 = json.load(open(os.path.splitext(outs[1])[0] + ".manifest.json"))
            for k in ("output_sha256", "inputs_sha256", "code_sha256", "config", "status_counts", "undetermined_cases"):
                self.assertEqual(m1[k], m2[k], k)
            for k in ("command", "config", "python", "git", "code_sha256", "inputs_sha256", "output_sha256", "undetermined_cases", "contract_valid", "final"):
                self.assertIn(k, m1)
            self.assertEqual(run_cli("verify", os.path.splitext(outs[0])[0] + ".manifest.json").returncode, 0)

    def test_verify_detects_tampering(self):
        with tempfile.TemporaryDirectory(dir=os.path.join(REPO, "runs")) as t:
            out = os.path.join(t, "output.csv")
            run_cli("run", "--data", FX, "--out", out, "--diagnostics", os.path.join(t, "d.json"))
            mp = os.path.splitext(out)[0] + ".manifest.json"
            m = json.load(open(mp))
            for key in ("output_sha256", "code_sha256"):
                bad = dict(m)
                bad[key] = "0" * 64
                json.dump(bad, open(mp, "w"))
                self.assertEqual(run_cli("verify", mp).returncode, 1, key)
            bad = dict(m)
            first = next(iter(m["inputs_sha256"]))
            bad["inputs_sha256"] = {**m["inputs_sha256"], first: "0" * 64}
            json.dump(bad, open(mp, "w"))
            self.assertEqual(run_cli("verify", mp).returncode, 1, "inputs")


class CodeHash(unittest.TestCase):
    def test_hash_covers_everything_that_can_change_a_prediction(self):
        files = ex.code_files()
        self.assertEqual(len([f for f in files if f.endswith(".json")]), 11, "all PNG transcriptions")
        for must in ("code/main.py", "code/requirements.txt", "code/ghostaudit/engine.py", "code/ghostaudit/account_proof.py"):
            self.assertIn(must, files)
        self.assertFalse([f for f in files if "__pycache__" in f or f.endswith(".pyc")])

    def test_changing_a_transcription_changes_the_hash(self):
        import hashlib
        files = ex.code_files()
        t = next(p for f, p in files.items() if f.endswith("evidence_09.json"))
        before = ex.code_hash()
        orig = open(t, "rb").read()
        try:
            open(t, "wb").write(orig + b" ")
            self.assertNotEqual(ex.code_hash(), before)
        finally:
            open(t, "wb").write(orig)
        self.assertEqual(ex.code_hash(), before)


class ExportGate(unittest.TestCase):
    def _subset(self, drop):
        """A copy of the fixtures without the given cases, so the gate can be tested on a fully resolved dataset."""
        tmp = tempfile.mkdtemp(dir=os.path.join(REPO, "runs"))
        shutil.copytree(FX, os.path.join(tmp, "d"))
        p = os.path.join(tmp, "d", "deletion_requests.csv")
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(r for r in rows if r["case_id"] not in drop)
        return tmp, os.path.join(tmp, "d")

    def _gate(self, data, policy="not_certified", **kw):
        ds, store, results = runner.run_dataset(data, unknown_policy=policy)
        out = os.path.join(os.path.dirname(data), "o.csv")
        runner.write_output(results, out)
        errs = ex.validate_output(ds, out)
        m = ex.build_manifest(["t"], {"unknown_policy": policy, "png_extraction": "complete"}, ds, results, out, errs)
        return ex.gate(ds, results, out, m, run_tests=False, **kw), m

    def test_refuses_when_cases_are_undetermined(self):
        tmp, data = self._subset(drop=set())
        try:
            reasons, m = self._gate(data, allow_dirty=True)
            self.assertTrue(m["undetermined_cases"])
            self.assertTrue(any("UNDETERMINED" in r for r in reasons), reasons)
            self.assertTrue(any("validation errors" in r for r in reasons), reasons)
        finally:
            shutil.rmtree(tmp)

    def test_exportable_when_fully_resolved_and_clean(self):
        tmp, data = self._subset(drop={"fx_case_07", "fx_case_14", "fx_case_17"})
        try:
            with mock.patch.object(ex, "git_state", return_value={"commit": "abc", "dirty": False, "dirty_files": [], "dirty_code_files": []}):
                reasons, m = self._gate(data)
            self.assertEqual(reasons, [])
            self.assertEqual(m["undetermined_cases"], [])
            self.assertTrue(m["contract_valid"])
        finally:
            shutil.rmtree(tmp)

    def test_refuses_dirty_tree_and_certifying_policy(self):
        tmp, data = self._subset(drop={"fx_case_07", "fx_case_14", "fx_case_17"})
        try:
            with mock.patch.object(ex, "git_state", return_value={"commit": "abc", "dirty": True, "dirty_files": ["x.py"], "dirty_code_files": ["code/ghostaudit/x.py"]}):
                reasons, _ = self._gate(data)
                self.assertTrue(any("prediction-affecting files differ" in r for r in reasons), reasons)
                reasons, _ = self._gate(data, policy="certify_established", allow_dirty=True)
                self.assertTrue(any("only 'not_certified'" in r for r in reasons), reasons)
        finally:
            shutil.rmtree(tmp)

    def test_documentation_only_changes_do_not_block_an_export(self):
        tmp, data = self._subset(drop={"fx_case_07", "fx_case_14", "fx_case_17"})
        try:
            with mock.patch.object(ex, "git_state", return_value={"commit": "abc", "dirty": True, "dirty_files": ["README.md", "code/evaluation/evaluation_report.md"],
                                                                  "dirty_code_files": []}):
                reasons, _ = self._gate(data)
            self.assertEqual(reasons, [])
        finally:
            shutil.rmtree(tmp)

    def test_git_state_keeps_the_first_dirty_file_name_intact(self):
        """Regression: stripping the whole porcelain output chopped the first path ("EADME.md")."""
        probe = os.path.join(REPO, "scripts", "_probe_dirty.txt")   # an untracked file under a non-ignored prefix
        with open(probe, "w") as f:
            f.write("x")
        try:
            names = ex.git_state()["dirty_files"]
            self.assertIn("scripts/_probe_dirty.txt", names)
            self.assertTrue(all(len(n) > 3 and not n.startswith(("EADME", "M ", "??")) for n in names), names)
        finally:
            os.remove(probe)

    def test_dirty_paths_are_classified_as_code_or_documentation(self):
        code = {"code/ghostaudit/engine.py", "code/ghostaudit/image_transcriptions/evidence_09.json", "code/main.py"}
        dirty = ["README.md", "code/ghostaudit/engine.py", "code/evaluation/evaluation_report.md", "code/ghostaudit/image_transcriptions/",
                 "code/docs/", "code/tests/test_export.py"]
        self.assertEqual(ex.dirty_code_paths(dirty, code), ["code/ghostaudit/engine.py", "code/ghostaudit/image_transcriptions/"])
        self.assertEqual(ex.dirty_code_paths(["README.md", "scripts/package.py"], code), [])
        self.assertIn("dirty_code_files", ex.git_state())

    def test_export_command_refuses_and_writes_nothing_on_unresolved_data(self):
        final = os.path.join(REPO, "output.csv")
        before = os.path.exists(final)
        r = run_cli("export", "--data", FX, "--skip-tests", "--allow-dirty")
        self.assertEqual(r.returncode, 1)
        self.assertIn("EXPORT REFUSED", r.stdout)
        self.assertEqual(os.path.exists(final), before, "a refused export must not create or change output.csv")

    def test_evidence_ids_of_all_kinds_are_time_checked(self):
        ds, _, _ = runner.run_dataset(FX)
        f = ex.evidence_time_resolver(ds)
        self.assertEqual(f("fxact_002"), "2026-06-02T07:30:00Z")   # activity id
        self.assertEqual(f("evidence_f02"), "2026-06-14T10:00:00Z")  # file id


if __name__ == "__main__":
    os.makedirs(os.path.join(REPO, "runs"), exist_ok=True)
    unittest.main(verbosity=2)
