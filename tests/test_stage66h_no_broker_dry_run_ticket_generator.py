#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from stage66h_no_broker_dry_run_ticket_generator import run


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class Stage66HTests(unittest.TestCase):
    def make_repo(self, active: bool = False, unsafe_g: bool = False) -> Path:
        root = Path(tempfile.mkdtemp())
        g = {
            "decision": "CONTROLLED_PAPER_ORDER_READINESS_DESIGN_BAND_B_NO_ORDER",
            "classification": "G_PASS_FAST_DESIGN_READY",
            "readiness_design": {
                "paper_order_is_authorized": False,
                "broker_connection_authorized": False,
                "live_or_paper_live_authorized": False,
                "initial_band": "B_conservative",
                "initial_notional_fraction": 0.05,
                "max_notional_fraction_before_new_forward_evidence": 0.10,
            },
        }
        if unsafe_g:
            g["readiness_design"]["paper_order_is_authorized"] = True
        write_json(root / "reports/stage66g_controlled_paper_order_readiness/stage66g_controlled_paper_order_readiness_summary.json", g)
        rule = {"conditions": [
            {"field": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
            {"field": "dxy_ret_20d", "operator": "<", "threshold": 0.0},
            {"field": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
            {"field": "etf_flow_tonnes_3m", "operator": ">", "threshold": 0.0},
            {"field": "central_bank_demand_tonnes_3m", "operator": ">", "threshold": 0.0},
            {"field": "gold_sma50_over_200", "operator": ">", "threshold": 0.0},
        ]}
        write_json(root / "configs/h64l_locked_rule_v2_stage66a3_exact_reconciled.json", rule)
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        if active:
            vals = {"gold_sma20_over_50": "1", "dxy_ret_20d": "-0.01", "real_yield_change_20d": "-0.1", "etf_flow_tonnes_3m": "10", "central_bank_demand_tonnes_3m": "1", "gold_sma50_over_200": "1"}
        else:
            vals = {"gold_sma20_over_50": "-1", "dxy_ret_20d": "0.01", "real_yield_change_20d": "0.1", "etf_flow_tonnes_3m": "-10", "central_bank_demand_tonnes_3m": "1", "gold_sma50_over_200": "1"}
        macro = [{"feature_date_utc": today, "sample_available_after_utc": today + "T00:00:00Z", **vals}]
        write_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", macro)
        start = dt.date.fromisoformat(today)
        ext = []
        for i in range(130):
            ext.append({"date_utc": (start + dt.timedelta(days=i)).isoformat(), "open": "100", "high": "101", "low": "99", "close": str(100 + i * 0.1), "volume": "0", "source": "test", "available_after_utc": (start + dt.timedelta(days=i)).isoformat()+"T00:00:00Z"})
        write_csv(root / "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv", ext)
        write_json(root / "configs/stage66h_no_broker_dry_run_ticket_generator.json", {
            "stage66g_summary_path": "reports/stage66g_controlled_paper_order_readiness/stage66g_controlled_paper_order_readiness_summary.json",
            "macro_dataset_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "external_d1_path": "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv",
            "rule_lock_path": "configs/h64l_locked_rule_v2_stage66a3_exact_reconciled.json",
            "external_date_column": "date_utc",
            "macro_max_calendar_lag_days": 7,
            "holding_period_trading_days": 120
        })
        return root

    def test_inactive_signal_waits_and_no_ticket(self):
        root = self.make_repo(active=False)
        summary = run(root, root / "configs/stage66h_no_broker_dry_run_ticket_generator.json", root / "reports/stage66h_no_broker_dry_run_ticket_generator")
        self.assertEqual(summary["decision"], "WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET")
        self.assertIsNone(summary["ticket_path"])

    def test_active_signal_generates_non_executing_ticket(self):
        root = self.make_repo(active=True)
        summary = run(root, root / "configs/stage66h_no_broker_dry_run_ticket_generator.json", root / "reports/stage66h_no_broker_dry_run_ticket_generator")
        self.assertEqual(summary["decision"], "DRY_RUN_TICKET_READY_NO_BROKER_NO_ORDER")
        ticket = json.loads((root / summary["ticket_path"]).read_text(encoding="utf-8"))
        self.assertFalse(ticket["non_execution_guards"]["broker_connection_authorized"])
        self.assertFalse(ticket["non_execution_guards"]["paper_order_is_authorized"])
        self.assertLessEqual(ticket["sizing_design"]["initial_notional_fraction"], 0.05)

    def test_unsafe_stage66g_blocks(self):
        root = self.make_repo(active=True, unsafe_g=True)
        summary = run(root, root / "configs/stage66h_no_broker_dry_run_ticket_generator.json", root / "reports/stage66h_no_broker_dry_run_ticket_generator")
        self.assertEqual(summary["decision"], "STOP_STAGE66G_READINESS_GATE_NOT_VALID_NO_TICKET")
        self.assertIsNone(summary["ticket_path"])


if __name__ == "__main__":
    unittest.main()
