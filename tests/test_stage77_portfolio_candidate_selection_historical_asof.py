import json
import tempfile
from pathlib import Path

import pandas as pd

from app.stage77_portfolio_candidate_selection_historical_asof import active_mask, compute_entries, metric_block


def main() -> None:
    dates = pd.bdate_range("2011-01-03", periods=900)
    df = pd.DataFrame({
        "feature_date_utc": dates.astype(str),
        "gold_close": [1000 + i * 1.5 for i in range(len(dates))],
        "gold_sma20_over_50": [1.0] * len(dates),
        "dxy_ret_20d": [1.0 if i % 250 < 120 else -1.0 for i in range(len(dates))],
        "real_yield_change_20d": [-1.0] * len(dates),
    })
    df["_date"] = pd.to_datetime(df["feature_date_utc"])
    mask, missing = active_mask(df, [
        {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
        {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
        {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
    ])
    assert not missing
    entries = compute_entries(df, mask, 120, "gold_close", 50.0, "K06_TEST")
    assert len(entries) >= 3
    metrics = metric_block(entries, "TOTAL")
    assert metrics["entry_count"] == len(entries)
    assert metrics["mean_net_return_bps"] is not None
    print("Stage77 tests passed")


if __name__ == "__main__":
    main()
