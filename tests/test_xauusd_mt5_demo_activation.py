from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
import sys
from pathlib import Path
from unittest import mock

PKG_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    path = PKG_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


arming = load_module("arming_module", "app/xauusd_mt5_demo_explicit_arming.py")
cycle = load_module("cycle_module", "app/xauusd_mt5_demo_operational_cycle.py")

HEADER = "\t".join(cycle.EXPECTED_HEADER) + "\n"


def write_bars(path: Path, rows: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [HEADER]
    for date, time, close in rows:
        value = float(close)
        lines.append("\t".join([
            date, time,
            f"{value:.2f}", f"{value + 1:.2f}", f"{value - 1:.2f}", f"{value:.2f}",
            "10", "25", "0",
        ]) + "\n")
    path.write_text("".join(lines), encoding="utf-8")


class MergeTests(unittest.TestCase):
    def test_atomic_merge_replaces_overlap_and_appends(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.csv"
            recent = root / "recent.csv"
            write_bars(target, [
                ("2026.07.27", "10:00", "4000"),
                ("2026.07.27", "10:05", "4001"),
            ])
            write_bars(recent, [
                ("2026.07.27", "10:05", "4101"),
                ("2026.07.27", "10:10", "4102"),
            ])
            result = cycle.merge_recent_atomic(target, recent, 1)
            self.assertEqual(result["existing_rows"], 2)
            self.assertEqual(result["output_rows"], 3)
            self.assertEqual(result["replaced_rows"], 1)
            self.assertEqual(result["inserted_rows"], 1)
            text = target.read_text(encoding="utf-8")
            self.assertIn("2026.07.27\t10:05\t4101.00", text)
            self.assertNotIn("2026.07.27\t10:05\t4001.00", text)

    def test_atomic_merge_fast_appends_when_tail_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.csv"
            recent = root / "recent.csv"
            write_bars(target, [
                ("2026.07.27", "10:00", "4000"),
                ("2026.07.27", "10:05", "4001"),
            ])
            write_bars(recent, [
                ("2026.07.27", "10:05", "4001"),
                ("2026.07.27", "10:10", "4002"),
            ])
            result = cycle.merge_recent_atomic(target, recent, 1)
            self.assertEqual(result["mode"], "APPEND_WITH_ROLLBACK")
            self.assertEqual(result["inserted_rows"], 1)
            self.assertIn("2026.07.27\t10:10\t4002.00", target.read_text(encoding="utf-8"))

    def test_atomic_merge_rejects_bad_ohlc_without_mutating_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.csv"
            recent = root / "recent.csv"
            write_bars(target, [("2026.07.27", "10:00", "4000")])
            before = target.read_bytes()
            recent.write_text(HEADER + "2026.07.27\t10:05\t4000\t3999\t3998\t4000\t1\t1\t0\n", encoding="utf-8")
            with self.assertRaises(cycle.CycleError):
                cycle.merge_recent_atomic(target, recent, 1)
            self.assertEqual(target.read_bytes(), before)


class ArmingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mt5 = self.root / "mt5_files"
        self.bridge_dir = self.mt5 / "XAUUSD_DEMO_BRIDGE"
        self.bridge_dir.mkdir(parents=True)
        (self.root / "app").mkdir()
        for name in ("xauusd_mt5_demo_bridge.py", "xauusd_mt5_demo_login_bound_review.py", "xauusd_mt5_demo_operational_cycle.py"):
            (self.root / "app" / name).write_text("# fixture\n", encoding="utf-8")
        self.runtime_path = self.root / "reports/xauusd_mt5_demo_bridge/mt5_demo_bridge_runtime_preflight.json"
        self.runtime_path.parent.mkdir(parents=True)
        self.runtime_path.write_text(json.dumps({
            "program": arming.RUNTIME_PROGRAM,
            "decision": arming.RUNTIME_DECISION,
            "pass": True,
            "arming_readiness_pass": True,
            "runtime_failed_checks": [],
            "arming_failed_checks": [],
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "heartbeat": {
                "account_trade_mode": "DEMO",
                "account_login": "7907958",
                "symbol": "XAUUSD",
                "magic_number": "1782401",
                "armed": "false",
                "arming_permit_present": "false",
                "minimum_volume_within_validated_ceiling": "true",
                "target_volume_executable": "true"
            }
        }), encoding="utf-8")
        self.fresh_path = self.root / "reports/xauusd_mt5_demo_bridge/mt5_demo_login_bound_fresh_dry_cycle_summary.json"
        self.fresh_path.write_text(json.dumps({
            "decision": arming.FRESH_DECISION,
            "pass": True,
            "allowed_demo_login": 7907958,
            "required_next_action": arming.FRESH_NEXT,
            "bridge_armed": False,
            "active_arming_permit_created": False,
            "active_candidate_written": False,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False
        }), encoding="utf-8")
        self.prearm_path = self.root / "reports/xauusd_mt5_demo_activation/pre_arm_refresh_summary.json"
        self.prearm_path.parent.mkdir(parents=True, exist_ok=True)
        self.prearm_path.write_text(json.dumps({
            "decision": "PASS_PRE_ARM_DATA_REFRESH_AND_FRESH_DRY_CYCLE_NO_ORDER",
            "pass": True,
            "bridge_armed": False,
            "current_order_allowed": False,
            "live_order_allowed": False
        }), encoding="utf-8")
        self.bounded = self.root / "reports/xauusd_bounded_demo_design/bounded_demo_preflight.json"
        self.bounded.parent.mkdir(parents=True)
        self.bounded.write_text(json.dumps({
            "decision": arming.BOUNDED_DECISION,
            "pass": True,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "design_contract": {
                "qualification_contract": {"maximum_calendar_days": 30, "maximum_resolved_positions": 10},
                "risk_contract": {"maximum_concurrent_positions": 1, "daily_new_positions_cap": 1}
            }
        }), encoding="utf-8")
        self.config = {
            "allowed_demo_login": 7907958,
            "expected_symbol": "XAUUSD",
            "magic_number": 1782401,
            "qualification_calendar_days": 30,
            "qualification_resolved_positions": 10,
            "permit_valid_hours": 720,
            "bridge_app": "app/xauusd_mt5_demo_bridge.py",
            "fresh_dry_cycle_app": "app/xauusd_mt5_demo_login_bound_review.py",
            "operational_cycle_app": "app/xauusd_mt5_demo_operational_cycle.py",
            "pre_arm_refresh_summary": "reports/xauusd_mt5_demo_activation/pre_arm_refresh_summary.json",
            "runtime_preflight": str(self.runtime_path),
            "bounded_demo_preflight": str(self.bounded),
            "report_dir": "reports/xauusd_mt5_demo_activation",
            "mt5_files_dir": str(self.mt5),
            "mt5_bridge_subdir": "XAUUSD_DEMO_BRIDGE",
            "heartbeat_file": "bridge_heartbeat.txt",
            "arming_permit_file": "arming_permit.txt",
            "candidate_file": "demo_candidate.txt",
        }

    def tearDown(self):
        self.tmp.cleanup()

    @mock.patch.object(arming, "run_checked")
    def test_arm_creates_exact_active_permit_but_no_candidate(self, run_checked):
        result = arming.arm(self.root, self.config)
        self.assertTrue(result["active_permit_created"])
        self.assertFalse(result["mt5_runtime_armed"])
        permit = self.bridge_dir / "arming_permit.txt"
        text = permit.read_text(encoding="utf-8")
        self.assertIn("schema_version=XAUUSD_DEMO_ARMING_PERMIT_V1", text)
        self.assertIn("authorized=true", text)
        self.assertIn("allowed_demo_login=7907958", text)
        self.assertFalse((self.bridge_dir / "demo_candidate.txt").exists())
        self.assertEqual(run_checked.call_count, 2)

    @mock.patch.object(arming, "run_checked")
    def test_verify_requires_armed_heartbeat(self, _):
        arming.arm(self.root, self.config)
        heartbeat = self.bridge_dir / "bridge_heartbeat.txt"
        heartbeat.write_text("\n".join([
            "program=XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_3_PROBE_ACCOUNTING_REPAIR",
            "status=ARMED_RUNTIME_GUARDS_REQUIRED",
            "armed=true",
            "account_trade_mode=DEMO",
            "account_login=7907958",
            "allowed_demo_login=7907958",
            "symbol=XAUUSD",
            "magic_number=1782401",
            "arming_permit_present=true",
            "minimum_volume_within_validated_ceiling=true",
            "target_volume_executable=true",
            "live_fallback_allowed=false",
            "",
        ]), encoding="utf-8")
        result = arming.verify(self.root, self.config)
        self.assertTrue(result["bridge_armed"])
        self.assertFalse(result["current_order_allowed"])

    @mock.patch.object(arming, "run_checked")
    def test_verify_fails_wrong_login(self, _):
        arming.arm(self.root, self.config)
        heartbeat = self.bridge_dir / "bridge_heartbeat.txt"
        heartbeat.write_text("armed=true\naccount_trade_mode=DEMO\naccount_login=1\n", encoding="utf-8")
        with self.assertRaises(arming.ArmingError):
            arming.verify(self.root, self.config)


class OperationalCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mt5 = self.root / "mt5_files"
        self.bridge = self.mt5 / "XAUUSD_DEMO_BRIDGE"
        self.source = self.bridge / "SOURCE"
        self.source.mkdir(parents=True)
        self.bridge.joinpath("arming_permit.txt").write_text(
            "schema_version=XAUUSD_DEMO_ARMING_PERMIT_V1\nauthorized=true\nallowed_demo_login=7907958\nmagic_number=1782401\nexpires_epoch=4102444800\nbounded_preflight_sha256=" + "a" * 64 + "\n",
            encoding="utf-8",
        )
        self.bridge.joinpath("bridge_heartbeat.txt").write_text("\n".join([
            "program=XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_3_PROBE_ACCOUNTING_REPAIR",
            "status=ARMED_RUNTIME_GUARDS_REQUIRED",
            "armed=true",
            "account_trade_mode=DEMO",
            "account_login=7907958",
            "allowed_demo_login=7907958",
            "symbol=XAUUSD",
            "magic_number=1782401",
            "arming_permit_present=true",
            "minimum_volume_within_validated_ceiling=true",
            "target_volume_executable=true",
            "live_fallback_allowed=false",
            "",
        ]), encoding="utf-8")
        self.source.joinpath("recent_export_status.txt").write_text("\n".join([
            "program=AMARKETS_RECENT_BAR_EXPORTER_EA_V1",
            "decision=PASS_RECENT_EXPORT",
            "account_login=7907958",
            "account_trade_mode=DEMO",
            "symbol=XAUUSD",
            "m5_rows=2",
            "h1_rows=2",
            "",
        ]), encoding="utf-8")
        write_bars(self.source / "amarkets_xauusd_5m_recent.csv", [
            ("2026.07.27", "10:05", "4101"),
            ("2026.07.27", "10:10", "4102"),
        ])
        write_bars(self.source / "amarkets_xauusd_1h_recent.csv", [
            ("2026.07.27", "10:00", "4100"),
            ("2026.07.27", "11:00", "4110"),
        ])
        self.m5 = self.root / "inbox/amarkets_xauusd_5m.csv"
        self.h1 = self.root / "inbox/amarkets_xauusd_1h.csv"
        write_bars(self.m5, [("2026.07.27", "10:00", "4000"), ("2026.07.27", "10:05", "4001")])
        write_bars(self.h1, [("2026.07.27", "09:00", "3990"), ("2026.07.27", "10:00", "4000")])
        (self.root / "app").mkdir()
        for name in ("stage180_frozen_model_shadow.py", "stage180_refresh_frozen_amarkets_alignment.py", "xauusd_controlled_paper.py", "xauusd_mt5_demo_bridge.py", "xauusd_mt5_demo_login_bound_review.py"):
            (self.root / "app" / name).write_text("# fixture\n", encoding="utf-8")
        controlled = self.root / "reports/xauusd_controlled_paper/controlled_paper_summary.json"
        controlled.parent.mkdir(parents=True)
        controlled.write_text(json.dumps({
            "program": "XAUUSD_CONTROLLED_PAPER_V1_5_BIDIRECTIONAL_PROBABILITY_TAILS_DIRECTION_PARITY",
            "paper_log_only": True,
            "direction_policy": "BIDIRECTIONAL_PROBABILITY_TAILS",
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "operational_freshness": {"pass": True, "decision": "PASS_OPERATIONAL_FRESHNESS_OPEN_MARKET"},
            "risk_state": {"hard_kill_latched": False, "weekly_pause_active": False}
        }), encoding="utf-8")
        candidate = self.root / "reports/xauusd_mt5_demo_bridge/mt5_demo_bridge_candidate_summary.json"
        candidate.parent.mkdir(parents=True)
        candidate.write_text(json.dumps({
            "decision": "NO_ELIGIBLE_CONTROLLED_PAPER_WAITING_SIGNAL",
            "candidate_emitted": False,
            "live_order_allowed": False
        }), encoding="utf-8")
        fresh = self.root / "reports/xauusd_mt5_demo_bridge/mt5_demo_login_bound_fresh_dry_cycle_summary.json"
        fresh.write_text(json.dumps({
            "decision": "PASS_LOGIN_BOUND_FRESH_DRY_CANDIDATE_CYCLE_NO_ORDER",
            "pass": True,
            "bridge_armed": False,
            "active_arming_permit_created": False,
            "active_candidate_written": False,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False
        }), encoding="utf-8")
        self.config = {
            "allowed_demo_login": 7907958,
            "expected_symbol": "XAUUSD",
            "magic_number": 1782401,
            "mt5_files_dir": str(self.mt5),
            "mt5_bridge_subdir": "XAUUSD_DEMO_BRIDGE",
            "heartbeat_file": "bridge_heartbeat.txt",
            "arming_permit_file": "arming_permit.txt",
            "recent_source_subdir": "SOURCE",
            "recent_status_file": "recent_export_status.txt",
            "recent_m5_file": "amarkets_xauusd_5m_recent.csv",
            "recent_h1_file": "amarkets_xauusd_1h_recent.csv",
            "maximum_recent_export_age_minutes": 12,
            "maximum_heartbeat_age_minutes": 5,
            "minimum_free_space_bytes": 1,
            "persistent_m5_csv": str(self.m5),
            "persistent_h1_csv": str(self.h1),
            "stage180_app": "app/stage180_frozen_model_shadow.py",
            "alignment_refresh_app": "app/stage180_refresh_frozen_amarkets_alignment.py",
            "fresh_dry_cycle_app": "app/xauusd_mt5_demo_login_bound_review.py",
            "controlled_paper_app": "app/xauusd_controlled_paper.py",
            "bridge_app": "app/xauusd_mt5_demo_bridge.py",
            "controlled_paper_summary": str(controlled),
            "accepted_controlled_programs": ["XAUUSD_CONTROLLED_PAPER_V1_5_BIDIRECTIONAL_PROBABILITY_TAILS_DIRECTION_PARITY"],
            "report_dir": "reports/xauusd_mt5_demo_activation",
        }

    def tearDown(self):
        self.tmp.cleanup()

    @mock.patch.object(cycle, "run_capture")
    def test_full_cycle_merges_and_keeps_live_closed(self, run_capture):
        run_capture.side_effect = lambda name, command, root: {"name": name, "command": list(command), "returncode": 0, "stdout_tail": ""}
        result = cycle.run_cycle(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertTrue(result["bridge_armed"])
        self.assertFalse(result["live_order_allowed"])
        self.assertEqual(result["merges"]["m5"]["output_rows"], 3)
        self.assertEqual(run_capture.call_count, 4)

    @mock.patch.object(cycle, "run_capture")
    def test_operational_cycle_skips_while_probe_is_active(self, run_capture):
        self.bridge.joinpath("qualification_probe_permit.txt").write_text(
            "schema_version=XAUUSD_DEMO_QUALIFICATION_PROBE_PERMIT_V1\n",
            encoding="utf-8",
        )
        heartbeat = self.bridge / "bridge_heartbeat.txt"
        heartbeat.write_text(heartbeat.read_text(encoding="utf-8") + "qualification_probe_supported=true\n", encoding="utf-8")
        result = cycle.run_cycle(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertEqual(result["decision"], "PASS_QUALIFICATION_PROBE_ACTIVE_SKIP_OPERATIONAL_CYCLE")
        self.assertFalse(result["live_order_allowed"])
        run_capture.assert_not_called()

    @mock.patch.object(cycle, "run_capture")
    def test_cycle_skips_heavy_work_when_h1_export_is_unchanged(self, run_capture):
        state = self.root / "reports/xauusd_mt5_demo_activation/operational_cycle_state.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({
            "recent_h1_sha256": cycle.sha256_file(self.source / "amarkets_xauusd_1h_recent.csv")
        }), encoding="utf-8")
        self.config["cycle_state_file"] = str(state)
        result = cycle.run_cycle(self.root, self.config)
        self.assertEqual(result["decision"], "PASS_NO_NEW_COMPLETED_H1_SKIP_HEAVY_CYCLE")
        run_capture.assert_not_called()

    @mock.patch.object(cycle, "run_capture")
    def test_prepare_arm_refresh_merges_recent_data_before_fresh_dry_cycle(self, run_capture):
        self.bridge.joinpath("arming_permit.txt").unlink()
        self.bridge.joinpath("bridge_heartbeat.txt").write_text("\n".join([
            "program=XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_3_PROBE_ACCOUNTING_REPAIR",
            "status=DISABLED_DEFAULT_NO_ORDER",
            "armed=false",
            "account_trade_mode=DEMO",
            "account_login=7907958",
            "allowed_demo_login=0",
            "symbol=XAUUSD",
            "magic_number=1782401",
            "arming_permit_present=false",
            "minimum_volume_within_validated_ceiling=true",
            "target_volume_executable=true",
            "live_fallback_allowed=false",
            "",
        ]), encoding="utf-8")
        run_capture.side_effect = lambda name, command, root: {"name": name, "command": list(command), "returncode": 0, "stdout_tail": ""}
        result = cycle.prepare_arm_refresh(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertFalse(result["bridge_armed"])
        self.assertEqual(result["decision"], "PASS_PRE_ARM_DATA_REFRESH_AND_FRESH_DRY_CYCLE_NO_ORDER")
        self.assertEqual(run_capture.call_count, 2)
        self.assertIn("2026.07.27\t10:10\t4102.00", self.m5.read_text(encoding="utf-8"))
        self.assertIn("2026.07.27\t11:00\t4110.00", self.h1.read_text(encoding="utf-8"))

    def test_cycle_fails_closed_when_exporter_status_is_stale(self):
        status = self.source / "recent_export_status.txt"
        os.utime(status, (1, 1))
        with self.assertRaises(cycle.CycleError):
            cycle.validate_recent_export(self.config)


class StaticSafetyTests(unittest.TestCase):
    def test_exporter_contains_no_order_path(self):
        text = (PKG_ROOT / "mt5/AMarkets_Recent_Bar_Exporter_EA.mq5").read_text(encoding="utf-8")
        for forbidden in ("OrderSend", "CTrade", "trade.Buy", "trade.Sell", "WebRequest"):
            self.assertNotIn(forbidden, text)
        self.assertIn("ACCOUNT_TRADE_MODE_DEMO", text)
        self.assertIn("InpAllowedDemoLogin", text)
        self.assertIn("iTime(g_symbol,tf,1)", text)

    def test_python_operator_contains_no_broker_library(self):
        combined = "\n".join((PKG_ROOT / path).read_text(encoding="utf-8") for path in (
            "app/xauusd_mt5_demo_explicit_arming.py",
            "app/xauusd_mt5_demo_operational_cycle.py",
        ))
        for forbidden in ("MetaTrader5", "mt5.order_send", "requests.post", "ccxt"):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
