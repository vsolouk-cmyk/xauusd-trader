#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import sys

MODULE = Path(__file__).resolve().parents[1] / "app" / "stage66j_dual_readiness_daily_ops.py"
spec = importlib.util.spec_from_file_location("stage66j", MODULE)
stage66j = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stage66j
spec.loader.exec_module(stage66j)


def classify(h_decision, i_decision):
    summaries = {
        "stage66h": {"decision": h_decision, "status": "OK"},
        "stage66i": {"decision": i_decision, "status": "OK"},
    }
    runs = {
        "stage66h": {"enabled": True, "status": "PASS", "summary_found": True},
        "stage66i": {"enabled": True, "status": "PASS", "summary_found": True},
    }
    return stage66j.classify_decisions(summaries, runs)


def test_both_wait():
    decision, classification, issues, _ = classify(stage66j.H64L_WAIT_DECISION, stage66j.D3_WAIT_DECISION)
    assert decision == "STAGE66J_DUAL_READINESS_WAIT_SIGNALS_NO_ORDER"
    assert classification == "J_WAIT_BOTH_INACTIVE"
    assert issues == []


def test_h64l_ticket_ready():
    decision, classification, issues, _ = classify(stage66j.H64L_READY_DECISION, stage66j.D3_WAIT_DECISION)
    assert decision == "STAGE66J_MANUAL_REVIEW_REQUIRED_H64L_DRY_RUN_TICKET_READY_NO_ORDER"
    assert classification == "J_H64L_TICKET_READY"
    assert issues == []


def test_both_ready():
    decision, classification, issues, _ = classify(stage66j.H64L_READY_DECISION, stage66j.D3_READY_DECISION)
    assert decision == "STAGE66J_MANUAL_REVIEW_REQUIRED_BOTH_DRY_RUN_TICKETS_READY_NO_ORDER"
    assert classification == "J_BOTH_TICKETS_READY"
    assert issues == []


if __name__ == "__main__":
    test_both_wait()
    test_h64l_ticket_ready()
    test_both_ready()
    print("Stage66J tests passed")
