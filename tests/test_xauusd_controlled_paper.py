from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "xauusd_controlled_paper.py"
SPEC = importlib.util.spec_from_file_location("xauusd_controlled_paper_tested", MODULE_PATH)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

UTC = timezone.utc
TEST_NOW = datetime(2015, 2, 17, 3, 0, tzinfo=UTC)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    def __init__(
        self,
        root: Path,
        *,
        spread_points: float = 20.0,
        event_db: bool = True,
        signal: bool = True,
        db_has_spread: bool = False,
        spread_csv: bool = True,
        spread_csv_time_offset_minutes: int = 0,
    ):
        self.root = root
        self.start = datetime(2015, 1, 2, 7, tzinfo=UTC)
        package_root = Path(__file__).resolve().parents[1]
        (root / "config").mkdir(parents=True, exist_ok=True)
        config = json.loads((package_root / "config/xauusd_controlled_paper.json").read_text(encoding="utf-8"))
        self.spread_csv = root / "fixture_downloads/amarkets_xauusd_5m.csv"
        # Unit tests must never fall through to a developer/user Downloads tree.
        config["spread_source"]["csv_candidates"] = [str(self.spread_csv)]
        write_json(root / "config/xauusd_controlled_paper.json", config)
        (root / "data/controlled_paper").mkdir(parents=True, exist_ok=True)
        (root / "data/controlled_paper/event_blackout.csv").write_text(
            "event_time_utc,blackout_before_minutes,blackout_after_minutes,title,required\n", encoding="utf-8"
        )
        self.market_db = root / "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"
        self.market_db.parent.mkdir(parents=True, exist_ok=True)
        self._market(spread_points, db_has_spread, spread_csv, spread_csv_time_offset_minutes)
        self._time_contract()
        if event_db:
            self._event()
        self.model = root / "data/local/stage178_commercial_edge_decision_sprint/stage178_selected_model.pkl"
        self.contract = root / "data/local/stage178_commercial_edge_decision_sprint/stage178_selected_model_contract.json"
        self.model.parent.mkdir(parents=True, exist_ok=True)
        self.model.write_bytes(b"frozen-model-fixture")
        write_json(self.contract, {
            "candidate": "logistic__direction_24h",
            "model": "logistic",
            "target": "direction_24h",
            "threshold": 0.60,
            "horizon_hours": 24,
            "selection_used_holdout": False,
        })
        self._commercial()
        self._stage180(signal)

    @staticmethod
    def _broker_naive(dt_utc: datetime) -> datetime:
        minutes = 180 if MOD.eu_dst_active_utc(dt_utc) else 120
        return (dt_utc + timedelta(minutes=minutes)).replace(tzinfo=None)

    def _market(
        self,
        spread_points: float,
        db_has_spread: bool,
        spread_csv: bool,
        spread_csv_time_offset_minutes: int,
    ) -> None:
        conn = sqlite3.connect(self.market_db)
        if db_has_spread:
            conn.executescript(
                """
                CREATE TABLE amarkets_h1_from_m5_utc(timestamp_ms INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, spread REAL);
                CREATE TABLE amarkets_m5_utc(timestamp_ms INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, spread REAL);
                """
            )
        else:
            conn.executescript(
                """
                CREATE TABLE amarkets_h1_from_m5_utc(timestamp_ms INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL);
                CREATE TABLE amarkets_m5_utc(timestamp_ms INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL);
                """
            )
        h1_rows = []
        m5_rows = []
        csv_rows = []
        for i in range(1100):
            dt = self.start + timedelta(hours=i)
            ts = int(dt.timestamp() * 1000)
            base = 2000.0 + i * 0.10
            h1_core = (ts, base, base + 1.0, base - 1.0, base + 0.20)
            h1_rows.append((*h1_core, spread_points) if db_has_spread else h1_core)
            for j in range(12):
                mdt = dt + timedelta(minutes=5 * j)
                mts = int(mdt.timestamp() * 1000)
                mbase = base + j * 0.01
                m5_core = (mts, mbase, mbase + 0.2, mbase - 0.2, mbase + 0.02)
                m5_rows.append((*m5_core, spread_points) if db_has_spread else m5_core)
                broker_dt = self._broker_naive(mdt + timedelta(minutes=spread_csv_time_offset_minutes))
                csv_rows.append((
                    broker_dt.strftime("%Y.%m.%d"),
                    broker_dt.strftime("%H:%M:%S"),
                    mbase,
                    mbase + 0.2,
                    mbase - 0.2,
                    mbase + 0.02,
                    100,
                    0,
                    spread_points,
                ))
        placeholders_h1 = ",".join("?" for _ in h1_rows[0])
        placeholders_m5 = ",".join("?" for _ in m5_rows[0])
        conn.executemany(f"INSERT INTO amarkets_h1_from_m5_utc VALUES({placeholders_h1})", h1_rows)
        conn.executemany(f"INSERT INTO amarkets_m5_utc VALUES({placeholders_m5})", m5_rows)
        conn.commit()
        conn.close()
        if spread_csv:
            self.spread_csv.parent.mkdir(parents=True, exist_ok=True)
            with self.spread_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>", "<TICKVOL>", "<VOL>", "<SPREAD>"])
                writer.writerows(csv_rows)

    def _time_contract(self) -> None:
        write_json(
            self.root / "reports/stage177c_amarkets_alignment/stage177c_time_contract.json",
            {
                "contract": "EU_DST_GMT_OFFSET_PAIR",
                "decision": "PASS_AMARKETS_DST_AWARE_UTC_CONTRACT",
                "dst_calendar": "EU",
                "dst_shift_minutes": -180,
                "standard_shift_minutes": -120,
                "stage": "177C",
                "shift_semantics": "timestamp_utc = timestamp_naive + shift_minutes",
                "selection_used_holdout": False,
                "source_amarkets_m5": str(self.spread_csv),
            },
        )

    def _event(self) -> None:
        path = self.root / "data/local/xauusd_local_store.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE macro_context_h1(utc_time TEXT PRIMARY KEY, has_block_event INTEGER, active_event_count INTEGER)")
        for i in range(1100):
            dt = self.start + timedelta(hours=i)
            conn.execute("INSERT INTO macro_context_h1 VALUES(?,?,?)", (dt.isoformat(), 0, 0))
        conn.commit()
        conn.close()

    def _commercial(self) -> None:
        report = self.root / "reports/commercial_closure"
        report.mkdir(parents=True, exist_ok=True)
        gates = {
            "bootstrap_p10_positive": True,
            "holdout_positive": True,
            "minimum_execution_coverage": False,
            "minimum_normal_mean": True,
            "minimum_profit_factor": True,
            "minimum_severe_mean": True,
            "minimum_trades": True,
            "positive_period_share": True,
            "risk_contract_drawdown": True,
            "stage178_reference_parity": True,
            "stress_8bps_positive": True,
            "transfer_ratio": True,
            "year_concentration": True,
        }
        write_json(report / "commercial_closure_summary.json", {
            "signals_total": 168,
            "execution_evaluated_trades": 146,
            "execution_coverage": 146 / 168,
            "gates": gates,
            "reference_parity": {"pass": True},
        })
        write_json(report / "commercial_closure_risk_contract.json", {
            "maximum_notional_to_equity": 0.1570396406876166,
            "maximum_concurrent_positions": 1,
            "daily_new_positions_cap": 1,
            "weekly_loss_pause_equity_pct": 2.0,
            "hard_drawdown_kill_switch_equity_pct": 8.0,
            "normal_execution_cost_floor_bps": 3.0,
            "severe_execution_cost_floor_bps": 4.5,
            "paper_only": True,
            "demo_allowed": False,
            "live_allowed": False,
        })
        ledger_path = report / "commercial_closure_execution_ledger.csv"
        fieldnames = [
            "timestamp", "dt", "source_period", "fold", "direction", "probability_up",
            "resolution_hours", "research_gross_bps", "horizon_semantics",
            "entry_bucket_timestamp", "exit_bucket_timestamp", "entry_bucket_utc",
            "exit_bucket_utc", "status", "m5_gross_bps",
            "gross_transfer_difference_bps", "entry_open", "exit_close",
            "observed_spread_bps", "normal_execution_cost_bps",
            "severe_execution_cost_bps", "normal_net_bps", "severe_net_bps",
            "stress_8bps_net_bps", "stress_10bps_net_bps",
        ]
        with ledger_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for i in range(22):
                signal_dt = datetime(2014, 1, 1, tzinfo=UTC) + timedelta(hours=i)
                writer.writerow({
                    "timestamp": signal_dt.isoformat(),
                    "dt": signal_dt.isoformat(),
                    "source_period": "pre_operational",
                    "fold": 0,
                    "direction": 1,
                    "probability_up": 0.70,
                    "resolution_hours": 24,
                    "research_gross_bps": 12.0,
                    "horizon_semantics": "i+1/i+24",
                    "status": "UNEVALUATED_MISSING_M5_COVERAGE",
                })
            for i in range(146):
                signal_dt = self.start + timedelta(hours=i)
                writer.writerow({
                    "timestamp": signal_dt.isoformat(),
                    "dt": signal_dt.isoformat(),
                    "source_period": "operational",
                    "fold": 1,
                    "direction": 1,
                    "probability_up": 0.70 if i < 55 else 0.30,
                    "resolution_hours": 24,
                    "research_gross_bps": 15.0,
                    "horizon_semantics": "i+1/i+24",
                    "entry_bucket_timestamp": signal_dt.isoformat(),
                    "exit_bucket_timestamp": (signal_dt + timedelta(hours=24)).isoformat(),
                    "entry_bucket_utc": signal_dt.isoformat(),
                    "exit_bucket_utc": (signal_dt + timedelta(hours=24)).isoformat(),
                    "status": "EVALUATED",
                    "m5_gross_bps": 13.0,
                    "gross_transfer_difference_bps": -2.0,
                    "entry_open": 2000.0,
                    "exit_close": 2002.6,
                    "observed_spread_bps": 1.0,
                    "normal_execution_cost_bps": 3.0,
                    "severe_execution_cost_bps": 4.5,
                    "normal_net_bps": 10.0,
                    "severe_net_bps": 8.5,
                    "stress_8bps_net_bps": 5.0,
                    "stress_10bps_net_bps": 3.0,
                })

        replay_report = self.root / "reports/xauusd_controlled_paper_replay"
        replay_report.mkdir(parents=True, exist_ok=True)
        commercial_summary_path = report / "commercial_closure_summary.json"
        write_json(replay_report / "historical_asof_replay_summary.json", {
            "program": "XAUUSD_CONTROLLED_PAPER_HISTORICAL_ASOF_REPLAY_V6_FORWARD_DIRECTION_POLICY_PARITY_CLOSURE",
            "decision": "PASS_CORE_HISTORICAL_ASOF_REPLAY_FORWARD_DIRECTION_POLICY_PARITY_CLOSED_EVENT_COVERAGE_INCOMPLETE",
            "pass": True,
            "forward_wait_required_for_replay": False,
            "source_execution_ledger_sha256": sha(ledger_path),
            "commercial_summary_sha256": sha(commercial_summary_path),
            "controlled_paper_promotion_allowed": True,
            "validation": {
                "evaluated_side_counts": {"LONG": 55, "SHORT": 91},
                "commercial_reference_metric_parity": {"pass": True},
                "stress_cost_contract": {
                    "source_proven": True,
                    "commercial_execution_parity_pass": True,
                },
            },
            "current_forward_policy_parity": {
                "pass": True,
                "forward_direction_policy": "BIDIRECTIONAL_PROBABILITY_TAILS",
            },
        })

    def _stage180(self, signal: bool) -> None:
        report = self.root / "reports/stage180_frozen_model_parallel_shadow"
        report.mkdir(parents=True, exist_ok=True)
        index = 1000
        dt = self.start + timedelta(hours=index)
        p = 0.70 if signal else 0.47
        direction = 1 if signal else 0
        status = "SIGNAL" if signal else "NO_SIGNAL"
        latest_h1 = self.start + timedelta(hours=1099)
        write_json(report / "stage180_summary.json", {
            "generated_utc": (latest_h1 + timedelta(minutes=30)).isoformat(),
            "aligned_last_complete_bar_utc": latest_h1.isoformat(),
            "decision": "STAGE180_FROZEN_MODEL_SHADOW_ACTIVE_NO_ORDER",
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "paper_order_allowed": False,
            "execution_allowed": False,
            "shadow_observation_allowed": True,
            "model_sha256": sha(self.model),
            "contract_sha256": sha(self.contract),
            "aligned_db": str(self.market_db),
            "refresh": {"sources": [str(self.spread_csv)]},
            "latest_observation": {
                "created_utc": dt.isoformat(),
                "direction": direction,
                "observation_status": status,
                "probability_up": p,
                "signal_dt": dt.isoformat(),
                "signal_timestamp": int(dt.timestamp() * 1000),
            },
        })


class ControlledPaperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._real_utc_now = MOD.utc_now
        MOD.utc_now = lambda: TEST_NOW

    def tearDown(self) -> None:
        MOD.utc_now = self._real_utc_now

    def test_python314_dynamic_import_regression(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "decorated_module.py"
            path.write_text(
                "from dataclasses import dataclass\n"
                "@dataclass(slots=True)\n"
                "class Sample:\n"
                "    value: int = 7\n",
                encoding="utf-8",
            )
            module = MOD.dynamic_import_module(path, "controlled_paper_dynamic_import_fixture")
            self.assertEqual(module.Sample().value, 7)
            self.assertIs(sys.modules["controlled_paper_dynamic_import_fixture"], module)

    def test_clean_preflight_and_exact_row_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = Fixture(root, signal=True, db_has_spread=False, spread_csv=True)
            code, payload = MOD.execute(root, None, "preflight")
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["missing_coverage_audit"]["decision"], "PASS_BOUNDED_MISSING_COVERAGE_NOT_CURRENT_SYSTEMATIC_DEFECT")
            self.assertFalse(payload["checks"]["m5_spread_present_in_aligned_db"])
            self.assertEqual(payload["checks"]["spread_source"]["kind"], "AMARKETS_M5_RAW_CSV_SPREAD")
            self.assertTrue(payload["checks"]["spread_source"]["pass"])
            self.assertTrue(payload["checks"]["operational_freshness"]["pass"])
            self.assertEqual(
                payload["checks"]["operational_freshness"]["decision"],
                "PASS_OPERATIONAL_FRESHNESS_OPEN_MARKET",
            )
            code, summary = MOD.execute(root, None, "run")
            self.assertEqual(code, 0, summary)
            self.assertEqual(summary["decision"], "CONTROLLED_PAPER_ACTIVE_PAPER_LOG_ONLY_NO_BROKER")
            conn = sqlite3.connect(root / "data/controlled_paper/xauusd_controlled_paper.sqlite")
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM positions").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "RESOLVED")
            self.assertEqual(row["entry_row_index"], 1001)
            self.assertEqual(row["exit_row_index"], 1024)
            expected_entry = 2000.0 + 1001 * 0.10
            expected_exit = 2000.0 + 1024 * 0.10 + 0.20
            self.assertAlmostEqual(row["entry_price"], expected_entry, places=9)
            self.assertAlmostEqual(row["exit_price"], expected_exit, places=9)
            self.assertLessEqual(row["entry_spread_bps"], 3.0764778059487488)
            conn.close()


    def test_v7_event_context_replay_is_accepted_by_controlled_paper_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, signal=False)
            replay_path = root / "reports/xauusd_controlled_paper_replay/historical_asof_replay_summary.json"
            replay = json.loads(replay_path.read_text(encoding="utf-8"))
            replay["program"] = "XAUUSD_CONTROLLED_PAPER_HISTORICAL_ASOF_REPLAY_V7_OFFICIAL_EVENT_CONTEXT_CLOSURE"
            replay["decision"] = "PASS_FULL_HISTORICAL_EVENT_AWARE_REPLAY_DEMO_DESIGN_ALLOWED_NO_FORWARD_WAIT"
            replay["historical_event_context"] = {"contract_pass": True}
            replay["event_evidence"] = {"coverage_complete": True}
            write_json(replay_path, replay)
            code, payload = MOD.execute(root, None, "preflight")
            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["checks"]["historical_replay_event_context_contract"])

    def test_no_signal_is_logged_without_position(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, signal=False)
            code, summary = MOD.execute(root, None, "run")
            self.assertEqual(code, 0, summary)
            self.assertEqual(summary["counts"]["signals"], 1)
            self.assertEqual(summary["counts"]["pending_positions"], 0)
            self.assertEqual(summary["counts"]["resolved_positions"], 0)

    def test_spread_guard_blocks_signal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, spread_points=100.0, signal=True)
            code, summary = MOD.execute(root, None, "run")
            self.assertEqual(code, 0, summary)
            conn = sqlite3.connect(root / "data/controlled_paper/xauusd_controlled_paper.sqlite")
            reason = conn.execute("SELECT reason FROM blocked_signals").fetchone()[0]
            status = conn.execute("SELECT status FROM positions").fetchone()[0]
            self.assertEqual(reason, "ENTRY_SPREAD_GUARD")
            self.assertEqual(status, "BLOCKED")
            conn.close()

    def test_missing_event_data_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, event_db=False, signal=True)
            code, summary = MOD.execute(root, None, "run")
            self.assertEqual(code, 0, summary)
            conn = sqlite3.connect(root / "data/controlled_paper/xauusd_controlled_paper.sqlite")
            reason = conn.execute("SELECT reason FROM blocked_signals").fetchone()[0]
            self.assertEqual(reason, "EVENT_DATA_ABSENT_FAIL_CLOSED")
            conn.close()

    def test_aligned_db_without_spread_and_missing_raw_csv_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, signal=False, db_has_spread=False, spread_csv=False)
            code, payload = MOD.execute(root, None, "preflight")
            self.assertEqual(code, 2)
            self.assertIn("required file not found", payload["error"])

    def test_spread_csv_alignment_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(
                root, signal=False, db_has_spread=False, spread_csv=True,
                spread_csv_time_offset_minutes=60,
            )
            code, payload = MOD.execute(root, None, "preflight")
            self.assertEqual(code, 2)
            self.assertIn("spread source parity failed", payload["error"])

    def test_eu_dst_mapping_winter_and_summer(self) -> None:
        winter_naive = datetime(2026, 1, 15, 12, 0)
        summer_naive = datetime(2026, 7, 15, 12, 0)
        winter = MOD.broker_naive_to_utc(winter_naive, -120, -180)
        summer = MOD.broker_naive_to_utc(summer_naive, -120, -180)
        self.assertEqual(winter, datetime(2026, 1, 15, 10, 0, tzinfo=UTC))
        self.assertEqual(summer, datetime(2026, 7, 15, 9, 0, tzinfo=UTC))

    def test_stage177c_contract_validation_is_semantic_and_fail_closed(self) -> None:
        canonical = {
            "contract": " EU_DST_GMT_OFFSET_PAIR ",
            "decision": " pass_amarkets_dst_aware_utc_contract ",
            "dst_calendar": " eu ",
            "dst_shift_minutes": -180,
            "standard_shift_minutes": -120,
            "stage": "177C",
            "shift_semantics": "timestamp_utc = timestamp_naive + shift_minutes",
            "selection_used_holdout": False,
        }
        audit = MOD.validate_spread_time_contract(canonical)
        self.assertTrue(audit["pass"], audit)
        self.assertEqual(audit["evidence_route"], "CANONICAL_PASS_DECISION")

        semantic = {
            "contract": "EU_DST_GMT_OFFSET_PAIR",
            "dst_calendar": "EU",
            "dst_shift_minutes": -180,
            "standard_shift_minutes": -120,
            "stage": "177C",
            "shift_semantics": "timestamp_utc = timestamp_naive + shift_minutes",
            "selection_used_holdout": False,
        }
        audit = MOD.validate_spread_time_contract(semantic)
        self.assertTrue(audit["pass"], audit)
        self.assertEqual(audit["evidence_route"], "EXACT_STAGE177C_SEMANTICS")

        invalid = dict(semantic, dst_shift_minutes=-120)
        audit = MOD.validate_spread_time_contract(invalid)
        self.assertFalse(audit["pass"], audit)


    def test_unevaluated_status_never_matches_evaluated_substring(self) -> None:
        row = {
            "status": "UNEVALUATED_MISSING_M5_COVERAGE",
            "research_gross_bps": "12.5",
            "normal_net_bps": "",
            "entry_open": "",
            "exit_close": "",
        }
        classification, diagnostic = MOD.coverage_row_classification(row)
        self.assertEqual(classification, "MISSING", diagnostic)
        self.assertTrue(diagnostic["status_negative"])
        self.assertFalse(diagnostic["status_positive"])
        self.assertFalse(MOD.row_has_execution(row))

    def test_production_execution_ledger_schema_resolves_168_146_22(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, signal=False)
            config = json.loads((root / "config/xauusd_controlled_paper.json").read_text(encoding="utf-8"))

            # A stale invalid-clock diagnostic ledger must not outrank the canonical ledger.
            invalid_dir = root / "reports/commercial_closure_sprint_invalid_clock_horizon_20260722"
            invalid_dir.mkdir(parents=True, exist_ok=True)
            invalid_path = invalid_dir / "commercial_closure_execution_ledger.csv"
            canonical_path = root / "reports/commercial_closure/commercial_closure_execution_ledger.csv"
            invalid_path.write_bytes(canonical_path.read_bytes())

            evaluated, missing, source = MOD.locate_coverage_rows(root, config)
            self.assertEqual(len(evaluated), 146)
            self.assertEqual(len(missing), 22)
            self.assertEqual(source["mode"], "single_execution_ledger_status_and_fields")
            self.assertEqual(Path(source["signal_source"]), canonical_path.resolve())
            self.assertEqual(source["classification_counts"], {
                "EVALUATED": 146, "MISSING": 22, "CONFLICT": 0,
            })

    def test_stale_open_market_blocks_without_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, signal=True)
            MOD.utc_now = lambda: TEST_NOW + timedelta(hours=10)
            code, summary = MOD.execute(root, None, "run")
            self.assertEqual(code, 2, summary)
            self.assertEqual(
                summary["decision"],
                "CONTROLLED_PAPER_BLOCKED_STALE_MARKET_DATA_NO_INGEST",
            )
            self.assertFalse(summary["operational_freshness"]["pass"])
            self.assertEqual(
                summary["operational_freshness"]["decision"],
                "BLOCK_STALE_MARKET_DATA_OPEN_MARKET",
            )
            self.assertEqual(summary["run_result"]["ingest"]["status"], "SKIPPED_STALE_MARKET_DATA")
            self.assertEqual(summary["counts"]["signals"], 0)
            conn = sqlite3.connect(root / "data/controlled_paper/xauusd_controlled_paper.sqlite")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0], 0)
            conn.close()

    def test_weekend_closure_defers_age_limits_but_keeps_clock_guard(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, signal=False)
            MOD.utc_now = lambda: datetime(2015, 2, 21, 12, 0, tzinfo=UTC)  # Saturday
            code, summary = MOD.execute(root, None, "run")
            self.assertEqual(code, 0, summary)
            self.assertEqual(
                summary["operational_freshness"]["decision"],
                "PASS_MARKET_CLOSED_FRESHNESS_DEFERRED",
            )
            self.assertFalse(summary["operational_freshness"]["market_expected_open"])
            self.assertEqual(summary["run_result"]["ingest"]["status"], "NO_SIGNAL_NEUTRAL_BAND")

    def test_short_probability_tail_queues_and_resolves_with_source_proven_costs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = Fixture(root, signal=False, spread_points=20.0)
            stage_path = root / "reports/stage180_frozen_model_parallel_shadow/stage180_summary.json"
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            observation = stage["latest_observation"]
            observation["probability_up"] = 0.35
            observation["direction"] = 1  # legacy non-execution metadata
            observation["observation_status"] = "NO_SIGNAL"  # expected under legacy long-only Stage180 status
            write_json(stage_path, stage)

            # Prove SHORT execution uses the final M5 spread of the exit H1 bucket,
            # not the entry spread or the first spread in the exit bucket.
            exit_dt = fixture.start + timedelta(hours=1024, minutes=55)
            exit_broker = fixture._broker_naive(exit_dt)
            with fixture.spread_csv.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
                fieldnames = list(rows[0].keys())
            changed = 0
            for row in rows:
                if row["<DATE>"] == exit_broker.strftime("%Y.%m.%d") and row["<TIME>"] == exit_broker.strftime("%H:%M:%S"):
                    row["<SPREAD>"] = "130.0"
                    changed += 1
            self.assertEqual(changed, 1)
            with fixture.spread_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)

            code, summary = MOD.execute(root, None, "run")
            self.assertEqual(code, 0, summary)
            self.assertEqual(summary["run_result"]["ingest"]["status"], "SHORT_SIGNAL_QUEUED")
            self.assertEqual(summary["position_side_counts"]["SHORT"], 1)
            conn = sqlite3.connect(root / "data/controlled_paper/xauusd_controlled_paper.sqlite")
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM positions").fetchone()
            self.assertEqual(row["status"], "RESOLVED")
            self.assertEqual(row["side"], "SHORT")
            self.assertEqual(row["side_source"], "PROBABILITY_TAILS_ONLY")
            self.assertLess(row["gross_bps"], 0.0)
            self.assertAlmostEqual(row["exit_spread_points"], 130.0, places=12)
            self.assertIsNotNone(row["exit_spread_bps"])
            observed = float(row["observed_cost_bps"])
            self.assertAlmostEqual(observed, float(row["exit_spread_bps"]), places=12)
            self.assertAlmostEqual(row["normal_cost_bps"], max(3.0, observed + 0.5), places=12)
            self.assertAlmostEqual(row["severe_cost_bps"], max(4.5, observed * 1.5 + 2.0), places=12)
            self.assertAlmostEqual(row["stress_8_cost_bps"], max(8.0, observed + 4.0), places=12)
            self.assertAlmostEqual(row["stress_10_cost_bps"], max(10.0, observed + 6.0), places=12)
            conn.close()

    def test_neutral_probability_band_never_creates_position(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, signal=False)
            code, summary = MOD.execute(root, None, "run")
            self.assertEqual(code, 0, summary)
            self.assertEqual(summary["run_result"]["ingest"]["status"], "NO_SIGNAL_NEUTRAL_BAND")
            self.assertEqual(summary["position_side_counts"], {"LONG": 0, "SHORT": 0})

    def test_probability_tail_side_source_ignores_direction_metadata_for_short(self) -> None:
        self.assertEqual(MOD.execution_side_from_probability(0.35, 0.60, 0.40), "SHORT")
        self.assertEqual(MOD.execution_side_from_probability(0.65, 0.60, 0.40), "LONG")
        self.assertIsNone(MOD.execution_side_from_probability(0.50, 0.60, 0.40))

    def test_existing_v14_ledger_schema_migrates_without_reset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "legacy.sqlite"
            conn = sqlite3.connect(db)
            conn.executescript(
                """
                CREATE TABLE signals (
                    signal_key TEXT PRIMARY KEY,
                    signal_timestamp_ms INTEGER NOT NULL,
                    signal_utc TEXT NOT NULL,
                    probability_up REAL NOT NULL,
                    direction INTEGER NOT NULL,
                    observation_status TEXT NOT NULL,
                    stage180_created_utc TEXT,
                    ingested_utc TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );
                CREATE TABLE positions (
                    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL,
                    signal_timestamp_ms INTEGER NOT NULL,
                    signal_utc TEXT NOT NULL,
                    entry_row_index INTEGER,
                    entry_timestamp_ms INTEGER,
                    entry_utc TEXT,
                    entry_price REAL,
                    entry_spread_points REAL,
                    entry_spread_bps REAL,
                    exit_row_index INTEGER,
                    exit_timestamp_ms INTEGER,
                    exit_utc TEXT,
                    exit_price REAL,
                    notional_to_equity REAL NOT NULL,
                    gross_bps REAL,
                    observed_cost_bps REAL,
                    normal_cost_bps REAL,
                    severe_cost_bps REAL,
                    stress_8_cost_bps REAL,
                    stress_10_cost_bps REAL,
                    normal_net_bps REAL,
                    severe_net_bps REAL,
                    stress_8_net_bps REAL,
                    stress_10_net_bps REAL,
                    equity_before REAL,
                    equity_after REAL,
                    equity_pnl_pct REAL,
                    block_reason TEXT,
                    detail_json TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?)",
                ("legacy", 1, "1970-01-01T00:00:00.001Z", 0.5, 1, "NO_SIGNAL", None, "now", "{}"),
            )
            conn.commit()
            conn.close()

            ledger = MOD.Ledger(db)
            signal_cols = {row[1] for row in ledger.conn.execute("PRAGMA table_info(signals)")}
            position_cols = {row[1] for row in ledger.conn.execute("PRAGMA table_info(positions)")}
            self.assertIn("execution_side", signal_cols)
            self.assertIn("side_source", signal_cols)
            self.assertIn("side", position_cols)
            self.assertIn("exit_spread_bps", position_cols)
            self.assertEqual(ledger.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 1)
            ledger.close()

    def test_stale_v5_replay_summary_cannot_authorize_bidirectional_logger(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Fixture(root, signal=False)
            path = root / "reports/xauusd_controlled_paper_replay/historical_asof_replay_summary.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["program"] = "XAUUSD_CONTROLLED_PAPER_HISTORICAL_ASOF_REPLAY_V5_SOURCE_PROVEN_COST_CONTRACT_REPAIR"
            payload["current_forward_policy_parity"]["pass"] = False
            write_json(path, payload)
            code, failure = MOD.execute(root, None, "preflight")
            self.assertEqual(code, 2)
            self.assertIn("historical replay evidence", failure["error"])

    def test_missing_dependencies_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config").mkdir(parents=True)
            config = json.loads((Path(__file__).resolve().parents[1] / "config/xauusd_controlled_paper.json").read_text())
            write_json(root / "config/xauusd_controlled_paper.json", config)
            code, payload = MOD.execute(root, None, "run")
            self.assertEqual(code, 2)
            self.assertEqual(payload["decision"], "CONTROLLED_PAPER_FAIL_CLOSED")
            self.assertFalse(payload["broker_order_allowed"])

    def test_application_contains_no_broker_execution_dependency(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8").lower()
        forbidden = ["metatrader" + "5", "order" + "send", "ccxt", "requests.post", "socket.socket"]
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
