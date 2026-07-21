from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage179_selected_candidate_commercial_audit.py"
SPEC = importlib.util.spec_from_file_location("stage179", MODULE_PATH)
stage179 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage179)


class Stage179Tests(unittest.TestCase):
    def test_profit_factor(self):
        self.assertAlmostEqual(stage179.profit_factor([2, -1, 3, -2]), 5 / 3)

    def test_max_drawdown(self):
        self.assertAlmostEqual(stage179.max_drawdown([5, -3, -4, 10]), 7.0)

    def test_moving_block_bootstrap_reproducible(self):
        values = np.arange(1, 9, dtype=float)
        a = stage179.moving_block_means(values, reps=50, block_length=3, seed=7)
        b = stage179.moving_block_means(values, reps=50, block_length=3, seed=7)
        np.testing.assert_allclose(a, b)

    def test_load_trades_rejects_duplicate_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            pd.DataFrame({
                "timestamp": [1, 1],
                "dt": ["2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"],
                "direction": [1, -1],
                "gross_bps": [10, -5],
                "net_bps": [7, -8],
                "severe_net_bps": [5.5, -9.5],
                "probability_up": [0.7, 0.2],
            }).to_csv(path, index=False)
            with self.assertRaises(RuntimeError):
                stage179.load_trades(path)

    def test_infer_costs(self):
        frame = pd.DataFrame({
            "gross_bps": [10.0, -5.0],
            "net_bps": [7.0, -8.0],
            "severe_net_bps": [5.5, -9.5],
        })
        self.assertEqual(stage179.infer_costs(frame), (3.0, 4.5))

    def test_always_long_matched(self):
        frame = pd.DataFrame({
            "direction": [1, -1],
            "gross_bps": [10.0, 8.0],
        })
        result = stage179.always_long_matched(frame, 3.0)
        np.testing.assert_allclose(result, [7.0, -11.0])

    def test_cost_stress(self):
        frame = pd.DataFrame({"gross_bps": [10.0, 20.0]})
        result = stage179.cost_stress(frame, [3.0, 8.0])
        self.assertAlmostEqual(result.loc[0, "mean_bps"], 12.0)
        self.assertAlmostEqual(result.loc[1, "mean_bps"], 7.0)

    def test_parity_audit(self):
        frame = pd.DataFrame({
            "dt": pd.to_datetime(
                ["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"], utc=True
            ),
            "net_bps": [10.0, -5.0],
        })
        m = stage179.metrics(frame["net_bps"])
        summary = {
            "selected_holdout_metrics": {
                "trades": 2,
                "mean_net_bps": m["mean_bps"],
                "profit_factor": m["profit_factor"],
                "max_drawdown_bps": m["max_drawdown_bps"],
                "first_trade_utc": frame["dt"].iloc[0].isoformat(),
                "last_trade_utc": frame["dt"].iloc[-1].isoformat(),
            }
        }
        result = stage179.parity_audit(frame, summary, 1e-8)
        self.assertTrue(result["pass"])


if __name__ == "__main__":
    unittest.main()
