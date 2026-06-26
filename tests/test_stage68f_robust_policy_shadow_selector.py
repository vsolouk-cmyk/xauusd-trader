#!/usr/bin/env python3
from pathlib import Path
import json
import tempfile

import pandas as pd

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.stage68f_robust_policy_shadow_selector import run


def write_fixture(root: Path) -> None:
    (root / "data/macro_regime/normalized").mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "feature_date_utc": "2026-06-25",
            "gold_sma20_over_50": -1.0,
            "gold_sma50_over_200": -1.0,
            "dxy_ret_20d": 1.0,
            "dxy_sma20_over_50": 1.0,
            "real_yield_change_20d": 1.0,
            "vix_change_20d": -1.0,
            "etf_flow_tonnes_3m": 1.0,
            "central_bank_demand_tonnes_3m": 1.0,
            "gold_close": 2300.0,
        },
        {
            "feature_date_utc": "2026-06-26",
            "gold_sma20_over_50": 1.0,
            "gold_sma50_over_200": 1.0,
            "dxy_ret_20d": -0.01,
            "dxy_sma20_over_50": -0.02,
            "real_yield_change_20d": -0.1,
            "vix_change_20d": 2.0,
            "etf_flow_tonnes_3m": 10.0,
            "central_bank_demand_tonnes_3m": 5.0,
            "gold_close": 2400.0,
        },
    ]
    pd.DataFrame(rows).to_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)


def write_config(root: Path) -> None:
    (root / "configs").mkdir(parents=True, exist_ok=True)
    cfg = {
        "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "policy_id": "D3_FIRST_EXCLUDE_D1",
        "policy_source": "test",
        "cluster_window_calendar_days": 60,
        "priority": ["d3_h60", "h64l_v2", "d4_backup"],
        "allow_rules": ["d3_h60", "h64l_v2", "d4_backup"],
        "reference_only_rules": ["d1_backup"],
        "rules": {
            "h64l_v2": {"label": "H64L v2", "horizon_trading_days": 120, "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": "<", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
                {"column": "etf_flow_tonnes_3m", "operator": ">", "threshold": 0.0},
                {"column": "central_bank_demand_tonnes_3m", "operator": ">", "threshold": 0.0},
                {"column": "gold_sma50_over_200", "operator": ">", "threshold": 0.0}
            ]},
            "d3_h60": {"label": "D3", "horizon_trading_days": 60, "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_sma20_over_50", "operator": "<", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": "<", "threshold": 0.0}
            ]},
            "d4_backup": {"label": "D4", "horizon_trading_days": 60, "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "vix_change_20d", "operator": ">", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0}
            ]},
            "d1_backup": {"label": "D1", "horizon_trading_days": 60, "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": "<", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0}
            ]},
        },
        "hard_blocks": ["NO_ORDER"]
    }
    (root / "configs/stage68f_robust_policy_shadow_selector.json").write_text(json.dumps(cfg), encoding="utf-8")


def test_selector_picks_d3_first():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        write_fixture(root)
        write_config(root)
        out = root / "reports/stage68f"
        summary = run(root, root / "configs/stage68f_robust_policy_shadow_selector.json", out)
        assert summary["status"] == "STAGE68F_COMPLETE_NO_PROMOTION"
        assert summary["policy_selection"]["policy_signal_active"] is True
        assert summary["policy_selection"]["selected_rule_key"] == "d3_h60"
        assert (out / "stage68f_robust_policy_shadow_selector_summary.json").exists()
        assert (out / "stage68f_robust_policy_shadow_selector_report.md").exists()


if __name__ == "__main__":
    test_selector_picks_d3_first()
    print("Stage68F tests passed")
