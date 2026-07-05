from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage150_mtf_separated_validation_discovery import (
    condition_active,
    hours_to_bars,
    add_features,
)

def make_bars(n=1200, step_minutes=5):
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

def test_m5_hour_conversion_preserved():
    assert hours_to_bars(4, 5) == 48

def test_current_active_prefilter_logic():
    latest = {"x": 10.0, "y": -1.0}
    assert condition_active(latest, [("x", ">=", 9.0)]) is True
    assert condition_active(latest, [("x", "<=", 9.0)]) is False

def test_features_still_timeframe_aware_after_stage150b():
    rows = add_features(make_bars(300, 5), horizon_hours=4, timeframe_minutes=5)
    assert rows[36]["ret_3h_bps"] is not None
    assert rows[35]["ret_3h_bps"] is None

def test_stage150b_source_contains_score_inactive_flag():
    src = (ROOT / "app/stage150_mtf_separated_validation_discovery.py").read_text(encoding="utf-8")
    assert "--score-inactive" in src
    assert "inactive_candidate_skipped_count" in src
