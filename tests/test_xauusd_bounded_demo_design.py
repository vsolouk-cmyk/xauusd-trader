from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app/xauusd_bounded_demo_design.py"
spec = importlib.util.spec_from_file_location("bounded_demo", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

UTC = timezone.utc


class BoundedDemoDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel in (
            "reports/xauusd_controlled_paper_replay",
            "reports/xauusd_historical_event_context",
            "reports/xauusd_controlled_paper",
            "reports/commercial_closure_sprint",
            "data/fundamental_event_inbox/features",
            "data/local/stage177c_amarkets_alignment",
            "config",
            "schemas",
        ):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        package_root = MODULE_PATH.parents[1]
        shutil.copy2(package_root / "config/xauusd_bounded_demo_design.json", self.root / "config/xauusd_bounded_demo_design.json")
        shutil.copy2(package_root / "config/xauusd_controlled_paper.json", self.root / "config/xauusd_controlled_paper.json")
        shutil.copy2(package_root / "schemas/xauusd_demo_intent.schema.json", self.root / "schemas/xauusd_demo_intent.schema.json")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def copy_actual_evidence(self) -> None:
        data_root = MODULE_PATH.parents[1] / "tests/fixtures"
        shutil.copy2(
            data_root / "historical_asof_replay_summary_v7.json",
            self.root / "reports/xauusd_controlled_paper_replay/historical_asof_replay_summary.json",
        )
        shutil.copy2(
            data_root / "historical_event_context_summary_v1_2.json",
            self.root / "reports/xauusd_historical_event_context/historical_event_context_summary.json",
        )
        shutil.copy2(
            data_root / "controlled_paper_summary_v1_5.json",
            self.root / "reports/xauusd_controlled_paper/controlled_paper_summary.json",
        )
        shutil.copy2(
            data_root / "controlled_paper_preflight_v1_5.json",
            self.root / "reports/xauusd_controlled_paper/controlled_paper_preflight.json",
        )

    def risk_contract(self) -> dict:
        # Exact real-artifact shape: the spread guard is not stored here.
        return {
            "bootstrap_p95_drawdown_bps_at_1x": 2153.4562324816197,
            "candidate": "logistic__direction_24h",
            "daily_new_positions_cap": 1,
            "decision": "KILL_CURRENT_COMMERCIAL_FORMULATION",
            "demo_allowed": False,
            "estimated_bootstrap_p95_drawdown_equity_pct": 3.381779929854221,
            "estimated_q95_single_trade_loss_equity_pct": 0.5,
            "hard_drawdown_kill_switch_equity_pct": 8.0,
            "live_allowed": False,
            "maximum_concurrent_positions": 1,
            "maximum_notional_to_equity": 0.1570396406876166,
            "normal_execution_cost_floor_bps": 3.0,
            "paper_only": True,
            "q95_single_trade_loss_bps_at_1x": 318.39094754081896,
            "severe_execution_cost_floor_bps": 4.5,
            "weekly_loss_pause_equity_pct": 2.0,
        }

    def write_risk(self) -> None:
        risk = self.risk_contract()
        (self.root / "reports/commercial_closure_sprint/commercial_closure_risk_contract.json").write_text(
            json.dumps(risk, indent=2), encoding="utf-8"
        )
        summary = {
            "program": "XAUUSD_COMMERCIAL_CLOSURE_SPRINT",
            "candidate": "logistic__direction_24h",
            "decision": "KILL_CURRENT_COMMERCIAL_FORMULATION",
            "observed_spread_p95_bps": 3.0764778059487488,
            "risk_contract": risk,
        }
        (self.root / "reports/commercial_closure_sprint/commercial_closure_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

    def write_event_csv_and_patch_hashes(self, latest_h1: datetime, calendar_days: int = 180) -> None:
        categories = sorted(mod.REQUIRED_EVENT_CATEGORIES)
        rows = []
        for index, category in enumerate(categories):
            event_time = latest_h1 + timedelta(days=calendar_days, hours=index)
            source = "BLS" if category.startswith("BLS") else "BEA" if category.startswith("BEA") else "FED"
            rows.append({
                "event_time_utc": mod.iso_utc(event_time),
                "source": source,
                "category": category,
                "title": category,
                "source_url": "https://example.invalid/official",
                "source_file": "fixture",
                "date_source": "FIXTURE",
                "time_source": "FIXTURE",
                "blackout_before_minutes": "60",
                "blackout_after_minutes": "60",
                "release_id": "",
            })
        event_csv = self.root / "data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv"
        with event_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        event_summary_path = self.root / "reports/xauusd_historical_event_context/historical_event_context_summary.json"
        event = json.loads(event_summary_path.read_text(encoding="utf-8"))
        event["source_official_events_csv_sha256"] = mod.sha256_file(event_csv)
        event_summary_path.write_text(json.dumps(event, indent=2), encoding="utf-8")
        replay_path = self.root / "reports/xauusd_controlled_paper_replay/historical_asof_replay_summary.json"
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        replay["historical_event_context"]["summary_sha256"] = mod.sha256_file(event_summary_path)
        replay_path.write_text(json.dumps(replay, indent=2), encoding="utf-8")

    def write_aligned_db(self, latest_h1: datetime) -> None:
        path = self.root / "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"
        con = sqlite3.connect(path)
        try:
            con.execute("CREATE TABLE amarkets_h1_direct_utc(timestamp INTEGER, open REAL, high REAL, low REAL, close REAL)")
            con.execute(
                "INSERT INTO amarkets_h1_direct_utc VALUES(?,?,?,?,?)",
                (int(latest_h1.timestamp() * 1000), 1.0, 1.0, 1.0, 1.0),
            )
            con.commit()
        finally:
            con.close()

    def test_actual_uploaded_summaries_close_design(self) -> None:
        self.copy_actual_evidence()
        config = mod.load_config(self.root, "config/xauusd_bounded_demo_design.json")
        result = mod.build_design(self.root, config)
        self.assertTrue(result["pass"])
        self.assertEqual(result["decision"], "PASS_BOUNDED_DEMO_DESIGN_NO_ORDER_PATH")
        self.assertFalse(result["demo_order_allowed"])
        self.assertEqual(result["validated_historical_readout"]["strict_resolved_positions"], 117)
        self.assertAlmostEqual(result["validated_historical_readout"]["strict_profit_factor"], 1.556682946785611)
        self.assertAlmostEqual(result["risk_contract"]["initial_demo_notional_to_equity"], 0.03925991017190415)

    def test_event_summary_hash_mismatch_fails_closed(self) -> None:
        self.copy_actual_evidence()
        event = self.root / "reports/xauusd_historical_event_context/historical_event_context_summary.json"
        payload = json.loads(event.read_text(encoding="utf-8"))
        payload["official_event_count"] = 999
        event.write_text(json.dumps(payload), encoding="utf-8")
        config = mod.load_config(self.root, "config/xauusd_bounded_demo_design.json")
        with self.assertRaisesRegex(mod.DemoDesignError, "event_summary_hash_link"):
            mod.build_design(self.root, config)

    def test_operational_preflight_passes_with_full_calendar_and_risk(self) -> None:
        self.copy_actual_evidence()
        latest = datetime(2026, 7, 24, 10, tzinfo=UTC)
        self.write_event_csv_and_patch_hashes(latest, calendar_days=180)
        self.write_aligned_db(latest)
        self.write_risk()
        config = mod.load_config(self.root, "config/xauusd_bounded_demo_design.json")
        result = mod.build_preflight(self.root, config)
        self.assertTrue(result["pass"])
        self.assertEqual(result["decision"], "PASS_BOUNDED_DEMO_OPERATIONAL_PREFLIGHT_NO_ORDER_PATH")
        self.assertFalse(result["demo_order_allowed"])
        self.assertTrue(result["operational_checks"]["official_event_calendar_through_exit_horizon"])

    def test_operational_preflight_rejects_short_calendar_horizon(self) -> None:
        self.copy_actual_evidence()
        latest = datetime(2026, 7, 24, 10, tzinfo=UTC)
        self.write_event_csv_and_patch_hashes(latest, calendar_days=0)
        self.write_aligned_db(latest)
        self.write_risk()
        config = mod.load_config(self.root, "config/xauusd_bounded_demo_design.json")
        with self.assertRaisesRegex(mod.DemoDesignError, "does not cover the full exit horizon"):
            mod.build_preflight(self.root, config)

    def test_exact_real_risk_contract_without_spread_field_passes(self) -> None:
        self.copy_actual_evidence()
        latest = datetime(2026, 7, 24, 10, tzinfo=UTC)
        self.write_event_csv_and_patch_hashes(latest, calendar_days=180)
        self.write_aligned_db(latest)
        self.write_risk()
        config = mod.load_config(self.root, "config/xauusd_bounded_demo_design.json")
        result = mod.build_preflight(self.root, config)
        provenance = result["operational_checks"]["spread_guard_provenance"]
        self.assertTrue(result["pass"])
        self.assertFalse(provenance["commercial_risk_contract_field_present"])
        self.assertTrue(all(provenance["checks"].values()))
        self.assertEqual(
            provenance["authoritative_source"],
            "commercial_closure_summary.observed_spread_p95_bps",
        )

    def test_commercial_summary_spread_mismatch_fails_closed(self) -> None:
        self.copy_actual_evidence()
        latest = datetime(2026, 7, 24, 10, tzinfo=UTC)
        self.write_event_csv_and_patch_hashes(latest, calendar_days=180)
        self.write_aligned_db(latest)
        self.write_risk()
        path = self.root / "reports/commercial_closure_sprint/commercial_closure_summary.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["observed_spread_p95_bps"] = 9.99
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        config = mod.load_config(self.root, "config/xauusd_bounded_demo_design.json")
        with self.assertRaisesRegex(mod.DemoDesignError, "spread guard provenance mismatch"):
            mod.build_preflight(self.root, config)

    def test_optional_risk_spread_field_must_match_when_present(self) -> None:
        self.copy_actual_evidence()
        latest = datetime(2026, 7, 24, 10, tzinfo=UTC)
        self.write_event_csv_and_patch_hashes(latest, calendar_days=180)
        self.write_aligned_db(latest)
        self.write_risk()
        risk_path = self.root / "reports/commercial_closure_sprint/commercial_closure_risk_contract.json"
        risk = json.loads(risk_path.read_text(encoding="utf-8"))
        risk["observed_entry_spread_guard_bps"] = 7.0
        risk_path.write_text(json.dumps(risk, indent=2), encoding="utf-8")
        summary_path = self.root / "reports/commercial_closure_sprint/commercial_closure_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["risk_contract"] = risk
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        config = mod.load_config(self.root, "config/xauusd_bounded_demo_design.json")
        with self.assertRaisesRegex(mod.DemoDesignError, "spread guard provenance mismatch"):
            mod.build_preflight(self.root, config)

    def test_controlled_config_uses_stage115_event_calendar(self) -> None:
        cfg = json.loads((self.root / "config/xauusd_controlled_paper.json").read_text(encoding="utf-8"))
        self.assertEqual(
            cfg["event_guard"]["csv_candidates"][0],
            "data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv",
        )


if __name__ == "__main__":
    unittest.main()
