from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage150_mtf_separated_validation_discovery import (
    hours_to_bars,
    add_features,
    split_rows_with_recent_embargo,
    rule_is_excluded,
)

def make_bars(n=1200, step_minutes=15):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    price = 1000.0
    for i in range(n):
        price += 0.1
        out.append({
            "utc_time": start + timedelta(minutes=i * step_minutes),
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
        })
    return out

def test_hours_to_bars_m15_and_m5():
    assert hours_to_bars(3, 15) == 12
    assert hours_to_bars(3, 5) == 36

def test_feature_lookback_is_timeframe_aware():
    rows = add_features(make_bars(200, 15), horizon_hours=4, timeframe_minutes=15)
    assert rows[12]["ret_3h_bps"] is not None
    assert rows[11]["ret_3h_bps"] is None

def test_recent_embargo_uses_hours_not_bars():
    rows = add_features(make_bars(500, 15), horizon_hours=4, timeframe_minutes=15)
    for r in rows:
        r["target"] = r.get("fwd_ret_4h_bps")
    s = split_rows_with_recent_embargo(rows, recent_embargo_hours=24)
    assert len(s["embargoed_recent"]) >= 90
    assert len(s["embargoed_recent"]) <= 100

def test_exclusion_still_works():
    excluded, reason = rule_is_excluded("D138C_ret_48h_bps_GEQ65__x", [], ["D138C_ret_48h_bps_GEQ65"])
    assert excluded
    assert reason.startswith("substring:")
