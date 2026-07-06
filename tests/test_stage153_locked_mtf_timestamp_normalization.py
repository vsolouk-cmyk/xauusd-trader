from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage151_locked_mtf_rule_state_writer import compute_latest_features, hours_to_bars

def make_bars(n=1300, step_minutes=5):
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

def test_source_contains_timestamp_shift_arg():
    src = (ROOT / "app/stage151_locked_mtf_rule_state_writer.py").read_text(encoding="utf-8")
    assert "--timestamp-shift-hours" in src
    assert "normalized_feature_time" in src
    assert "raw_feature_date" in src
    assert "timestamp_shift_hours" in src

def test_feature_computation_still_works():
    latest = compute_latest_features(make_bars(), timeframe_minutes=5)
    assert latest["trend_8_20_bps"] is not None
    assert latest["trend_50_100_bps"] is not None

def test_hours_to_bars_preserved():
    assert hours_to_bars(100, 5) == 1200
