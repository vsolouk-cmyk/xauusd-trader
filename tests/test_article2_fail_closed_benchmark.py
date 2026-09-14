from __future__ import annotations

import copy
import unittest

from app import article2_fail_closed_benchmark as m


class Article2BenchmarkTests(unittest.TestCase):
    def test_three_arms_are_frozen(self):
        self.assertEqual(
            m.ARMS,
            (
                "NAIVE_LATEST_STATE",
                "POINT_IN_TIME_FAIL_OPEN",
                "POINT_IN_TIME_PROVENANCE_FAIL_CLOSED",
            ),
        )

    def test_fault_matrix_is_bounded_and_unique(self):
        ids = [item.fault_id for item in m.FAULTS]
        self.assertEqual(len(ids), 12)
        self.assertEqual(len(ids), len(set(ids)))

    def test_clean_fixture_is_accepted_by_every_arm(self):
        fixture = m.base_fixture()
        for arm in m.ARMS:
            with self.subTest(arm=arm):
                result = m.evaluate_arm(arm, fixture, "CLEAN", False)
                self.assertTrue(result.accepted)
                self.assertFalse(result.detected)

    def test_each_fault_is_isolated_and_full_arm_blocks_it(self):
        clean = m.base_fixture()
        for spec in m.FAULTS:
            with self.subTest(fault=spec.fault_id):
                corrupted = m.apply_fault(clean, spec.fault_id)
                self.assertEqual(clean, m.base_fixture(), "fault injection mutated the frozen clean fixture")
                result = m.evaluate_arm(m.ARMS[2], corrupted, spec.fault_id, True)
                self.assertFalse(result.accepted)
                self.assertTrue(result.detected)
                self.assertIn(spec.expected_check, result.reasons)

    def test_naive_arm_silently_accepts_faults(self):
        clean = m.base_fixture()
        for spec in m.FAULTS:
            result = m.evaluate_arm(m.ARMS[0], m.apply_fault(clean, spec.fault_id), spec.fault_id, True)
            self.assertTrue(result.accepted)
            self.assertFalse(result.detected)

    def test_point_in_time_fail_open_never_blocks(self):
        clean = m.base_fixture()
        for spec in m.FAULTS:
            result = m.evaluate_arm(m.ARMS[1], m.apply_fault(clean, spec.fault_id), spec.fault_id, True)
            self.assertTrue(result.accepted)

    def test_manifest_tamper_is_hash_detected(self):
        result = m.evaluate_arm(m.ARMS[2], m.apply_fault(m.base_fixture(), "MANIFEST_TAMPER"), "MANIFEST_TAMPER", True)
        self.assertEqual(result.reasons, ("DATA_HASH_BINDING",))

    def test_config_tamper_is_hash_detected(self):
        result = m.evaluate_arm(m.ARMS[2], m.apply_fault(m.base_fixture(), "CONFIG_TAMPER"), "CONFIG_TAMPER", True)
        self.assertIn("CONFIG_HASH_BINDING", result.reasons)

    def test_cost_corruption_is_economic_not_hash_failure(self):
        result = m.evaluate_arm(m.ARMS[2], m.apply_fault(m.base_fixture(), "COST_CONTRACT_CORRUPTION"), "COST", True)
        self.assertEqual(result.reasons, ("COST_IDENTITY",))

    def test_duplicate_and_off_grid_faults_have_distinct_reasons(self):
        duplicate = m.evaluate_arm(m.ARMS[2], m.apply_fault(m.base_fixture(), "DUPLICATE_BAR"), "DUP", True)
        off_grid = m.evaluate_arm(m.ARMS[2], m.apply_fault(m.base_fixture(), "OFF_GRID_BAR"), "GRID", True)
        self.assertIn("BAR_TIMESTAMP_UNIQUENESS", duplicate.reasons)
        self.assertNotIn("BAR_GRID_ALIGNMENT", duplicate.reasons)
        self.assertIn("BAR_GRID_ALIGNMENT", off_grid.reasons)
        self.assertNotIn("BAR_TIMESTAMP_UNIQUENESS", off_grid.reasons)

    def test_benchmark_is_deterministic(self):
        first = m.run_benchmark(repeats=2)
        second = m.run_benchmark(repeats=2)
        self.assertEqual(first["deterministic_digest_sha256"], second["deterministic_digest_sha256"])

    def test_full_arm_meets_frozen_gate(self):
        benchmark = m.run_benchmark(repeats=2)
        passed, reasons = m.article2_gate(benchmark)
        self.assertTrue(passed, reasons)
        full = benchmark["metrics"][m.ARMS[2]]
        self.assertEqual(full["fault_detection_rate"], 1.0)
        self.assertEqual(full["unsafe_acceptance_rate"], 0.0)
        self.assertEqual(full["false_blocking_rate"], 0.0)

    def test_no_execution_connector(self):
        self.assertTrue(m.no_execution_connector_tokens())


if __name__ == "__main__":
    unittest.main()

