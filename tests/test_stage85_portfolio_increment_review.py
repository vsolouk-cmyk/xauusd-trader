#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        src = Path(__file__).resolve().parents[1] / "app" / "stage85_portfolio_increment_review.py"
        (root / "app" / "stage85_portfolio_increment_review.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        cfg = {
            "stage77b_summary_relpath": "reports/stage77b/summary.json",
            "stage84_summary_relpath": "reports/stage84/summary.json",
            "macro_dataset_relpath": "data/macro.csv",
            "date_col": "feature_date_utc",
            "price_col": "gold_close",
            "max_additions": 2,
            "max_overlap_with_current_pct": 35.0,
            "min_incremental_union_active_days": 5,
            "min_hard_audit_score": 1000.0,
            "min_final_holdout_mean_bps": 500.0,
            "min_post_plus_final_mean_bps": 500.0,
            "min_total_win_rate": 0.55,
        }
        write_json(root / "config.json", cfg)

        write_json(root / "reports/stage77b/summary.json", {
            "selected_rule_ids": [
                "K06_RESILIENT_GOLD_VS_DXY_H120",
                "K03_SAFE_HAVEN_REALYIELD_H120",
                "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
            ]
        })
        write_json(root / "reports/stage84/summary.json", {
            "selected_for_stage85": [
                {
                    "rule_id": "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
                    "hard_audit_score": 4000.0,
                    "final_holdout_mean_net_bps": 1500.0,
                    "post_plus_final_mean_net_bps": 1600.0,
                    "total_win_rate": 0.62,
                    "total_mean_net_bps": 500.0,
                },
                {
                    "rule_id": "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
                    "hard_audit_score": 3900.0,
                    "final_holdout_mean_net_bps": 1400.0,
                    "post_plus_final_mean_net_bps": 1500.0,
                    "total_win_rate": 0.66,
                    "total_mean_net_bps": 450.0,
                },
            ]
        })

        n = 260
        dates = pd.date_range("2020-01-01", periods=n, freq="B")
        # Create deterministic feature regimes with low overlap between current and candidate rules.
        df = pd.DataFrame({
            "feature_date_utc": dates.strftime("%Y-%m-%d"),
            "gold_close": [1800 + i for i in range(n)],
            "dxy": [100 - 0.02 * i for i in range(n)],
            "real_yield": [1.0 - 0.004 * i for i in range(n)],
            "vix": [20 + (i % 7) for i in range(n)],
            "etf_flow_tonnes_3m": [1.0 for _ in range(n)],
            "central_bank_demand_tonnes_3m": [1.0 for _ in range(n)],
            "gold_sma20_over_50": [0.02 if i < 120 else -0.02 for i in range(n)],
            "dxy_ret_20d": [0.01 if i < 80 else -0.01 for i in range(n)],
            "real_yield_change_20d": [-0.01 if i < 80 else 0.01 for i in range(n)],
            "vix_change_20d": [0.5 if 40 <= i < 90 else -0.5 for i in range(n)],
            "dxy_sma20_over_50": [-0.01 if i < 100 else 0.01 for i in range(n)],
            "real_yield_change_120d": [None if i < 120 else -0.2 for i in range(n)],
            "dxy_ret_120d": [None if i < 120 else -0.05 for i in range(n)],
        })
        (root / "data").mkdir()
        df.to_csv(root / "data/macro.csv", index=False)

        out = root / "reports/stage85"
        result = subprocess.run(
            [sys.executable, str(root / "app/stage85_portfolio_increment_review.py"),
             "--root", str(root), "--config", str(root / "config.json"), "--out", str(out)],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        summary = json.loads((out / "stage85_portfolio_increment_review_summary.json").read_text())
        assert summary["status"] == "STAGE85_COMPLETE_NO_PROMOTION"
        assert "NO_ORDER_AUTHORIZATION_FROM_STAGE85" in summary["hard_blocks"]
        assert (out / "stage85_portfolio_increment_review.csv").exists()
        assert (out / "stage85_selected_for_stage86.csv").exists()
        print("Stage85 tests passed")


if __name__ == "__main__":
    main()
