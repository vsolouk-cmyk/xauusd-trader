#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def build_dataset(path: Path) -> None:
    dates = pd.bdate_range("2011-01-03", periods=900)
    n = len(dates)
    idx = pd.Series(range(n), dtype=float)
    df = pd.DataFrame({
        "feature_date_utc": dates.strftime("%Y-%m-%d"),
        "gold_close": 1200 + idx * 0.8 + 20 * (idx % 37 == 0),
        "dxy": 100 - idx * 0.01 + (idx % 53) * 0.01,
        "real_yield": 2.0 - idx * 0.002,
        "vix": 15 + (idx % 40) * 0.05,
        "etf_flow_tonnes_3m": 10 + (idx % 80) * 0.5,
        "central_bank_demand_tonnes_3m": 20 + (idx % 90) * 0.4,
    })
    # Create a late orthogonal active pocket with eventual gains.
    df.loc[500:750, "gold_close"] = 1500 + (pd.Series(range(251)) * 1.5).to_numpy()
    df.loc[450:750, "dxy"] = 96 - (pd.Series(range(301)) * 0.03).to_numpy()
    df.loc[450:750, "real_yield"] = 1.0 - (pd.Series(range(301)) * 0.003).to_numpy()
    df.loc[450:750, "etf_flow_tonnes_3m"] = 60
    df.loc[450:750, "central_bank_demand_tonnes_3m"] = 70
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def main() -> None:
    pkg_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        shutil.copytree(pkg_root / "app", root / "app")
        shutil.copytree(pkg_root / "configs", root / "configs")
        (root / "reports/stage83_orthogonal_thesis_discovery_expansion").mkdir(parents=True)
        macro_path = root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        build_dataset(macro_path)
        stage83_summary = {
            "decision": "STAGE83_ORTHOGONAL_DISCOVERY_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER",
            "shortlist_rule_ids": [
                "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
                "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
                "S83_22_GOLD_60D_PULLBACK_CB_SUPPORT_H120",
                "S83_21_GOLD_60D_PULLBACK_ETF_SUPPORT_H120",
                "S83_24_REALYIELD_120D_DOWN_CB_SUPPORT_GOLD_PULLBACK_H120",
                "S83_23_DXY_120D_DOWN_ETF_SUPPORT_GOLD_PULLBACK_H120",
                "S83_16_CB_DEMAND_CHANGE_POS_GOLD_PULLBACK_H60",
                "S83_05_RISKOFF_GOLD_PULLBACK_H60",
            ],
        }
        (root / "reports/stage83_orthogonal_thesis_discovery_expansion/stage83_orthogonal_thesis_discovery_expansion_summary.json").write_text(json.dumps(stage83_summary), encoding="utf-8")
        result = subprocess.run([
            sys.executable,
            str(root / "app/stage84_hard_audit_stage83_orthogonal_shortlist.py"),
            "--root", str(root),
            "--config", str(root / "configs/stage84_hard_audit_stage83_orthogonal_shortlist.json"),
            "--out", str(root / "reports/stage84_hard_audit_stage83_orthogonal_shortlist"),
        ], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr + result.stdout
        summary_path = root / "reports/stage84_hard_audit_stage83_orthogonal_shortlist/stage84_hard_audit_stage83_orthogonal_shortlist_summary.json"
        metrics_path = root / "reports/stage84_hard_audit_stage83_orthogonal_shortlist/stage84_hard_audit_metrics.csv"
        selected_path = root / "reports/stage84_hard_audit_stage83_orthogonal_shortlist/stage84_selected_for_stage85.csv"
        assert summary_path.exists()
        assert metrics_path.exists()
        assert selected_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["status"] == "STAGE84_COMPLETE_NO_PROMOTION"
        assert "NO_ORDER_AUTHORIZATION_FROM_STAGE84" in summary["hard_blocks"]
        metrics = pd.read_csv(metrics_path)
        assert set(["rule_id", "pass_hard_audit_candidate", "hard_fail_reasons"]).issubset(metrics.columns)
        print("Stage84 tests passed")


if __name__ == "__main__":
    main()
