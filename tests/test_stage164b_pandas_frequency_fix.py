import pandas as pd

from app.stage164_higher_tf_macro_regime_rebuild import resample_ohlc


def test_resample_uses_pandas3_compatible_lowercase_hour_rules():
    df = pd.DataFrame({
        "time_utc": pd.date_range("2026-07-08 00:00:00", periods=24, freq="5min", tz="UTC"),
        "open": [100.0 + i for i in range(24)],
        "high": [101.0 + i for i in range(24)],
        "low": [99.0 + i for i in range(24)],
        "close": [100.5 + i for i in range(24)],
        "volume": [1] * 24,
        "spread": [30] * 24,
    })
    h1 = resample_ohlc(df, "1h")
    h4 = resample_ohlc(df, "4h")
    assert len(h1) == 2
    assert len(h4) == 1
    assert float(h1.iloc[0]["open"]) == 100.0
    assert float(h1.iloc[0]["close"]) == 111.5


def test_uppercase_hour_rules_are_not_required_by_stage164b():
    # Pandas 3 / Python 3.14 can reject uppercase H. The stage should use lowercase internally.
    df = pd.DataFrame({
        "time_utc": pd.date_range("2026-07-08 00:00:00", periods=12, freq="5min", tz="UTC"),
        "open": [1.0] * 12,
        "high": [2.0] * 12,
        "low": [0.5] * 12,
        "close": [1.5] * 12,
        "volume": [1] * 12,
        "spread": [1] * 12,
    })
    out = resample_ohlc(df, "1h")
    assert len(out) == 1
