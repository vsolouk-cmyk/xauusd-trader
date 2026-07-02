from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage145_clean_ledger_performance_gate import evaluate, run

def test_small_n_continue():
    rows = [
        {"outcome": "PROFIT", "net_profit": "18.04", "bps_move": "45.12", "signal_key": "s1", "rule_id": "r1"},
        {"outcome": "PROFIT", "net_profit": "18.10", "bps_move": "44.79", "signal_key": "s2", "rule_id": "r2"},
    ]
    m = evaluate(rows, 10, 0.55, 2.0, 3)
    assert m["closed_trade_count"] == 2
    assert m["profit_count"] == 2
    assert m["gate_decision"] == "STAGE145_CONTINUE_DEMO_ACCUMULATION_SMALL_N"

def test_loss_streak_freeze():
    rows = [
        {"outcome": "LOSS", "net_profit": "-1", "bps_move": "-2"},
        {"outcome": "LOSS", "net_profit": "-1", "bps_move": "-2"},
        {"outcome": "LOSS", "net_profit": "-1", "bps_move": "-2"},
    ]
    m = evaluate(rows, 10, 0.55, 2.0, 3)
    assert m["gate_decision"] == "STAGE145_FREEZE_REPAIR_RULE_LOSS_STREAK"
    assert m["severity"] == "HIGH"

def test_positive_after_min_eval_continue():
    rows = [{"outcome": "PROFIT", "net_profit": "1", "bps_move": "3"} for _ in range(10)]
    m = evaluate(rows, 10, 0.55, 2.0, 3)
    assert m["gate_decision"] == "STAGE145_DEMO_EDGE_STILL_POSITIVE_CONTINUE_ACCUMULATION"

def test_run_writes_summary(tmp_path):
    root = tmp_path
    ledger = root / "data/demo_execution/stage144_clean_demo_execution_ledger.csv"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        "outcome,net_profit,bps_move,signal_key,rule_id\n"
        "PROFIT,18.04,45.12,s1,r1\n"
        "PROFIT,18.10,44.79,s2,r2\n",
        encoding="utf-8"
    )
    s = run(root, ledger, 10, 0.55, 2.0, 3)
    assert s["closed_trade_count"] == 2
    assert s["gate_decision"] == "STAGE145_CONTINUE_DEMO_ACCUMULATION_SMALL_N"
    assert Path(s["summary_json"]).exists()
