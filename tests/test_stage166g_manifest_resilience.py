import csv
import json
import subprocess
import sys
from pathlib import Path


POINT_FIELDS = [
    "time_bucket_utc", "profile", "event_count", "gold_long_pressure", "gold_short_pressure",
    "geopolitical_escalation_score", "deescalation_score", "macro_policy_hawkish_score",
    "macro_policy_dovish_score", "inflation_energy_shock_score", "market_stress_score",
    "central_bank_gold_score", "source",
]
STATUS_FIELDS = [
    "profile", "start_utc", "end_utc", "ok", "bytes", "point_count", "error",
    "json_fallback_ok", "json_fallback_bytes", "json_fallback_error", "url",
]


def write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_store(tmp_path: Path, manifest_text):
    prior = tmp_path / "prior"
    incoming = tmp_path / "incoming"
    out = tmp_path / "out"
    prior.mkdir(parents=True)
    if manifest_text is not None:
        (prior / "stage166g_persistent_manifest.json").write_text(manifest_text, encoding="utf-8")
    write_csv(incoming / "stage166f_gdelt_points.csv", [], POINT_FIELDS)
    write_csv(
        incoming / "stage166f_fetch_status.csv",
        [{
            "profile": "market_stress",
            "start_utc": "2026-07-13T00:00:00Z",
            "end_utc": "2026-07-14T00:00:00Z",
            "ok": "False",
            "error": "HTTP 429",
        }],
        STATUS_FIELDS,
    )
    script = Path(__file__).parents[1] / "app" / "stage166g_gdelt_persistent_store.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--prior-dir", str(prior), "--incoming-dir", str(incoming), "--out-dir", str(out)],
        text=True,
        capture_output=True,
    )
    return cp, json.loads((out / "stage166g_persistent_manifest.json").read_text()) if cp.returncode == 0 else None


def test_empty_prior_manifest_is_ignored(tmp_path):
    cp, manifest = run_store(tmp_path, "")
    assert cp.returncode == 0, cp.stderr
    assert manifest["prior_manifest_read"]["reason"] == "EMPTY_FILE_IGNORED"
    assert manifest["failed_task_count"] == 1


def test_malformed_prior_manifest_is_ignored(tmp_path):
    cp, manifest = run_store(tmp_path, "{not-json")
    assert cp.returncode == 0, cp.stderr
    assert manifest["prior_manifest_read"]["reason"] == "INVALID_JSON_IGNORED"


def test_valid_prior_manifest_is_used(tmp_path):
    cp, manifest = run_store(tmp_path, json.dumps({"valid_start_utc": "2026-07-01T00:00:00Z"}))
    assert cp.returncode == 0, cp.stderr
    assert manifest["prior_manifest_read"]["ok"] is True
    assert manifest["valid_start_utc"] == "2026-07-01T00:00:00Z"
