#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="stage94_test_"))
    for p in [
        root / "app",
        root / "configs",
        root / "data" / "frontier_raw" / "cot",
        root / "data" / "frontier_raw" / "events",
    ]:
        p.mkdir(parents=True, exist_ok=True)

    src_root = Path(__file__).resolve().parents[1]
    (root / "app" / "stage94_cot_event_frontier_dataset_builder.py").write_text(
        (src_root / "app" / "stage94_cot_event_frontier_dataset_builder.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    cot_rows = []
    base = pd.Timestamp("2018-01-02")
    for i in range(70):
        cot_rows.append({
            "report_date_as_yyyy_mm_dd": (base + pd.Timedelta(days=7*i)).strftime("%Y-%m-%d"),
            "m_money_positions_long_all": 100000 + i * 100,
            "m_money_positions_short_all": 75000 - i * 50,
            "open_interest_all": 250000 + i * 500,
        })
    pd.DataFrame(cot_rows).to_csv(root / "data" / "frontier_raw" / "cot" / "gold_cot.csv", index=False)

    event_rows = []
    base_dt = pd.Timestamp("2020-01-01 13:30:00")
    types = ["CPI", "NFP"]
    for i in range(80):
        event_rows.append({
            "event_time_utc": (base_dt + pd.Timedelta(days=30*i)).strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": types[i % 2],
            "actual": 100 + i * 0.1,
            "forecast": 99 + i * 0.08,
            "previous": 98 + i * 0.07,
        })
    pd.DataFrame(event_rows).to_csv(root / "data" / "frontier_raw" / "events" / "events.csv", index=False)

    cfg = {
        "cot_search_paths": ["data/frontier_raw/cot"],
        "cot_patterns": ["*.csv"],
        "event_search_paths": ["data/frontier_raw/events"],
        "event_patterns": ["*.csv"],
        "output_data_dir": "data/external_frontiers",
        "template_dir": "data/frontier_templates",
        "min_cot_rows": 50,
        "min_event_rows": 50,
        "cot_z_min_periods": 10,
        "event_z_min_periods": 5,
    }
    (root / "configs" / "stage94_cot_event_frontier_dataset_builder.json").write_text(json.dumps(cfg), encoding="utf-8")

    cmd = [
        sys.executable,
        str(root / "app" / "stage94_cot_event_frontier_dataset_builder.py"),
        "--root", str(root),
        "--config", "configs/stage94_cot_event_frontier_dataset_builder.json",
        "--out", "reports/stage94",
    ]
    subprocess.run(cmd, check=True)

    summary = json.loads((root / "reports" / "stage94" / "stage94_cot_event_frontier_dataset_builder_summary.json").read_text())
    assert summary["status"] == "STAGE94_COMPLETE_NO_PROMOTION"
    assert summary["cot_dataset_ready"] is True
    assert summary["event_dataset_ready"] is True
    assert "NO_ORDER_AUTHORIZATION_FROM_STAGE94" in summary["hard_blocks"]
    assert (root / "data" / "external_frontiers" / "cot_positioning_normalized.csv").exists()
    assert (root / "data" / "external_frontiers" / "event_surprise_normalized.csv").exists()
    print("Stage94 tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
