import json
from pathlib import Path
import pandas as pd

from app.stage121_dry_run_observer_preflight import parse_condition_text, apply_event_spacing, run


def test_parse_condition_text():
    conds = parse_condition_text("a >= 1.5; b <= -2; c == 0")
    assert len(conds) == 3
    assert conds[0].feature == "a"
    assert conds[1].op_text == "<="


def test_apply_event_spacing():
    df = pd.DataFrame({
        "_stage121_timestamp": pd.to_datetime([
            "2024-01-01T00:00:00Z",
            "2024-01-01T01:00:00Z",
            "2024-01-06T01:00:00Z",
        ], utc=True),
        "x": [1, 2, 3],
    })
    spaced = apply_event_spacing(df, 120)
    assert len(spaced) == 2


def test_run_with_minimal_fixture(tmp_path: Path):
    root = tmp_path
    stage120 = root / "reports/stage120_observer_design_review"
    stage117 = root / "reports/stage117_segmented_macro_cot_dollar_discovery"
    stage120.mkdir(parents=True)
    stage117.mkdir(parents=True)

    pd.DataFrame([{
        "observer_design_rule_id": "R1",
        "source_rule_id": "S1",
        "is_stage121_preflight_candidate": True,
        "condition_text": "a >= 1; b <= 2",
        "required_features": "a;b",
        "event_spacing_hours": 120,
        "raw_all_events": 3,
        "candidate_only": True,
    }]).to_csv(stage120 / "stage120_stage121_preflight_queue.csv", index=False)

    pd.DataFrame({
        "utc_time": ["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "2024-01-06T01:00:00Z"],
        "a": [1, 2, 3],
        "b": [1, 1, 1],
    }).to_csv(stage117 / "stage117_selection_rows.csv", index=False)

    summary = run(root)
    assert summary["status"] == "STAGE121_COMPLETE_DRY_RUN_PREFLIGHT_READY_NO_UPDATE"
    assert summary["pass_preflight_count"] == 1
    assert Path(summary["signal_events"]).exists()
