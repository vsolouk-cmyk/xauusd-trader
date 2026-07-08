from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

from app.stage162_macro_data_freshness_triage import probe_file, diagnose


def test_probe_file_detects_latest_date(tmp_path: Path):
    p = tmp_path / "macro.csv"
    pd.DataFrame({"date": ["2026-07-07", "2026-07-08"], "value": [1, 2]}).to_csv(p, index=False)
    probe = probe_file("macro", p, True, 5, datetime(2026, 7, 8, tzinfo=timezone.utc))
    assert probe.exists
    assert probe.row_count == 2
    assert probe.selected_date_column == "date"
    assert probe.freshness_status == "FRESH"


def test_probe_file_flags_stale(tmp_path: Path):
    p = tmp_path / "macro.csv"
    pd.DataFrame({"observation_date": ["2026-06-01"], "value": [1]}).to_csv(p, index=False)
    probe = probe_file("macro", p, True, 5, datetime(2026, 7, 8, tzinfo=timezone.utc))
    assert probe.freshness_status == "STALE_REQUIRED"


def test_diagnose_requires_all_required_fresh(tmp_path: Path):
    p1 = tmp_path / "fresh.csv"
    p2 = tmp_path / "stale.csv"
    pd.DataFrame({"date": ["2026-07-08"], "value": [1]}).to_csv(p1, index=False)
    pd.DataFrame({"date": ["2026-06-01"], "value": [1]}).to_csv(p2, index=False)
    now = datetime(2026, 7, 8, tzinfo=timezone.utc)
    probes = [probe_file("fresh", p1, True, 5, now), probe_file("stale", p2, True, 5, now)]
    decision, severity, recommended, issues = diagnose(probes)
    assert decision == "STAGE162_MACRO_CONTENT_STALE_OR_INCOMPLETE_REPAIR_REQUIRED"
    assert severity == "HIGH"
    assert issues
