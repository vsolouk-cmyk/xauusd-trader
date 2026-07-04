from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage149_stage143_timezone_and_bar_audit import classify_gap, run

def write_bars(path, dts):
    lines = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n"]
    for dt in dts:
        lines.append(f"{dt:%Y.%m.%d}\t{dt:%H:%M:%S}\t1\t2\t0.5\t1.5\n")
    path.write_text("".join(lines), encoding="utf-8")

def test_christmas_gap_is_expected():
    a = datetime(2024, 12, 24, 19, 0, tzinfo=timezone.utc)
    b = datetime(2024, 12, 26, 1, 0, tzinfo=timezone.utc)
    g = classify_gap(a, b, 75)
    assert g["classification"] == "expected_exchange_holiday_or_early_close"

def test_small_intraday_gap_is_session_gap():
    a = datetime(2026, 7, 7, 19, 0, tzinfo=timezone.utc)
    b = datetime(2026, 7, 8, 1, 0, tzinfo=timezone.utc)
    g = classify_gap(a, b, 75)
    assert g["classification"] == "expected_intraday_session_or_broker_maintenance_gap"

def test_recent_large_intraweek_gap_blocks(tmp_path):
    bars = tmp_path / "bars.csv"
    start = datetime.now(timezone.utc) - timedelta(days=3)
    dts = [start, start + timedelta(hours=1), start + timedelta(hours=10)]
    write_bars(bars, dts)
    s = run(tmp_path, bars, recent_audit_days=90)
    assert s["recent_suspicious_gap_count"] == 1
    assert "recent_suspicious_intraweek_h1_gaps_detected" in s["issues"]

def test_historical_suspicious_gap_logged_not_blocking(tmp_path):
    bars = tmp_path / "bars.csv"
    old = datetime(2024, 6, 4, 10, 0, tzinfo=timezone.utc)
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    dts = [old, old + timedelta(hours=10), recent, recent + timedelta(hours=1)]
    write_bars(bars, dts)
    s = run(tmp_path, bars, recent_audit_days=90)
    assert s["historical_suspicious_gap_count"] >= 1
    assert s["recent_suspicious_gap_count"] == 0
    assert "recent_suspicious_intraweek_h1_gaps_detected" not in s["issues"]
