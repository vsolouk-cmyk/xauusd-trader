#!/usr/bin/env python3
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import pandas as pd
import numpy as np

def make_dataset(path: Path):
    dates = pd.bdate_range("2023-01-02", "2025-12-31")
    n = len(dates)
    close = np.linspace(1800, 2500, n)
    df = pd.DataFrame({
        "feature_date_utc": dates.strftime("%Y-%m-%d"),
        "gold_close": close,
        "gold_sma20_over_50": -1.0,
        "dxy_ret_20d": 1.0,
        "real_yield_change_20d": 1.0,
        "dxy": 100.0,
        "real_yield": 1.0,
        "vix": 20.0,
        "etf_flow_tonnes_3m": 1.0,
        "central_bank_demand_tonnes_3m": 1.0,
    })
    # K06 entries around known/pre-asof, post-asof, and final
    for idx in [5, 130, 300, 500]:
        if idx < n:
            df.loc[idx:idx+5, "gold_sma20_over_50"] = 1.0
            df.loc[idx:idx+5, "real_yield_change_20d"] = -1.0
    df.to_csv(path, index=False)

def main():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        macro_dir = root / "data/macro_regime/normalized"
        macro_dir.mkdir(parents=True)
        make_dataset(macro_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv")
        (root / "configs").mkdir()
        cfg = json.loads((repo / "configs/stage73b_corrected_asof_validation_bridge.json").read_text())
        cfg["as_of_date"] = "2024-01-01"
        cfg["final_holdout_start"] = "2025-01-01"
        cfg["horizon_trading_days"] = 20
        cfg["entry_cooldown_trading_days"] = 20
        cfg["decision_constraints"]["min_replay_rows"] = 100
        cfg["decision_constraints"]["min_post_plus_final_matured_events"] = 1
        (root / "configs/stage73b_corrected_asof_validation_bridge.json").write_text(json.dumps(cfg))
        cmd = [
            sys.executable,
            str(repo / "app/stage73b_corrected_asof_validation_bridge.py"),
            "--root", str(root),
            "--config", "configs/stage73b_corrected_asof_validation_bridge.json",
            "--out", "reports/stage73b",
        ]
        subprocess.check_call(cmd)
        summary = json.loads((root / "reports/stage73b/stage73b_corrected_asof_validation_bridge_summary.json").read_text())
        assert summary["status"] == "STAGE73B_COMPLETE_NO_PROMOTION"
        assert summary["historical_daily_replay"]["lookahead_violations"] == 0
        assert summary["historical_daily_replay"]["missing_required_feature_rows"] == 0
        assert "MISSING_REQUIRED_FEATURE_ROWS_PRESENT" not in summary["hard_failures"]
        print("Stage73B tests passed")

if __name__ == "__main__":
    main()
