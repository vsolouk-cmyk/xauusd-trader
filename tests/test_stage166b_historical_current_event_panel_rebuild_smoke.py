import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_stage166b_smoke(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    bars_path = inbox / "amarkets_xauusd_5m.csv"
    # MT5-like bars for 10 days.
    times = pd.date_range("2024-01-01 03:00:00", periods=10 * 24 * 12, freq="5min")
    bars = pd.DataFrame({
        "<DATE>": times.strftime("%Y.%m.%d"),
        "<TIME>": times.strftime("%H:%M:%S"),
        "<OPEN>": 2000.0,
        "<HIGH>": 2001.0,
        "<LOW>": 1999.0,
        "<CLOSE>": 2000.5,
        "<TICKVOL>": 10,
        "<VOL>": 0,
        "<SPREAD>": 20,
    })
    bars.to_csv(bars_path, sep="\t", index=False)
    events = pd.DataFrame({
        "time_utc": ["2024-01-02T00:00:00Z", "2024-01-03T12:00:00Z", "2024-01-05T00:00:00Z"],
        "profile": ["geopolitical_escalation", "macro_policy_hawkish", "inflation_energy_shock"],
        "raw_count": [100, 80, 60],
    })
    events.to_csv(inbox / "manual_current_events.csv", index=False)
    script = Path(__file__).resolve().parents[1] / "app" / "stage166b_historical_current_event_panel_rebuild.py"
    out = subprocess.check_output([
        sys.executable, str(script),
        "--root", str(root),
        "--bars-m5", str(bars_path),
        "--event-inbox", str(inbox),
        "--min-panel-rows", "10",
        "--min-train-active-event-bars", "1",
        "--holdout-pct", "0.20",
    ], text=True)
    summary = json.loads(out)
    assert summary["status"] == "STAGE166B_COMPLETE_HISTORICAL_EVENT_PANEL_REBUILD_READY"
    assert Path(summary["outputs"]["current_event_intraday_panel_csv"]).exists()
    assert summary["event_panel_health"]["panel_rows"] >= 10
    assert summary["event_panel_health"]["train_active_event_bars"] >= 1
