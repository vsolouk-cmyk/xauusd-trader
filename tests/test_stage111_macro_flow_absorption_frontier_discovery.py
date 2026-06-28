import json
import tempfile
from pathlib import Path

import pandas as pd

from app.stage111_macro_flow_absorption_frontier_discovery import load_config, run


def test_stage111_smoke_generates_outputs():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data/macro_regime/normalized").mkdir(parents=True)
        (root / "data/external_frontiers").mkdir(parents=True)
        dates = pd.bdate_range("2011-01-03", periods=900)
        # Synthetic upward gold with waves; enough valid H120 outcomes.
        gold = [1000 + i * 0.8 + (i % 40 - 20) * 0.5 for i in range(len(dates))]
        macro = pd.DataFrame({
            "date_utc": dates.strftime("%Y-%m-%d"),
            "gold_close": gold,
            "gold_ret_20d": pd.Series(gold).pct_change(20),
            "gold_ret_60d": pd.Series(gold).pct_change(60),
            "gold_sma20_over_50": pd.Series(gold).rolling(20).mean() / pd.Series(gold).rolling(50).mean() - 1.0,
            "gold_sma50_over_200": pd.Series(gold).rolling(50).mean() / pd.Series(gold).rolling(200).mean() - 1.0,
            "dxy_ret_20d": [0.01 if i % 90 < 45 else -0.01 for i in range(len(dates))],
            "dxy_ret_60d": [0.02 if i % 120 < 60 else -0.02 for i in range(len(dates))],
            "dxy_ret_120d": [0.03 if i % 150 < 75 else -0.03 for i in range(len(dates))],
            "dxy_sma20_over_50": [0.01 if i % 100 < 50 else -0.01 for i in range(len(dates))],
            "real_yield_change_20d": [0.05 if i % 70 < 35 else -0.05 for i in range(len(dates))],
            "real_yield_change_60d": [0.10 if i % 110 < 55 else -0.10 for i in range(len(dates))],
            "real_yield_change_120d": [0.15 if i % 160 < 80 else -0.15 for i in range(len(dates))],
            "vix_change_20d": [2.0 if i % 80 < 40 else -2.0 for i in range(len(dates))],
            "gold_etf_flow_tonnes_20d": [5.0 if i % 60 < 30 else -5.0 for i in range(len(dates))],
            "gold_etf_flow_tonnes_60d": [10.0 if i % 90 < 45 else -10.0 for i in range(len(dates))],
            "central_bank_demand_tonnes_3m": [20.0 if i % 100 < 70 else -20.0 for i in range(len(dates))],
        })
        macro.to_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)
        cot_dates = pd.bdate_range("2011-01-04", periods=130, freq="W-TUE")
        cot = pd.DataFrame({
            "report_date_utc": cot_dates.strftime("%Y-%m-%d"),
            "available_after_utc": (cot_dates + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
            "cot_mm_net_z": [0.2 if i % 6 else 1.2 for i in range(len(cot_dates))],
            "cot_mm_net_z_change_4w": [-0.1 if i % 5 else 0.1 for i in range(len(cot_dates))],
        })
        cot.to_csv(root / "data/external_frontiers/cot_positioning_normalized.csv", index=False)
        cfg = load_config(root, "missing_config.json")
        cfg["segments"] = {
            "train": ["2011-01-01", "2012-06-30"],
            "validation": ["2012-07-01", "2013-06-30"],
            "tail_forward": ["2013-07-01", "2014-12-31"],
        }
        cfg["asof_years"] = [2011, 2012]
        summary = run(root, cfg, root / "reports/stage111_macro_flow_absorption_frontier_discovery")
        assert summary["status"] == "STAGE111_COMPLETE_NO_PROMOTION"
        assert summary["generated_candidate_count"] > 0
        assert (root / "reports/stage111_macro_flow_absorption_frontier_discovery/stage111_candidate_metrics.csv").exists()
        assert (root / "reports/stage111_macro_flow_absorption_frontier_discovery/stage111_selected_for_stage112.csv").exists()
        loaded = json.loads((root / "reports/stage111_macro_flow_absorption_frontier_discovery/stage111_macro_flow_absorption_frontier_discovery_summary.json").read_text())
        assert loaded["hard_blocks"]
