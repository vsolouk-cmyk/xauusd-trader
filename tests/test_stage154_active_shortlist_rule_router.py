from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage154_active_shortlist_rule_router import parse_conditions, choose_active_candidate


def test_parse_conditions():
    raw = '[{"feature":"a","op":">=","threshold":1.5},{"feature":"b","op":"<=","threshold":"2"}]'
    conds = parse_conditions(raw)
    assert conds == [
        {"feature": "a", "op": ">=", "threshold": 1.5},
        {"feature": "b", "op": "<=", "threshold": 2.0},
    ]


def test_choose_active_candidate_prefers_tail_mean():
    rows = [
        {
            "rule_id": "r1", "label": "r1", "gate": "PASS", "excluded": "false",
            "conditions_json": '[{"feature":"x","op":">=","threshold":5}]',
            "validation_mean_bps": "3", "validation_hit_rate": "0.55",
            "tail_mean_bps": "2", "tail_hit_rate": "0.52",
            "tail_events": "10", "validation_events": "10",
        },
        {
            "rule_id": "r2", "label": "r2", "gate": "PASS", "excluded": "false",
            "conditions_json": '[{"feature":"x","op":">=","threshold":4}]',
            "validation_mean_bps": "4", "validation_hit_rate": "0.56",
            "tail_mean_bps": "6", "tail_hit_rate": "0.53",
            "tail_events": "10", "validation_events": "10",
        },
    ]
    selected, active, eligible = choose_active_candidate(rows, {"x": 5.5}, 2.0, 0.53, 1.0, 0.5, 50)
    assert eligible == 2
    assert len(active) == 2
    assert selected["rule_id"] == "r2"


def test_choose_active_candidate_none_when_inactive():
    rows = [
        {
            "rule_id": "r1", "label": "r1", "gate": "PASS", "excluded": "false",
            "conditions_json": '[{"feature":"x","op":">=","threshold":5}]',
            "validation_mean_bps": "3", "validation_hit_rate": "0.55",
            "tail_mean_bps": "2", "tail_hit_rate": "0.52",
        }
    ]
    selected, active, eligible = choose_active_candidate(rows, {"x": 1.0}, 2.0, 0.53, 1.0, 0.5, 50)
    assert eligible == 1
    assert active == []
    assert selected is None


def test_stage154_direct_script_help_runs_without_pythonpath():
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "app/stage154_active_shortlist_rule_router.py"), "--help"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--score-csv" in result.stdout
