from pathlib import Path
import json
import tempfile
import pandas as pd

from app.stage166d_offline_event_seed_and_market_implied_shock import run, build_parser


def test_stage166d_smoke(tmp_path: Path):
    root = tmp_path / "repo"
    inbox = tmp_path / "inbox"
    root.mkdir()
    inbox.mkdir()
    # Build synthetic MT5-style M5 bars with a few strong hourly shocks.
    times = pd.date_range("2022-01-01 00:00:00", periods=2000, freq="5min")
    price = 1800.0
    rows = []
    for i, t in enumerate(times):
        if i in {300, 900, 1500}:
            price += 20.0
        elif i in {600, 1200}:
            price -= 18.0
        op = price
        close = price + (0.5 if i % 17 == 0 else -0.2 if i % 13 == 0 else 0.05)
        high = max(op, close) + 0.3
        low = min(op, close) - 0.3
        price = close
        rows.append({"<DATE>": t.strftime("%Y.%m.%d"), "<TIME>": t.strftime("%H:%M:%S"), "<OPEN>": op, "<HIGH>": high, "<LOW>": low, "<CLOSE>": close, "<TICKVOL>": 100, "<VOL>": 0, "<SPREAD>": 20})
    bars = tmp_path / "bars.csv"
    pd.DataFrame(rows).to_csv(bars, sep="\t", index=False)
    manual = inbox / "manual_current_events.csv"
    pd.DataFrame([
        {"event_time_utc": "2022-01-02T00:00:00Z", "event_end_utc": "", "event_title": "test", "event_category": "geopolitical_escalation", "direction": "LONG", "severity_1_5": 4, "confidence_0_1": 0.9, "decay_hours": 24, "source": "test", "notes": ""}
    ]).to_csv(manual, index=False)
    args = build_parser().parse_args([
        "--root", str(root),
        "--bars-m5", str(bars),
        "--event-inbox", str(inbox),
        "--timestamp-shift-hours", "0",
        "--holdout-pct", "0.2",
        "--write-stage166-compatible-panel",
        "--backup-existing-compatible-panel",
        "--min-train-active-event-bars", "10",
        "--min-panel-nonzero-rows", "10",
        "--market-implied-quantile", "0.95",
        "--market-implied-max-events", "50",
    ])
    summary = run(args)
    assert summary["status"].startswith("STAGE166D_COMPLETE")
    assert Path(summary["outputs"]["current_event_intraday_panel_csv"]).exists()
    assert summary["event_panel_health"]["panel_nonzero_shock_rows"] > 0
