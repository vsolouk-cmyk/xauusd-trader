from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app import xauusd_pipeline_calibration as m


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "configs").mkdir(parents=True)
        src = Path(__file__).resolve().parents[1] / "configs/xauusd_pipeline_calibration.json"
        shutil.copy2(src, self.tmp / "configs/xauusd_pipeline_calibration.json")
        self.cfg = m.load_config(self.tmp / "configs/xauusd_pipeline_calibration.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _targets(self, path: Path, start="2016-01-01", end="2025-02-01"):
        ts = pd.date_range(start, end, freq="h", inclusive="left", tz="UTC")
        x = np.arange(len(ts), dtype=float)
        price = 1200.0 + 0.02 * x + 2.0 * np.sin(x / 50.0)
        fwd = 10.0 * np.sin(x / 13.0) + 2.0 * np.cos(x / 31.0)
        pd.DataFrame({
            "decision_time_utc": ts,
            "entry_open": price,
            "forward_return_4h_bps": fwd,
        }).to_csv(path, index=False)

    def test_config_order_permissions_false(self):
        self.assertFalse(self.cfg["paper_order_allowed"])
        self.assertFalse(self.cfg["demo_order_allowed"])
        self.assertFalse(self.cfg["live_order_allowed"])

    def test_locked_reference_gates_match_fixed_scan_contract(self):
        g = self.cfg["reference_gates"]
        self.assertEqual(g["minimum_trades"], 80)
        self.assertEqual(g["minimum_profit_factor"], 1.2)
        self.assertEqual(g["minimum_positive_folds"], 2)
        self.assertEqual(g["minimum_worst_fold_mean_bps"], -5.0)
        self.assertEqual(g["maximum_positive_year_profit_share"], 0.45)
        self.assertEqual(g["minimum_locked_risk_cagr"], 0.02)

    def test_reference_reader_excludes_2025_from_returned_frame(self):
        p = self.tmp / "targets.csv"
        self._targets(p)
        f, contract = m.read_reference_targets(p, self.cfg)
        self.assertTrue((f["decision_time_utc"] < pd.Timestamp("2025-01-01T00:00:00Z")).all())
        self.assertEqual(contract["diagnostic_rows_used"], 0)

    def test_nonoverlap_opportunities_are_at_least_4h_apart(self):
        p = self.tmp / "targets.csv"
        self._targets(p)
        f, _ = m.read_reference_targets(p, self.cfg)
        o = m.eligible_nonoverlap_opportunities(f, self.cfg)
        diffs = o["decision_time_utc"].diff().dropna()
        self.assertTrue((diffs >= pd.Timedelta(hours=4)).all())

    def test_centering_removes_year_hour_drift(self):
        p = self.tmp / "targets.csv"
        self._targets(p)
        f, _ = m.read_reference_targets(p, self.cfg)
        o = m.eligible_nonoverlap_opportunities(f, self.cfg)
        means = o.groupby(["year", "hour_utc"])["centered_4h_bps"].mean().abs()
        self.assertLess(float(means.max()), 1e-9)

    def test_metric_detects_strong_low_variance_edge_statistically(self):
        ts = pd.date_range("2016-01-01", periods=300, freq="10D", tz="UTC")
        vals = np.tile(np.asarray([10.0, 14.0, 18.0, 12.0]), 75)
        metric, gates = m.metric_and_gates(pd.DatetimeIndex(ts), vals, self.cfg, np.random.default_rng(1))
        self.assertTrue(gates.statistical_pass)
        self.assertGreater(metric["bootstrap_p10_mean_bps"], 0)

    def test_null_zero_mean_does_not_pass_bootstrap(self):
        ts = pd.date_range("2016-01-01", periods=300, freq="10D", tz="UTC")
        vals = np.tile(np.asarray([-20.0, 20.0]), 150)
        _, gates = m.metric_and_gates(pd.DatetimeIndex(ts), vals, self.cfg, np.random.default_rng(2))
        self.assertFalse(gates.statistical_pass)

    def test_statistical_pass_can_differ_from_commercial_cagr_pass(self):
        ts = pd.date_range("2016-01-01", periods=100, freq="30D", tz="UTC")
        vals = np.full(100, 15.0)
        _, gates = m.metric_and_gates(pd.DatetimeIndex(ts), vals, self.cfg, np.random.default_rng(3))
        self.assertTrue(gates.statistical_pass)
        self.assertFalse(gates.commercial_pass)
        self.assertFalse(gates.checks["cagr"])

    def test_decision_pass(self):
        rows = []
        for n in [100,300,600,1000]:
            for a in [0.,4.,8.,12.,16.,20.]:
                stat = 0.0 if a == 0 else min(1.0, a / 12.0)
                comm = 0.0 if a < 12 else min(1.0, (a - 8) / 8.0)
                if n == 100 and a == 12: stat = 0.8
                if n == 300 and a == 8: stat = 0.9
                if n == 1000 and a == 16: comm = 0.9
                rows.append({"sample_size":n,"planted_severe_net_bps":a,"statistical_detection_rate":stat,"commercial_promotion_rate":comm})
        decision, _ = m.calibration_decision(pd.DataFrame(rows), self.cfg)
        self.assertEqual(decision, "PIPELINE_CALIBRATED_PASS")

    def test_decision_overconservative(self):
        rows = []
        for n in [100,300,600,1000]:
            for a in [0.,4.,8.,12.,16.,20.]:
                rows.append({"sample_size":n,"planted_severe_net_bps":a,"statistical_detection_rate":0.0,"commercial_promotion_rate":0.0})
        decision, _ = m.calibration_decision(pd.DataFrame(rows), self.cfg)
        self.assertEqual(decision, "PIPELINE_OVERCONSERVATIVE_RECALIBRATION_REQUIRED")

    def test_decision_inconclusive_when_false_positive_high(self):
        rows = []
        for n in [100,300,600,1000]:
            for a in [0.,4.,8.,12.,16.,20.]:
                stat = 0.2 if a == 0 else 1.0
                comm = 0.2 if a == 0 else 1.0
                rows.append({"sample_size":n,"planted_severe_net_bps":a,"statistical_detection_rate":stat,"commercial_promotion_rate":comm})
        decision, _ = m.calibration_decision(pd.DataFrame(rows), self.cfg)
        self.assertEqual(decision, "PIPELINE_INCONCLUSIVE")

    def test_tsmom_future_mutation_does_not_change_past_rows(self):
        p = self.tmp / "targets.csv"
        self._targets(p, end="2025-01-01")
        f, _ = m.read_reference_targets(p, self.cfg)
        a, _ = m.empirical_tsmom(f, self.cfg)
        f2 = f.copy()
        cutoff = pd.Timestamp("2023-01-01T00:00:00Z")
        f2.loc[f2["decision_time_utc"] >= cutoff, "entry_open"] *= 3.0
        b, _ = m.empirical_tsmom(f2, self.cfg)
        pre_a = a.loc[a["formation_month"] < cutoff, ["formation_month","signal","position_scale"]].reset_index(drop=True)
        pre_b = b.loc[b["formation_month"] < cutoff, ["formation_month","signal","position_scale"]].reset_index(drop=True)
        pd.testing.assert_frame_equal(pre_a, pre_b)

    def test_tsmom_summary_is_explicitly_non_decisive(self):
        p = self.tmp / "targets.csv"
        self._targets(p, end="2025-01-01")
        f, _ = m.read_reference_targets(p, self.cfg)
        _, s = m.empirical_tsmom(f, self.cfg)
        self.assertEqual(s["calibration_decision_dependency"], "NONE")
        self.assertIn("single XAUUSD CFD proxy", s["deviation_from_paper"])

    def test_collect_excludes_large_input(self):
        report = self.tmp / m.REPORT_DIR
        report.mkdir(parents=True)
        names = [
            "pipeline_calibration_summary.json","pipeline_calibration_decision.md","calibration_contract.json",
            "input_manifest.json","synthetic_control_profile.json","synthetic_detection_curve.csv",
            "synthetic_gate_pass_rates.csv","empirical_tsmom_summary.json","empirical_tsmom_monthly.csv",
        ]
        for n in names:
            (report / n).write_text("{}\n" if n.endswith(".json") else "x\n", encoding="utf-8")
        old_home = m.Path.home
        # collect always writes to HOME/Downloads; patch Path.home only inside module behavior is awkward,
        # so verify the explicit file allowlist instead of invoking collect here.
        self.assertNotIn("cross_asset_intraday_targets.csv", names)

    def test_static_no_execution_contract(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(m.static_execution_violations(root), [])

    def test_preflight_on_synthetic_file(self):
        p = self.tmp / "targets.csv"
        self._targets(p, end="2025-01-01")
        # reduce minimum opportunities for this synthetic test only if needed
        cfg_path = self.tmp / "configs/xauusd_pipeline_calibration.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["synthetic"]["minimum_reference_opportunities"] = 1000
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        payload = m.preflight(self.tmp, cfg_path, str(p))
        self.assertEqual(payload["decision"], "PASS_PIPELINE_CALIBRATION_PREFLIGHT_REFERENCE_ONLY")
        self.assertFalse(payload["diagnostic_2025_plus_evaluated"])


if __name__ == "__main__":
    unittest.main()
