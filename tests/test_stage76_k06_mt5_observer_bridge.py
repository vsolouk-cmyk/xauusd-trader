#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd


def load_module():
    module_path = Path(__file__).resolve().parents[1] / "app" / "stage76_k06_mt5_observer_bridge.py"
    spec = importlib.util.spec_from_file_location("stage76", module_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_stage76_smoke():
    mod = load_module()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        macro = root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        macro.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([
            {
                "feature_date_utc": "2026-06-26",
                "gold_close": 3333.0,
                "gold_sma20_over_50": 0.1,
                "dxy_ret_20d": 0.02,
                "real_yield_change_20d": -0.01,
            }
        ]).to_csv(macro, index=False)
        locks = [
            ("stage70b_champion_hard_audit", "stage70b_champion_hard_audit_summary.json", "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"),
            ("stage71_locked_historical_forward_test", "stage71_locked_historical_forward_test_summary.json", "K06_PASSES_LOCKED_HISTORICAL_FORWARD"),
            ("stage72_historical_daily_replay", "stage72_historical_daily_replay_summary.json", "K06_PASSES_HISTORICAL_DAILY_REPLAY"),
            ("stage73b_corrected_asof_validation_bridge", "stage73b_corrected_asof_validation_bridge_summary.json", "K06_PASSES_CORRECTED_ASOF_VALIDATION"),
            ("stage75_historical_activation_drill", "stage75_historical_activation_drill_summary.json", "K06_PASSES_HISTORICAL_ACTIVATION_DRILL"),
        ]
        for folder, filename, disposition in locks:
            write_json(root / "reports" / folder / filename, {"disposition": disposition})
        config = {
            "macro_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "date_col": "feature_date_utc",
            "price_col": "gold_close",
            "thesis_id": "K06_RESILIENT_GOLD_VS_DXY",
            "family": "GOLD_RESILIENCE_AGAINST_DXY",
            "direction": "long",
            "horizon_trading_days": 120,
            "entry_cooldown_trading_days": 120,
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
            ],
            "max_stale_calendar_days": 9999,
            "bridge_csv_path": "data/mt5_bridge/k06_observer_signal.csv",
            "stage_locks": [
                {"stage": "Stage70B", "summary_path": "reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_summary.json", "required_disposition": "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"},
                {"stage": "Stage71", "summary_path": "reports/stage71_locked_historical_forward_test/stage71_locked_historical_forward_test_summary.json", "required_disposition": "K06_PASSES_LOCKED_HISTORICAL_FORWARD"},
                {"stage": "Stage72", "summary_path": "reports/stage72_historical_daily_replay/stage72_historical_daily_replay_summary.json", "required_disposition": "K06_PASSES_HISTORICAL_DAILY_REPLAY"},
                {"stage": "Stage73B", "summary_path": "reports/stage73b_corrected_asof_validation_bridge/stage73b_corrected_asof_validation_bridge_summary.json", "required_disposition": "K06_PASSES_CORRECTED_ASOF_VALIDATION"},
                {"stage": "Stage75", "summary_path": "reports/stage75_historical_activation_drill/stage75_historical_activation_drill_summary.json", "required_disposition": "K06_PASSES_HISTORICAL_ACTIVATION_DRILL"},
            ],
            "hard_blocks": ["NO_AUTOMATED_ORDER", "OBSERVER_ONLY_EA"],
        }
        summary = mod.run(root, config, root / "reports/stage76")
        assert summary["status"] == "STAGE76_COMPLETE_NO_PROMOTION"
        assert summary["bridge_csv"]["written"] is True
        bridge = root / "data/mt5_bridge/k06_observer_signal.csv"
        assert bridge.exists()
        text = bridge.read_text(encoding="utf-8")
        assert "OBSERVER_ONLY_NO_TRADE" in text
        assert "true" in text
        assert "NO_AUTOMATED_ORDER" in json.dumps(summary)


def test_mql5_is_observer_only():
    ea = Path(__file__).resolve().parents[1] / "mt5" / "K06_ObserverOnly_EA.mq5"
    text = ea.read_text(encoding="utf-8")
    forbidden = ["OrderSend", "CTrade", ".Buy", ".Sell", "PositionOpen", "TRADE_ACTION_DEAL"]
    for token in forbidden:
        assert token not in text
    assert "OBSERVER_ONLY_NO_TRADE" in text
    assert "InpAllowTrading" in text


if __name__ == "__main__":
    test_stage76_smoke()
    test_mql5_is_observer_only()
    print("Stage76 tests passed")
