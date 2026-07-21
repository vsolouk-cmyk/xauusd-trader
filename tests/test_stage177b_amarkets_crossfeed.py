import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "stage177b_crossfeed", ROOT / "app" / "stage177b_amarkets_crossfeed.py"
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class CrossFeedTests(unittest.TestCase):
    def test_best_shift_is_recovered(self):
        count = 1000
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
        # Naive AMarkets time is two hours ahead of UTC; adding -120m aligns it.
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
        self.assertEqual(best["shift_minutes"], -120)
        self.assertAlmostEqual(best["return_corr"], 1.0, places=10)

    def test_flexible_csv_normalization(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "am.csv"
            path.write_text(
                "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\n"
                "2025.01.01\t00:00\t100\t101\t99\t100.5\t10\n",
                encoding="utf-8",
            )
            frame = module.normalize_ohlc(path, module.H1_MS)
            self.assertEqual(len(frame), 1)
            self.assertEqual(frame.iloc[0]["close"], 100.5)


if __name__ == "__main__":
    unittest.main()
