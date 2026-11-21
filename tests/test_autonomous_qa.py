"""Tests the QA loop's discovery, diagnosis, control replay and fail-closed behavior."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "tools" / "autonomous_qa.py"
spec = importlib.util.spec_from_file_location("autonomous_qa", path)
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class QALoopTests(unittest.TestCase):
    def test_discovers_controls_and_generates_six_plans(self):
        discovery = qa.discover(qa.SYNTHETIC_HTML)
        self.assertEqual(len(discovery["plans"]), 6)
        self.assertEqual(set(discovery["identified_controls"]),
                         {"heading", "email", "buy", "health", "admin", "orders"})

    def test_absent_control_fails_closed(self):
        html = qa.SYNTHETIC_HTML.replace('id="buy"', 'id="removed"')
        with self.assertRaisesRegex(ValueError, "UI controls missing"):
            qa.execute(html, ("checkout",))

    def test_unknown_contract_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown contract"):
            qa.execute(qa.SYNTHETIC_HTML, ("unknown",))

    def test_one_fault_diagnosed_without_claiming_repair(self):
        result = qa.execute(qa.SYNTHETIC_HTML, ("auth_bypass",))
        self.assertEqual(result["detected"], 1)
        self.assertEqual(result["false_positive_controls"], 0)
        row = result["results"][0]
        self.assertTrue(row["before"]["detected"])
        self.assertFalse(row["control_replay"]["detected"])
        self.assertEqual(row["before"]["diagnosis"]["code"], "UNAUTHORIZED_ACCESS")
        self.assertFalse(row["repair_verified"])
        self.assertFalse(row["before"]["diagnosis"]["patch_applied"])

    def test_full_loop_detects_all_six_without_false_positives(self):
        result = qa.execute(qa.SYNTHETIC_HTML)
        self.assertEqual(result["detected"], 6)
        self.assertEqual(result["false_positive_controls"], 0)
        self.assertEqual(result["patches_applied"], 0)
        self.assertFalse(result["repair_verified"])
        self.assertEqual(result["vendor_calls"], 0)


if __name__ == "__main__":
    unittest.main()
