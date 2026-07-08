import csv
import json
from pathlib import Path

from app.stage158_trade_attribution_audit import build_audit, family_key_from_rule, main


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def test_family_key_from_rule():
    assert family_key_from_rule("D150C_M5_ret_6h_bps_LEQ50__trend_8_20_bps_GEQ65") == "D150C_M5_ret_6h_bps__trend_8_20_bps"
    assert family_key_from_rule("D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65") == "D138C_ret_48h_bps__trend_50_100_bps"


def test_stage158_classifies_stale_and_router_protocol(tmp_path):
    root = tmp_path
    ledger = root / "data/demo_execution/stage144_clean_demo_execution_ledger.csv"
    rows = [
        {
            "audit_order": "1", "signal_key": "2026-07-03T19:55:00Z|D150C_M5_trend_8_20_bps_GEQ65__trend_50_100_bps_GEQ35",
            "rule_id": "D150C_M5_trend_8_20_bps_GEQ65__trend_50_100_bps_GEQ35", "feature_date": "2026-07-03T19:55:00Z",
            "entry_time": "2026-07-06T04:43:57Z", "entry_price": "4199.94", "exit_time": "2026-07-06T05:07:07Z", "exit_price": "4178.72",
            "exit_reason": "SL", "net_profit": "-21.22", "bps_move": "-50.52", "outcome": "LOSS"
        },
        {
            "audit_order": "2", "signal_key": "2026-07-07T18:30:00Z|D150C_M5_ret_12h_bps_GEQ35__trend_50_100_bps_GEQ35",
            "rule_id": "D150C_M5_ret_12h_bps_GEQ35__trend_50_100_bps_GEQ35", "feature_date": "2026-07-07T18:30:00Z",
            "entry_time": "2026-07-07T21:30:00Z", "entry_price": "4100", "exit_time": "2026-07-07T22:00:00Z", "exit_price": "4080",
            "exit_reason": "SL", "net_profit": "-20", "bps_move": "-48.78", "outcome": "LOSS"
        },
        {
            "audit_order": "3", "signal_key": "2026-07-07T18:30:00Z|D150C_M5_ret_6h_bps_LEQ50__trend_8_20_bps_GEQ65",
            "rule_id": "D150C_M5_ret_6h_bps_LEQ50__trend_8_20_bps_GEQ65", "feature_date": "2026-07-07T18:30:00Z",
            "entry_time": "2026-07-07T22:05:00Z", "entry_price": "4100", "exit_time": "2026-07-07T23:00:00Z", "exit_price": "4110",
            "exit_reason": "TIME_EXIT", "net_profit": "10", "bps_move": "24.39", "outcome": "PROFIT"
        },
    ]
    write_csv(ledger, rows)
    risk = root / "reports/stage145_clean_ledger_performance_gate/stage145_clean_ledger_performance_gate_summary.json"
    risk.parent.mkdir(parents=True, exist_ok=True)
    risk.write_text(json.dumps({"gate_decision": "STAGE145_FREEZE_REPAIR_RULE_NEGATIVE_EXPECTANCY", "recommended_action": "FREEZE_CURRENT_RULE_AND_REPAIR_DISCOVERY"}), encoding="utf-8")
    score = root / "reports/stage150_mtf_separated_validation_discovery/m5/stage150_candidate_scores.csv"
    write_csv(score, [{"rule_id": rows[1]["rule_id"], "validation_mean_bps": "5", "tail_mean_bps": "3"}])

    class Args:
        pass
    args = Args()
    args.root = str(root)
    args.clean_ledger = str(ledger)
    args.score_csv = str(score)
    args.risk_summary = str(risk)
    args.bars_m5 = ""
    args.timestamp_shift_hours = -3.0
    args.entry_time_shift_hours = -3.0
    args.max_signal_age_sec = 7200.0
    args.horizon_hours = 4.0
    args.stage155_start_utc = "2026-07-07T09:20:00Z"
    args.mfe_exit_fail_bps = 20.0
    args.rule_fail_bps = 10.0
    args.execution_delay_warn_minutes = 90.0
    args.slippage_warn_bps = 10.0
    args.flat_bps = 2.0

    summary = build_audit(args)
    assert summary["decision"] == "STAGE158_FREEZE_CONFIRMED_REPAIR_DISCOVERY_REQUIRED"
    assert summary["diagnosis_counts"]["STALE_CONTAMINATED"] == 1
    assert summary["diagnosis_counts"]["ROUTER_PROTOCOL_FAIL"] == 1
    assert summary["diagnosis_counts"]["ROUTER_PROTOCOL_RISK_PROFIT"] == 1
    assert Path(summary["trade_attribution_csv"]).exists()


def test_cli_smoke(tmp_path):
    root = tmp_path
    ledger = root / "data/demo_execution/stage144_clean_demo_execution_ledger.csv"
    write_csv(ledger, [{
        "audit_order": "1", "signal_key": "s", "rule_id": "D150C_M5_a_GEQ35__b_LEQ50", "feature_date": "2026-07-07T18:30:00Z",
        "entry_time": "2026-07-07T21:35:00Z", "entry_price": "100", "exit_time": "2026-07-07T22:00:00Z", "exit_price": "101",
        "exit_reason": "TP", "net_profit": "1", "bps_move": "100", "outcome": "PROFIT"
    }])
    assert main(["--root", str(root), "--clean-ledger", str(ledger)]) == 0
