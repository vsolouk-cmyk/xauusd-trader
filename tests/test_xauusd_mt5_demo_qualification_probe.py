import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app/xauusd_mt5_demo_qualification_probe.py"
spec = importlib.util.spec_from_file_location("probe", MODULE_PATH)
probe = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(probe)
UTC = timezone.utc


class QualificationProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mt5 = self.root / "mt5_files"
        self.bridge = self.mt5 / "XAUUSD_DEMO_BRIDGE"
        self.bridge.mkdir(parents=True)
        self.events = self.root / "events.csv"
        self.events.write_text(
            "event_time_utc,blackout_before_minutes,blackout_after_minutes,source,category,title\n"
            "2026-08-03T20:00:00Z,30,30,test,macro,far event\n",
            encoding="utf-8",
        )
        self.config = {
            "allowed_demo_login": 7907958,
            "expected_symbol": "XAUUSD",
            "magic_number": 1782401,
            "mt5_files_dir": str(self.mt5),
            "mt5_bridge_subdir": "XAUUSD_DEMO_BRIDGE",
            "heartbeat_file": "bridge_heartbeat.txt",
            "arming_permit_file": "arming_permit.txt",
            "candidate_file": "demo_candidate.txt",
            "official_event_csv": str(self.events),
        }
        self.now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC)
        (self.bridge / "bridge_heartbeat.txt").write_text("\n".join([
            f"program={probe.EA_PROGRAM}",
            "status=ARMED_RUNTIME_GUARDS_REQUIRED",
            "armed=true",
            "account_trade_mode=DEMO",
            "account_login=7907958",
            "allowed_demo_login=7907958",
            "symbol=XAUUSD",
            "magic_number=1782401",
            "target_volume_executable=true",
            "live_fallback_allowed=false",
            "symbol_bid=4000.00",
            "symbol_ask=4000.40",
            "spread_guard_bps=3.076477805949",
            "notional_to_equity=0.039259910172",
            "volume_min=0.010000000000",
            "qualification_probe_supported=true",
            "",
        ]), encoding="utf-8")
        hb_path = self.bridge / "bridge_heartbeat.txt"
        os.utime(hb_path, (self.now.timestamp(), self.now.timestamp()))
        (self.bridge / "arming_permit.txt").write_text("\n".join([
            f"schema_version={probe.ARMING_PERMIT_SCHEMA}",
            "authorized=true",
            "allowed_demo_login=7907958",
            "magic_number=1782401",
            f"expires_epoch={int(self.now.timestamp()) + 86400}",
            "bounded_preflight_sha256=abc123",
            "",
        ]), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_preflight_passes_inside_safe_window(self):
        result = probe.preflight(self.root, self.config, now=self.now)
        self.assertTrue(result["pass"])
        self.assertEqual(result["decision"], "PASS_QUALIFICATION_PROBE_PREFLIGHT_NO_ORDER")
        self.assertFalse(result["current_order_allowed"])

    def test_weekend_fails_closed(self):
        weekend = datetime(2026, 8, 1, 10, 0, 0, tzinfo=UTC)
        with self.assertRaises(probe.ProbeError):
            probe.preflight(self.root, self.config, now=weekend)
        failure = json.loads((self.root / "reports/xauusd_mt5_demo_qualification_probe/qualification_probe_preflight.json").read_text())
        self.assertIn("market_window", failure["failed_checks"])

    def test_stale_heartbeat_fails_closed(self):
        hb = self.bridge / "bridge_heartbeat.txt"
        old = self.now.timestamp() - 500
        os.utime(hb, (old, old))
        with self.assertRaises(probe.ProbeError):
            probe.preflight(self.root, self.config, now=self.now)

    def test_emit_writes_labelled_candidate_and_intent_bound_permit(self):
        result = probe.emit(self.root, self.config, "LONG", now=self.now)
        self.assertTrue(result["pass"])
        candidate = (self.bridge / "demo_candidate.txt").read_text()
        permit = (self.bridge / "qualification_probe_permit.txt").read_text()
        self.assertIn("candidate_class=QUALIFICATION_PROBE_NOT_ALPHA", candidate)
        self.assertIn("probe_exit_after_seconds=120", candidate)
        self.assertIn(f"intent_id={result['intent_id']}", permit)
        self.assertIn("maximum_volume=0.01000000", permit)
        self.assertIn("python_order_authorized=False", candidate)
        summary = json.loads((self.root / "reports/xauusd_mt5_demo_qualification_probe/qualification_probe_emit_summary.json").read_text())
        self.assertEqual(summary["state"], "EMITTED")


    def test_inspect_without_emit_returns_explicit_no_order_state(self):
        result = probe.inspect(self.root, self.config)
        self.assertFalse(result["pass"])
        self.assertEqual(result["decision"], "QUALIFICATION_PROBE_NOT_EMITTED_NO_ORDER")
        self.assertEqual(result["failed_checks"], ["emit_intent_present"])
        self.assertFalse(result["current_order_allowed"])

    def test_collect_without_complete_lifecycle_creates_no_zip(self):
        output = self.root / "evidence.zip"
        result = probe.collect(self.root, self.config, output)
        self.assertFalse(result["pass"])
        self.assertEqual(result["decision"], "QUALIFICATION_PROBE_EVIDENCE_NOT_READY")
        self.assertFalse(result["output_created"])
        self.assertFalse(output.exists())

    def test_inspect_recovers_intent_from_outbox_when_summary_missing(self):
        emitted = probe.emit(self.root, self.config, "LONG", now=self.now)
        summary = self.root / "reports/xauusd_mt5_demo_qualification_probe/qualification_probe_emit_summary.json"
        summary.unlink()
        result = probe.inspect(self.root, self.config)
        self.assertEqual(result["intent_id"], emitted["intent_id"])
        self.assertEqual(result["emit_record_source"], "outbox_candidate")
        self.assertEqual(result["decision"], "QUALIFICATION_PROBE_PENDING_OR_FAIL_CLOSED")

    def test_inspect_accepts_complete_single_lifecycle(self):
        emitted = probe.emit(self.root, self.config, "LONG", now=self.now)
        intent = emitted["intent_id"]
        (self.bridge / "qualification_probe_permit.txt").unlink()
        receipts = self.bridge / "receipts"
        receipts.mkdir()
        (receipts / f"{intent}.txt").write_text("\n".join([
            f"intent_id={intent}", "status=RESOLVED", "reason=QUALIFICATION_PROBE_TIME_EXIT", "",
        ]), encoding="utf-8")
        (receipts / f"{intent}_DUPLICATE_BLOCKED.txt").write_text(f"intent_id={intent}\nevent=DUPLICATE_BLOCKED\n", encoding="utf-8")
        (self.bridge / "qualification_probe_lockdown.txt").write_text(
            f"intent_id={intent}\nstatus=RESOLVED\nreason=QUALIFICATION_PROBE_TIME_EXIT\n",
            encoding="utf-8",
        )
        header = "server_time\tevent\tintent_id\treason\taccount_trade_mode\taccount_login\tsymbol\tmagic_number\torder_ticket\tdeal_ticket\tposition_ticket\trequested_price\tfill_price\tvolume\tspread_bps\tslippage_bps\tprofit\tcommission\tswap\tfee\tretcode\tretcode_description\n"
        rows = [
            f"2026.08.03 13:30:10\tOPEN_FILLED\t{intent}\tRUNTIME_GUARDS_PASSED\tDEMO\t7907958\tXAUUSD\t1782401\t101\t201\t301\t4000.40\t4000.40\t0.01000000\t1.0\t0.0\t0\t-0.1\t0\t0\t10009\tRequest completed\n",
            f"2026.08.03 13:30:11\tDUPLICATE_BLOCKED\t{intent}\tRECEIPT_EXISTS_IDEMPOTENCY_GUARD\tDEMO\t7907958\tXAUUSD\t1782401\t0\t0\t0\t0\t0\t0\t1.0\t0\t0\t0\t0\t0\t0\t\n",
            f"2026.08.03 13:32:10\tRESOLVED\t{intent}\tQUALIFICATION_PROBE_TIME_EXIT\tDEMO\t7907958\tXAUUSD\t1782401\t102\t202\t301\t4000.20\t4000.20\t0.01000000\t1.0\t0.0\t-0.2\t-0.1\t0\t0\t10009\tRequest completed\n",
        ]
        (self.bridge / "qualification_probe_journal.tsv").write_text(header + "".join(rows), encoding="utf-8")
        result = probe.inspect(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertEqual(result["decision"], "PASS_DEMO_QUALIFICATION_PROBE_FULL_LIFECYCLE")


    def test_inspect_rejects_missing_exit_accounting_price(self):
        emitted = probe.emit(self.root, self.config, "LONG", now=self.now)
        intent = emitted["intent_id"]
        (self.bridge / "qualification_probe_permit.txt").unlink()
        receipts = self.bridge / "receipts"
        receipts.mkdir()
        (receipts / f"{intent}.txt").write_text(f"intent_id={intent}\nstatus=RESOLVED\n", encoding="utf-8")
        (receipts / f"{intent}_DUPLICATE_BLOCKED.txt").write_text(f"intent_id={intent}\nevent=DUPLICATE_BLOCKED\n", encoding="utf-8")
        (self.bridge / "qualification_probe_lockdown.txt").write_text(f"intent_id={intent}\nstatus=RESOLVED\n", encoding="utf-8")
        header = "server_time\tevent\tintent_id\treason\taccount_trade_mode\taccount_login\tsymbol\tmagic_number\torder_ticket\tdeal_ticket\tposition_ticket\trequested_price\tfill_price\tvolume\tspread_bps\tslippage_bps\tprofit\tcommission\tswap\tfee\tretcode\tretcode_description\n"
        rows = [
            f"2026.08.03 13:30:10\tOPEN_FILLED\t{intent}\tRUNTIME_GUARDS_PASSED\tDEMO\t7907958\tXAUUSD\t1782401\t101\t201\t301\t4000.40\t4000.40\t0.01000000\t1.0\t0.0\t0\t0\t0\t0\t10009\tdone\n",
            f"2026.08.03 13:30:11\tDUPLICATE_BLOCKED\t{intent}\tRECEIPT_EXISTS_IDEMPOTENCY_GUARD\tDEMO\t7907958\tXAUUSD\t1782401\t0\t0\t0\t0\t0\t0\t1.0\t0\t0\t0\t0\t0\t0\t\n",
            f"2026.08.03 13:32:10\tRESOLVED\t{intent}\tQUALIFICATION_PROBE_TIME_EXIT\tDEMO\t7907958\tXAUUSD\t1782401\t102\t202\t301\t0.00\t4000.20\t0.01000000\t1.0\t0.0\t-0.2\t0\t0\t0\t10009\tdone\n",
        ]
        (self.bridge / "qualification_probe_journal.tsv").write_text(header + "".join(rows), encoding="utf-8")
        result = probe.inspect(self.root, self.config)
        self.assertFalse(result["pass"])
        self.assertIn("exit_requested_price_recorded", result["failed_checks"])

    def test_cleanup_requires_disabled_heartbeat_and_removes_activation_files(self):
        emitted = probe.emit(self.root, self.config, "LONG", now=self.now)
        rdir = self.root / "reports/xauusd_mt5_demo_qualification_probe"
        (rdir / "qualification_probe_inspection.json").write_text(json.dumps({"pass": True}), encoding="utf-8")
        (self.bridge / "qualification_probe_lockdown.txt").write_text(f"intent_id={emitted['intent_id']}\n", encoding="utf-8")
        (self.bridge / "bridge_heartbeat.txt").write_text("armed=false\nstatus=DISABLED_DEFAULT_NO_ORDER\n", encoding="utf-8")
        result = probe.cleanup(self.root, self.config)
        self.assertTrue(result["pass"])
        self.assertFalse((self.bridge / "demo_candidate.txt").exists())
        self.assertFalse((self.bridge / "qualification_probe_lockdown.txt").exists())

    def test_ea_source_contains_fail_closed_probe_contract(self):
        ea = (Path(__file__).resolve().parents[1] / "mt5/XAUUSD_BoundedDemoBridge.mq5").read_text()
        for token in (
            "QUALIFICATION_PROBE_NOT_ALPHA",
            "XAUUSD_DEMO_QUALIFICATION_PROBE_PERMIT_V1",
            "qualification_probe_journal.tsv",
            "QUALIFICATION_PROBE_COMPLETE_MANUAL_DISARM_REQUIRED",
            "DUPLICATE_BLOCKED",
            "InpProbeMaximumExitSeconds",
            "ConsumeQualificationProbePermit",
            "ReadDealAccountingWithRetry",
            "ExitAdverseSlippageBps",
        ):
            self.assertIn(token, ea)
        for forbidden in ("LIVE_ACCOUNT_FALLBACK", "WebRequest("):
            self.assertNotIn(forbidden, ea)


if __name__ == "__main__":
    unittest.main()
