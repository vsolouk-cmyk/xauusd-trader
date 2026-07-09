import json
from pathlib import Path

import pandas as pd

from app.stage165_macro_thesis_regime_rebuild import load_bars, daily_ohlc_from_m5, build_macro_regimes, run, build_arg_parser


def test_mt5_tsv_loader_combines_date_time(tmp_path):
    p = tmp_path / "m5.tsv"
    p.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2026.07.08\t14:00:00\t4052\t4056\t4050\t4053\t10\t0\t33\n"
        "2026.07.08\t14:05:00\t4053\t4054\t4048\t4049\t11\t0\t33\n"
    )
    bars, meta = load_bars(p, timestamp_shift_hours=-3)
    assert len(bars) == 2
    assert meta["parse_mode"] == "split_date_time_mt5_tsv"
    assert str(bars["time_utc"].iloc[0]).startswith("2026-07-08 11:00:00")


def test_macro_regime_classification():
    dates = pd.date_range("2026-01-01", periods=30, freq="1d", tz="UTC")
    macro = pd.DataFrame({
        "macro_date": dates,
        "dollar_pressure_index": list(range(30)),
        "real_yield_10y": [2.0 + i * 0.01 for i in range(30)],
        "vix": [15.0] * 30,
    })
    out, info = build_macro_regimes(macro)
    assert info["macro_feature_status"] == "READY"
    assert out["macro_regime"].iloc[-1] == "USD_REAL_YIELD_HEADWIND_FOR_GOLD"
    assert out["macro_supported_side"].iloc[-1] == "SHORT"


def test_run_writes_failure_safe_outputs(tmp_path):
    root = tmp_path
    (root / "data/fundamental_event_inbox/features").mkdir(parents=True)
    bars_path = tmp_path / "m5.tsv"
    rows = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>"]
    # 80 days of hourly-ish M5-sparse bars, enough to aggregate daily.
    for i in range(80):
        d = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        rows.append(f"{d:%Y.%m.%d}\t01:00:00\t{100+i}\t{101+i}\t{99+i}\t{100+i}\t10\t0\t30")
    bars_path.write_text("\n".join(rows) + "\n")
    macro_path = root / "data/fundamental_event_inbox/features/stage115_daily_macro_feature_panel.csv"
    macro = pd.DataFrame({
        "date": pd.date_range("2025-12-15", periods=100, freq="1d").strftime("%Y-%m-%d"),
        "dollar_pressure_index": range(100),
        "real_yield_10y": [2.0 + i * 0.01 for i in range(100)],
        "vix": [15.0] * 100,
    })
    macro.to_csv(macro_path, index=False)
    args = build_arg_parser().parse_args([
        "--root", str(root),
        "--bars-m5", str(bars_path),
        "--macro-panel", str(macro_path),
        "--timestamp-shift-hours", "-3",
        "--horizons-days", "1,3",
        "--min-events", "5",
        "--min-mean-bps", "-999",
        "--min-hit-rate", "0.0",
        "--min-recent-mean-bps", "-999",
        "--min-positive-folds", "0",
    ])
    summary = run(args)
    assert summary["stage"] == "Stage165_MACRO_THESIS_REGIME_REBUILD"
    assert summary["demo_release_allowed"] is False
    assert Path(summary["outputs"]["summary_json"]).exists()
    assert Path(summary["outputs"]["candidate_scores_csv"]).exists()
