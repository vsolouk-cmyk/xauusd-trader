from pathlib import Path
import json
import tempfile

import pandas as pd

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.stage70b_champion_hard_audit import run


def make_dataset(path: Path) -> None:
    dates = pd.bdate_range("2011-01-03", periods=900)
    rows = []
    price = 1000.0
    for i, d in enumerate(dates):
        # Rising price with mild waves. K06 active in recurring windows.
        price *= 1.0007
        active = (i % 160) < 55 and i > 50
        rows.append({
            "feature_date_utc": d.strftime("%Y-%m-%d"),
            "gold_close": price,
            "gold_sma20_over_50": 0.01 if active or (i % 90) < 40 else -0.01,
            "dxy_ret_20d": 0.01 if active else -0.01,
            "real_yield_change_20d": -0.01 if active else 0.01,
            "dxy_sma20_over_50": -0.01 if (i % 100) < 50 else 0.01,
            "gold_sma50_over_200": 0.02 if i > 220 else -0.02,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def make_config(root: Path, cfg_path: Path) -> None:
    cfg = {
        "champion": {
            "thesis_id": "K06_RESILIENT_GOLD_VS_DXY",
            "family": "GOLD_RESILIENCE_AGAINST_DXY",
            "direction": "long",
            "horizon_trading_days": 60,
            "conditions": [
                {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
                {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
                {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
            ],
            "entry_price_column": "gold_close",
            "date_column_candidates": ["feature_date_utc", "date_utc"],
            "cost_bps_total": 50.0,
            "entry_cooldown_trading_days": 60,
        },
        "macro_dataset_path": "data/macro_regime/normalized/test_macro.csv",
        "periods": [
            {"period_id": "P1", "start": "2011-01-01", "end": "2011-12-31"},
            {"period_id": "P2", "start": "2012-01-01", "end": "2012-12-31"},
            {"period_id": "P3", "start": "2013-01-01", "end": "2013-12-31"},
            {"period_id": "P4", "start": "2014-01-01", "end": "2014-12-31"},
        ],
        "stress_cost_bps": [50.0, 100.0, 150.0],
        "benchmark_rules": [
            {"rule_key": "B1", "label": "bench", "horizon_trading_days": 60, "conditions": [{"column": "gold_sma50_over_200", "operator": ">", "threshold": 0.0}]}
        ],
        "backlog_register": [{"thesis_id": "K07", "status": "BACKLOG_REFERENCE", "reentry_trigger": "after K06", "required_data": "macro"}],
        "decision_constraints": {
            "min_entry_count": 3,
            "min_mean_net_return_bps": 10.0,
            "min_median_net_return_bps": 0.0,
            "min_win_rate": 0.4,
            "min_positive_period_share": 0.25,
            "min_positive_year_share": 0.25,
            "max_year_entry_share": 0.8,
            "max_abs_min_net_return_bps": 5000.0,
            "max_recent_period_share_of_total_return": 1.0,
            "min_leave_one_period_out_mean_bps": -1000.0,
            "min_mean_net_bps_at_150_cost": -1000.0,
            "max_benchmark_overlap_jaccard_pct": 100.0,
        },
        "hard_blocks": ["NO_AUTOMATED_ORDER", "NO_LIVE"],
    }
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")


def test_stage70b_runs_and_writes_outputs():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data_path = root / "data/macro_regime/normalized/test_macro.csv"
        cfg_path = root / "configs/test_stage70b.json"
        out = root / "reports/stage70b"
        make_dataset(data_path)
        make_config(root, cfg_path)
        summary = run(root, cfg_path, out)
        assert summary["status"] == "STAGE70B_COMPLETE_NO_PROMOTION"
        assert summary["decision"] in {
            "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE",
            "KILL_CHAMPION_CLOSE_STAGE70",
            "AMBIGUOUS_ONE_DIAGNOSTIC_ONLY",
        }
        assert Path(summary["outputs"]["summary_json"]).exists()
        assert Path(summary["outputs"]["entry_returns_csv"]).exists()
        assert Path(summary["outputs"]["backlog_register_csv"]).exists()
        assert summary["backlog_policy"]["registered_backlog_count"] == 1


if __name__ == "__main__":
    test_stage70b_runs_and_writes_outputs()
    print("Stage70B tests passed")
