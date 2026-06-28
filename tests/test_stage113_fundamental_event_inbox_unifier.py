import csv
import json
import subprocess
import sys
from pathlib import Path


def test_stage113_creates_inbox_manifest_and_gitignore(tmp_path):
    root = tmp_path / "repo"
    downloads = tmp_path / "Downloads"
    root.mkdir()
    downloads.mkdir()
    (root / ".gitignore").write_text("reports/\n", encoding="utf-8")

    inbox = downloads / "xauusd_fundamental_event_inbox"
    (inbox / "events" / "bls").mkdir(parents=True)
    (inbox / "cot" / "cftc").mkdir(parents=True)
    (inbox / "events" / "bls" / "bls_cpi_calendar.csv").write_text("date,event\n2026-01-01,CPI\n", encoding="utf-8")
    (inbox / "cot" / "cftc" / "cftc_gold_cot.csv").write_text("date,value\n2026-01-01,1\n", encoding="utf-8")

    script = Path("app/stage113_fundamental_event_inbox_unifier.py")
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(root),
            "--downloads-dir",
            str(downloads),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "STAGE113_COMPLETE_INTAKE_READY_NO_PROMOTION"
    assert payload["input_files"] == 2
    assert payload["copied_files"] == 2

    manifest = root / "data" / "fundamental_event_inbox" / "manifests" / "stage113_fundamental_event_file_manifest.csv"
    assert manifest.exists()
    rows = list(csv.DictReader(manifest.open()))
    assert len(rows) == 2
    assert {r["source_bucket"] for r in rows} == {"events_bls", "cot_cftc"}

    gi = (root / ".gitignore").read_text(encoding="utf-8")
    assert "data/fundamental_event_inbox/raw/" in gi
    assert "data/economic_events_raw/" in gi
