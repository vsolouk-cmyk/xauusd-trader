from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.stage112_vol_risk_premium_rotation_frontier_discovery import main


def test_stage112_runs_and_persists_splits(tmp_path: Path) -> None:
    root = tmp_path
    data_dir = root / "data" / "macro_regime" / "normalized"
    data_dir.mkdir(parents=True)
    rows = []
    dates = pd.date_range("2018-01-01", periods=420, freq="B", tz="UTC")
    price = 1300.0
    for i, dt in enumerate(dates):
        price *= 1.0 + (0.0007 if (i % 17) < 9 else -0.0002)
        rows.append({
            "date_utc": dt.date().isoformat(),
            "gold_close": price,
            "gold_ret_20d": (i % 41) - 20,
            "gold_ret_60d": (i % 67) - 33,
            "gold_sma20_over_50": ((i % 29) - 14) / 100.0,
            "gold_sma50_over_200": ((i % 37) - 18) / 100.0,
            "dxy_ret_20d": 20 - (i % 41),
            "dxy_ret_60d": 33 - (i % 67),
            "dxy_ret_120d": 50 - (i % 101),
            "real_yield_change_20d": (i % 31) - 15,
            "real_yield_change_60d": (i % 43) - 21,
            "real_yield_change_120d": (i % 59) - 29,
            "vix_change_20d": (i % 53) - 26,
            "vix_ret_20d": (i % 53) - 26,
            "central_bank_demand_tonnes_3m": 50 + (i % 23),
        })
    pd.DataFrame(rows).to_csv(data_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)
    (root / "configs").mkdir()
    (root / "configs" / "stage112_vol_risk_premium_rotation_frontier_discovery.json").write_text(json.dumps({
        "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "horizon_trading_days": 20,
        "min_selection_events": 2,
        "min_validation_events": 1,
        "min_tail_forward_events": 1,
        "max_year_concentration": 1.0
    }), encoding="utf-8")

    rc = main(["--root", str(root), "--out", "reports/stage112_test"])
    assert rc == 0
    out = root / "reports" / "stage112_test"
    summary = json.loads((out / "stage112_vol_risk_premium_rotation_frontier_discovery_summary.json").read_text())
    assert summary["stage"] == "Stage112_VOL_RISK_PREMIUM_ROTATION_FRONTIER_DISCOVERY"
    assert summary["generated_candidate_count"] == 8
    assert (out / "splits" / "stage112_selection_rows.csv").exists()
    assert (out / "splits" / "stage112_validation_rows.csv").exists()
    assert (out / "splits" / "stage112_tail_forward_proxy_rows.csv").exists()
    assert (out / "splits" / "stage112_split_manifest.json").exists()
