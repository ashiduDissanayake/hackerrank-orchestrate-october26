"""Corruption tests for the scorer and validator.

Identity scoring only proves the scorer runs. Here known mutations are applied to the public
sample answers and the exact metric effect is asserted, independently of the scorer's logic.
Run: python3 code/evaluation/test_scoring.py   (from the repo root, stdlib unittest only)
"""
import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from ghostaudit.contract import OP_PHASE, OP_STATE, OPERATION_TABLE, canonical_sort  # noqa: E402
from ghostaudit.validate import validate_row  # noqa: E402
import scoring  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
GOLD = scoring.load_output(os.path.join(ROOT, "dataset", "sample_output.csv"))


def clone():
    return copy.deepcopy(GOLD)


def renumber(steps):
    for i, s in enumerate(steps, start=1):
        s["step_no"] = i
    return steps


def totals(g):
    G = sum(len(v["steps"]) for v in g.values())
    return G, len(g)


def row_errors(cid, rec):
    return validate_row(cid, rec["status"], json.dumps(rec["steps"]))


class Baseline(unittest.TestCase):
    def test_gold_is_valid_and_perfect(self):
        for cid, rec in GOLD.items():
            self.assertEqual(row_errors(cid, rec), [], cid)
        m = scoring.score(GOLD, clone())
        for k in ("status_accuracy", "alignment_coverage", "evidence_accuracy", "sequence_exact_rate", "sequence_mean_lcs"):
            self.assertEqual(m[k], 1.0, k)
        self.assertEqual(m["step_strict"]["f1"], 1.0)
        self.assertEqual(m["step_lenient"]["f1"], 1.0)

    def test_sample_set_has_no_not_applicable(self):
        # documents the coverage gap that the labeled fixtures must fill
        self.assertNotIn("NOT_APPLICABLE", {v["status"] for v in GOLD.values()})


