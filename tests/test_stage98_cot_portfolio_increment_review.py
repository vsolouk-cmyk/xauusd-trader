import json
import tempfile
from pathlib import Path

import pandas as pd

from app.stage98_cot_portfolio_increment_review import main


def test_stage98_selects_incremental_cot_candidate(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "configs").mkdir()
        (root / "reports/stage97_cot_positioning_hard_audit").mkdir(parents=True)
        (root / "data/macro_regime/normalized").mkdir(parents=True)
        (root / "data/external_frontiers").mkdir(parents=True)

        dates = pd.date_range("2020-01-01", periods=220, freq="D")
        macro = pd.DataFrame({
            "feature_date_utc": dates,
            "gold_close": range(1000, 1220),
            "gold_sma20_over_50": [-1.0] * 120 + [1.0] * 100,
            "dxy_ret_20d": [0.01] * 220,
            "dxy_sma20_over_50": [0.01] * 220,
            "real_yield_change_20d": [0.1] * 220,
            "vix_change_20d": [-1.0] * 220,
            "etf_flow_tonnes_3m": [10.0] * 220,
            "central_bank_demand_tonnes_3m": [10.0] * 220,
        })
        macro.to_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)

        cot = pd.DataFrame({
            "report_date_utc": dates[::7],
            "available_after_utc": dates[::7],
            "cot_mm_net_z": [0.0] * len(dates[::7]),
        })
        cot.to_csv(root / "data/external_frontiers/cot_positioning_normalized.csv", index=False)

        summary = {
            "disposition": "COT_HARD_AUDIT_SHORTLIST_READY_FOR_STAGE98_PORTFOLIO_REVIEW",
            "decision": "TEST",
        }
        (root / "reports/stage97_cot_positioning_hard_audit/stage97_cot_positioning_hard_audit_summary.json").write_text(json.dumps(summary), encoding="utf-8")

        selected = pd.DataFrame([
            {
                "rule_id": "C96_TEST",
                "label": "TEST",
                "condition_text": "cot_mm_net_z<1.0 AND central_bank_demand_tonnes_3m>0.0",
                "pass_cot_hard_audit_candidate": True,
                "cot_hard_audit_score": 6000.0,
                "final_holdout_mean_net_bps": 1500.0,
                "post_asof_mean_net_bps": 1600.0,
                "total_win_rate": 0.7,
            }
        ])
        selected.to_csv(root / "reports/stage97_cot_positioning_hard_audit/stage97_selected_for_stage98.csv", index=False)

        cfg = {
            "paths": {
                "stage97_summary": "reports/stage97_cot_positioning_hard_audit/stage97_cot_positioning_hard_audit_summary.json",
                "stage97_selected_csv": "reports/stage97_cot_positioning_hard_audit/stage97_selected_for_stage98.csv",
                "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
                "cot_dataset": "data/external_frontiers/cot_positioning_normalized.csv",
            },
            "columns": {"macro_date_col": "feature_date_utc"},
            "cot_default_lag_days": 3,
            "required_stage97_disposition": "COT_HARD_AUDIT_SHORTLIST_READY_FOR_STAGE98_PORTFOLIO_REVIEW",
            "constraints": {
                "max_additions": 2,
                "min_cot_hard_audit_score": 5000.0,
                "min_final_holdout_mean_bps": 1200.0,
                "min_post_asof_mean_bps": 1200.0,
                "min_total_win_rate": 0.60,
                "max_overlap_with_current_pct": 90.0,
                "min_incremental_union_active_days": 10,
                "max_pairwise_overlap_with_selected_addition_pct": 85.0,
            },
        }
        cfg_path = root / "configs/stage98_cot_portfolio_increment_review.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

        out = root / "reports/stage98_cot_portfolio_increment_review"
        monkeypatch.setattr("sys.argv", ["x", "--root", str(root), "--config", str(cfg_path), "--out", str(out)])
        assert main() == 0
        result = json.loads((out / "stage98_cot_portfolio_increment_review_summary.json").read_text())
        assert result["selected_count"] == 1
        assert result["selected_rule_ids"] == ["C96_TEST"]
        assert result["hard_blocks"]


def test_stage98_load_cot_no_errors_ignore_and_preserves_text(monkeypatch):
    from app.stage98_cot_portfolio_increment_review import load_cot
    import json
    import tempfile
    from pathlib import Path
    import pandas as pd

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data/external_frontiers").mkdir(parents=True)
        cot_path = root / "data/external_frontiers/cot_positioning_normalized.csv"
        pd.DataFrame({
            "report_date_utc": ["2024-01-02", "2024-01-09"],
            "available_after_utc": ["2024-01-05", "2024-01-12"],
            "cot_mm_net_z": ["0.5", "bad"],
            "text_note": ["keep_me", "also_keep"],
        }).to_csv(cot_path, index=False)
        cfg = {
            "paths": {"cot_dataset": "data/external_frontiers/cot_positioning_normalized.csv"},
            "cot_default_lag_days": 3,
        }
        df = load_cot(root, cfg)
        assert "cot_available_after_utc" in df.columns
        assert pd.api.types.is_numeric_dtype(df["cot_mm_net_z"])
        assert df["text_note"].tolist() == ["keep_me", "also_keep"]



def test_stage98_aliases_stage95_official_cot_columns():
    from app.stage98_cot_portfolio_increment_review import load_cot
    import tempfile
    from pathlib import Path
    import pandas as pd

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data/external_frontiers").mkdir(parents=True)
        cot_path = root / "data/external_frontiers/cot_positioning_normalized.csv"
        pd.DataFrame({
            "report_date_utc": ["2024-01-02", "2024-01-09", "2024-01-16"],
            "available_after_utc": ["2024-01-05", "2024-01-12", "2024-01-19"],
            "managed_money_net_pct_oi_z_156w": ["0.5", "0.7", "0.9"],
            "managed_money_net_pct_oi_change_4w": ["0.1", "0.2", "0.3"],
        }).to_csv(cot_path, index=False)
        cfg = {
            "paths": {"cot_dataset": "data/external_frontiers/cot_positioning_normalized.csv"},
            "cot_default_lag_days": 3,
        }
        df = load_cot(root, cfg)
        assert "cot_mm_net_z" in df.columns
        assert "cot_mm_net_z_change_4w" in df.columns
        assert df["cot_mm_net_z"].tolist() == [0.5, 0.7, 0.9]
        assert df["cot_mm_net_z_change_4w"].tolist() == [0.1, 0.2, 0.3]
