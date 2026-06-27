#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_stage105_smoke(tmp_path: Path) -> None:
    root = tmp_path
    (root / "data/macro_regime/normalized").mkdir(parents=True)
    (root / "data/external_frontiers").mkdir(parents=True)
    dates = pd.bdate_range("2011-01-03", periods=900, tz="UTC")
    macro = pd.DataFrame({
        "date_utc": dates.date.astype(str),
        "gold_close": [1000 + i * 0.8 for i in range(len(dates))],
        "gold_ret_20d": [-0.02 if i % 40 < 20 else 0.03 for i in range(len(dates))],
        "real_yield_change_20d": [-0.1 if i % 50 < 25 else 0.2 for i in range(len(dates))],
        "dxy_ret_20d": [-0.01 if i % 60 < 30 else 0.02 for i in range(len(dates))],
        "dxy_ret_120d": [-0.03 if i % 80 < 40 else 0.04 for i in range(len(dates))],
        "gold_sma20_over_50": [0.1 if i % 70 < 35 else -0.1 for i in range(len(dates))],
        "dxy_sma20_over_50": [-0.1 if i % 90 < 45 else 0.1 for i in range(len(dates))],
        "vix_change_20d": [1.0 if i % 55 < 27 else -1.0 for i in range(len(dates))],
        "real_yield_change_120d": [-0.2 if i % 100 < 50 else 0.3 for i in range(len(dates))],
        "central_bank_demand_tonnes_3m": [10.0 if i % 65 < 32 else -10.0 for i in range(len(dates))],
        "etf_flow_tonnes_3m": [5.0 if i % 75 < 37 else -5.0 for i in range(len(dates))],
    })
    macro.to_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)

    cot_dates = pd.date_range("2011-01-04", periods=180, freq="W-TUE", tz="UTC")
    cot = pd.DataFrame({
        "report_date_utc": cot_dates.date.astype(str),
        "available_after_utc": (cot_dates + pd.Timedelta(days=3)).date.astype(str),
        "managed_money_net_pct_oi_z_156w": [0.5 if i % 5 else -1.2 for i in range(len(cot_dates))],
        "managed_money_net_pct_oi_change_4w": [-0.2 if i % 4 else 0.4 for i in range(len(cot_dates))],
    })
    cot.to_csv(root / "data/external_frontiers/cot_positioning_normalized.csv", index=False)

    pkg_root = Path(__file__).resolve().parents[1]
    cfg = json.loads((pkg_root / "configs/stage105_second_order_cot_macro_thesis_discovery.json").read_text())
    cfg["constraints"]["min_post_asof_entries"] = 0
    cfg["constraints"]["min_post_asof_mean_bps"] = -999999
    cfg["constraints"]["min_final_holdout_entries"] = 0
    cfg["constraints"]["min_final_holdout_mean_bps"] = -999999
    cfg["constraints"]["min_incremental_union_active_days"] = 0
    cfg_path = root / "config.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    out = root / "reports/stage105"
    subprocess.check_call([
        sys.executable,
        str(pkg_root / "app/stage105_second_order_cot_macro_thesis_discovery.py"),
        "--root", str(root),
        "--config", str(cfg_path),
        "--out", str(out),
    ])
    summary = json.loads((out / "stage105_second_order_cot_macro_thesis_discovery_summary.json").read_text())
    assert summary["status"] == "STAGE105_COMPLETE_NO_PROMOTION"
    assert summary["candidate_count"] == 12
    assert summary["data_join"]["lookahead_violations"] == 0
    assert (out / "stage105_second_order_cot_macro_candidate_metrics.csv").exists()


if __name__ == "__main__":
    test_stage105_smoke(Path("/tmp/stage105_smoke_test"))
    print("Stage105 tests passed")
