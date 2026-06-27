#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def write_csv(path: Path, rows: int, step_min: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["utc_time", "open", "high", "low", "close", "volume", "spread"])
        for i in range(rows):
            w.writerow([f"2024-01-01T00:{i%60:02d}:00Z", 2000, 2001, 1999, 2000.5, 10, 12])


def main() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        pkg = Path(__file__).resolve().parents[1]
        (root / "app").mkdir()
        (root / "configs").mkdir()
        (root / "reports/stage90_data_frontier_thesis_router").mkdir(parents=True)
        (root / "reports/stage90_data_frontier_thesis_router/stage90_data_frontier_thesis_router_summary.json").write_text(json.dumps({"decision": "NO_RESIDUAL", "selected_frontier": "FLOW_REFINEMENT"}), encoding="utf-8")
        script = pkg / "app/stage91_intraday_frontier_readiness_router.py"
        config = root / "configs/stage91_intraday_frontier_readiness_router.json"
        write_csv(root / "downloads/amarkets_xauusd_m1.csv", 1000, 1)
        write_csv(root / "downloads/amarkets_xauusd_m5.csv", 1000, 5)
        cfg = {
            "stage90_summary_path": "reports/stage90_data_frontier_thesis_router/stage90_data_frontier_thesis_router_summary.json",
            "repo_data_dirs": ["downloads"],
            "external_csv_paths": ["downloads/amarkets_xauusd_m1.csv", "downloads/amarkets_xauusd_m5.csv"],
            "sqlite_globs": [],
            "minimums": {"m1_min_rows": 500, "m5_min_rows": 500, "m15_min_rows": 500, "h1_min_rows": 500, "min_distinct_timeframes_ready": 2},
            "output_names": {}
        }
        config.write_text(json.dumps(cfg), encoding="utf-8")
        out = root / "reports/stage91"
        result = subprocess.run([sys.executable, str(script), "--root", str(root), "--config", str(config), "--out", str(out)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr + result.stdout
        summary = json.loads((out / "stage91_intraday_frontier_readiness_router_summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "STAGE91_COMPLETE_NO_PROMOTION"
        assert summary["disposition"] == "INTRADAY_FRONTIER_READY_FOR_STAGE92"
        assert summary["csv_read_ok_count"] >= 2
        assert (out / "stage91_intraday_thesis_queue.csv").exists()
        print("Stage91 tests passed")


if __name__ == "__main__":
    main()
