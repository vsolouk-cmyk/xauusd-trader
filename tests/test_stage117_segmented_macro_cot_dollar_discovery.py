from pathlib import Path
import json
import pandas as pd
import numpy as np

from app.stage117_segmented_macro_cot_dollar_discovery import (
    normalize_colname,
    build_thresholds,
    make_rule_mask,
    RULES,
    split_by_time,
)


def test_normalize_colname():
    assert normalize_colname(" Report Date as YYYY-MM-DD ") == "report_date_as_yyyy_mm_dd"
    assert normalize_colname("DXY Close%") == "dxy_close"


def test_split_by_time_counts():
    df = pd.DataFrame({"utc_time": pd.date_range("2020-01-01", periods=100, freq="h", tz="UTC")})
    labels = split_by_time(df)
    assert (labels == "selection").sum() == 60
    assert (labels == "validation").sum() == 20
    assert (labels == "tail_forward_proxy").sum() == 20


def test_rule_mask_smoke():
    n = 300
    df = pd.DataFrame({
        "real_yield_10y_chg_20d": np.r_[np.repeat(-1.0, 100), np.repeat(0.2, 200)],
        "dollar_pressure_chg_20d": np.r_[np.repeat(-2.0, 100), np.repeat(0.5, 200)],
        "cot_mm_net_z": np.r_[np.repeat(0.0, 100), np.repeat(2.0, 200)],
        "real_yield_10y_chg_60d": np.random.normal(0, 1, n),
        "cot_decrowd_4w": np.random.normal(0, 1, n),
        "cot_decrowd_12w": np.random.normal(0, 1, n),
    })
    th = build_thresholds(df)
    mask = make_rule_mask(df, RULES[0], th)
    assert mask.sum() >= 50


def test_coerce_numeric_pandas3_safe():
    import pandas as pd
    import numpy as np
    from app.stage117_segmented_macro_cot_dollar_discovery import coerce_numeric

    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "value": ["1,234.5", "2%", "bad"],
    })
    out = coerce_numeric(df, exclude=["date"])
    assert out["date"].tolist() == df["date"].tolist()
    assert out["value"].iloc[0] == 1234.5
    assert out["value"].iloc[1] == 2.0
    assert np.isnan(out["value"].iloc[2])
