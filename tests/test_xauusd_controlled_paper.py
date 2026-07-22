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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    def __init__(self, root: Path, *, spread_points: float = 20.0, event_db: bool = True, signal: bool = True):
        self.root = root
        self.start = datetime(2015, 1, 2, 7, tzinfo=UTC)
        package_root = Path(__file__).resolve().parents[1]
        (root / "config").mkdir(parents=True, exist_ok=True)
        config = json.loads((package_root / "config/xauusd_controlled_paper.json").read_text(encoding="utf-8"))
        write_json(root / "config/xauusd_controlled_paper.json", config)
        (root / "data/controlled_paper").mkdir(parents=True, exist_ok=True)
        (root / "data/controlled_paper/event_blackout.csv").write_text(
            "event_time_utc,blackout_before_minutes,blackout_after_minutes,title,required\n", encoding="utf-8"
        )
        self.market_db = root / "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"
        self.market_db.parent.mkdir(parents=True, exist_ok=True)
        self._market(spread_points)
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

    def _market(self, spread_points: float) -> None:
        conn = sqlite3.connect(self.market_db)
        conn.executescript(
            """
            CREATE TABLE h1_bars(timestamp_ms INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, spread REAL);
            CREATE TABLE m5_bars(timestamp_ms INTEGER PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, spread REAL);
            """
        )
        h1_rows = []
        m5_rows = []
        for i in range(1100):
            dt = self.start + timedelta(hours=i)
            ts = int(dt.timestamp() * 1000)
            base = 2000.0 + i * 0.10
            h1_rows.append((ts, base, base + 1.0, base - 1.0, base + 0.20, spread_points))
            for j in range(12):
                mts = int((dt + timedelta(minutes=5 * j)).timestamp() * 1000)
                mbase = base + j * 0.01
                m5_rows.append((mts, mbase, mbase + 0.2, mbase - 0.2, mbase + 0.02, spread_points))
        conn.executemany("INSERT INTO h1_bars VALUES(?,?,?,?,?,?)", h1_rows)
        conn.executemany("INSERT INTO m5_bars VALUES(?,?,?,?,?,?)", m5_rows)
        conn.commit()
        conn.close()

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
        ledger_path = report / "commercial_closure_ledger.csv"
        with ledger_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["signal_dt", "execution_status", "normal_net_bps"])
            writer.writeheader()
            for i in range(22):
                writer.writerow({
                    "signal_dt": (datetime(2014, 1, 1, tzinfo=UTC) + timedelta(hours=i)).isoformat(),
                    "execution_status": "MISSING_EXECUTION_COVERAGE",
                    "normal_net_bps": "",
                })
            for i in range(146):
                writer.writerow({
                    "signal_dt": (self.start + timedelta(hours=i)).isoformat(),
                    "execution_status": "EVALUATED",
                    "normal_net_bps": 10.0,
                })

    def _stage180(self, signal: bool) -> None:
        report = self.root / "reports/stage180_frozen_model_parallel_shadow"
        report.mkdir(parents=True, exist_ok=True)
        index = 1000
        dt = self.start + timedelta(hours=index)
        p = 0.70 if signal else 0.47
        direction = 1 if signal else 0
        status = "SIGNAL" if signal else "NO_SIGNAL"
        write_json(report / "stage180_summary.json", {
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
            fixture = Fixture(root, signal=True)
            code, payload = MOD.execute(root, None, "preflight")
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["missing_coverage_audit"]["decision"], "PASS_BOUNDED_MISSING_COVERAGE_NOT_CURRENT_SYSTEMATIC_DEFECT")
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
