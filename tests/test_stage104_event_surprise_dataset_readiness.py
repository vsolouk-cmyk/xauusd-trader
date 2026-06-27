#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from app.stage104_event_surprise_dataset_readiness import main


def write_events(path: Path, rows: int = 160) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = date(2015, 1, 1)
    events = ["CPI", "Nonfarm Payrolls", "FOMC Rate Decision", "ISM Manufacturing PMI"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "time", "currency", "impact", "event", "actual", "forecast", "previous"])
        w.writeheader()
        for i in range(rows):
            ev = events[i % len(events)]
            d = start + timedelta(days=i * 7)
            base = 100 + (i % 20)
            actual = base + ((i % 5) - 2)
            forecast = base
            w.writerow({
                "date": d.isoformat(),
                "time": "13:30",
                "currency": "USD",
                "impact": "High",
                "event": ev,
                "actual": str(actual),
                "forecast": str(forecast),
                "previous": str(base - 1),
            })


def test_stage104_builds_ready_event_dataset() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_events(root / "data" / "external_frontiers" / "raw_events" / "us_calendar_events.csv", 220)
        cfg = {
            "event_search_paths": ["data/external_frontiers/raw_events"],
            "event_patterns": ["*.csv"],
            "ignore_path_fragments": [],
            "output_data_dir": "data/external_frontiers",
            "template_dir": "data/frontier_templates",
            "assume_naive_timezone": "UTC",
            "accepted_event_types": ["CPI", "NFP", "FOMC", "ISM"],
            "min_impact_rank": 0,
            "event_z_window": 20,
            "event_z_min_periods": 5,
            "min_event_rows": 100,
            "min_accepted_rows": 80,
            "min_zscore_non_null": 20,
        }
        cfg_path = root / "configs" / "stage104_event_surprise_dataset_readiness.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        rc = main(["--root", str(root), "--config", str(cfg_path), "--out", "reports/stage104"])
        assert rc == 0
        summary = json.loads((root / "reports" / "stage104" / "stage104_event_surprise_dataset_readiness_summary.json").read_text())
        assert summary["decision"] == "STAGE104_EVENT_SURPRISE_DATASET_READY_FOR_STAGE105_THESIS_DISCOVERY_NO_ORDER"
        assert summary["normalized_rows"] == 220
        assert summary["zscore_non_null"] > 20
        normalized = root / "data" / "external_frontiers" / "event_surprise_normalized.csv"
        assert normalized.exists()
        text = normalized.read_text(encoding="utf-8")
        assert "surprise_z_asof" in text
        assert "NFP" in text


if __name__ == "__main__":
    test_stage104_builds_ready_event_dataset()
    print("Stage104 tests passed")
