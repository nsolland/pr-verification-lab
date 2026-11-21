"""Standard-library unit tests for strict benchmark comparison, no network calls."""
import importlib.util
import pathlib
import unittest

MODULE = pathlib.Path(__file__).resolve().parents[1] / "tools" / "compare_functional_e2e.py"
spec = importlib.util.spec_from_file_location("compare_functional_e2e", MODULE)
compare_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_module)


def report(name, missing=None, spurious=None):
    missing = set(missing or ())
    spurious = set(spurious or ())
    return {"runner": name,
            "cases": [
                {"case": case, "injected": injected,
                 "detected": (case not in missing) if injected else (case in spurious)}
                for case in sorted(compare_module.FAULTS)
                for injected in (False, True)]}


class ComparisonTests(unittest.TestCase):
    def test_incremental_detection(self):
        result = compare_module.compare(
            report("baseline", missing={"checkout", "persistence"}),
            report("candidate", missing={"persistence"}, spurious={"validation"}))
        self.assertEqual(result["additional_true_positives"], ["checkout"])
        self.assertEqual(result["regressions"], [])
        self.assertEqual(result["candidate_false_positives"], ["validation"])
        self.assertEqual(result["baseline"]["true_positives"], 4)
        self.assertEqual(result["candidate"]["true_positives"], 5)
        self.assertFalse(result["verified_e2e"])

    def test_reject_missing_and_duplicates(self):
        example = report("candidate")
        for bad in (dict(example, cases=example["cases"][:-1]),
                    dict(example, cases=example["cases"][:-1] + [example["cases"][0]])):
            with self.assertRaises(ValueError):
                compare_module.validate(bad)

    def test_no_positive_does_not_divide_by_zero(self):
        result = compare_module.metrics(report("empty", missing=compare_module.FAULTS))
        self.assertIsNone(result["precision"])
        self.assertEqual(result["recall"], 0)


if __name__ == "__main__":
    unittest.main()
