from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

MODULE = Path(__file__).resolve().parents[1] / "app" / "stage180_frozen_model_shadow.py"
SPEC = importlib.util.spec_from_file_location("stage180", MODULE)
stage180 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage180)


class Stage180Tests(unittest.TestCase):
    def valid_summaries(self):
        s178 = {
            "decision": "PROMOTE_TO_CONTROLLED_PAPER_DESIGN",
            "selected_candidate": {
                "candidate": "logistic__direction_24h",
                "model": "logistic",
                "target": "direction_24h",
                "horizon_hours": 24,
            },
        }
        s179 = {
            "decision": "RESEARCH_SURVIVOR_NEEDS_ONE_TARGETED_DIAGNOSTIC",
            "gates": {
                "candidate_bootstrap_p10_positive": False,
                "stage178_parity": True,
                "minimum_trades": True,
            },
            "parity": {"pass": True},
            "broker_order_allowed": False,
            "stage178_selected": {
                "candidate": "logistic__direction_24h",
                "model": "logistic",
                "target": "direction_24h",
            },
        }
        return s178, s179

    def test_authorization_only_uncertainty_gate(self):
        s178, s179 = self.valid_summaries()
        self.assertTrue(stage180.authorization_check(s178, s179)["pass"])

    def test_authorization_rejects_second_failed_gate(self):
        s178, s179 = self.valid_summaries()
        s179["gates"]["minimum_trades"] = False
        self.assertFalse(stage180.authorization_check(s178, s179)["pass"])

    def test_probability_to_direction(self):
        self.assertEqual(stage180.probability_to_direction(0.61, 0.60), 1)
        self.assertEqual(stage180.probability_to_direction(0.39, 0.60), -1)
        self.assertEqual(stage180.probability_to_direction(0.50, 0.60), 0)

    def test_load_complete_h1_filters_partial_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "x.sqlite"
            with sqlite3.connect(db) as con:
                con.execute(
                    """CREATE TABLE h1(
                    timestamp INTEGER, open REAL, high REAL, low REAL,
                    close REAL, volume REAL, m5_bar_count INTEGER)"""
                )
                con.executemany(
                    "INSERT INTO h1 VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (0, 10, 11, 9, 10.5, 100, 12),
                        (3_600_000, 10.5, 12, 10, 11, 50, 4),
                    ],
                )
            frame = stage180.load_complete_h1(db, "h1", 12)
            self.assertEqual(len(frame), 1)

    def test_resolver_uses_24_future_bars_not_clock_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite"
            stage180.init_ledger(ledger)
            timestamps = [i * stage180.MS_HOUR for i in range(30)]
            # Insert a weekend-sized timestamp jump after row 10. Row position,
            # not wall-clock equality, must determine the exit.
            timestamps[11:] = [value + 72 * stage180.MS_HOUR for value in timestamps[11:]]
            bars = pd.DataFrame({
                "timestamp": timestamps,
                "open": np.arange(100, 130, dtype=float),
                "high": np.arange(101, 131, dtype=float),
                "low": np.arange(99, 129, dtype=float),
                "close": np.arange(100.5, 130.5, dtype=float),
                "volume": 1.0,
                "dt": pd.to_datetime(timestamps, unit="ms", utc=True),
            })
            stage180.insert_signal(ledger, timestamps[0], 0.7, 1)
            resolved = stage180.resolve_pending_signals(ledger, bars, 24, 3.0, 4.5)
            self.assertEqual(resolved, 1)
            _, signals = stage180.ledger_frames(ledger)
            self.assertAlmostEqual(signals.iloc[0]["entry_open"], bars.iloc[1]["open"])
            self.assertAlmostEqual(signals.iloc[0]["exit_close"], bars.iloc[24]["close"])

    def test_ledger_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite"
            stage180.init_ledger(ledger)
            stage180.insert_observation(ledger, 1, 0.7, 1, "SHADOW_SIGNAL")
            stage180.insert_observation(ledger, 1, 0.7, 1, "SHADOW_SIGNAL")
            stage180.insert_signal(ledger, 1, 0.7, 1)
            stage180.insert_signal(ledger, 1, 0.7, 1)
            observations, signals = stage180.ledger_frames(ledger)
            self.assertEqual(len(observations), 1)
            self.assertEqual(len(signals), 1)

    def test_model_contract_check(self):
        s178, s179 = self.valid_summaries()
        contract = {
            "stage": "178",
            "candidate": "logistic__direction_24h",
            "model": "logistic",
            "target": "direction_24h",
            "horizon_hours": 24,
            "probability_threshold": 0.6,
            "feature_columns": ["ret_1h"],
            "selection_used_amarkets_holdout": False,
            "execution_allowed": False,
        }
        self.assertTrue(stage180.model_contract_check(s178, s179, contract)["pass"])

    def test_import_module_registers_dataclass_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            module_path = Path(tmp) / "dataclass_runtime.py"
            module_path.write_text(
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True)\n"
                "class RuntimeContract:\n"
                "    value: int\n",
                encoding="utf-8",
            )
            module_name = "stage180_test_dataclass_runtime"
            sys.modules.pop(module_name, None)
            module = stage180.import_module(module_path, module_name)
            self.assertIs(sys.modules[module_name], module)
            self.assertEqual(module.RuntimeContract(7).value, 7)
            sys.modules.pop(module_name, None)

    def test_import_exact_stage178_runtime_with_dataclass(self):
        candidates = [
            Path(__file__).resolve().parents[1]
            / "app"
            / "stage178_commercial_edge_decision_sprint.py",
            Path("/mnt/data/stage178_exact_for_qa/app/stage178_commercial_edge_decision_sprint.py"),
            Path("/mnt/data/stage178_repair_pkg/app/stage178_commercial_edge_decision_sprint.py"),
            Path("/mnt/data/stage178_build/app/stage178_commercial_edge_decision_sprint.py"),
        ]
        stage178_path = next((path for path in candidates if path.exists()), None)
        if stage178_path is None:
            self.skipTest("Exact Stage178 source is not available in this QA environment")
        module_name = "stage180_test_exact_stage178_runtime"
        sys.modules.pop(module_name, None)
        module = stage180.import_module(stage178_path, module_name)
        self.assertTrue(hasattr(module, "build_features"))
        sys.modules.pop(module_name, None)

    def test_alignment_contract_prefers_pass_db_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db = tmp_path / "alignment.sqlite"
            fallback = tmp_path / "failed_report.json"
            fallback.write_text(
                json.dumps({"decision": "BLOCK", "contract": "WRONG"}),
                encoding="utf-8",
            )
            passed = {
                "decision": "PASS_AMARKETS_DST_AWARE_UTC_CONTRACT",
                "contract": "EU_DST_GMT_OFFSET_PAIR",
                "selection_used_holdout": False,
                "source_amarkets_m5": "/tmp/m5.csv",
                "source_amarkets_h1": "/tmp/h1.csv",
            }
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE provenance(key TEXT PRIMARY KEY, value TEXT)")
                con.execute(
                    "INSERT INTO provenance VALUES (?, ?)",
                    ("stage177c_time_contract", json.dumps(passed)),
                )
            loaded = stage180.read_alignment_contract_from_db(db, fallback)
            self.assertEqual(loaded["contract"], "EU_DST_GMT_OFFSET_PAIR")
            self.assertTrue(loaded["decision"].startswith("PASS"))


    def test_source_contains_no_order_api(self):
        source = MODULE.read_text(encoding="utf-8").lower()
        forbidden = ["ordersend", "send_order", "mt5.order_send", "broker_api"]
        self.assertTrue(all(token not in source for token in forbidden))


if __name__ == "__main__":
    unittest.main()
