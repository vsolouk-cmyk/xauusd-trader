from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.stage160_macro_pipeline_readiness_audit import main as stage160_main
from app.stage161_macro_aware_candidate_classifier import main as stage161_main


def _write_feature(path: Path, rows=40, cols=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = cols or {"date": pd.date_range("2026-01-01", periods=rows, freq="D"), "value": range(rows)}
    pd.DataFrame(cols).to_csv(path, index=False)


def test_stage160_writes_failure_safe_outputs(tmp_path: Path):
    root = tmp_path
    feature_dir = root / "data/fundamental_event_inbox/features"
    # Create required files above row thresholds used in this temporary test via small files and relaxed thresholds is not exposed,
    # so the decision may warn/block. The critical contract is that outputs are written and no exception is raised.
    for name in [
        "stage115_daily_macro_feature_panel.csv",
        "stage115_fred_macro_daily_wide.csv",
        "stage115_cot_gold_weekly_features.csv",
        "stage115_unified_event_calendar_features.csv",
        "stage116_validated_dollar_pressure.csv",
        "stage117_joined_macro_cot_dollar_h1_research_dataset.csv",
    ]:
        _write_feature(feature_dir / name, rows=120)
    stage160_main(["--root", str(root), "--max-mtime-age-hours", "999999"])
    summary = root / "reports/stage160_macro_pipeline_readiness_audit/stage160_macro_pipeline_readiness_audit_summary.json"
    inv = root / "reports/stage160_macro_pipeline_readiness_audit/stage160_macro_feature_inventory.csv"
    assert summary.exists()
    assert inv.exists()
    payload = json.loads(summary.read_text())
    assert payload["stage"] == "Stage160_MACRO_PIPELINE_READINESS_AUDIT"
    assert payload["order_routing_allowed"] is False


def test_stage161_classifies_macro_supported_candidate(tmp_path: Path):
    root = tmp_path
    feature_dir = root / "data/fundamental_event_inbox/features"
    feature_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2026-05-15", periods=60, freq="D", tz="UTC")
    # DXY and real yield falling => tailwind for long gold momentum candidates.
    pd.DataFrame({"date": dates, "dxy": list(range(120, 60, -1)), "DFII10": [2.0 - i * 0.01 for i in range(60)]}).to_csv(
        feature_dir / "stage116_validated_dollar_pressure.csv", index=False
    )
    pd.DataFrame({"date": dates, "VIXCLS": [20] * 60}).to_csv(feature_dir / "stage115_daily_macro_feature_panel.csv", index=False)
    pd.DataFrame({"date": dates, "DGS10": [4.0] * 60}).to_csv(feature_dir / "stage115_fred_macro_daily_wide.csv", index=False)
    pd.DataFrame({"event_date": ["2025-01-01"], "event_name": ["old event"]}).to_csv(
        feature_dir / "stage115_unified_event_calendar_features.csv", index=False
    )
    out160 = root / "reports/stage160_macro_pipeline_readiness_audit"
    out160.mkdir(parents=True, exist_ok=True)
    (out160 / "stage160_macro_pipeline_readiness_audit_summary.json").write_text(
        json.dumps({"decision": "STAGE160_MACRO_CORE_READY_WITH_WARNINGS_FOR_CLASSIFICATION_ONLY"})
    )
    s159 = root / "reports/stage159_locked_family_repair_discovery"
    s159.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"rule_id": ["D150C_M5_ret_24h_bps_GEQ65__trend_8_20_bps_GEQ65"], "mean_bps": [5.0]}).to_csv(
        s159 / "stage159_locked_family_shortlist.csv", index=False
    )
    pd.DataFrame({"family_key": ["D150C_M5_ret_24h_bps__trend_8_20_bps"]}).to_csv(
        s159 / "stage159_family_repair_summary.csv", index=False
    )
    stage161_main(["--root", str(root)])
    summary = json.loads((root / "reports/stage161_macro_aware_candidate_classifier/stage161_macro_aware_candidate_classifier_summary.json").read_text())
    assert summary["candidate_row_count"] == 1
    assert summary["macro_label_counts"].get("MACRO_SUPPORTED") == 1
    assert summary["demo_release_allowed"] is False


def test_stage161_event_blackout_blocks(tmp_path: Path):
    root = tmp_path
    feature_dir = root / "data/fundamental_event_inbox/features"
    feature_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2026-05-15", periods=60, freq="D", tz="UTC")
    pd.DataFrame({"date": dates, "dxy": list(range(120, 60, -1)), "DFII10": [2.0 - i * 0.01 for i in range(60)]}).to_csv(
        feature_dir / "stage116_validated_dollar_pressure.csv", index=False
    )
    pd.DataFrame({"date": dates, "VIXCLS": [20] * 60}).to_csv(feature_dir / "stage115_daily_macro_feature_panel.csv", index=False)
    pd.DataFrame({"date": dates, "DGS10": [4.0] * 60}).to_csv(feature_dir / "stage115_fred_macro_daily_wide.csv", index=False)
    pd.DataFrame({"event_date": [dates[-1].date().isoformat()], "event_name": ["FOMC CPI NFP"]}).to_csv(
        feature_dir / "stage115_unified_event_calendar_features.csv", index=False
    )
    out160 = root / "reports/stage160_macro_pipeline_readiness_audit"
    out160.mkdir(parents=True, exist_ok=True)
    (out160 / "stage160_macro_pipeline_readiness_audit_summary.json").write_text(json.dumps({"decision": "OK"}))
    s159 = root / "reports/stage159_locked_family_repair_discovery"
    s159.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"rule_id": ["D150_M5_trend_8_20_bps_GEQ65"]}).to_csv(s159 / "stage159_locked_family_shortlist.csv", index=False)
    stage161_main(["--root", str(root)])
    summary = json.loads((root / "reports/stage161_macro_aware_candidate_classifier/stage161_macro_aware_candidate_classifier_summary.json").read_text())
    assert summary["decision"] == "STAGE161_EVENT_BLACKOUT_ACTIVE_KEEP_FREEZE"
