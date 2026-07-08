import pandas as pd

from app.stage159_locked_family_repair_discovery import compute_features


def test_fold_column_can_accept_string_labels_without_int_dtype_error(tmp_path):
    # Reproduce the fold assignment pattern on feature data.
    n = 120
    bars = pd.DataFrame({
        "utc_time": pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC"),
        "open": [100.0 + i * 0.01 for i in range(n)],
        "high": [100.2 + i * 0.01 for i in range(n)],
        "low": [99.8 + i * 0.01 for i in range(n)],
        "close": [100.0 + i * 0.01 for i in range(n)],
        "volume": [1 for _ in range(n)],
        "spread": [30 for _ in range(n)],
    })
    df = compute_features(bars, timeframe_minutes=5)
    horizon_bars = 48
    df["future_close"] = df["close"].shift(-horizon_bars)
    df["future_bps"] = (df["future_close"] / df["close"] - 1.0) * 10000.0
    valid_index = df.dropna(subset=["future_bps"]).index
    df["fold"] = pd.Series("UNASSIGNED", index=df.index, dtype="object")
    labels = pd.qcut(
        pd.Series(range(len(valid_index)), index=valid_index),
        4,
        labels=["F1_OLD", "F2", "F3", "F4_RECENT"],
        duplicates="drop",
    )
    df.loc[valid_index, "fold"] = labels.astype(str).astype("object")
    assert set(df.loc[valid_index, "fold"].unique()).issubset({"F1_OLD", "F2", "F3", "F4_RECENT"})
    assert str(df["fold"].dtype) == "object"
