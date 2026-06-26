#!/usr/bin/env python3
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "app" / "stage66i_no_broker_complementary_dry_run_ticket_generator.py"


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def base_files(root: Path, active: bool):
    write_json(root / "reports/stage66e_complementary_shortlist_audit/stage66e_complementary_shortlist_audit_summary.json", {
        "decision": "STAGE66E_PASS_FAST_COMPLEMENTARY_RULE_LOCK_READY_WAIT_SIGNAL_NO_ORDER",
        "classification": "E_PASS_FAST_WAIT_SIGNAL",
    })
    write_json(root / "configs/stage66e_selected_complementary_rule_lock.json", {
        "rule_id": "D3_DOLLAR_RELIEF_TREND_CONTINUATION_LONG_H60",
        "thesis_id": "D3_DOLLAR_RELIEF_TREND_CONTINUATION_LONG",
        "horizon_trading_days": 60,
        "rule_sha256": "unit-test",
        "conditions": [
            {"field": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
            {"field": "dxy_sma20_over_50", "operator": "<", "threshold": 0.0},
            {"field": "dxy_ret_20d", "operator": "<", "threshold": 0.0},
        ],
        "entry_rule": "first_external_d1_close_on_or_after_sample_available_after_utc",
        "exit_rule": "fixed_registered_horizon",
        "position_mode": "single_position_non_overlapping",
        "cost_policy": {"total_penalty_bps": 50.0},
    })
    # Use a near-future-ish date relative to common CI date not needed: script allows 7-day freshness.
    # Keep this test robust by using today's UTC date as feature date and sample time at midnight.
    import datetime as dt
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    vals = {
        "feature_date_utc": today,
        "sample_available_after_utc": today + "T00:00:00Z",
        "gold_sma20_over_50": "0.1" if active else "-0.1",
        "dxy_sma20_over_50": "-0.1" if active else "0.1",
        "dxy_ret_20d": "-0.1" if active else "0.1",
    }
    write_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", [vals], list(vals.keys()))
    write_csv(root / "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv", [{
        "date_utc": today,
        "open": "2000",
        "high": "2010",
        "low": "1990",
        "close": "2005",
        "volume": "0",
        "source": "unit-test",
    }], ["date_utc", "open", "high", "low", "close", "volume", "source"])
    write_json(root / "configs/stage66i_no_broker_complementary_dry_run_ticket_generator.json", {
        "stage66e_summary_path": "reports/stage66e_complementary_shortlist_audit/stage66e_complementary_shortlist_audit_summary.json",
        "rule_lock_path": "configs/stage66e_selected_complementary_rule_lock.json",
        "macro_dataset_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "external_d1_path": "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv",
        "macro_date_column": "feature_date_utc",
        "external_date_column": "date_utc",
        "macro_freshness_max_calendar_lag_days": 7,
    })


def run_stage(root: Path):
    out = root / "reports/stage66i_no_broker_complementary_dry_run_ticket_generator"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--root", str(root),
        "--config", "configs/stage66i_no_broker_complementary_dry_run_ticket_generator.json",
        "--out", str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    summary = json.loads((out / "stage66i_no_broker_complementary_dry_run_ticket_generator_summary.json").read_text())
    return summary, out


def test_inactive_wait():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        base_files(root, active=False)
        summary, out = run_stage(root)
        assert summary["decision"] == "WAIT_FOR_FRESH_COMPLEMENTARY_D3_H60_SIGNAL_NO_DRY_RUN_TICKET"
        assert summary["ticket_path"] is None
        assert not (out / "stage66i_no_broker_complementary_dry_run_ticket.json").exists()


def test_active_ticket():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        base_files(root, active=True)
        summary, out = run_stage(root)
        assert summary["decision"] == "COMPLEMENTARY_DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER"
        ticket = out / "stage66i_no_broker_complementary_dry_run_ticket.json"
        assert ticket.exists()
        payload = json.loads(ticket.read_text())
        assert payload["explicit_later_authorization_required_before_any_order"] is True


def test_blocked_bad_stage66e():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        base_files(root, active=True)
        write_json(root / "reports/stage66e_complementary_shortlist_audit/stage66e_complementary_shortlist_audit_summary.json", {
            "decision": "BAD",
            "classification": "BAD",
        })
        summary, _ = run_stage(root)
        assert summary["decision"] == "BLOCKED_INPUT_OR_GOVERNANCE_GATE_NO_DRY_RUN_TICKET"


if __name__ == "__main__":
    test_inactive_wait()
    test_active_ticket()
    test_blocked_bad_stage66e()
    print("Stage66I tests passed")
