from pathlib import Path
import json
from app.stage159_locked_family_repair_discovery import main


def test_stage159b_writes_failure_artifacts(tmp_path):
    rc = main([
        "--root", str(tmp_path),
        "--bars-m5", str(tmp_path / "missing_bars.csv"),
        "--score-csv", str(tmp_path / "missing_scores.csv"),
    ])
    assert rc == 2
    out = tmp_path / "reports" / "stage159_locked_family_repair_discovery"
    summary = out / "stage159_locked_family_repair_discovery_summary.json"
    assert summary.exists()
    data = json.loads(summary.read_text())
    assert data["decision"] == "STAGE159C_REPAIR_DISCOVERY_RUN_FAILED_NO_DEMO_RELEASE"
    assert (out / "stage159_locked_family_shortlist.csv").exists()
    assert (out / "stage159_family_repair_summary.csv").exists()
