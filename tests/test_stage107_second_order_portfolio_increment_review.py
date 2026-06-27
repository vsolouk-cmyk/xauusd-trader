from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from app.stage107_second_order_portfolio_increment_review import main


def test_stage107_smoke(tmp_path: Path):
    root = tmp_path
    (root / "reports/stage106_second_order_cot_macro_hard_audit").mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(parents=True, exist_ok=True)

    summary = {
        "decision": "STAGE106_SECOND_ORDER_HARD_AUDIT_READY_FOR_PORTFOLIO_REVIEW_NO_ORDER",
        "selected_rule_ids": ["S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120"],
        "current_unified_portfolio_rule_ids": ["K06", "K03", "K07", "S83_14", "S83_13", "C96_07"],
        "selected_for_stage107": [{"current_union_active_days_recomputed": 1987}]
    }
    (root / "reports/stage106_second_order_cot_macro_hard_audit/stage106_second_order_cot_macro_hard_audit_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    selected_csv = root / "reports/stage106_second_order_cot_macro_hard_audit/stage106_selected_for_stage107.csv"
    fields = [
        "rule_id", "label", "bucket", "condition_text", "second_order_hard_audit_score",
        "total_entry_count", "total_mean_net_bps", "total_win_rate", "total_min_net_return_bps",
        "locked_forward_entry_count", "locked_forward_mean_net_bps",
        "final_holdout_entry_count", "final_holdout_mean_net_bps",
        "post_asof_entry_count", "post_asof_mean_net_bps", "max_year_entry_share",
        "missing_required_feature_rows", "lookahead_violations",
        "candidate_active_days_recomputed", "incremental_union_active_days_recomputed",
        "overlap_with_current_union_pct_recomputed"
    ]
    with selected_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow({
            "rule_id": "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120",
            "label": "COT_DECROWDING_CB_SUPPORT_RY_RELIEF",
            "bucket": "cot_flow_interaction",
            "condition_text": "cot_mm_net_z_change_4w<0.0 AND central_bank_demand_tonnes_3m>0.0 AND real_yield_change_20d<0.0",
            "second_order_hard_audit_score": "7807.1342",
            "total_entry_count": "28",
            "total_mean_net_bps": "421.0365",
            "total_win_rate": "0.5714",
            "total_min_net_return_bps": "-1598.1892",
            "locked_forward_entry_count": "7",
            "locked_forward_mean_net_bps": "606.1549",
            "final_holdout_entry_count": "5",
            "final_holdout_mean_net_bps": "2136.0759",
            "post_asof_entry_count": "4",
            "post_asof_mean_net_bps": "2517.1354",
            "max_year_entry_share": "0.1071",
            "missing_required_feature_rows": "0",
            "lookahead_violations": "0",
            "candidate_active_days_recomputed": "836",
            "incremental_union_active_days_recomputed": "301",
            "overlap_with_current_union_pct_recomputed": "63.9952",
        })

    config = {
        "stage106_summary_path": "reports/stage106_second_order_cot_macro_hard_audit/stage106_second_order_cot_macro_hard_audit_summary.json",
        "stage106_selected_csv_path": "reports/stage106_second_order_cot_macro_hard_audit/stage106_selected_for_stage107.csv",
        "constraints": {
            "max_additions": 1,
            "min_second_order_hard_audit_score": 7000.0,
            "min_total_entries": 10,
            "min_total_mean_net_bps": 300.0,
            "min_total_win_rate": 0.55,
            "max_abs_worst_loss_bps": 2200.0,
            "min_locked_forward_entries": 2,
            "min_locked_forward_mean_bps": 300.0,
            "min_final_holdout_entries": 2,
            "min_final_holdout_mean_bps": 1500.0,
            "min_post_asof_entries": 2,
            "min_post_asof_mean_bps": 1500.0,
            "max_year_entry_share": 0.30,
            "max_missing_required_feature_rows": 0,
            "max_lookahead_violations": 0,
            "min_candidate_active_days": 150,
            "min_incremental_union_active_days": 250,
            "max_overlap_with_current_pct": 75.0
        }
    }
    cfg_path = root / "configs/stage107_second_order_portfolio_increment_review.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    out = root / "reports/stage107_second_order_portfolio_increment_review"
    rc = main(["--root", str(root), "--config", str(cfg_path), "--out", str(out)])
    assert rc == 0
    result = json.loads((out / "stage107_second_order_portfolio_increment_review_summary.json").read_text(encoding="utf-8"))
    assert result["status"] == "STAGE107_COMPLETE_NO_PROMOTION"
    assert result["selected_count"] == 1
    assert "NO_PAPER_ORDER" in result["hard_blocks"]


if __name__ == "__main__":
    tmp = Path("/tmp/stage107_smoke_test")
    if tmp.exists():
        shutil.rmtree(tmp)
    test_stage107_smoke(tmp)
    print("Stage107 tests passed")
