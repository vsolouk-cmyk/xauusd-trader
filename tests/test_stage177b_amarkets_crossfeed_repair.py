import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "stage177b_crossfeed_repair",
    ROOT / "app" / "stage177b_amarkets_crossfeed.py",
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class CrossFeedRepairTests(unittest.TestCase):
    def test_mt5_tab_loader_retains_large_history(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "amarkets_xauusd_5m.csv"
            start = pd.Timestamp("2022-01-03 00:00:00")
            count = 12_000
            with path.open("w", encoding="utf-8") as handle:
                handle.write(
                    "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\n"
                )
                for index in range(count):
                    stamp = start + pd.Timedelta(minutes=5 * index)
                    price = 1800.0 + index * 0.001
                    handle.write(
                        f"{stamp:%Y.%m.%d}\t{stamp:%H:%M:%S}\t"
                        f"{price:.3f}\t{price + 0.5:.3f}\t"
                        f"{price - 0.5:.3f}\t{price + 0.1:.3f}\t{100 + index % 50}\n"
                    )
            frame = module.normalize_ohlc(path, module.M5_MS)
            self.assertEqual(len(frame), count)
            diagnostics = frame.attrs["loader_diagnostics"]
            self.assertEqual(diagnostics["separator"], "TAB")
            self.assertEqual(diagnostics["raw_rows"], count)
            self.assertEqual(diagnostics["normalized_rows"], count)
            self.assertEqual(diagnostics["timestamp_parse_failures"], 0)

    def test_no_overlap_never_emits_fake_shift(self):
        reference = pd.DataFrame(
            {
                "timestamp": np.arange(500, dtype=np.int64) * module.H1_MS,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1.0,
            }
        )
        far_future = 100_000 * module.H1_MS
        amarkets = pd.DataFrame(
            {
                "timestamp_naive_ms": far_future
                + np.arange(500, dtype=np.int64) * module.H1_MS,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1.0,
            }
        )
        best, _ = module.candidate_grid(
            amarkets,
            reference,
            [-120, -60, 0, 60, 120],
            module.H1_MS,
        )
        self.assertEqual(best["status"], "INSUFFICIENT_OVERLAP")
        self.assertIsNone(best["shift_minutes"])
        self.assertEqual(best["overlap_rows"], 0)

    def test_best_shift_is_recovered(self):
        count = 1_000
        timestamps = np.arange(count, dtype=np.int64) * module.H1_MS
        prices = 100 + np.cumsum(np.sin(np.arange(count) / 10) * 0.1 + 0.01)
        width = 0.5 + (np.arange(count) % 17) / 100
        reference = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": prices,
                "high": prices + width,
                "low": prices - width,
                "close": prices,
                "volume": 1,
            }
        )
        amarkets = pd.DataFrame(
            {
                "timestamp_naive_ms": timestamps + 120 * 60_000,
                "open": prices,
                "high": prices + width,
                "low": prices - width,
                "close": prices,
                "volume": 1,
            }
        )
        best, _ = module.candidate_grid(
            amarkets, reference, [-180, -120, -60, 0], module.H1_MS
        )
        self.assertEqual(best["status"], "EVALUATED")
        self.assertEqual(best["shift_minutes"], -120)
        self.assertAlmostEqual(best["return_corr"], 1.0, places=10)

    def test_m5_derived_h1(self):
        count = 24
        timestamps = np.arange(count, dtype=np.int64) * module.M5_MS
        close = 100 + np.arange(count) * 0.1
        frame = pd.DataFrame(
            {
                "timestamp_naive_ms": timestamps,
                "open": close - 0.05,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1.0,
            }
        )
        derived = module.derive_h1_from_m5(frame)
        self.assertEqual(len(derived), 2)
        self.assertAlmostEqual(derived.iloc[0]["open"], 99.95)
        self.assertAlmostEqual(derived.iloc[0]["close"], 101.1)


if __name__ == "__main__":
    unittest.main()
