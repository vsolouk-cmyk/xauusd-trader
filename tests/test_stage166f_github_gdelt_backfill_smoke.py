import json
import subprocess
import sys
from pathlib import Path


def test_stage166f_skip_network_smoke(tmp_path):
    script = Path(__file__).resolve().parents[1] / "app" / "stage166f_github_gdelt_backfill.py"
    out_dir = tmp_path / "out"
    cmd = [
        sys.executable,
        str(script),
        "fetch",
        "--output-dir",
        str(out_dir),
        "--start-date",
        "2026-01-01",
        "--end-date",
        "2026-01-03",
        "--chunk-days",
        "1",
        "--max-workers",
        "1",
        "--max-queries",
        "2",
        "--skip-network",
    ]
    res = subprocess.run(cmd, check=True, text=True, capture_output=True)
    data = json.loads(res.stdout)
    assert data["stage"] == "Stage166F_GITHUB_GDELT_BACKFILL"
    assert (out_dir / "stage166f_fetch_status.csv").exists()
    assert (out_dir / "stage166f_current_event_intraday_panel.csv").exists()
    assert data["task_count"] == 2
