from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage142_demo_loop_supervisor import classify_loop, build_commands, run

def test_classify_after_profit():
    c = classify_loop(
        {},
        {"selected_rule_id": "D138", "bar_max_utc": "2026-07-01T11:00:00Z"},
        {},
        {},
        {
            "decision": "STAGE141_DEMO_OUTCOME_PROFIT_CONFIRMED_CONTINUE_LOOP",
            "outcome_status": "PROFIT",
            "signal_key": "sig",
            "net_profit": "18.04",
            "bps_move": "45.12",
            "ledger_row_count": 1,
        },
    )
    assert c["loop_decision"] == "STAGE142_LOOP_READY_FOR_NEXT_DISTINCT_SIGNAL_AFTER_PROFIT"
    assert c["next_action"] == "KEEP_STAGE138_STAGE134_RUNNING_WAIT_FOR_NEXT_DISTINCT_SIGNAL"

def test_build_commands_contains_expected_scripts(tmp_path):
    cmds = build_commands(tmp_path, "/tmp/bars.csv", True, True, True, True)
    names = [x[0] for x in cmds]
    assert "stage138_refresh" in names
    assert "stage134_collector" in names
    assert "stage141_ledger" in names
    assert any("--write-mt5" in c for _, c in cmds)

def test_dry_run_writes_summary(tmp_path):
    root = tmp_path
    # Seed stage141 profit summary so classify has a meaningful state.
    p = root / "reports/stage141_demo_execution_outcome_ledger/stage141_demo_execution_outcome_ledger_summary.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "decision": "STAGE141_DEMO_OUTCOME_PROFIT_CONFIRMED_CONTINUE_LOOP",
        "outcome_status": "PROFIT",
        "net_profit": "18.04",
        "bps_move": "45.12",
        "ledger_row_count": 1,
        "signal_key": "sig",
    }), encoding="utf-8")
    summary = run(root, "/tmp/bars.csv", True, True, True, True, True, 5)
    assert summary["dry_run"] is True
    assert summary["commands_run"] == 5
    assert Path(summary["summary_json"]).exists()
