#!/usr/bin/env python3
import json
import tempfile
import subprocess
import sys
from pathlib import Path


def test_stage66e_runs_on_synthetic_pass_fast():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "configs").mkdir()
        (root / "reports/stage66d_limited_complementary_thesis_scan").mkdir(parents=True)
        (root / "reports/stage66h_no_broker_dry_run_ticket_generator").mkdir(parents=True)
        (root / "data/macro_regime/normalized").mkdir(parents=True)

        src = Path(__file__).resolve().parents[1] / "app/stage66e_complementary_shortlist_audit.py"
        dst = root / "app/stage66e_complementary_shortlist_audit.py"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        cfg_src = Path(__file__).resolve().parents[1] / "configs/stage66e_complementary_shortlist_audit.json"
        (root / "configs/stage66e_complementary_shortlist_audit.json").write_text(cfg_src.read_text(encoding="utf-8"), encoding="utf-8")

        stage66d = {
            "decision": "STAGE66D_PASS_FAST_COMPLEMENTARY_SHORTLIST_NO_ORDER",
            "execution_model": {"entry_rule": "x", "position_mode": "single_position_non_overlapping", "round_trip_execution_cost_bps": 35.0, "feed_mismatch_penalty_bps": 15.0, "total_penalty_bps": 50.0},
            "top_ranked_results": [{
                "classification": "PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER",
                "thesis_id": "D3_DOLLAR_RELIEF_TREND_CONTINUATION_LONG",
                "horizon_trading_days": 60,
                "hypothesis": "synthetic",
                "conditions": [
                    {"field": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                    {"field": "dxy_sma20_over_50", "operator": "<", "threshold": 0.0},
                    {"field": "dxy_ret_20d", "operator": "<", "threshold": 0.0}
                ],
                "diagnostics": {"active_rows": 100, "closed_positions": 33, "skipped_overlap": 67, "lookahead_breaches": 0},
                "position_stats": {
                    "trade_count": 33,
                    "mean_net_return_bps": 201.0,
                    "win_rate": 0.61,
                    "min_net_return_bps": -1000.0,
                    "max_year_trade_share": 0.12,
                    "payoff_ratio_win_mean_abs_loss_mean": 1.3,
                    "sizing_band_stats": [{"band": "D_base", "max_drawdown_pct": -2.7}]
                }
            }]
        }
        (root / "reports/stage66d_limited_complementary_thesis_scan/stage66d_limited_complementary_thesis_scan_summary.json").write_text(json.dumps(stage66d), encoding="utf-8")
        (root / "reports/stage66h_no_broker_dry_run_ticket_generator/stage66h_no_broker_dry_run_ticket_generator_summary.json").write_text(json.dumps({"decision":"WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET"}), encoding="utf-8")
        (root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv").write_text(
            "feature_date_utc,sample_available_after_utc,gold_sma20_over_50,dxy_sma20_over_50,dxy_ret_20d\n"
            "2026-01-01,2026-01-02T00:00:00Z,1,-1,-1\n",
            encoding="utf-8"
        )
        r = subprocess.run([sys.executable, str(dst), "--root", str(root)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr + r.stdout
        out = json.loads((root / "reports/stage66e_complementary_shortlist_audit/stage66e_complementary_shortlist_audit_summary.json").read_text())
        assert out["classification"] == "E_PASS_FAST_SIGNAL_ACTIVE_DESIGN_READY"
        assert (root / "configs/stage66e_selected_complementary_rule_lock.json").exists()


def test_stage66e_gate_fails_on_wrong_top_candidate():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "configs").mkdir()
        (root / "reports/stage66d_limited_complementary_thesis_scan").mkdir(parents=True)
        (root / "data/macro_regime/normalized").mkdir(parents=True)
        src = Path(__file__).resolve().parents[1] / "app/stage66e_complementary_shortlist_audit.py"
        dst = root / "app/stage66e_complementary_shortlist_audit.py"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        cfg_src = Path(__file__).resolve().parents[1] / "configs/stage66e_complementary_shortlist_audit.json"
        (root / "configs/stage66e_complementary_shortlist_audit.json").write_text(cfg_src.read_text(encoding="utf-8"), encoding="utf-8")
        stage66d = {"decision":"STAGE66D_PASS_FAST_COMPLEMENTARY_SHORTLIST_NO_ORDER","top_ranked_results":[{"classification":"PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER","thesis_id":"OTHER","horizon_trading_days":60}]}
        (root / "reports/stage66d_limited_complementary_thesis_scan/stage66d_limited_complementary_thesis_scan_summary.json").write_text(json.dumps(stage66d), encoding="utf-8")
        r = subprocess.run([sys.executable, str(dst), "--root", str(root)], capture_output=True, text=True)
        assert r.returncode == 0
        out = json.loads((root / "reports/stage66e_complementary_shortlist_audit/stage66e_complementary_shortlist_audit_summary.json").read_text())
        assert out["classification"] == "E_FAIL_OR_REVIEW"


if __name__ == "__main__":
    test_stage66e_runs_on_synthetic_pass_fast()
    test_stage66e_gate_fails_on_wrong_top_candidate()
    print("Stage66E tests passed")
