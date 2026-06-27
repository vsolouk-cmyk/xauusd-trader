from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_stage102_dry_run_and_apply(tmp_path: Path):
    pkg = Path(__file__).resolve().parents[1]
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "reports" / "x").mkdir(parents=True)
    (root / "reports" / "x" / "a.json").write_text("{}")
    (root / "_incoming_stage99").mkdir()
    (root / "_incoming_stage99" / "tmp.txt").write_text("x")
    (root / "app").mkdir()
    (root / "app" / "keep.py").write_text("print('keep')")
    (root / "data" / "external_frontiers").mkdir(parents=True)
    (root / "data" / "external_frontiers" / "cot_positioning_normalized.csv").write_text("a,b\n1,2\n")
    (root / "stage100.zip").write_text("zip")
    out = root / "out"
    cfg = pkg / "configs" / "stage102_repo_runtime_folder_cleaner.json"
    script = pkg / "app" / "stage102_repo_runtime_folder_cleaner.py"

    subprocess.run([sys.executable, str(script), "--root", str(root), "--config", str(cfg), "--out", str(out)], check=True)
    assert (root / "reports" / "x" / "a.json").exists()
    summary = json.loads((out / "stage102_repo_runtime_folder_cleaner_summary.json").read_text())
    assert summary["apply"] is False
    assert summary["candidate_count"] >= 3

    subprocess.run([sys.executable, str(script), "--root", str(root), "--config", str(cfg), "--out", str(out), "--apply"], check=True)
    assert not (root / "reports").exists()
    assert not (root / "_incoming_stage99").exists()
    assert not (root / "stage100.zip").exists()
    assert (root / "app" / "keep.py").exists()
    # Generated data is preserved unless explicitly requested.
    assert (root / "data" / "external_frontiers" / "cot_positioning_normalized.csv").exists()


if __name__ == "__main__":
    test_stage102_dry_run_and_apply(Path("/tmp/stage102_test"))
    print("Stage102 tests passed")
