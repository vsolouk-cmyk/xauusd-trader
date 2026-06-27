import json
import tempfile
from pathlib import Path
import pandas as pd

from app.stage97_cot_positioning_hard_audit import main


def test_stage97_hard_audit_selects_clean_cot_candidate():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "reports/stage96_cot_positioning_thesis_discovery").mkdir(parents=True)
        (root / "configs").mkdir()
        (root / "out").mkdir()

        summary = {
            "decision": "STAGE96_COT_THESIS_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER",
            "classification": "S96_COT_DISCOVERY_SHORTLIST_READY",
            "disposition": "COT_THESIS_SHORTLIST_READY_FOR_STAGE97_HARD_AUDIT",
            "cot_dataset": {"normalized_rows": 808},
            "lookahead_violations": 0,
            "residual_only": True,
        }
        (root / "reports/stage96_cot_positioning_thesis_discovery/stage96_cot_positioning_thesis_discovery_summary.json").write_text(json.dumps(summary), encoding="utf-8")

        rows = [
            {
                "rule_id": "C96_TEST_PASS",
                "label": "TEST_PASS",
                "pass_cot_discovery_candidate": True,
                "missing_required_feature_rows": 0,
                "warmup_missing_rows_ignored": 259,
                "lookahead_violations": 0,
                "total_entry_count": 18,
                "total_mean_net_bps": 750.0,
                "total_median_net_bps": 200.0,
                "total_win_rate": 0.66,
                "total_min_net_return_bps": -1700.0,
                "validation_entry_count": 6,
                "validation_mean_net_bps": 50.0,
                "locked_forward_entry_count": 5,
                "locked_forward_mean_net_bps": 650.0,
                "final_holdout_entry_count": 4,
                "final_holdout_mean_net_bps": 2500.0,
                "post_asof_entry_count": 3,
                "post_asof_mean_net_bps": 3000.0,
                "max_year_entry_share": 0.12,
                "incremental_union_active_days": 500,
                "overlap_with_current_union_pct": 62.0,
            },
            {
                "rule_id": "C96_TEST_FAIL",
                "label": "TEST_FAIL",
                "pass_cot_discovery_candidate": True,
                "missing_required_feature_rows": 0,
                "lookahead_violations": 0,
                "total_entry_count": 4,
                "total_mean_net_bps": 900.0,
                "total_median_net_bps": 200.0,
                "total_win_rate": 0.70,
                "total_min_net_return_bps": -500.0,
                "validation_entry_count": 1,
                "validation_mean_net_bps": 50.0,
                "locked_forward_entry_count": 1,
                "locked_forward_mean_net_bps": 650.0,
                "final_holdout_entry_count": 1,
                "final_holdout_mean_net_bps": 2500.0,
                "post_asof_entry_count": 1,
                "post_asof_mean_net_bps": 3000.0,
                "max_year_entry_share": 0.12,
                "incremental_union_active_days": 500,
                "overlap_with_current_union_pct": 10.0,
            },
        ]
        pd.DataFrame(rows).to_csv(root / "reports/stage96_cot_positioning_thesis_discovery/stage96_cot_thesis_shortlist.csv", index=False)

        cfg = {"max_selected_for_stage98": 3}
        (root / "configs/stage97_cot_positioning_hard_audit.json").write_text(json.dumps(cfg), encoding="utf-8")

        rc = main([
            "--root", str(root),
            "--config", "configs/stage97_cot_positioning_hard_audit.json",
            "--out", "out"
        ])
        assert rc == 0
        out_summary = json.loads((root / "out/stage97_cot_positioning_hard_audit_summary.json").read_text())
        assert out_summary["decision"] == "STAGE97_COT_HARD_AUDIT_SHORTLIST_READY_FOR_PORTFOLIO_REVIEW_NO_ORDER"
        assert out_summary["selected_rule_ids"] == ["C96_TEST_PASS"]
        metrics = pd.read_csv(root / "out/stage97_cot_hard_audit_metrics.csv")
        assert metrics.loc[metrics["rule_id"] == "C96_TEST_PASS", "pass_cot_hard_audit_candidate"].iloc[0] == True


if __name__ == "__main__":
    test_stage97_hard_audit_selects_clean_cot_candidate()
    print("Stage97 tests passed")
