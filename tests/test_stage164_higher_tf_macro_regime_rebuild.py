import json
from pathlib import Path

import pandas as pd

from app.stage164_higher_tf_macro_regime_rebuild import load_bars, classify_macro, add_features, score_candidates


def test_mt5_tsv_loader_combines_date_time(tmp_path: Path):
    p = tmp_path / "m5.tsv"
    p.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2026.07.08\t14:00:00\t4052.91\t4056.85\t4050.32\t4053.83\t465\t0\t34\n"
        "2026.07.08\t14:05:00\t4053.85\t4054.24\t4048.85\t4049.19\t427\t0\t33\n",
        encoding="utf-8",
    )
    df, meta = load_bars(p, timestamp_shift_hours=-3)
    assert len(df) == 2
    assert meta["loader_selected_sep"] == "\t"
    assert meta["loader_parse_mode"] == "split_date_time_mt5_tsv"
    assert str(df["time_utc"].iloc[0]) == "2026-07-08 11:00:00+00:00"


def test_classify_macro_headwind_short_only():
    pressure, sides, note = classify_macro({"macro_context": {"gold_macro_pressure": "USD_REAL_YIELD_HEADWIND_FOR_GOLD"}})
    assert pressure == "USD_REAL_YIELD_HEADWIND_FOR_GOLD"
    assert sides == ["SHORT"]
    assert "Headwind" in note


def test_score_candidates_returns_macro_aligned_rows():
    n = 240
    t = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    # Downtrend should create some short-side positive future returns.
    close = pd.Series([2000 - i * 0.5 for i in range(n)], dtype=float)
    df = pd.DataFrame({
        "time_utc": t,
        "open": close + 0.1,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 1,
        "spread": 30,
    })
    feat = add_features(df)
    scores = score_candidates(feat, "H1", horizon_bars=6, macro_supported_sides=["SHORT"])
    assert not scores.empty
    assert scores["macro_aligned"].any()
    assert set(scores.loc[scores["macro_aligned"], "side"]) == {"SHORT"}
