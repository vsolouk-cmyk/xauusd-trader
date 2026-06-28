import json
import csv
from pathlib import Path

from app.stage122_shadow_observer_package_review import run


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def test_stage122_builds_stage123_queue(tmp_path):
    root = tmp_path
    s121 = root / "reports" / "stage121_dry_run_observer_preflight"
    s120 = root / "reports" / "stage120_observer_design_review"
    s121.mkdir(parents=True)
    s120.mkdir(parents=True)

    (s121 / "stage121_dry_run_observer_preflight_summary.json").write_text(json.dumps({
        "status": "STAGE121_COMPLETE_DRY_RUN_PREFLIGHT_READY_NO_UPDATE",
        "decision": "STAGE121_DRY_RUN_PREFLIGHT_REPORT_READY_NO_OBSERVER_UPDATE",
        "pass_preflight_count": 1
    }), encoding="utf-8")

    row = {
        "observer_design_rule_id": "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN",
        "source_rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF",
        "preflight_status": "PASS_DRY_RUN_PREFLIGHT",
        "raw_signal_rows": "1976",
        "spaced_signal_rows": "50",
        "expected_raw_all_events": "1976",
        "raw_event_count_delta_pct": "0.0",
        "missing_required_features": "",
        "condition_parse_count": "3",
        "event_spacing_hours": "120",
        "candidate_only": "True",
        "stage116_dxy_fallback_active": "True",
        "stage116_direct_dxy_valid": "False",
        "stage116_spdr_status": "VALIDATED_CANDIDATE",
        "readiness_score": "85",
        "bucket": "PRIMARY_DESIGN"
    }
    write_csv(s121 / "stage121_preflight_metrics.csv", [row])
    write_csv(s121 / "stage121_selected_for_stage122.csv", [{"observer_design_rule_id": row["observer_design_rule_id"]}])
    (s120 / "stage120_observer_rule_specs_draft.json").write_text(json.dumps({
        "rules": [{"observer_design_rule_id": row["observer_design_rule_id"], "conditions": ["a", "b", "c"]}]
    }), encoding="utf-8")

    summary = run(root)
    assert summary["stage123_static_replay_candidate_count"] == 1
    assert summary["watch_or_block_count"] == 0
    assert summary["decision"] == "STAGE122_STAGE123_STATIC_REPLAY_QUEUE_READY_NO_UPDATE"
    assert (root / "reports" / "stage122_shadow_observer_package_review" / "stage122_stage123_static_replay_queue.csv").exists()


def test_stage122_blocks_low_readiness(tmp_path):
    root = tmp_path
    s121 = root / "reports" / "stage121_dry_run_observer_preflight"
    s120 = root / "reports" / "stage120_observer_design_review"
    s121.mkdir(parents=True)
    s120.mkdir(parents=True)
    (s121 / "stage121_dry_run_observer_preflight_summary.json").write_text(json.dumps({"pass_preflight_count": 1}), encoding="utf-8")
    write_csv(s121 / "stage121_preflight_metrics.csv", [{
        "observer_design_rule_id": "R1",
        "source_rule_id": "S1",
        "preflight_status": "PASS_DRY_RUN_PREFLIGHT",
        "raw_signal_rows": "100",
        "spaced_signal_rows": "10",
        "expected_raw_all_events": "100",
        "raw_event_count_delta_pct": "0",
        "missing_required_features": "",
        "condition_parse_count": "1",
        "event_spacing_hours": "120",
        "candidate_only": "False",
        "stage116_spdr_status": "VALIDATED_CANDIDATE",
        "readiness_score": "20",
        "bucket": "PRIMARY_DESIGN"
    }])
    summary = run(root)
    assert summary["stage123_static_replay_candidate_count"] == 0
    assert summary["watch_or_block_count"] == 1
