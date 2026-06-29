from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage123_static_replay_shadow_observer_package.py"
spec = importlib.util.spec_from_file_location("stage123", MODULE_PATH)
stage123 = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(stage123)


def test_stage123_passes_report_only_static_replay(tmp_path: Path) -> None:
    root = tmp_path
    stage122 = root / "reports/stage122_shadow_observer_package_review"
    stage121 = root / "reports/stage121_dry_run_observer_preflight"
    stage122.mkdir(parents=True)
    stage121.mkdir(parents=True)

    pd.DataFrame([
        {
            "observer_design_rule_id": "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN",
            "source_rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF",
            "stage122_decision": "STAGE123_STATIC_REPLAY_QUEUE",
            "shadow_observer_rule_id": "S122_SHADOW_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN",
            "bucket": "PRIMARY_DESIGN",
            "readiness_score": 85,
            "candidate_only": True,
            "raw_signal_rows": 1976,
            "spaced_signal_rows": 5,
            "event_spacing_hours": 120,
            "stage116_dxy_fallback_active": True,
            "stage116_direct_dxy_valid": False,
            "stage116_spdr_status": "VALIDATED_CANDIDATE",
            "active_update_allowed": False,
            "report_only_shadow_package": True,
            "stage123_task": "STATIC_REPLAY_SHADOW_OBSERVER_PACKAGE_ONLY",
            "min_spacing_hours": 120,
            "allowed_output_scope": "reports_only",
            "blocked_outputs": "active_observer;observer_bridge;MQL5/Files;paper_order;live_order",
        }
    ]).to_csv(stage122 / "stage122_stage123_static_replay_queue.csv", index=False)

    pd.DataFrame([
        {
            "observer_design_rule_id": "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN",
            "source_rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF",
            "utc_time": f"{2020+i}-01-01T00:00:00Z",
            "stage117_split": "tail_forward_proxy" if i >= 3 else "validation",
            "fwd_ret_bps_h120": 50 + i,
        }
        for i in range(5)
    ]).to_csv(stage121 / "stage121_dry_run_signal_events.csv", index=False)
    (stage122 / "stage122_shadow_observer_package_review_summary.json").write_text(json.dumps({"status": "OK", "stage123_static_replay_candidate_count": 1}))
    (stage121 / "stage121_dry_run_observer_preflight_summary.json").write_text(json.dumps({"status": "OK", "dry_run_signal_event_rows": 5}))

    summary = stage123.run(root)
    assert summary["status"] == stage123.STATUS_OK
    assert summary["pass_static_replay_count"] == 1
    assert summary["stage124_shadow_telemetry_candidate_count"] == 1
    assert (root / "reports/stage123_static_replay_shadow_observer_package/stage123_selected_for_stage124.csv").exists()


def test_stage123_blocks_active_update_contract(tmp_path: Path) -> None:
    root = tmp_path
    stage122 = root / "reports/stage122_shadow_observer_package_review"
    stage121 = root / "reports/stage121_dry_run_observer_preflight"
    stage122.mkdir(parents=True)
    stage121.mkdir(parents=True)

    pd.DataFrame([
        {
            "observer_design_rule_id": "R",
            "source_rule_id": "S",
            "stage122_decision": "STAGE123_STATIC_REPLAY_QUEUE",
            "shadow_observer_rule_id": "SHADOW_R",
            "active_update_allowed": True,
            "report_only_shadow_package": True,
            "stage123_task": "STATIC_REPLAY_SHADOW_OBSERVER_PACKAGE_ONLY",
            "min_spacing_hours": 120,
            "allowed_output_scope": "reports_only",
            "blocked_outputs": "active_observer;observer_bridge;MQL5/Files;paper_order;live_order",
        }
    ]).to_csv(stage122 / "stage122_stage123_static_replay_queue.csv", index=False)
    pd.DataFrame([{"observer_design_rule_id": "R", "source_rule_id": "S", "utc_time": "2024-01-01T00:00:00Z", "fwd_ret_bps_h120": 1}]).to_csv(stage121 / "stage121_dry_run_signal_events.csv", index=False)

    summary = stage123.run(root)
    assert summary["status"] == stage123.STATUS_BLOCKED
    assert summary["blocked_static_replay_count"] == 1
