from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_stage103_archives_then_removes_only_superseded(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text("", encoding="utf-8")
    for d in ["app", "configs", "docs", "tests"]:
        (root / d).mkdir()
    # Superseded: should be archived/removed.
    (root / "app" / "stage80_old.py").write_text("print('old')\n", encoding="utf-8")
    (root / "configs" / "stage98_old.json").write_text("{}\n", encoding="utf-8")
    # Preserved operational.
    (root / "app" / "stage99_unified_observer_cot_expansion.py").write_text("print('keep')\n", encoding="utf-8")
    (root / "configs" / "stage100_daily_unified_cot_observer_combo.json").write_text("{}\n", encoding="utf-8")
    # Non-stage file untouched.
    (root / "app" / "common_loader.py").write_text("x=1\n", encoding="utf-8")

    cfg = {
        "archive_root": "_local_archive/source_stage_archives",
        "source_dirs": ["app", "configs", "docs", "tests"],
        "stage_filename_regex": "stage([0-9]{1,3})[a-zA-Z0-9_\\-]*",
        "preserve_stage_numbers": [67, 95, 99, 100, 103],
        "preserve_name_contains": ["stage99_unified_observer_cot_expansion", "stage100_daily_unified_cot_observer_combo", "stage103_source_stage_local_archiver"],
        "archive_stage_min": 1,
        "archive_stage_max": 102,
        "append_gitignore": True,
        "gitignore_block": "# BEGIN XAUUSD local source archives - Stage103\n_local_archive/\n*.archive.zip\n# END XAUUSD local source archives - Stage103\n",
        "hard_blocks": ["NO_DELETE_WITHOUT_ARCHIVE"],
    }
    cfg_path = root / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    out = root / "reports" / "stage103"
    script = Path(__file__).resolve().parents[1] / "app" / "stage103_source_stage_local_archiver.py"
    cp = subprocess.run([sys.executable, str(script), "--root", str(root), "--config", str(cfg_path), "--out", str(out), "--apply"], text=True, capture_output=True)
    assert cp.returncode == 0, cp.stderr + cp.stdout
    assert not (root / "app" / "stage80_old.py").exists()
    assert not (root / "configs" / "stage98_old.json").exists()
    assert (root / "app" / "stage99_unified_observer_cot_expansion.py").exists()
    assert (root / "configs" / "stage100_daily_unified_cot_observer_combo.json").exists()
    assert (root / "app" / "common_loader.py").exists()
    archives = list((root / "_local_archive" / "source_stage_archives").glob("*.archive.zip"))
    assert len(archives) == 1
    summary = json.loads((out / "stage103_source_stage_local_archiver_summary.json").read_text(encoding="utf-8"))
    assert summary["archive_result"]["verified"] is True
    assert summary["archive_result"]["removed_file_count"] == 2
