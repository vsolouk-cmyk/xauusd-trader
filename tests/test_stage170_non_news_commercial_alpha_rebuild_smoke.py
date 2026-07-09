import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_stage170_smoke(tmp_path: Path):
    root = tmp_path
    bars_path = tmp_path / "bars.tsv"
    rows = []
    start = pd.Timestamp("2025-01-01 00:00:00")
    price = 2000.0
    for i in range(1200):
        t = start + pd.Timedelta(minutes=5*i)
        drift = 0.03 if (i % 100) < 60 else -0.02
        price += drift
        high = price + 0.4
        low = price - 0.4
        rows.append([t.strftime("%Y.%m.%d"), t.strftime("%H:%M:%S"), price-0.1, high, low, price, 100, 0, 25])
    pd.DataFrame(rows, columns=["<DATE>","<TIME>","<OPEN>","<HIGH>","<LOW>","<CLOSE>","<TICKVOL>","<VOL>","<SPREAD>"]).to_csv(bars_path, sep="\t", index=False)
    ev_path = tmp_path / "event.csv"
    ev = pd.DataFrame({
        "time_bucket_utc": pd.date_range("2025-01-01", periods=120, freq="1h", tz="UTC"),
        "shock_abs": [0, 0, 1000, 0] * 30,
        "gold_long_pressure": [0, 0, 800, 0] * 30,
        "gold_short_pressure": [0] * 120,
    })
    ev.to_csv(ev_path, index=False)
    script = Path(__file__).resolve().parents[1] / "app" / "stage170_non_news_commercial_alpha_rebuild.py"
    subprocess.check_call([
        sys.executable, str(script),
        "--root", str(root),
        "--bars-m5", str(bars_path),
        "--event-panel", str(ev_path),
        "--timestamp-shift-hours", "0",
        "--min-train-events", "5",
        "--min-holdout-events", "2",
    ])
    summary_path = root / "reports" / "stage170_non_news_commercial_alpha_rebuild" / "stage170_non_news_commercial_alpha_rebuild_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text())
    assert summary["order_routing_allowed"] is False
    assert summary["demo_release_allowed"] is False
    assert summary["evaluation_context"]["score_count"] > 0
    assert (root / "reports" / "stage170_non_news_commercial_alpha_rebuild" / "stage170_decision.md").exists()
