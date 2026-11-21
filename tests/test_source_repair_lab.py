"""Regression tests for actual source changes applied only in a disposable workspace."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools" / "source_repair_lab.py"
spec = importlib.util.spec_from_file_location("source_repair_lab", PATH)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class SourceRepairTests(unittest.TestCase):
    def test_exact_anchor_must_be_unique(self):
        with self.assertRaisesRegex(ValueError, "expected one source anchor"):
            lab.guarded_substitution("abc abc", "abc", "def")
        with self.assertRaisesRegex(ValueError, "expected one source anchor"):
            lab.guarded_substitution("xyz", "abc", "def")

    def test_source_patch_has_distinct_hash_and_fixed_guard(self):
        original = lab.FIXTURE.read_text(encoding="utf-8")
        vulnerable = lab.inject_vulnerability(original)
        patch = lab.propose_patch(vulnerable)
        self.assertTrue(patch["modified_source"])
        self.assertNotEqual(patch["before_sha256"], patch["after_sha256"])
        self.assertIn('if authorized else 403,', patch["source"])
        self.assertNotIn(lab.VULNERABLE_GUARD, patch["source"])
        self.assertNotIn(lab.VULNERABLE_PAYLOAD, patch["source"])

    def test_repair_of_real_temporary_python_source(self):
        result = lab.repair_lab()
        self.assertFalse(result["before_contracts"]["auth_bypass"])
        self.assertTrue(all(result["after_contracts"].values()), result)
        self.assertTrue(result["verified"])
        self.assertFalse(result["production_modified"])
        self.assertNotEqual(result["vulnerable_sha256"], result["patched_sha256"])

    def test_denies_arbitrary_external_file(self):
        with self.assertRaisesRegex(ValueError, "only repository"):
            lab.repair_lab(Path(__file__))


if __name__ == "__main__":
    unittest.main()
