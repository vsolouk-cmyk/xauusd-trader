import json
import subprocess
import sys
from pathlib import Path
import pandas as pd


def test_stage166e_smoke(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    app = Path(__file__).resolve().parents[1] / "app" / "stage166e_event_data_failover_intake.py"
    bars = tmp_path / "bars.csv"
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    rows = []
    price = 2000.0
    for i in range(12*24*10):
        t = start + pd.Timedelta(minutes=5*i)
        price += 0.1
        rows.append({"time_utc": t.isoformat(), "open": price, "high": price+1, "low": price-1, "close": price+0.2, "spread": 20})
    pd.DataFrame(rows).to_csv(bars, index=False)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    manual = inbox / "manual_current_events.csv"
    manual.write_text("timestamp_utc,title,description,source,category,side,impact,confidence,decay_hours\n2026-01-02T00:00:00Z,Military escalation supports gold,missile strike conflict,manual,geopolitical_escalation,LONG,3,0.8,48\n")
    out = subprocess.check_output([
        sys.executable, str(app),
        "--root", str(root),
        "--bars-m5", str(bars),
        "--event-inbox", str(inbox),
        "--write-stage166-compatible-panel",
        "--backup-existing-compatible-panel",
    ], text=True)
    summary = json.loads(out)
    assert summary["status"].startswith("STAGE166E_COMPLETE")
    assert summary["event_counts"]["normalized_events"] >= 1
    assert Path(summary["outputs"]["current_event_intraday_panel_csv"]).exists()
