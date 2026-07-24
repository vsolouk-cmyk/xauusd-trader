from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bridge", PACKAGE_ROOT / "app" / "xauusd_mt5_demo_bridge.py"
)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in (
            "app", "config", "mt5", "schemas", "reports/xauusd_bounded_demo_design",
            "reports/xauusd_controlled_paper", "data/controlled_paper",
            "data/local/stage177c_amarkets_alignment",
            "data/fundamental_event_inbox/features", "reports/xauusd_mt5_demo_bridge",
        ):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        for rel in (
            "app/xauusd_mt5_demo_bridge.py",
            "mt5/XAUUSD_BoundedDemoBridge.mq5",
            "schemas/xauusd_demo_candidate.schema.json",
        ):
            src = PACKAGE_ROOT / rel
            dst = self.root / rel
            dst.write_bytes(src.read_bytes())
        bounded = json.loads((PACKAGE_ROOT / "tests/fixtures/bounded_demo_preflight_pass.json").read_text())
        (self.root / "reports/xauusd_bounded_demo_design/bounded_demo_preflight.json").write_text(
            json.dumps(bounded), encoding="utf-8"
        )
        self.mt5_files = self.root / "mt5_files"
        self.mt5_experts = self.root / "mt5_experts"
        self.mt5_files.mkdir()
        self.mt5_experts.mkdir()
        config = json.loads((PACKAGE_ROOT / "config/xauusd_mt5_demo_bridge.json").read_text())
        config["mt5_files_dir"] = str(self.mt5_files)
        config["mt5_experts_dir"] = str(self.mt5_experts)
        (self.root / "config/xauusd_mt5_demo_bridge.json").write_text(json.dumps(config), encoding="utf-8")
        self.config = config
        self._write_controlled_files()
        self._write_ledger()
        self._write_h1()
        self._write_events([])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_controlled_files(self) -> None:
        summary = {
            "program": bridge.CONTROLLED_PROGRAM,
            "direction_policy": "BIDIRECTIONAL_PROBABILITY_TAILS",
            "paper_log_only": True,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "risk_state": {
                "hard_kill_latched": False,
                "weekly_pause_active": False,
            },
        }
        preflight = {
            "program": bridge.CONTROLLED_PROGRAM,
            "decision": bridge.CONTROLLED_PREFLIGHT_DECISION,
            "pass": True,
        }
        (self.root / "reports/xauusd_controlled_paper/controlled_paper_summary.json").write_text(json.dumps(summary))
        (self.root / "reports/xauusd_controlled_paper/controlled_paper_preflight.json").write_text(json.dumps(preflight))

    def _write_ledger(self, waiting: bool = True) -> None:
        path = self.root / "data/controlled_paper/xauusd_controlled_paper.sqlite"
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE signals(
              signal_key TEXT PRIMARY KEY, signal_timestamp_ms INTEGER, signal_utc TEXT,
              probability_up REAL
            );
            CREATE TABLE positions(
              signal_key TEXT PRIMARY KEY, signal_timestamp_ms INTEGER, signal_utc TEXT,
              side TEXT, side_source TEXT, status TEXT
            );
            CREATE TABLE blocked_signals(signal_key TEXT, reason TEXT);
            """
        )
        signal_dt = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        signal_ms = int(signal_dt.timestamp() * 1000)
        conn.execute(
            "INSERT INTO signals VALUES(?,?,?,?)",
            (str(signal_ms), signal_ms, bridge.iso_utc(signal_dt), 0.63),
        )
        if waiting:
            conn.execute(
                "INSERT INTO positions VALUES(?,?,?,?,?,?)",
                (str(signal_ms), signal_ms, bridge.iso_utc(signal_dt), "LONG", "PROBABILITY_TAILS_ONLY", "WAIT_ENTRY"),
            )
        conn.commit()
        conn.close()

    def _write_h1(self) -> None:
        path = self.root / "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE amarkets_h1_direct_utc(timestamp INTEGER)")
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        for i in range(60):
            conn.execute("INSERT INTO amarkets_h1_direct_utc VALUES(?)", (int((start + timedelta(hours=i)).timestamp() * 1000),))
        conn.commit()
        conn.close()

    def _write_events(self, events: list[dict[str, str]]) -> None:
        path = self.root / "data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv"
        fields = ["event_time_utc", "source", "category", "title", "blackout_before_minutes", "blackout_after_minutes"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(events)

    def test_design_is_disabled_and_source_safe(self) -> None:
        result = bridge.build_design(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertFalse(result["bridge_armed"])
        self.assertFalse(result["demo_order_allowed"])
        self.assertTrue(all(result["checks"]["ea_source_safety"].values()))

    def test_install_preflight_sees_paths(self) -> None:
        result = bridge.build_install_preflight(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertTrue(result["local_mt5_paths_ready"])
        self.assertEqual(result["decision"], "PASS_MT5_DEMO_BRIDGE_INSTALL_PREFLIGHT_DISABLED_NO_ORDER")

    def test_emit_candidate_is_deterministic_and_non_authorizing(self) -> None:
        now = datetime(2026, 1, 1, 10, 59, 30, tzinfo=UTC)
        first = bridge.emit_candidate(self.root, self.config, now=now)
        second = bridge.emit_candidate(self.root, self.config, now=now)
        self.assertTrue(first["candidate_emitted"])
        self.assertEqual(first["candidate"]["intent_id"], second["candidate"]["intent_id"])
        self.assertFalse(first["candidate"]["python_order_authorized"])
        self.assertTrue(first["candidate"]["requires_mt5_runtime_authorization"])
        mt5_file = self.mt5_files / "XAUUSD_DEMO_BRIDGE/demo_candidate.txt"
        self.assertTrue(mt5_file.is_file())
        text = mt5_file.read_text()
        self.assertIn("event_guard_pass=True", text)
        self.assertIn("python_order_authorized=False", text)
        self.assertIn("exit_after_h1_bars=24", text)

    def test_latest_signal_projects_future_rows_and_uses_bar_count_exit(self) -> None:
        # Rebuild ledger/H1 so the signal is the latest known H1 row.
        (self.root / "data/controlled_paper/xauusd_controlled_paper.sqlite").unlink()
        ledger = self.root / "data/controlled_paper/xauusd_controlled_paper.sqlite"
        conn = sqlite3.connect(ledger)
        conn.executescript("""
            CREATE TABLE signals(signal_key TEXT PRIMARY KEY, signal_timestamp_ms INTEGER, signal_utc TEXT, probability_up REAL);
            CREATE TABLE positions(signal_key TEXT PRIMARY KEY, signal_timestamp_ms INTEGER, signal_utc TEXT, side TEXT, side_source TEXT, status TEXT);
            CREATE TABLE blocked_signals(signal_key TEXT, reason TEXT);
        """)
        signal_dt = datetime(2026, 1, 2, 23, 0, tzinfo=UTC)
        signal_ms = int(signal_dt.timestamp()*1000)
        conn.execute("INSERT INTO signals VALUES(?,?,?,?)", (str(signal_ms), signal_ms, bridge.iso_utc(signal_dt), 0.63))
        conn.execute("INSERT INTO positions VALUES(?,?,?,?,?,?)", (str(signal_ms), signal_ms, bridge.iso_utc(signal_dt), "LONG", "PROBABILITY_TAILS_ONLY", "WAIT_ENTRY"))
        conn.commit(); conn.close()

        db = self.root / "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"
        db.unlink()
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE amarkets_h1_direct_utc(timestamp INTEGER)")
        start = datetime(2025, 12, 29, 0, 0, tzinfo=UTC)
        current = start
        while current <= signal_dt:
            if current.weekday() < 5:
                conn.execute("INSERT INTO amarkets_h1_direct_utc VALUES(?)", (int(current.timestamp()*1000),))
            current += timedelta(hours=1)
        conn.commit(); conn.close()
        result = bridge.emit_candidate(self.root, self.config, now=datetime(2026, 1, 4, 23, 59, 30, tzinfo=UTC))
        self.assertTrue(result["candidate_emitted"])
        self.assertEqual(result["candidate"]["exit_after_h1_bars"], 24)
        self.assertGreater(result["candidate"]["target_exit_epoch"], result["candidate"]["target_entry_epoch"])

    def test_far_weekend_entry_waits_without_failure(self) -> None:
        # The latest-signal projection fixture is created in the dedicated test; this test exercises current fixture lead.
        result = bridge.emit_candidate(self.root, self.config, now=datetime(2026, 1, 1, 8, 0, tzinfo=UTC))
        self.assertFalse(result["candidate_emitted"])
        self.assertEqual(result["decision"], "WAIT_FOR_TARGET_ENTRY_WINDOW_NO_CANDIDATE")

    def test_event_blackout_blocks_candidate(self) -> None:
        self._write_events([
            {
                "event_time_utc": "2026-01-01T11:00:00Z",
                "source": "BLS",
                "category": "BLS_CPI",
                "title": "CPI",
                "blackout_before_minutes": "60",
                "blackout_after_minutes": "60",
            }
        ])
        result = bridge.emit_candidate(self.root, self.config, now=datetime(2026, 1, 1, 10, 59, tzinfo=UTC))
        self.assertFalse(result["candidate_emitted"])
        self.assertEqual(result["decision"], "BLOCK_MT5_DEMO_CANDIDATE_EVENT_BLACKOUT")

    def test_no_waiting_signal_is_non_failure(self) -> None:
        (self.root / "data/controlled_paper/xauusd_controlled_paper.sqlite").unlink()
        self._write_ledger(waiting=False)
        result = bridge.emit_candidate(self.root, self.config, now=datetime(2026, 1, 1, 10, 59, tzinfo=UTC))
        self.assertTrue(result["pass"])
        self.assertFalse(result["candidate_emitted"])
        self.assertEqual(result["decision"], "NO_ELIGIBLE_CONTROLLED_PAPER_WAITING_SIGNAL")

    def test_stale_entry_blocks_without_emission(self) -> None:
        result = bridge.emit_candidate(self.root, self.config, now=datetime(2026, 1, 1, 11, 2, tzinfo=UTC))
        self.assertFalse(result["candidate_emitted"])
        self.assertEqual(result["decision"], "BLOCK_DEMO_CANDIDATE_STALE_ENTRY_WINDOW")

    def test_runtime_preflight_passes_disabled_demo_heartbeat(self) -> None:
        bridge.build_design(self.root, self.config)
        folder = self.mt5_files / "XAUUSD_DEMO_BRIDGE"
        folder.mkdir()
        (folder / "bridge_heartbeat.txt").write_text(
            "\n".join([
                "program=XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_1_VOLUME_DIAGNOSTIC_LOGGING",
                "status=DISABLED_DEFAULT_NO_ORDER",
                "armed=false",
                "account_trade_mode=DEMO",
                "account_login=123456",
                "symbol=XAUUSD",
                "magic_number=1782401",
                "live_fallback_allowed=false",
                "spread_guard_bps=3.0764778059487488",
                "notional_to_equity=0.03925991017190415",
                "validated_maximum_notional_ratio=0.1570396406876166",
                "account_equity=100000.0",
                "symbol_bid=3350.0",
                "symbol_ask=3350.2",
                "symbol_mid_price=3350.1",
                "trade_contract_size=100.0",
                "volume_min=0.01",
                "volume_max=100.0",
                "volume_step=0.01",
                "minimum_volume_notional=3350.1",
                "raw_target_volume=0.1171905316",
                "floored_target_volume=0.11",
                "actual_executable_ratio=0.0368511",
                "required_equity_for_validated_ceiling=21332.0",
                "required_equity_for_initial_target=85330.0",
                "equity_multiplier_to_validated_ceiling=0.21332",
                "equity_multiplier_to_initial_target=0.85330",
                "volume_contract_decision=READY_UNDER_LOCKED_VOLUME_CONTRACT",
                "minimum_volume_ratio=0.02",
                "minimum_volume_within_validated_ceiling=true",
                "target_volume_executable=true",
            ]) + "\n"
        )
        result = bridge.runtime_preflight(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertFalse(result["bridge_armed"])

    def test_runtime_preflight_blocks_minimum_lot_risk_increase(self) -> None:
        bridge.build_design(self.root, self.config)
        folder = self.mt5_files / "XAUUSD_DEMO_BRIDGE"
        folder.mkdir()
        (folder / "bridge_heartbeat.txt").write_text(
            "\n".join([
                "program=XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_1_VOLUME_DIAGNOSTIC_LOGGING",
                "status=DISABLED_DEFAULT_NO_ORDER",
                "armed=false",
                "account_trade_mode=DEMO",
                "symbol=XAUUSD",
                "magic_number=1782401",
                "live_fallback_allowed=false",
                "spread_guard_bps=3.0764778059487488",
                "notional_to_equity=0.03925991017190415",
                "validated_maximum_notional_ratio=0.1570396406876166",
                "account_equity=4102.465641449475",
                "symbol_bid=3350.0",
                "symbol_ask=3350.2",
                "symbol_mid_price=3350.1",
                "trade_contract_size=100.0",
                "volume_min=0.01",
                "volume_max=100.0",
                "volume_step=0.01",
                "minimum_volume_notional=3350.1",
                "raw_target_volume=0.000480769180",
                "floored_target_volume=0.0",
                "actual_executable_ratio=-1.0",
                "required_equity_for_validated_ceiling=21332.830267129953",
                "required_equity_for_initial_target=85331.32106851981",
                "equity_multiplier_to_validated_ceiling=5.200002177128",
                "equity_multiplier_to_initial_target=20.800008708512",
                "volume_contract_decision=BLOCK_ARMING_MINIMUM_LOT_EXCEEDS_VALIDATED_CEILING",
                "minimum_volume_ratio=0.816606473471",
                "minimum_volume_within_validated_ceiling=false",
                "target_volume_executable=false",
            ]) + "\n"
        )
        result = bridge.runtime_preflight(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertTrue(result["runtime_installation_pass"])
        self.assertFalse(result["arming_readiness_pass"])
        self.assertEqual(
            result["decision"],
            "PASS_MT5_DEMO_BRIDGE_RUNTIME_DISABLED_ARMING_BLOCKED_VOLUME_CONTRACT",
        )
        self.assertIn("minimum_volume_within_validated_ceiling", result["arming_failed_checks"])
        self.assertAlmostEqual(
            result["volume_diagnostic"]["equity_multiplier_to_validated_ceiling"],
            5.200002177128,
            places=9,
        )
        self.assertAlmostEqual(
            result["volume_diagnostic"]["equity_multiplier_to_initial_target"],
            20.800008708512,
            places=9,
        )
        self.assertFalse(result["demo_order_allowed"])

    def test_python_has_no_broker_import(self) -> None:
        text = (PACKAGE_ROOT / "app/xauusd_mt5_demo_bridge.py").read_text()
        self.assertNotIn("import MetaTrader5", text)
        self.assertNotIn("OrderSend", text)

    def test_mql5_contract_is_default_disabled_and_demo_only(self) -> None:
        text = (PACKAGE_ROOT / "mt5/XAUUSD_BoundedDemoBridge.mq5").read_text()
        for token in (
            "input bool   InpArmed                         = false;",
            "ACCOUNT_TRADE_MODE_DEMO",
            "DEMO_LOGIN_NOT_EXPLICITLY_BOUND",
            "ARMING_PERMIT_MISSING",
            "XAUUSD_DEMO_ARMING_PERMIT_V1",
            "TARGET_BELOW_MINIMUM_VOLUME",
            "bridge_runtime.log",
            "volume_contract_decision",
            "InpDiagnosticLogSeconds",
            "Comment(",
            "VOLUME_ROUNDING_WOULD_INCREASE_TARGET_RISK",
            "LIVE_SPREAD_GUARD",
            "ReceiptExists",
            "HARD_DRAWDOWN_KILL",
            "DAILY_NEW_POSITION_CAP",
            "QUALIFICATION_BOUND_REACHED",
        ):
            self.assertIn(token, text)
        self.assertIn("XAUUSD_BOUNDED_DEMO_BRIDGE_EA_V1_1_VOLUME_DIAGNOSTIC_LOGGING", text)
        self.assertNotIn("WebRequest(", text)
        self.assertIn("if(InpArmed)\n      InitializeRiskState();", text)
        self.assertIn("close blocked: account is not DEMO", text)


if __name__ == "__main__":
    unittest.main()
