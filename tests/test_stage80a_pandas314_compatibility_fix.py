#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pandas as pd


def load_module():
    src = Path(__file__).resolve().parents[1] / "app" / "stage80_structured_thesis_discovery_expansion.py"
    spec = importlib.util.spec_from_file_location("stage80", src)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    mod = load_module()
    df = pd.DataFrame({
        "feature_date_utc": pd.bdate_range("2020-01-01", periods=80).strftime("%Y-%m-%d"),
        "metadata_source": ["synthetic"] * 80,
        "gold_close": [1500 + i for i in range(80)],
        "dxy": [100 - i * 0.01 for i in range(80)],
        "real_yield": [1.0 - i * 0.005 for i in range(80)],
        "vix": [18 + (i % 5) for i in range(80)],
    })
    added = mod.add_derived_features(df)
    assert "gold_ret_20d" in added
    assert "dxy_ret_20d" in added
    assert "real_yield_change_20d" in added
    assert "metadata_source" in df.columns
    assert df["metadata_source"].iloc[0] == "synthetic"
    print("Stage80A pandas compatibility test passed")


if __name__ == "__main__":
    main()
