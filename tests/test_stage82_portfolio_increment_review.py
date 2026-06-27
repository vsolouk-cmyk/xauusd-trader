#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        src_app = Path(__file__).resolve().parents[1] / "app" / "stage82_portfolio_increment_review.py"
        dst_app = root / "app" / "stage82_portfolio_increment_review.py"
        dst_app.write_text(src_app.read_text(encoding="utf-8"), encoding="utf-8")

        cfg_dir = root / "configs"
        cfg_dir.mkdir()
        out_dir = root / "reports" / "stage82_portfolio_increment_review"
        macro_dir = root / "data" / "macro_regime" / "normalized"
        macro_dir.mkdir(parents=True)

        # Build synthetic daily macro dataset with enough rows for 60d features.
        n = 180
        dates = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
        df = pd.DataFrame({
            "feature_date_utc": dates.strftime("%Y-%m-%d"),
            "gold_close": [1500 + i * 2 for i in range(n)],
            "dxy": [100 - i * 0.05 for i in range(n)],
            "real_yield": [1.0 - i * 0.01 for i in range(n)],
            "gold_sma20_over_50": [0.1] * n,
            "dxy_ret_20d": [0.02 if i < 60 else -0.02 for i in range(n)],
            "real_yield_change_20d": [-0.05] * n,
            "dxy_sma20_over_50": [-0.01] * n,
            "vix_change_20d": [1.0 if i % 3 else -1.0 for i in range(n)],
            "central_bank_demand_tonnes_3m": [10.0] * n,
            "etf_flow_tonnes_3m": [5.0 if i % 2 else -5.0 for i in range(n)],
        })
        df.to_csv(macro_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)

        write_json(root / "reports" / "stage77b_corrected_portfolio_candidate_selection_historical_asof" / "stage77b_corrected_portfolio_candidate_selection_historical_asof_summary.json", {
            "disposition": "PORTFOLIO_READY_WITH_K06_PLUS_COMPLEMENTS",
            "selected_rule_ids": [
                "K06_RESILIENT_GOLD_VS_DXY_H120",
                "K03_SAFE_HAVEN_REALYIELD_H120",
                "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
            ],
        })
        write_json(root / "reports" / "stage81b_corrected_hard_audit_stage80_shortlist" / "stage81b_corrected_hard_audit_stage80_shortlist_summary.json", {
            "disposition": "HARD_AUDIT_SHORTLIST_READY_FOR_PORTFOLIO_REVIEW",
            "selected_for_stage82": [
                {
                    "rule_id": "S80_31_DXY_60D_RELIEF_CB_SUPPORT_H120",
                    "label": "SIXTY_DAY_DXY_RELIEF_WITH_CB_SUPPORT",
                    "pass_hard_audit_candidate": True,
                    "hard_audit_score": 4356.0,
                    "final_holdout_mean_net_bps": 1731.0,
                    "post_plus_final_mean_net_bps": 1731.0,
                    "total_win_rate": 0.64,
                    "total_mean_net_return_bps": 558.0,
                    "locked_forward_mean_net_bps": 720.0,
                    "total_min_net_return_bps": -1105.0,
                },
                {
                    "rule_id": "S80_33_DXY_60D_RELIEF_ETF_SUPPORT_H120",
                    "label": "SIXTY_DAY_DXY_RELIEF_WITH_ETF_SUPPORT",
                    "pass_hard_audit_candidate": True,
                    "hard_audit_score": 3628.0,
                    "final_holdout_mean_net_bps": 1586.0,
                    "post_plus_final_mean_net_bps": 1586.0,
                    "total_win_rate": 0.5926,
                    "total_mean_net_return_bps": 489.0,
                    "locked_forward_mean_net_bps": 531.0,
                    "total_min_net_return_bps": -1105.0,
                },
            ],
        })
        write_json(cfg_dir / "stage82_portfolio_increment_review.json", {
            "max_additions": 2,
            "max_overlap_with_current_pct": 100.0,
            "max_pairwise_addition_overlap_pct": 100.0,
            "min_hard_audit_score": 3000.0,
            "min_final_holdout_mean_bps": 1000.0,
            "min_post_plus_final_mean_bps": 1000.0,
            "min_total_win_rate": 0.55,
            "min_incremental_union_active_days": 1,
        })

        result = subprocess.run(
            [sys.executable, str(dst_app), "--root", str(root), "--config", "configs/stage82_portfolio_increment_review.json", "--out", str(out_dir.relative_to(root))],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        summary = json.loads((out_dir / "stage82_portfolio_increment_review_summary.json").read_text(encoding="utf-8"))
        assert summary["status"].startswith("STAGE82_COMPLETE_NO_PROMOTION"), summary
        assert "NO_ORDER_AUTHORIZATION_FROM_STAGE82" in summary["hard_blocks"]
        assert (out_dir / "stage82_portfolio_increment_review.csv").exists()
        assert (out_dir / "stage82_pairwise_overlap_review.csv").exists()
        assert (out_dir / "stage82_latest_signal_snapshot.csv").exists()
    print("Stage82 tests passed")


if __name__ == "__main__":
    main()
