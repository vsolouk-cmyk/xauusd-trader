from pathlib import Path
import tempfile
import pandas as pd

from app.stage166_current_event_shock_overlay import normalize_and_score, build_panels, build_holdout_map


def test_stage166_scoring_and_panels_smoke():
    records = [
        {"title": "Gold rises as missile attack escalates Middle East conflict", "seendate": "20260709T010000Z", "url": "https://example.com/a"},
        {"title": "Ceasefire talks reduce safe haven demand for gold", "seendate": "20260709T020000Z", "url": "https://example.com/b"},
    ]
    events = normalize_and_score(records, source_kind_default="local_json", recent_days=365, half_life_hours=100000)
    assert len(events) == 2
    assert "gold_long_pressure" in events.columns
    intraday, daily = build_panels(events)
    assert len(intraday) >= 1
    assert len(daily) >= 1
    assert "event_shock_regime" in daily.columns


def test_stage166_holdout_map_smoke():
    bars = pd.DataFrame({"time_utc": pd.date_range("2026-01-01", periods=100, freq="5min", tz="UTC")})
    holdout = build_holdout_map(bars, holdout_pct=0.2)
    assert holdout["loaded"] is True
    assert holdout["holdout_rows"] == 20
    assert holdout["train_rows"] == 80
