#!/usr/bin/env python3
from pathlib import Path
import json
import tempfile
import pandas as pd
import subprocess
import sys

def test_stage106_smoke():
    with tempfile.TemporaryDirectory(prefix="stage106_smoke_") as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "configs").mkdir()
        (root / "reports/stage105_second_order_cot_macro_thesis_discovery").mkdir(parents=True)
        (root / "data/macro_regime/normalized").mkdir(parents=True)
        (root / "data/external_frontiers").mkdir(parents=True)

        # 500 daily rows, enough for active-day recomputation.
        dates = pd.date_range("2024-01-01", periods=500, freq="D", tz="UTC")
        macro = pd.DataFrame({
            "date_utc": dates.strftime("%Y-%m-%d"),
            "gold_close": [2000 + i for i in range(500)],
            "gold_sma20_over_50": [-1.0] * 500,
            "dxy_ret_20d": [1.0] * 500,
            "real_yield_change_20d": [-1.0] * 500,
            "vix_change_20d": [-1.0] * 500,
            "dxy_sma20_over_50": [1.0] * 500,
            "real_yield_change_120d": [1.0] * 500,
            "gold_ret_20d": [-1.0] * 500,
            "dxy_ret_120d": [1.0] * 500,
            "central_bank_demand_tonnes_3m": [10.0] * 500,
        })
        macro.to_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)

        cot_dates = pd.date_range("2023-12-15", periods=80, freq="7D", tz="UTC")
        cot = pd.DataFrame({
            "report_date_utc": cot_dates.strftime("%Y-%m-%d"),
            "available_after_utc": (cot_dates + pd.Timedelta(days=4)).strftime("%Y-%m-%d"),
            "managed_money_net_pct_oi_z_156w": [0.5] * 80,
            "managed_money_net_pct_oi_change_4w": [-0.2] * 80,
        })
        cot.to_csv(root / "data/external_frontiers/cot_positioning_normalized.csv", index=False)

        summary = {
            "decision": "STAGE105_SECOND_ORDER_COT_MACRO_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER",
            "shortlist_rule_ids": ["S105_TEST"],
            "current_union_active_days": 0
        }
        (root / "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_thesis_discovery_summary.json").write_text(json.dumps(summary))

        row = {
            "rule_id": "S105_TEST",
            "label": "TEST",
            "bucket": "test",
            "horizon_trading_days": 120,
            "cooldown_trading_days": 120,
            "condition_text": "cot_mm_net_z_change_4w<0.0 AND central_bank_demand_tonnes_3m>0.0 AND real_yield_change_20d<0.0",
            "missing_columns": "",
            "warmup_missing_rows_ignored": 0,
            "missing_required_feature_rows": 0,
            "raw_active_days": 400,
            "residual_active_days": 250,
            "current_union_active_days": 0,
            "current_union_active_days_after_candidate": 250,
            "incremental_union_active_days": 250,
            "overlap_with_current_union_days": 0,
            "overlap_with_current_union_pct": 0,
            "total_entry_count": 20,
            "total_mean_net_bps": 500,
            "total_median_net_bps": 400,
            "total_win_rate": 0.65,
            "total_min_net_return_bps": -900,
            "total_max_net_return_bps": 2500,
            "total_total_net_return_bps": 10000,
            "train_entry_count": 4,
            "train_mean_net_bps": 10,
            "train_win_rate": 0.5,
            "validation_entry_count": 4,
            "validation_mean_net_bps": 50,
            "validation_win_rate": 0.5,
            "locked_forward_entry_count": 4,
            "locked_forward_mean_net_bps": 500,
            "locked_forward_win_rate": 0.75,
            "final_holdout_entry_count": 4,
            "final_holdout_mean_net_bps": 1500,
            "final_holdout_win_rate": 1.0,
            "post_asof_entry_count": 3,
            "post_asof_mean_net_bps": 1600,
            "post_asof_win_rate": 1.0,
            "max_entry_year": 2024,
            "max_year_entry_share": 0.10,
            "pass_second_order_discovery_candidate": True,
            "fail_reasons": "",
            "second_order_discovery_score": 1000,
            "lookahead_violations": 0,
        }
        pd.DataFrame([row]).to_csv(root / "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_shortlist.csv", index=False)
        pd.DataFrame([row]).to_csv(root / "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_candidate_metrics.csv", index=False)

        cfg = {
            "paths": {
                "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
                "cot_dataset": "data/external_frontiers/cot_positioning_normalized.csv",
                "stage105_summary": "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_thesis_discovery_summary.json",
                "stage105_shortlist": "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_shortlist.csv",
                "stage105_candidate_metrics": "reports/stage105_second_order_cot_macro_thesis_discovery/stage105_second_order_cot_macro_candidate_metrics.csv",
            },
            "constraints": {
                "min_total_entries": 10,
                "min_total_mean_net_bps": 250,
                "min_total_win_rate": 0.55,
                "max_abs_worst_loss_bps": 2200,
                "min_locked_forward_entries": 2,
                "min_locked_forward_mean_bps": 300,
                "min_final_holdout_entries": 2,
                "min_final_holdout_mean_bps": 1200,
                "min_post_asof_entries": 2,
                "min_post_asof_mean_bps": 1200,
                "max_year_entry_share": 0.30,
                "max_missing_required_feature_rows": 0,
                "max_lookahead_violations": 0,
                "min_candidate_active_days": 150,
                "min_incremental_union_active_days_recomputed": 150,
                "max_overlap_with_current_pct_recomputed": 80,
            }
        }
        cfg_path = root / "configs/stage106_second_order_cot_macro_hard_audit.json"
        cfg_path.write_text(json.dumps(cfg))

        script_path = Path(__file__).resolve().parents[1] / "app/stage106_second_order_cot_macro_hard_audit.py"
        # In installed repo script is under root/app, in package test script is under package/app.
        if not script_path.exists():
            script_path = Path.cwd() / "app/stage106_second_order_cot_macro_hard_audit.py"

        subprocess.check_call([
            sys.executable, str(script_path),
            "--root", str(root),
            "--config", str(cfg_path),
            "--out", str(root / "reports/stage106_second_order_cot_macro_hard_audit"),
        ])

        out = json.loads((root / "reports/stage106_second_order_cot_macro_hard_audit/stage106_second_order_cot_macro_hard_audit_summary.json").read_text())
        assert out["status"] == "STAGE106_COMPLETE_NO_PROMOTION"
        assert out["candidate_count"] == 1

if __name__ == "__main__":
    test_stage106_smoke()
    print("Stage106 tests passed")
