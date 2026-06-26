#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "stage66j2_multi_readiness_daily_ops.py"
spec = importlib.util.spec_from_file_location("stage66j2", APP)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore


def test_compact_signal_handles_empty():
    s = mod.compact_signal({})
    assert s["signal_active"] is None
    assert s["ticket_path"] is None


def test_backup_compact_active():
    item = {
        "rule_lock": {"rule_id": "D1", "horizon_trading_days": 60},
        "audit_gate": {"all_gates_ok": True, "metrics_used": {"trade_count": 10}},
        "readiness_gate": {"backup_signal_active": True},
        "signal_evaluation": {"feature_date_utc": "2026-01-01", "rule_failures": []},
    }
    b = mod.backup_compact(item)
    assert b["rule_id"] == "D1"
    assert b["signal_active"] is True
    assert b["audit_pass"] is True


def test_report_builds():
    summary = {
        "status": "STAGE66J2_COMPLETE_NO_PROMOTION",
        "decision": mod.WAIT_DECISION,
        "classification": "J2_WAIT_ALL_INACTIVE",
        "signal_snapshot": {
            "h64l_v2": {"decision": "WAIT", "signal_active": False, "feature_date_utc": "2026-01-01", "ticket_path": None, "rule_failures": []},
            "d3_h60": {"decision": "WAIT", "signal_active": False, "feature_date_utc": "2026-01-01", "ticket_path": None, "rule_failures": []},
        },
        "backup_readiness": [],
        "issues": [],
    }
    report = mod.build_report(summary)
    assert "Stage66J2" in report
    assert mod.WAIT_DECISION in report


if __name__ == "__main__":
    test_compact_signal_handles_empty()
    test_backup_compact_active()
    test_report_builds()
    print("Stage66J2 tests passed")
