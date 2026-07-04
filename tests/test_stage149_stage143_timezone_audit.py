from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage149_stage143_timezone_and_bar_audit import run

def test_timezone_audit_passes_monotonic_h1_sample(tmp_path):
    root = tmp_path
    bars = tmp_path / "bars.csv"
    start = datetime.now(timezone.utc) - timedelta(hours=20)
    lines = ["<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n"]
    for i in range(10):
        dt = start + timedelta(hours=i)
        lines.append(f"{dt:%Y.%m.%d}\t{dt:%H:%M:%S}\t1\t2\t0.5\t1.5\n")
    bars.write_text("".join(lines), encoding="utf-8")
    s = run(root, bars, max_allowed_step_minutes=75, max_future_minutes=180)
    assert s["gap_count"] == 0
    assert s["non_monotonic_count"] == 0

def test_timezone_audit_detects_gap(tmp_path):
    root = tmp_path
    bars = tmp_path / "bars.csv"
    now = datetime.now(timezone.utc) - timedelta(hours=20)
    a = now
    b = now + timedelta(hours=3)
    bars.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n"
        f"{a:%Y.%m.%d}\t{a:%H:%M:%S}\t1\t2\t0.5\t1.5\n"
        f"{b:%Y.%m.%d}\t{b:%H:%M:%S}\t1\t2\t0.5\t1.5\n",
        encoding="utf-8",
    )
    s = run(root, bars, max_allowed_step_minutes=75, max_future_minutes=180)
    assert s["gap_count"] == 1
    assert "h1_gaps_detected" in s["issues"]
