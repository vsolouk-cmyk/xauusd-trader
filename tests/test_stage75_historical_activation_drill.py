from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pandas as pd

from app.stage75_historical_activation_drill import run


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_stage75_historical_activation_drill_smoke():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        macro = root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        macro.parent.mkdir(parents=True, exist_ok=True)
        dates = pd.bdate_range("2019-01-01", periods=520, tz="UTC")
        rows = []
        price = 1000.0
        for i, d in enumerate(dates):
            price += 1.0
            active = i in (10, 140, 270, 400)
            rows.append({
                "feature_date_utc": d.strftime("%Y-%m-%d"),
                "gold_close": price,
                "gold_sma20_over_50": 1.0 if active else -1.0,
                "dxy_ret_20d": 0.1 if active else -0.1,
                "real_yield_change_20d": -0.1 if active else 0.1,
            })
        pd.DataFrame(rows).to_csv(macro, index=False)

        locks = [
            ("stage70b_champion_hard_audit", "stage70b_champion_hard_audit_summary.json", "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"),
            ("stage71_locked_historical_forward_test", "stage71_locked_historical_forward_test_summary.json", "K06_PASSES_LOCKED_HISTORICAL_FORWARD"),
            ("stage72_historical_daily_replay", "stage72_historical_daily_replay_summary.json", "K06_PASSES_HISTORICAL_DAILY_REPLAY"),
            ("stage73b_corrected_asof_validation_bridge", "stage73b_corrected_asof_validation_bridge_summary.json", "K06_PASSES_CORRECTED_ASOF_VALIDATION"),
        ]
        for folder, fname, disp in locks:
            write_json(root / "reports" / folder / fname, {"disposition": disp})

        cfg = root / "configs/stage75_historical_activation_drill.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({
            "macro_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "date_col": "feature_date_utc",
            "price_col": "gold_close",
            "thesis_id": "K06_RESILIENT_GOLD_VS_DXY",
            "family": "GOLD_RESILIENCE_AGAINST_DXY",
            "direction": "long",
            "horizon_trading_days": 60,
            "entry_cooldown_trading_days": 60,
            "cost_bps_total": 50.0,
            "drill_start_date": "2019-01-01",
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0}
            ],
            "required_lock_files": [
                {"stage": "Stage70B", "path": "reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_summary.json", "required_disposition": "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"},
                {"stage": "Stage71", "path": "reports/stage71_locked_historical_forward_test/stage71_locked_historical_forward_test_summary.json", "required_disposition": "K06_PASSES_LOCKED_HISTORICAL_FORWARD"},
                {"stage": "Stage72", "path": "reports/stage72_historical_daily_replay/stage72_historical_daily_replay_summary.json", "required_disposition": "K06_PASSES_HISTORICAL_DAILY_REPLAY"},
                {"stage": "Stage73B", "path": "reports/stage73b_corrected_asof_validation_bridge/stage73b_corrected_asof_validation_bridge_summary.json", "required_disposition": "K06_PASSES_CORRECTED_ASOF_VALIDATION"}
            ],
            "decision_constraints": {
                "min_matured_activation_packets": 3,
                "max_lookahead_violations": 0,
                "max_missing_required_feature_rows": 0,
                "min_mean_net_return_bps": 0.0,
                "min_win_rate": 0.5,
                "max_abs_worst_loss_bps": 1500.0
            },
            "hard_blocks": ["NO_ORDER_AUTHORIZATION_FROM_STAGE75"]
        }), encoding="utf-8")

        summary = run(root, cfg, root / "reports/stage75_historical_activation_drill")
        assert summary["status"] == "STAGE75_COMPLETE_NO_PROMOTION"
        assert summary["activation_packets"] >= 4
        assert summary["activation_drill_metrics"]["matured_count"] >= 4
        assert summary["lookahead_violations"] == 0
        assert summary["missing_required_feature_rows"] == 0
        assert summary["outputs"]["latest_packet_json"]


if __name__ == "__main__":
    test_stage75_historical_activation_drill_smoke()
    print("Stage75 tests passed")
