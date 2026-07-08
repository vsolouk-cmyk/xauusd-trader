import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.stage163_macro_supported_side_discovery import compute_features, load_bars, macro_supported_sides, scan_candidates


def test_macro_supported_sides_headwind_short():
    summary = {"macro_context": {"gold_macro_pressure": "USD_REAL_YIELD_HEADWIND_FOR_GOLD"}}
    sides, pressure, note = macro_supported_sides(summary)
    assert sides == ["SHORT"]
    assert "HEADWIND" in pressure
    assert "short" in note.lower()


def test_compute_features_contains_outcomes():
    n = 800
    times = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    close = pd.Series(np.linspace(2000, 2100, n) + np.sin(np.arange(n) / 10) * 2)
    bars = pd.DataFrame({
        "utc_time": times,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1,
    })
    feat = compute_features(bars, horizon_bars=48)
    assert "ret_24h_bps" in feat.columns
    assert "future_long_bps" in feat.columns
    assert "future_short_bps" in feat.columns
    assert feat["future_long_bps"].notna().sum() > 100


def test_scan_candidates_returns_rows_on_synthetic():
    n = 900
    times = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    # Downtrend makes short-side outcomes more likely for momentum conditions.
    close = pd.Series(np.linspace(2100, 1900, n) + np.sin(np.arange(n) / 7) * 3)
    bars = pd.DataFrame({
        "utc_time": times,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1,
    })
    feat = compute_features(bars, horizon_bars=48)
    rows, shortlist, active = scan_candidates(
        feat,
        supported_sides=["SHORT"],
        min_events=30,
        min_mean_bps=0.1,
        min_hit_rate=0.50,
        min_recent_mean_bps=0.0,
        max_pairs=500,
    )
    assert rows
    assert all(r["macro_alignment"] in {"MACRO_SUPPORTED_SIDE", "MACRO_CONFLICTED_SIDE"} for r in rows[:10])
    assert any(r["side"] == "SHORT" for r in rows)