class Mutations(unittest.TestCase):
    def setUp(self):
        self.G, self.N = totals(GOLD)

    def test_drop_step(self):
        p = clone()
        k = 0
        for rec in p.values():
            if len(rec["steps"]) >= 2:
                del rec["steps"][len(rec["steps"]) // 2]
                renumber(rec["steps"])
                k += 1
        m = scoring.score(GOLD, p)
        self.assertEqual(m["step_strict"]["precision"], 1.0)
        self.assertAlmostEqual(m["step_strict"]["recall"], (self.G - k) / self.G)
        self.assertAlmostEqual(m["sequence_exact_rate"], (self.N - k) / self.N)
        self.assertAlmostEqual(m["alignment_coverage"], (self.G - k) / self.G)

    def test_extra_step(self):
        p = clone()
        k = 0
        for rec in p.values():
            ev = "" if rec["status"] == "INCOMPLETE" else "evidence_01"
            rec["steps"].append({
                "step_no": 0, "phase": "VERIFICATION", "system_id": "zzz_service", "resource_id": "zzz_1",
                "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev,
            })
            rec["steps"] = canonical_sort(rec["steps"])
            k += 1
        m = scoring.score(GOLD, p)
        self.assertEqual(m["step_strict"]["recall"], 1.0)
        self.assertAlmostEqual(m["step_strict"]["precision"], self.G / (self.G + k))
        self.assertEqual(m["sequence_exact_rate"], 0.0)

    def test_duplicate_step(self):
        p = clone()
        k = 0
        errs = 0
        for cid, rec in p.items():
            rec["steps"].insert(1, copy.deepcopy(rec["steps"][0]))
            renumber(rec["steps"])
            k += 1
            errs += any("duplicate" in e for e in row_errors(cid, rec))
        m = scoring.score(GOLD, p)
        self.assertEqual(m["step_strict"]["recall"], 1.0)
        self.assertAlmostEqual(m["step_strict"]["precision"], self.G / (self.G + k))
        self.assertEqual(errs, k, "validator must flag every duplicated step")

    def test_wrong_citation(self):
        p = clone()
        k = 0
        E = sum(1 for v in GOLD.values() for s in v["steps"] if s["evidence_id"])
        for rec in p.values():
            for s in rec["steps"]:
                if s["evidence_id"]:
                    s["evidence_id"] = "evidence_99"
                    k += 1
                    break
        m = scoring.score(GOLD, p)
        self.assertEqual(m["step_lenient"]["f1"], 1.0, "citation error must not affect lenient score")
        self.assertAlmostEqual(m["step_strict"]["recall"], (self.G - k) / self.G)
        self.assertAlmostEqual(m["evidence_accuracy"], (E - k) / E)
        self.assertAlmostEqual(m["field_accuracy"]["evidence_id"], (self.G - k) / self.G)
        self.assertEqual(m["field_accuracy"]["state"], 1.0)

    def test_wrong_state(self):
        p = clone()
        k = 0
        errs = 0
        for cid, rec in p.items():
            rec["steps"][0]["state"] = "ZZZ"
            k += 1
            errs += bool(row_errors(cid, rec))
        m = scoring.score(GOLD, p)
        self.assertEqual(m["alignment_coverage"], 1.0, "state does not affect alignment")
        self.assertAlmostEqual(m["field_accuracy"]["state"], (self.G - k) / self.G)
        self.assertAlmostEqual(m["step_lenient"]["recall"], (self.G - k) / self.G)
        self.assertEqual(errs, k)

    def test_wrong_operation(self):
        p = clone()
        k = 0
        for rec in p.values():
            s = rec["steps"][0]
            same = [(op, st) for ph, op, st in OPERATION_TABLE if ph == s["phase"] and op != s["operation"]]
            s["operation"], s["state"] = same[0]
            rec["steps"] = canonical_sort(rec["steps"])
            k += 1
        m = scoring.score(GOLD, p)
        self.assertAlmostEqual(m["alignment_coverage"], (self.G - k) / self.G)
        self.assertAlmostEqual(m["step_lenient"]["recall"], (self.G - k) / self.G)
        self.assertAlmostEqual(m["step_lenient"]["precision"], (self.G - k) / self.G)

    def test_reorder_two_steps(self):
        p = clone()
        k = 0
        errs = 0
        for cid, rec in p.items():
            st = rec["steps"]
            if len(st) >= 2 and (st[0]["phase"], st[0]["operation"], st[0]["system_id"], st[0]["resource_id"]) != (
                st[1]["phase"], st[1]["operation"], st[1]["system_id"], st[1]["resource_id"]
            ):
                st[0], st[1] = st[1], st[0]
                renumber(st)
                k += 1
                errs += any("canonical order" in e for e in row_errors(cid, rec))
        m = scoring.score(GOLD, p)
        self.assertEqual(m["step_strict"]["f1"], 1.0, "reorder leaves the step multiset unchanged")
        self.assertAlmostEqual(m["sequence_exact_rate"], (self.N - k) / self.N)
        self.assertLess(m["sequence_mean_lcs"], 1.0)
        self.assertEqual(errs, k, "validator must flag every reordered case")

    def test_renumber_break(self):
        p = clone()
        errs = 0
        for cid, rec in p.items():
            for s in rec["steps"]:
                s["step_no"] += 1
            errs += any("step_no" in e for e in row_errors(cid, rec))
        m = scoring.score(GOLD, p)
        self.assertEqual(m["step_strict"]["f1"], 1.0)
        self.assertEqual(m["sequence_exact_rate"], 0.0)
        self.assertEqual(errs, self.N)

    def test_flip_status(self):
        p = clone()
        k = 0
        for rec in p.values():
            rec["status"] = "INCOMPLETE" if rec["status"] == "COMPLETE" else "COMPLETE"
            k += 1
        m = scoring.score(GOLD, p)
        self.assertEqual(m["status_accuracy"], 0.0)
        self.assertEqual(m["step_strict"]["f1"], 1.0, "steps untouched")

    def test_missing_case(self):
        p = clone()
        victim = sorted(p)[0]
        n_steps = len(p[victim]["steps"])
        del p[victim]
        m = scoring.score(GOLD, p)
        self.assertAlmostEqual(m["status_accuracy"], (self.N - 1) / self.N)
        self.assertAlmostEqual(m["step_strict"]["recall"], (self.G - n_steps) / self.G)
        self.assertEqual(m["confusion"][f"{GOLD[victim]['status']}->MISSING"], 1)


class NotApplicable(unittest.TestCase):
    def test_empty_arrays(self):
        g = {"c1": {"status": "NOT_APPLICABLE", "steps": []}}
        self.assertEqual(scoring.score(g, copy.deepcopy(g))["sequence_mean_lcs"], 1.0)
        self.assertEqual(validate_row("c1", "NOT_APPLICABLE", "[]"), [])
        self.assertTrue(validate_row("c1", "NOT_APPLICABLE", '[{"x":1}]'))
        wrong = {"c1": {"status": "INCOMPLETE", "steps": [{
            "step_no": 1, "phase": "FINDING", "system_id": "s", "resource_id": "r",
            "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "e"}]}}
        m = scoring.score(g, wrong)
        self.assertEqual(m["status_accuracy"], 0.0)
        self.assertEqual(m["step_strict"]["precision"], 0.0)


class ValidatorRules(unittest.TestCase):
    def test_status_rules(self):
        ver = {"step_no": 1, "phase": "VERIFICATION", "system_id": "a", "resource_id": "r",
               "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""}
        self.assertTrue(validate_row("c", "COMPLETE", json.dumps([ver])), "COMPLETE needs evidence")
        find = dict(ver, phase="FINDING", operation="REPORT_REMAINING_RECORD", state="PRESENT", evidence_id="e1")
        rem = dict(ver, step_no=2, phase="REMEDIATION", operation="DELETE_RECORD", state="ABSENT", evidence_id="e1")
        self.assertTrue(validate_row("c", "INCOMPLETE", json.dumps([find, rem])), "remediation must use empty evidence")
        self.assertTrue(validate_row("c", "COMPLETE", json.dumps([dict(find)])), "COMPLETE must be verification-only")

    def test_evidence_after_audit_is_rejected(self):
        ver = {"step_no": 1, "phase": "VERIFICATION", "system_id": "a", "resource_id": "r",
               "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": "evidence_9"}
        times = {"evidence_9": "2026-09-16T00:00:00Z"}
        errs = validate_row("c", "COMPLETE", json.dumps([ver]), audit_at="2026-09-15T12:00:00Z", evidence_time=times.get)
        self.assertTrue(any("after audit_at" in e for e in errs))
        self.assertEqual(validate_row("c", "COMPLETE", json.dumps([ver]), audit_at="2026-09-16T00:00:00Z", evidence_time=times.get), [],
                         "boundary is inclusive")
        self.assertTrue(any("does not exist" in e for e in validate_row("c", "COMPLETE", json.dumps([ver]),
                                                                       audit_at="2027-01-01T00:00:00Z", evidence_time={}.get)))

    def test_table_is_consistent(self):
        for ph, op, st in OPERATION_TABLE:
            self.assertEqual(OP_PHASE[op], ph)
            self.assertEqual(OP_STATE[op], st)


class ScoreCli(unittest.TestCase):
    """README regression: scoring the 518-case output against the 32 labeled samples compared disjoint case sets."""

    def _cli(self, pred, gold):
        import subprocess
        return subprocess.run([sys.executable, os.path.join(HERE, "main.py"), "score", "--pred", pred, "--gold", gold], capture_output=True, text=True)

    def test_disjoint_case_sets_are_an_error_not_a_score(self):
        repo = os.path.dirname(os.path.dirname(HERE))
        r = self._cli(os.path.join(repo, "dataset", "output.csv"), os.path.join(repo, "dataset", "sample_output.csv"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("share no case_id", r.stderr)
        self.assertIn("--requests sample_deletion_requests.csv", r.stderr)

    def test_identical_sets_score_normally(self):
        repo = os.path.dirname(os.path.dirname(HERE))
        gold = os.path.join(repo, "dataset", "sample_output.csv")
        r = self._cli(gold, gold)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
