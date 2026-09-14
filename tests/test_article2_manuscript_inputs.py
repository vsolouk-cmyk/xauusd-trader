from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "article_publication" / "build_article2_manuscript_inputs.py"
SPEC = importlib.util.spec_from_file_location("article2_manuscript_inputs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Article2ManuscriptInputsTests(unittest.TestCase):
    def evidence(self, root: Path) -> Path:
        target = root / "artifacts" / "article2" / "article2_evidence_v1"
        target.mkdir(parents=True)
        source = ROOT / "artifacts" / "article2" / "article2_evidence_v1"
        for name in (
            "article2_decision.json", "article2_benchmark_summary.json", "article2_coverage_summary.json",
            "article2_reproducibility_report.json", "article2_existing_core_regression_summary.json",
            "article2_unit_test_summary.json", "article2_core_adapter_results.json", "article2_environment.json",
        ):
            (target / name).write_bytes((source / name).read_bytes())
        return target

    def run_build(self, root: Path) -> dict:
        return MODULE.build(
            root,
            root / "artifacts/article2/article2_evidence_v1",
            root / "artifacts/article2/article2_manuscript_v1",
            root / "artifacts/article2/XAUUSD_ARTICLE2_MANUSCRIPT_INPUTS_V1.zip",
        )

    def test_builds_expected_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.evidence(root)
            result = self.run_build(root)
            self.assertEqual(result["decision"], "ARTICLE2_MANUSCRIPT_INPUTS_READY")
            self.assertEqual(result["files"], 11)
            self.assertTrue((root / result["zip"]).is_file())

    def test_snapshot_preserves_frozen_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.evidence(root)
            self.run_build(root)
            snapshot = json.loads((root / "artifacts/article2/article2_manuscript_v1/article2_results_snapshot.json").read_text())
            self.assertEqual(snapshot["benchmark"]["fault_count"], 12)
            self.assertEqual(snapshot["verification"]["tests_total"], 44)
            self.assertAlmostEqual(snapshot["verification"]["scoped_line_coverage_rate"], 0.9593908629441624)

    def test_rebuild_is_deterministic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.evidence(root)
            first = self.run_build(root)["zip_sha256"]
            second = self.run_build(root)["zip_sha256"]
            self.assertEqual(first, second)

    def test_blocks_nonpassing_source_decision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = self.evidence(root)
            path = evidence / "article2_decision.json"
            payload = json.loads(path.read_text())
            payload["decision"] = "BLOCK_ARTICLE2"
            payload["pass"] = False
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "not ARTICLE2_EVIDENCE_SUFFICIENT"):
                self.run_build(root)


if __name__ == "__main__":
    unittest.main()
