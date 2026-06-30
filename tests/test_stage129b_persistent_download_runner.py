from pathlib import Path
import importlib.util
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

def test_existing_valid_file_is_skipped(tmp_path):
    mod = load_module(ROOT / "scripts/download_xauusd_official_data_batch.py", "download_runner")
    out = tmp_path / "fred_macro" / "DFII10.csv"
    out.parent.mkdir(parents=True)
    out.write_text("DATE,DFII10\n2024-01-01,1.5\n", encoding="utf-8")
    result = mod.curl_download("https://example.invalid/should-not-run.csv", out)
    assert result["status"] == "SKIPPED_EXISTING_VALID"
    assert result["size_bytes"] > 0

def test_force_refresh_dry_run_does_not_skip(tmp_path):
    mod = load_module(ROOT / "scripts/download_xauusd_official_data_batch.py", "download_runner_force")
    out = tmp_path / "fred_macro" / "DFII10.csv"
    out.parent.mkdir(parents=True)
    out.write_text("DATE,DFII10\n2024-01-01,1.5\n", encoding="utf-8")
    result = mod.curl_download("https://example.invalid/should-not-run.csv", out, dry_run=True, force_refresh=True)
    assert result["status"] == "DRY_RUN"

def test_pipeline_accepts_persistence_flags():
    cp = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_xauusd_fundamental_unify_normalize_pipeline.py"), "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert cp.returncode == 0
    assert "--force-refresh" in cp.stdout
    assert "--refresh-stale-hours" in cp.stdout
