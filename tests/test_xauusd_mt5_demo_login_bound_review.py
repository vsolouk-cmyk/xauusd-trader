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
    "review", PACKAGE_ROOT / "app" / "xauusd_mt5_demo_login_bound_review.py"
)
review = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = review
SPEC.loader.exec_module(review)


class ReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel in (
            "app", "config", "reports/xauusd_mt5_demo_bridge",
            "reports/xauusd_bounded_demo_design", "reports/xauusd_controlled_paper",
            "data/controlled_paper", "data/local/stage177c_amarkets_alignment",
            "data/fundamental_event_inbox/features", "mt5_files/XAUUSD_DEMO_BRIDGE",
        ):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        for rel in (
            "app/xauusd_mt5_demo_bridge.py",
            "app/xauusd_mt5_demo_login_bound_review.py",
        ):
            (self.root / rel).write_bytes((PACKAGE_ROOT / rel).read_bytes())
        bounded = json.loads((PACKAGE_ROOT / "tests/fixtures/bounded_demo_preflight_pass.json").read_text())
        (self.root / "reports/xauusd_bounded_demo_design/bounded_demo_preflight.json").write_text(json.dumps(bounded))
        runtime = json.loads((PACKAGE_ROOT / "tests/fixtures/runtime_preflight_ready.json").read_text())
        runtime["generated_utc"] = "2026-07-26T11:45:34Z"
        (self.root / "reports/xauusd_mt5_demo_bridge/mt5_demo_bridge_runtime_preflight.json").write_text(json.dumps(runtime))
        bridge_cfg = json.loads((PACKAGE_ROOT / "config/xauusd_mt5_demo_bridge.json").read_text())
        bridge_cfg["mt5_files_dir"] = str(self.root / "mt5_files")
        (self.root / "config/xauusd_mt5_demo_bridge.json").write_text(json.dumps(bridge_cfg))
        cfg = json.loads((PACKAGE_ROOT / "config/xauusd_mt5_demo_login_bound_review.json").read_text())
        cfg["mt5_files_dir"] = str(self.root / "mt5_files")
        (self.root / "config/xauusd_mt5_demo_login_bound_review.json").write_text(json.dumps(cfg))
        self.config = cfg
        self.bridge_config = bridge_cfg
        self._write_controlled()
        self._write_ledger(waiting=False)
        self._write_h1()
        self._write_events([])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _now(self) -> datetime:
        return datetime(2026, 7, 26, 12, 0, tzinfo=UTC)

    def _runtime_path(self) -> Path:
        return self.root / "reports/xauusd_mt5_demo_bridge/mt5_demo_bridge_runtime_preflight.json"

    def _write_controlled(self) -> None:
        summary = {
            "program": "XAUUSD_CONTROLLED_PAPER_V1_5_BIDIRECTIONAL_PROBABILITY_TAILS_DIRECTION_PARITY",
            "direction_policy": "BIDIRECTIONAL_PROBABILITY_TAILS",
            "paper_log_only": True,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "risk_state": {"hard_kill_latched": False, "weekly_pause_active": False},
        }
        preflight = {
            "program": summary["program"],
            "decision": "PASS_CONTROLLED_PAPER_PREFLIGHT",
            "pass": True,
        }
        (self.root / "reports/xauusd_controlled_paper/controlled_paper_summary.json").write_text(json.dumps(summary))
        (self.root / "reports/xauusd_controlled_paper/controlled_paper_preflight.json").write_text(json.dumps(preflight))

    def _write_ledger(self, waiting: bool, signal_dt: datetime | None = None) -> None:
        path = self.root / "data/controlled_paper/xauusd_controlled_paper.sqlite"
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(path)
        conn.executescript("""
        CREATE TABLE signals(signal_key TEXT PRIMARY KEY, signal_timestamp_ms INTEGER, signal_utc TEXT, probability_up REAL);
        CREATE TABLE positions(signal_key TEXT PRIMARY KEY, signal_timestamp_ms INTEGER, signal_utc TEXT, side TEXT, side_source TEXT, status TEXT);
        CREATE TABLE blocked_signals(signal_key TEXT, reason TEXT);
        """)
        signal_dt = signal_dt or datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        signal_ms = int(signal_dt.timestamp() * 1000)
        conn.execute("INSERT INTO signals VALUES(?,?,?,?)", (str(signal_ms), signal_ms, review.iso_utc(signal_dt), 0.63))
        if waiting:
            conn.execute("INSERT INTO positions VALUES(?,?,?,?,?,?)", (str(signal_ms), signal_ms, review.iso_utc(signal_dt), "LONG", "PROBABILITY_TAILS_ONLY", "WAIT_ENTRY"))
        conn.commit(); conn.close()

    def _write_h1(self) -> None:
        path = self.root / "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE amarkets_h1_direct_utc(timestamp INTEGER)")
        start = datetime(2025, 12, 29, 0, 0, tzinfo=UTC)
        for i in range(24 * 10):
            dt = start + timedelta(hours=i)
            if dt.weekday() < 5:
                conn.execute("INSERT INTO amarkets_h1_direct_utc VALUES(?)", (int(dt.timestamp() * 1000),))
        conn.commit(); conn.close()

    def _write_events(self, rows: list[dict[str, str]]) -> None:
        path = self.root / "data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv"
        fields = ["event_time_utc", "source", "category", "title", "blackout_before_minutes", "blackout_after_minutes"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)

    def test_review_accepts_current_generic_success_decision(self) -> None:
        result = review.build_review(self.root, self.config, self._now())
        self.assertTrue(result["pass"])
        self.assertEqual(result["decision"], "PASS_LOGIN_BOUND_ARMING_REVIEW_DRY_ONLY_NO_ORDER")
        self.assertEqual(result["allowed_demo_login"], 7907958)
        self.assertFalse(result["active_arming_permit_created"])
        self.assertFalse(result["demo_order_allowed"])

    def test_review_rejects_wrong_login(self) -> None:
        payload = json.loads(self._runtime_path().read_text())
        payload["heartbeat"]["account_login"] = "123"
        self._runtime_path().write_text(json.dumps(payload))
        with self.assertRaises(review.ReviewError):
            review.build_review(self.root, self.config, self._now())

    def test_review_rejects_not_ready_even_with_pass_decision(self) -> None:
        payload = json.loads(self._runtime_path().read_text())
        payload["arming_readiness_pass"] = False
        payload["arming_failed_checks"] = ["target_volume_executable_without_risk_increase"]
        self._runtime_path().write_text(json.dumps(payload))
        with self.assertRaises(review.ReviewError):
            review.build_review(self.root, self.config, self._now())

    def test_review_rejects_active_permit(self) -> None:
        permit = self.root / "mt5_files/XAUUSD_DEMO_BRIDGE/arming_permit.txt"
        permit.write_text("schema_version=XAUUSD_DEMO_ARMING_PERMIT_V1\n")
        with self.assertRaises(review.ReviewError):
            review.build_review(self.root, self.config, self._now())

    def test_review_quarantines_active_candidate(self) -> None:
        candidate = self.root / "mt5_files/XAUUSD_DEMO_BRIDGE/demo_candidate.txt"
        candidate.write_text("unsafe-stale\n")
        result = review.build_review(self.root, self.config, self._now())
        self.assertFalse(candidate.exists())
        self.assertIsNotNone(result["quarantined_active_candidate"])

    def test_preview_permit_is_explicitly_non_executable(self) -> None:
        result = review.build_review(self.root, self.config, self._now())
        path = Path(result["outputs"]["staged_non_executable_permit_preview"])
        text = path.read_text()
        self.assertIn("schema_version=XAUUSD_DEMO_ARMING_PERMIT_PREVIEW_V1_NOT_EXECUTABLE", text)
        self.assertIn("authorized=false", text)
        self.assertNotEqual(path.name, "arming_permit.txt")

    def test_dry_cycle_no_signal_passes_without_active_writes(self) -> None:
        result = review.dry_cycle(self.root, self.config, self._now())
        self.assertTrue(result["pass"])
        self.assertEqual(result["dry_cycle"]["status"], "NO_ELIGIBLE_CONTROLLED_PAPER_WAITING_SIGNAL")
        self.assertFalse((self.root / "mt5_files/XAUUSD_DEMO_BRIDGE/arming_permit.txt").exists())
        self.assertFalse((self.root / "mt5_files/XAUUSD_DEMO_BRIDGE/demo_candidate.txt").exists())

    def test_dry_cycle_builds_preview_only_for_eligible_signal(self) -> None:
        signal_dt = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        self._write_ledger(waiting=True, signal_dt=signal_dt)
        runtime = json.loads(self._runtime_path().read_text())
        runtime["generated_utc"] = "2026-01-01T10:30:00Z"
        self._runtime_path().write_text(json.dumps(runtime))
        result = review.dry_cycle(self.root, self.config, datetime(2026, 1, 1, 10, 59, 30, tzinfo=UTC))
        self.assertTrue(result["pass"])
        self.assertTrue(result["dry_cycle"]["candidate_previewed"])
        self.assertEqual(result["dry_cycle"]["preview"]["execution_mode"], "DRY_PREVIEW_ONLY")
        self.assertFalse(result["dry_cycle"]["preview"]["python_order_authorized"])
        self.assertFalse((self.root / "mt5_files/XAUUSD_DEMO_BRIDGE/demo_candidate.txt").exists())

    def test_dry_cycle_event_blackout_blocks_preview(self) -> None:
        signal_dt = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        self._write_ledger(waiting=True, signal_dt=signal_dt)
        runtime = json.loads(self._runtime_path().read_text())
        runtime["generated_utc"] = "2026-01-01T10:30:00Z"
        self._runtime_path().write_text(json.dumps(runtime))
        self._write_events([{
            "event_time_utc": "2026-01-01T11:00:00Z",
            "source": "BLS", "category": "BLS_CPI", "title": "CPI",
            "blackout_before_minutes": "60", "blackout_after_minutes": "60",
        }])
        result = review.dry_cycle(self.root, self.config, datetime(2026, 1, 1, 10, 59, 30, tzinfo=UTC))
        self.assertEqual(result["dry_cycle"]["status"], "EVENT_BLACKOUT_BLOCKED")
        self.assertFalse((self.root / "mt5_files/XAUUSD_DEMO_BRIDGE/demo_candidate.txt").exists())

    def test_weekend_stale_server_time_does_not_control_freshness(self) -> None:
        payload = json.loads(self._runtime_path().read_text())
        payload["heartbeat"]["generated_server_time"] = "2026.07.24 23:54:59"
        self._runtime_path().write_text(json.dumps(payload))
        result = review.build_review(self.root, self.config, self._now())
        self.assertTrue(result["checks"]["runtime"]["runtime_preflight_fresh"])

    def test_source_contains_no_active_permit_or_broker_calls(self) -> None:
        text = (PACKAGE_ROOT / "app/xauusd_mt5_demo_login_bound_review.py").read_text()
        self.assertNotIn("import MetaTrader5", text)
        self.assertNotIn("OrderSend", text)
        self.assertNotIn('write_text(active_paths(config)["arming_permit"]', text)
        self.assertIn("authorized=false", text)
        self.assertIn("active_candidate_written", text)


if __name__ == "__main__":
    unittest.main()
