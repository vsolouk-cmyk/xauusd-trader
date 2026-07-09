import json
import subprocess
import sys
from pathlib import Path
import pandas as pd


def test_stage166c_no_fetch_smoke(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    bars = tmp_path / "bars.csv"
    rows = []
    start = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    for i in range(240):
        t = start + pd.Timedelta(minutes=5*i)
        rows.append({"<DATE>": t.strftime("%Y.%m.%d"), "<TIME>": t.strftime("%H:%M:%S"), "<OPEN>": 2000+i*0.01, "<HIGH>": 2001+i*0.01, "<LOW>": 1999+i*0.01, "<CLOSE>": 2000.2+i*0.01, "<TICKVOL>": 10, "<VOL>": 0, "<SPREAD>": 15})
    pd.DataFrame(rows).to_csv(bars, index=False, sep="\t")
    manual = inbox / "manual_current_event_history.csv"
    pd.DataFrame({
        "time_utc": ["2024-01-01T01:00:00Z", "2024-01-01T04:00:00Z"],
        "profile": ["geopolitical_escalation", "macro_policy_dovish"],
        "raw_count": [5, 3],
    }).to_csv(manual, index=False)
    script = Path(__file__).parents[1] / "app" / "stage166b_historical_current_event_panel_rebuild.py"
    subprocess.check_call([
        sys.executable, str(script),
        "--root", str(root),
        "--bars-m5", str(bars),
        "--event-inbox", str(inbox),
        "--holdout-pct", "0.20",
        "--min-panel-rows", "1",
        "--min-train-active-event-bars", "1",
        "--write-stage166-compatible-panel",
    ])
    summary = root / "reports" / "stage166b_historical_current_event_panel_rebuild" / "stage166b_historical_current_event_panel_rebuild_summary.json"
    obj = json.loads(summary.read_text())
    assert obj["stage"] == "Stage166C_FAST_GDELT_HISTORICAL_EVENT_PANEL_REBUILD"
    assert obj["panel_rows"] > 0
    assert "event_panel_health" in obj
