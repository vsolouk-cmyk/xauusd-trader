from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage141_demo_execution_outcome_ledger import run, infer_exit_reason

def write_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")

def test_infer_tp_from_comment_even_if_label_so():
    s = {
        "latest_exit_reason_label": "SO",
        "recent_deals": [
            {"entry_code": "1", "comment": "[tp 4015.84]"}
        ]
    }
    assert infer_exit_reason(s) == "TP"

def test_profit_ledger_append_once(tmp_path):
    root = tmp_path
    s134 = root / "reports/stage134_demo_executor_pilot/stage134_demo_executor_pilot_summary.json"
    s138 = root / "reports/stage138_broker_technical_demo_discovery/stage138_broker_technical_demo_discovery_summary.json"
    s140 = root / "reports/stage140_demo_closed_deal_outcome_monitor/stage140_demo_closed_deal_outcome_monitor_summary.json"

    write_json(s134, {
        "latest_trade_retcode": "10009",
        "latest_trade_retcode_description": "done at 3997.84"
    })
    write_json(s138, {
        "selected_rule_id": "D138",
        "selected_label": "trend <= q35",
        "bar_max_utc": "2026-07-01T11:00:00+00:00",
        "selected_score": {"validation_mean_bps": 24.3, "tail_mean_bps": 4.2}
    })
    write_json(s140, {
        "collector_decision": "STAGE140_CLOSED_DEMO_DEAL_PROFIT",
        "latest_net_profit": "18.04",
        "latest_points_move": "18.04",
        "latest_bps_move": "45.12",
        "latest_stage134_rule_id": "D138",
        "latest_stage134_signal_key": "sig|D138",
        "latest_entry_time": "2026-07-01T13:59:45Z",
        "latest_entry_price": "3997.84",
        "latest_entry_volume": "0.01",
        "latest_entry_deal_ticket": "101",
        "latest_exit_time": "2026-07-01T14:11:10Z",
        "latest_exit_price": "4015.88",
        "latest_exit_volume": "0.01",
        "latest_exit_deal_ticket": "102",
        "latest_exit_reason_label": "SO",
        "latest_exit_reason_code": "5",
        "latest_stage134_retcode": "10009",
        "account_mode": "DEMO",
        "stage134_trade_attempts": 1,
        "stage134_trade_accepted": 1,
        "recent_deals": [
            {"entry_code": "1", "comment": "[tp 4015.84]"}
        ]
    })
    a = run(root, s134, s138, s140)
    b = run(root, s134, s138, s140)
    assert a["decision"] == "STAGE141_DEMO_OUTCOME_PROFIT_CONFIRMED_CONTINUE_LOOP"
    assert a["exit_reason_inferred"] == "TP"
    assert a["ledger_row_appended"] is True
    assert b["ledger_row_appended"] is False
    assert b["ledger_row_count"] == 1

def test_loss_decision(tmp_path):
    root = tmp_path
    s134 = root / "a.json"
    s138 = root / "b.json"
    s140 = root / "c.json"
    write_json(s134, {})
    write_json(s138, {})
    write_json(s140, {
        "collector_decision": "STAGE140_CLOSED_DEMO_DEAL_LOSS",
        "latest_net_profit": "-5.00",
        "latest_stage134_signal_key": "s",
        "latest_entry_deal_ticket": "1",
        "latest_exit_deal_ticket": "2",
    })
    summary = run(root, s134, s138, s140)
    assert summary["outcome_status"] == "LOSS"
    assert "LOSS" in summary["decision"]
