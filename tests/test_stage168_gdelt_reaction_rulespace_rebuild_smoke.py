import json
import math
from pathlib import Path
import subprocess
import sys

import pandas as pd


def test_stage168_smoke(tmp_path: Path):
    root = tmp_path / "repo"
    app = root / "app"
    app.mkdir(parents=True)
    src = Path(__file__).resolve().parents[1] / "app" / "stage168_gdelt_reaction_rulespace_rebuild.py"
    dst = app / "stage168_gdelt_reaction_rulespace_rebuild.py"
    dst.write_text(src.read_text())

    times = pd.date_range("2024-01-01", periods=3000, freq="5min", tz="UTC")
    px = []
    p = 2000.0
    for i, _ in enumerate(times):
        # tiny drift plus event-like jump zones
        p += math.sin(i / 20.0) * 0.05
        if 400 < i < 460 or 1400 < i < 1460 or 2300 < i < 2360:
            p += 0.12
        px.append(p)
    bars = pd.DataFrame({
        "time_utc": times,
        "open": px,
        "high": [x + 0.5 for x in px],
        "low": [x - 0.5 for x in px],
        "close": px,
        "spread": 20,
    })
    bars_path = tmp_path / "bars.csv"
    bars.to_csv(bars_path, index=False)

    et = pd.date_range("2024-01-01", periods=260, freq="1h", tz="UTC")
    ev = pd.DataFrame({"time_bucket_utc": et})
    ev["event_count"] = 0
    ev["gold_long_pressure"] = 0.0
    ev["gold_short_pressure"] = 0.0
    ev["shock_abs"] = 0.0
    ev["geopolitical_escalation_score"] = 0.0
    ev["deescalation_score"] = 0.0
    ev["macro_policy_hawkish_score"] = 0.0
    ev["macro_policy_dovish_score"] = 0.0
    ev["inflation_energy_shock_score"] = 0.0
    ev["market_stress_score"] = 0.0
    ev["central_bank_gold_score"] = 0.0
    ev["net_gold_event_pressure"] = 0.0
    # nonzero sparse event hours across train and holdout
    for j in [35,36,37,110,111,112,190,191,192,230,231,232]:
        if j < len(ev):
            ev.loc[j, ["event_count","gold_long_pressure","shock_abs","geopolitical_escalation_score","net_gold_event_pressure"]] = [1, 100, 100, 100, 100]
    ev_path = tmp_path / "events.csv"
    ev.to_csv(ev_path, index=False)

    subprocess.check_call([sys.executable, "-m", "py_compile", str(dst)])
    out = subprocess.check_output([
        sys.executable, str(dst),
        "--root", str(root),
        "--bars-m5", str(bars_path),
        "--event-panel", str(ev_path),
        "--timestamp-shift-hours", "0",
        "--holdout-pct", "0.25",
        "--min-train-active-event-bars", "10",
        "--min-train-events", "1",
        "--min-holdout-events", "1",
        "--min-train-hit-rate", "0",
        "--min-holdout-hit-rate", "0",
        "--min-train-mean-bps", "-999",
        "--min-holdout-mean-bps", "-999",
        "--min-holdout-p10-bps", "-999",
    ], text=True)
    data = json.loads(out)
    assert data["score_count"] > 0
    summary_path = root / "reports" / "stage168_gdelt_reaction_rulespace_rebuild" / "stage168_gdelt_reaction_rulespace_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text())
    assert summary["order_routing_allowed"] is False
    assert summary["demo_release_allowed"] is False
