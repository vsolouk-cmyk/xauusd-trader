from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pandas as pd

from app.stage73_asof_validation_bridge import run


def test_stage73_asof_validation_bridge_smoke():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data_dir = root / "data/macro_regime/normalized"
        data_dir.mkdir(parents=True)
        rows = []
        dates = pd.bdate_range("2023-01-02", periods=720)
        price = 1800.0
        for i, d in enumerate(dates):
            price *= 1.001 if i % 150 < 120 else 0.998
            rows.append({
                "feature_date_utc": d.strftime("%Y-%m-%d"),
                "gold_close": price,
                "gold_sma20_over_50": 0.01 if i in list(range(0, 120)) + list(range(260, 380)) + list(range(520, 640)) else -0.01,
                "dxy_ret_20d": 0.01 if i in list(range(0, 120)) + list(range(260, 380)) + list(range(520, 640)) else -0.01,
                "real_yield_change_20d": -0.01 if i in list(range(0, 120)) + list(range(260, 380)) + list(range(520, 640)) else 0.01,
                "dxy": 100.0,
                "real_yield": 1.0,
                "vix": 20.0,
                "etf_flow_tonnes_3m": 1.0,
                "central_bank_demand_tonnes_3m": 1.0,
            })
        pd.DataFrame(rows).to_csv(data_dir / "stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)
        cfg = {
            "macro_dataset_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "date_col": "feature_date_utc",
            "price_col": "gold_close",
            "as_of_date": "2024-01-01",
            "final_holdout_start": "2025-01-01",
            "replay_start": "2024-01-01",
            "replay_end": None,
            "horizon_trading_days": 60,
            "entry_cooldown_trading_days": 60,
            "cost_bps_total": 50.0,
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
            ],
            "compatibility_columns": ["gold_close", "dxy", "dxy_ret_20d", "real_yield", "real_yield_change_20d"],
            "decision_constraints": {
                "min_replay_rows": 100,
                "min_post_asof_matured_events": 1,
                "min_post_asof_mean_net_bps": -9999,
                "min_post_asof_win_rate": 0.0,
                "max_abs_post_asof_worst_loss_bps": 99999,
                "max_lookahead_violations": 0,
                "max_missing_feature_rows": 0,
                "max_mean_error_bps_for_no_caution": 99999
            },
        }
        cfg_path = root / "configs/stage73_asof_validation_bridge.json"
        cfg_path.parent.mkdir()
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        out = root / "reports/stage73"
        summary = run(root, cfg_path, out)
        assert summary["status"] == "STAGE73_COMPLETE_NO_PROMOTION"
        assert (out / "stage73_asof_validation_bridge_summary.json").exists()
        assert (out / "stage73_k06_asof_entry_returns.csv").exists()
        assert summary["historical_daily_replay"]["lookahead_violations"] == 0


if __name__ == "__main__":
    test_stage73_asof_validation_bridge_smoke()
    print("Stage73 tests passed")
