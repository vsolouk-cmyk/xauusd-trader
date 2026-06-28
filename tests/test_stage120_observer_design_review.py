from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.stage120_observer_design_review import run


def test_stage120_builds_preflight_queue(tmp_path: Path) -> None:
    root = tmp_path
    s119 = root / "reports" / "stage119_portfolio_observer_readiness_review"
    s117 = root / "reports" / "stage117_segmented_macro_cot_dollar_discovery"
    s119.mkdir(parents=True)
    s117.mkdir(parents=True)

    pd.DataFrame([
        {
            "rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF",
            "description": "SPDR support with macro relief, candidate-only",
            "stage118_audit_decision": "HARD_PASS_STAGE119_AUDIT_QUEUE",
            "candidate_only": True,
            "observer_readiness": "PRIMARY_OBSERVER_REVIEW_CANDIDATE_NO_UPDATE",
            "readiness_score": 85.0,
            "validation_cost10_mean_bps": 62.4,
            "validation_cost10_hit_rate": 0.62,
            "tail_cost10_mean_bps": 97.5,
            "tail_cost10_hit_rate": 0.76,
            "raw_all_events": 1976,
            "stage116_dxy_fallback_active": True,
            "stage116_direct_dxy_valid": False,
            "stage116_spdr_status": "VALIDATED_CANDIDATE",
        },
        {
            "rule_id": "S117_01_RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED",
            "description": "watch",
            "stage118_audit_decision": "WATCH_STAGE119_ONLY_WITH_EXTRA_CONFIRMATION",
            "candidate_only": False,
            "observer_readiness": "WATCH_ONLY_EXTRA_CONFIRMATION_NO_UPDATE",
            "readiness_score": 32.0,
            "tail_cost10_mean_bps": 3.4,
            "tail_cost10_hit_rate": 0.52,
            "stage116_dxy_fallback_active": True,
            "stage116_direct_dxy_valid": False,
            "stage116_spdr_status": "VALIDATED_CANDIDATE",
        },
    ]).to_csv(s119 / "stage119_observer_readiness_queue.csv", index=False)

    pd.DataFrame([
        {"rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF", "feature": "spdr_value_chg_20d", "full_coverage_pct": 100, "event_coverage_pct": 100},
        {"rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF", "feature": "dollar_pressure_chg_20d", "full_coverage_pct": 100, "event_coverage_pct": 100},
        {"rule_id": "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF", "feature": "real_yield_10y_chg_20d", "full_coverage_pct": 75.6, "event_coverage_pct": 100},
    ]).to_csv(s119 / "stage119_feature_coverage_review.csv", index=False)
    pd.DataFrame([{"rule_id_a":"a", "rule_id_b":"b", "raw_hourly_jaccard":0.1}]).to_csv(s119 / "stage119_portfolio_overlap_review.csv", index=False)
    (s119 / "stage119_portfolio_observer_readiness_review_summary.json").write_text(json.dumps({
        "stage116_context": {
            "direct_dxy_valid": False,
            "dxy_fallback_active": True,
            "spdr_gld_status": "VALIDATED_CANDIDATE",
        }
    }))
    pd.DataFrame([{ 
        "spdr_value_chg_20d_q75": 251933.5,
        "dollar_pressure_chg_20d_q50": 0.1349,
        "real_yield_10y_chg_20d_q50": 0.03,
        "real_yield_10y_chg_20d_q25": -0.12,
        "dollar_pressure_chg_20d_q25": -1.0633,
    }]).to_csv(s117 / "stage117_selection_thresholds.csv", index=False)

    summary = run(root)
    assert summary["stage121_preflight_candidate_count"] == 1
    assert summary["watch_only_count"] == 1
    assert "NO_OBSERVER_UPDATE_FROM_STAGE120" in summary["hard_blocks"]
    preflight = pd.read_csv(root / "reports" / "stage120_observer_design_review" / "stage120_stage121_preflight_queue.csv")
    assert preflight.iloc[0]["source_rule_id"] == "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF"
    assert "spdr_value_chg_20d" in preflight.iloc[0]["condition_text"]
