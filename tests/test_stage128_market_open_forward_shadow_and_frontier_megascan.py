from pathlib import Path
import pandas as pd
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage128_market_open_forward_shadow_and_frontier_megascan import (
    coerce_num, scan_frontier, run
)


def test_coerce_bool_to_numeric():
    s = pd.Series([True, False, True])
    out = coerce_num(s)
    assert list(out) == [1.0, 0.0, 1.0]


def test_scan_frontier_selects_strong_synthetic_rule(tmp_path):
    n = 300
    dates = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame({
        "utc_time": dates,
        "vix_chg_20d": [i % 10 for i in range(n)],
        "dollar_pressure_chg_20d": [-(i % 7) for i in range(n)],
        "real_yield_10y_chg_20d": [-(i % 5) for i in range(n)],
        "spdr_value_chg_20d": [i % 6 for i in range(n)],
        "cot_mm_net_z": [0.1] * n,
        "fwd_ret_bps_h120": [120 if (i % 10 > 5 and -(i % 7) < -2) else -20 for i in range(n)]
    })
    df["_stage128_forward_return_bps"] = df["fwd_ret_bps_h120"]
    metrics, selected, watch, th = scan_frontier(df, 120, 120)
    assert len(metrics) > 0
    assert "rule_id" in metrics.columns


def test_run_no_order_outputs(tmp_path):
    root = tmp_path
    data_dir = root / "data/fundamental_event_inbox/features"
    data_dir.mkdir(parents=True)
    n = 300
    dates = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame({
        "utc_time": dates,
        "vix_chg_20d": [i % 10 for i in range(n)],
        "dollar_pressure_chg_20d": [-(i % 7) for i in range(n)],
        "real_yield_10y_chg_20d": [-(i % 5) for i in range(n)],
        "spdr_value_chg_20d": [i % 6 for i in range(n)],
        "cot_mm_net_z": [0.1] * n,
        "fwd_ret_bps_h120": [120 if (i % 10 > 5 and -(i % 7) < -2) else -20 for i in range(n)]
    })
    df.to_csv(data_dir / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv", index=False)
    mt5_files = root / "MQL5/Files"
    mt5_files.mkdir(parents=True)
    (mt5_files / "xauusd_stage124f_rule8_overlay_kv.csv").write_text("status|PASS_STATIC_REPLAY\nallow_trading|false\n")
    summary = run(root, mt5_files, root / "MQL5/Indicators", write_mt5_status_kv=True)
    assert summary["status"].startswith("STAGE128_COMPLETE")
    assert "NO_ORDER_SEND" in summary["hard_blocks"]
    assert Path(summary["selected_for_stage129"]).exists()
