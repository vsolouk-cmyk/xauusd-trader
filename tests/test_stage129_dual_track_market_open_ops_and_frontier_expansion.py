from pathlib import Path
import pandas as pd
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage129_dual_track_market_open_ops_and_frontier_expansion import run

def test_stage129_run_no_order(tmp_path):
    root = tmp_path
    data = root / "data/fundamental_event_inbox/features"
    data.mkdir(parents=True)
    n = 300
    dates = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame({
        "utc_time": dates,
        "vix_chg_20d": [i % 10 for i in range(n)],
        "dollar_pressure_chg_20d": [-(i % 7) for i in range(n)],
        "real_yield_10y_chg_20d": [-(i % 5) for i in range(n)],
        "spdr_value_chg_20d": [i % 6 for i in range(n)],
        "cot_mm_net_z": [0.2] * n,
        "fwd_ret_bps_h120": [100 if i % 10 > 5 else -20 for i in range(n)],
    })
    df.to_csv(data / "stage117_joined_macro_cot_dollar_h1_research_dataset.csv", index=False)
    mt5 = root / "MQL5/Files"
    mt5.mkdir(parents=True)
    (mt5 / "xauusd_stage124f_rule8_overlay_kv.csv").write_text("status|PASS\nallow_trading|false\n")
    (mt5 / "xauusd_stage126_rule9_frontier_status_kv.csv").write_text("status|WATCH\nallow_trading|false\n")
    summary = run(root, mt5, write_mt5_status_kv=True)
    assert summary["status"] == "STAGE129_COMPLETE_DUAL_TRACK_READY_NO_ORDER"
    assert "NO_ORDER_SEND" in summary["hard_blocks"]
    assert Path(summary["market_open_runtime_snapshot"]).exists()
    assert Path(summary["selected_for_stage130"]).exists()
