#!/usr/bin/env python3
import json, tempfile, unittest, subprocess, sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "stage66g_controlled_paper_order_readiness.py"

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")

class Stage66GTests(unittest.TestCase):
    def make_root(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "reports/stage66c_h64l_paper_execution_simulator").mkdir(parents=True)
        (root / "reports/stage65b_forward_shadow_daily_ops").mkdir(parents=True)
        (root / "configs").mkdir()
        cfg = {
            "stage66c_summary_path": "reports/stage66c_h64l_paper_execution_simulator/stage66c_h64l_paper_execution_simulator_summary.json",
            "stage65_summary_path": "reports/stage65b_forward_shadow_daily_ops/stage65b_forward_shadow_daily_ops_summary.json",
            "allowed_stage66c_decisions": ["PASS_FAST_PAPER_EXECUTION_SIM_BAND_B_NO_ORDER"],
            "thresholds": {
                "base_band_name": "B_base", "min_closed_positions": 8,
                "pass_fast_min_win_rate": 0.55, "pass_fast_min_mean_net_bps": 300.0,
                "pass_fast_min_stress_mean_net_bps": 200.0, "stress_gate_penalty_bps": 100.0,
                "pass_fast_max_base_band_drawdown_pct": 8.0, "kill_if_single_trade_loss_bps_lt": -2200.0,
                "max_year_trade_share": 0.35, "small_size_min_win_rate": 0.50,
                "small_size_min_mean_net_bps": 150.0
            },
            "paper_design": {"sizing": {"A_micro": 0.02, "B_conservative": 0.05, "B_base": 0.10},
                              "operational_gates": {"fresh_h64l_v2_signal_required": True}}
        }
        write_json(root / "configs/stage66g_controlled_paper_order_readiness.json", cfg)
        return td, root

    def test_pass_fast_design(self):
        td, root = self.make_root()
        with td:
            s66c = {"decision": "PASS_FAST_PAPER_EXECUTION_SIM_BAND_B_NO_ORDER", "metrics": {
                "position_stats": {"trade_count": 13, "win_rate": 0.69, "mean_net_return_bps": 507.0,
                                   "min_net_return_bps": -1148.0, "max_year_trade_share": 0.23},
                "sizing_band_stats": [{"band": "B_base", "max_drawdown_pct": -2.2}],
                "stress_cost_stats": [{"round_trip_total_penalty_bps": 100.0, "mean_net_return_bps": 457.0}]}}
            write_json(root / "reports/stage66c_h64l_paper_execution_simulator/stage66c_h64l_paper_execution_simulator_summary.json", s66c)
            write_json(root / "reports/stage65b_forward_shadow_daily_ops/stage65b_forward_shadow_daily_ops_summary.json", {"latest_signal_state": {"signal_active": "False"}})
            subprocess.check_call([sys.executable, str(SCRIPT), "--root", str(root), "--config", "configs/stage66g_controlled_paper_order_readiness.json", "--out", "reports/stage66g"])
            out = json.loads((root / "reports/stage66g/stage66g_controlled_paper_order_readiness_summary.json").read_text())
            self.assertEqual(out["decision"], "CONTROLLED_PAPER_ORDER_READINESS_DESIGN_BAND_B_NO_ORDER")
            self.assertFalse(out["readiness_design"]["paper_order_is_authorized"])

    def test_fail_bad_decision(self):
        td, root = self.make_root()
        with td:
            write_json(root / "reports/stage66c_h64l_paper_execution_simulator/stage66c_h64l_paper_execution_simulator_summary.json", {"decision": "FAIL_PAPER_EXECUTION_SIM_NO_ORDER", "metrics": {"position_stats": {}}})
            subprocess.check_call([sys.executable, str(SCRIPT), "--root", str(root), "--config", "configs/stage66g_controlled_paper_order_readiness.json", "--out", "reports/stage66g"])
            out = json.loads((root / "reports/stage66g/stage66g_controlled_paper_order_readiness_summary.json").read_text())
            self.assertEqual(out["decision"], "STOP_OR_STAGE66D_REQUIRED_NO_ORDER")

    def test_signal_active_arms_design_only(self):
        td, root = self.make_root()
        with td:
            s66c = {"decision": "PASS_FAST_PAPER_EXECUTION_SIM_BAND_B_NO_ORDER", "metrics": {
                "position_stats": {"trade_count": 13, "win_rate": 0.7, "mean_net_return_bps": 500, "min_net_return_bps": -1000, "max_year_trade_share": 0.2},
                "sizing_band_stats": [{"band": "B_base", "max_drawdown_pct": -2.0}],
                "stress_cost_stats": [{"round_trip_total_penalty_bps": 100.0, "mean_net_return_bps": 450}]}}
            write_json(root / "reports/stage66c_h64l_paper_execution_simulator/stage66c_h64l_paper_execution_simulator_summary.json", s66c)
            write_json(root / "reports/stage65b_forward_shadow_daily_ops/stage65b_forward_shadow_daily_ops_summary.json", {"latest_signal_state": {"signal_active": "True"}})
            subprocess.check_call([sys.executable, str(SCRIPT), "--root", str(root), "--config", "configs/stage66g_controlled_paper_order_readiness.json", "--out", "reports/stage66g"])
            out = json.loads((root / "reports/stage66g/stage66g_controlled_paper_order_readiness_summary.json").read_text())
            self.assertTrue(out["readiness_design"]["armed_now"])
            self.assertFalse(out["readiness_design"]["paper_order_is_authorized"])

if __name__ == "__main__":
    unittest.main()
