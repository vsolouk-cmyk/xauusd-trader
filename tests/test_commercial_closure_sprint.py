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


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "commercial_closure_sprint.py"
)
SPEC = importlib.util.spec_from_file_location("commercial_closure", MODULE_PATH)
closure = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["commercial_closure"] = closure
SPEC.loader.exec_module(closure)


class CommercialClosureTests(unittest.TestCase):
    def test_safe_import_registers_dataclass_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.py"
            path.write_text(
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True)\n"
                "class Contract:\n"
                "    value: int\n",
                encoding="utf-8",
            )
            module = closure.safe_import(path, "closure_dataclass_probe")
            self.assertEqual(module.Contract(4).value, 4)
            sys.modules.pop("closure_dataclass_probe", None)

    def test_datetime_to_epoch_ms_is_resolution_stable(self):
        values = pd.date_range("2025-01-01", periods=2, freq="1h", tz="UTC")
        result = closure.datetime_to_epoch_ms(values)
        self.assertEqual(int(result[1] - result[0]), 3_600_000)

    def test_infer_point_size(self):
        size, diag = closure.infer_point_size(
            pd.Series(["2500.12", "2500.13", "2500.10"])
        )
        self.assertEqual(size, 0.01)
        self.assertEqual(diag["mode_decimals"], 2)

    def test_profit_factor(self):
        self.assertAlmostEqual(closure.profit_factor([5, -2, 3, -1]), 8 / 3)

    def test_execution_ledger_long_and_short_spread(self):
        signal_rows = pd.DataFrame([
            {
                "timestamp": 0,
                "dt": pd.Timestamp("1970-01-01", tz="UTC"),
                "source_period": "A",
                "fold": "F",
                "direction": 1,
                "probability_up": 0.7,
                "resolution_hours": 2,
                "gross_bps": 10.0,
            },
            {
                "timestamp": 10 * closure.MS_HOUR,
                "dt": pd.Timestamp("1970-01-01T10:00:00Z"),
                "source_period": "B",
                "fold": "F",
                "direction": -1,
                "probability_up": 0.2,
                "resolution_hours": 2,
                "gross_bps": 10.0,
            },
        ])
        rows = []
        for bucket, start, end, spread in [
            (closure.MS_HOUR, 100.0, 100.0, 0.10),
            (2 * closure.MS_HOUR, 101.0, 102.0, 0.10),
            (11 * closure.MS_HOUR, 100.0, 100.0, 0.20),
            (12 * closure.MS_HOUR, 99.0, 98.0, 0.20),
        ]:
            for i in range(12):
                rows.append({
                    "timestamp": bucket + i * 300_000,
                    "bucket_h1": bucket,
                    "open": start if i == 0 else start,
                    "close": end if i == 11 else start,
                    "spread_price": spread,
                })
        ledger = closure.execution_ledger(
            signal_rows,
            pd.DataFrame(rows),
            np.array([
                0,
                closure.MS_HOUR,
                2 * closure.MS_HOUR,
                10 * closure.MS_HOUR,
                11 * closure.MS_HOUR,
                12 * closure.MS_HOUR,
            ], dtype=np.int64),
            minimum_normal_cost_bps=3.0,
            minimum_severe_cost_bps=4.5,
            normal_slippage_bps=0.5,
            severe_slippage_bps=2.0,
            severe_spread_multiplier=1.5,
        )
        self.assertEqual(len(ledger), 2)
        self.assertTrue((ledger["status"] == "EVALUATED").all())
        self.assertGreater(ledger.iloc[0]["m5_gross_bps"], 0)
        self.assertGreater(ledger.iloc[1]["m5_gross_bps"], 0)

    def test_execution_ledger_rejects_incomplete_bucket(self):
        signals = pd.DataFrame([{
            "timestamp": 0,
            "dt": pd.Timestamp("1970-01-01", tz="UTC"),
            "source_period": "A",
            "direction": 1,
            "resolution_hours": 2,
            "gross_bps": 1.0,
        }])
        m5 = pd.DataFrame([{
            "timestamp": closure.MS_HOUR,
            "bucket_h1": closure.MS_HOUR,
            "open": 100.0,
            "close": 100.0,
            "spread_price": 0.1,
        }])
        ledger = closure.execution_ledger(
            signals,
            m5,
            np.array(
                [0, closure.MS_HOUR, 2 * closure.MS_HOUR],
                dtype=np.int64,
            ),
            minimum_normal_cost_bps=3.0,
            minimum_severe_cost_bps=4.5,
            normal_slippage_bps=0.5,
            severe_slippage_bps=2.0,
            severe_spread_multiplier=1.5,
        )
        self.assertEqual(
            ledger.iloc[0]["status"],
            "MISSING_COMPLETE_M5_BUCKET",
        )

    def test_bootstrap_reproducible(self):
        values = np.arange(1, 21, dtype=float)
        a = closure.moving_block_means(
            values, reps=100, block_length=4, seed=7
        )
        b = closure.moving_block_means(
            values, reps=100, block_length=4, seed=7
        )
        np.testing.assert_allclose(a, b)

    def test_risk_contract_caps_exposure(self):
        values = np.array([20, -50, 30, -10, 40, -80, 25] * 10, dtype=float)
        result = closure.risk_contract(
            values,
            target_q95_trade_loss_equity_pct=0.5,
            maximum_bootstrap_drawdown_pct=10.0,
            bootstrap_reps=200,
            block_length=4,
            seed=8,
        )
        self.assertGreater(result["maximum_notional_to_equity"], 0)
        self.assertLessEqual(result["maximum_notional_to_equity"], 0.50)

    def test_read_pass_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "x.sqlite"
            payload = {
                "decision": "PASS_AMARKETS_DST_AWARE_UTC_CONTRACT",
                "selection_used_holdout": False,
                "contract": "EU_DST_GMT_OFFSET_PAIR",
            }
            with sqlite3.connect(db) as con:
                con.execute(
                    "CREATE TABLE provenance(key TEXT PRIMARY KEY, value TEXT)"
                )
                con.execute(
                    "INSERT INTO provenance VALUES (?, ?)",
                    ("stage177c_time_contract", json.dumps(payload)),
                )
            loaded = closure.read_pass_contract_from_db(db)
            self.assertEqual(loaded["contract"], "EU_DST_GMT_OFFSET_PAIR")

    def test_execution_uses_h1_row_horizon_across_weekend_gap(self):
        hour = closure.MS_HOUR
        # Eleven hourly bars, then a 72-hour weekend jump, then more H1 rows.
        h1 = [i * hour for i in range(11)]
        h1.extend([(82 + i) * hour for i in range(20)])
        h1 = np.asarray(h1, dtype=np.int64)

        signal = pd.DataFrame([{
            "timestamp": h1[0],
            "dt": pd.to_datetime(h1[0], unit="ms", utc=True),
            "source_period": "TEST",
            "fold": "F",
            "direction": 1,
            "probability_up": 0.7,
            "resolution_hours": 24,
            "gross_bps": 100.0,
        }])

        entry_bucket = int(h1[1])
        row_horizon_exit = int(h1[24])
        wrong_clock_exit = int(h1[0] + 24 * hour)

        rows = []
        for bucket, close in [
            (entry_bucket, 100.0),
            (row_horizon_exit, 110.0),
            (wrong_clock_exit, 50.0),
        ]:
            for i in range(12):
                rows.append({
                    "timestamp": bucket + i * 300_000,
                    "bucket_h1": bucket,
                    "open": 100.0,
                    "close": close if i == 11 else 100.0,
                    "spread_price": 0.01,
                })

        ledger = closure.execution_ledger(
            signal,
            pd.DataFrame(rows),
            h1,
            minimum_normal_cost_bps=3.0,
            minimum_severe_cost_bps=4.5,
            normal_slippage_bps=0.5,
            severe_slippage_bps=2.0,
            severe_spread_multiplier=1.5,
        )
        self.assertEqual(ledger.iloc[0]["status"], "EVALUATED")
        self.assertEqual(
            int(ledger.iloc[0]["exit_bucket_timestamp"]),
            row_horizon_exit,
        )
        self.assertGreater(float(ledger.iloc[0]["m5_gross_bps"]), 900.0)

    def test_load_operational_h1_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "aligned.sqlite"
            with sqlite3.connect(db) as con:
                con.execute(
                    "CREATE TABLE amarkets_h1_from_m5_utc("
                    "timestamp INTEGER, open REAL, high REAL, low REAL, close REAL)"
                )
                con.executemany(
                    "INSERT INTO amarkets_h1_from_m5_utc VALUES (?, 1, 1, 1, 1)",
                    [(3,), (1,), (2,), (2,)],
                )
            values = closure.load_operational_h1_timestamps(db)
            np.testing.assert_array_equal(values, np.array([1, 2, 3]))

    def test_source_has_no_order_api(self):
        source = MODULE_PATH.read_text(encoding="utf-8").lower()
        forbidden = ["ordersend", "mt5.order_send", "send_order", "broker_api"]
        self.assertTrue(all(token not in source for token in forbidden))


if __name__ == "__main__":
    unittest.main()
