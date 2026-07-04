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

def test_weekend_gap_is_expected_not_suspicious():
    fri = datetime(2026, 7, 3, 19, 0, tzinfo=timezone.utc)
    mon = datetime(2026, 7, 6, 1, 0, tzinfo=timezone.utc)
    g = classify_gap(fri, mon, 75)
    assert g["classification"].startswith("expected_")

def test_intraweek_gap_is_suspicious():
    tue1 = datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc)
    tue2 = datetime(2026, 7, 7, 13, 0, tzinfo=timezone.utc)
    g = classify_gap(tue1, tue2, 75)
    assert g["classification"] == "suspicious_intraweek_gap"

def test_run_does_not_fail_on_weekend_gap_only(tmp_path):
    bars = tmp_path / "bars.csv"
    dts = [
        datetime(2026, 7, 3, 18, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 3, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 6, 1, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 6, 2, 0, tzinfo=timezone.utc),
    ]
    write_bars(bars, dts)
    s = run(tmp_path, bars)
    assert s["expected_market_closure_gap_count"] == 1
    assert s["suspicious_gap_count"] == 0
    assert "suspicious_intraweek_h1_gaps_detected" not in s["issues"]
