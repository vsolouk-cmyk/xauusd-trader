from __future__ import annotations

import importlib.util
import math
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

spec = importlib.util.spec_from_file_location(
    "stage177c", APP / "stage177c_amarkets_dst_contract.py"
)
stage177c = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = stage177c
spec.loader.exec_module(stage177c)


class Stage177CTest(unittest.TestCase):
    def test_us_and_eu_dst_dates(self):
        self.assertEqual(
            stage177c.dst_dates(2025, "US"),
            (pd.Timestamp("2025-03-09").date(), pd.Timestamp("2025-11-02").date()),
        )
        self.assertEqual(
            stage177c.dst_dates(2025, "EU"),
            (pd.Timestamp("2025-03-30").date(), pd.Timestamp("2025-10-26").date()),
        )

    def test_viterbi_suppresses_single_week_flip(self):
        rows = []
        weeks = pd.date_range("2025-01-06", periods=8, freq="7D")
        for index, week in enumerate(weeks):
            for shift in (-180, -120):
                score = 0.9 if shift == -120 else 0.1
                if index == 3:
                    score = 0.95 if shift == -180 else 0.90
                rows.append(
                    {
                        "week_start": week.date().isoformat(),
                        "shift_minutes": shift,
                        "score": score,
                        "overlap_rows": 1000,
                        "return_corr_60m": score,
                    }
                )
        result = stage177c.viterbi_weekly_states(
            pd.DataFrame(rows),
            [-180, -120],
            transition_penalty=0.35,
            max_transition_minutes=60,
        )
        self.assertEqual(set(result["selected_shift_minutes"]), {-120})

    def test_us_template_beats_constant_on_synthetic_crossfeed(self):
        rng = np.random.default_rng(7)
        timestamps = pd.date_range(
            "2024-01-01", "2026-06-30 23:55", freq="5min", tz="UTC"
        )
        timestamps = timestamps[timestamps.weekday < 5]
        # Keep a realistic intraday block while preserving 5-minute continuity.
        timestamps = timestamps[(timestamps.hour >= 6) & (timestamps.hour < 18)]
        n = len(timestamps)
        returns = rng.normal(0.0, 0.00012, n)
        close = 2000.0 * np.exp(np.cumsum(returns))
        open_ = np.r_[close[0], close[:-1]]
        spread = np.abs(rng.normal(0.15, 0.04, n))
        high = np.maximum(open_, close) + spread
        low = np.minimum(open_, close) - spread
        ref = pd.DataFrame(
            {
                "timestamp": stage177c.datetime_to_epoch_ms(timestamps),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": np.full(n, 10.0),
            }
        )
        contract = stage177c.Contract(
            "US_DST_GMT_OFFSET_PAIR", -120, -180, "US"
        )
        utc_naive = timestamps.tz_convert(None)
        shifts = stage177c.shift_for_dates(pd.Series(utc_naive), contract).to_numpy()
        # timestamp_utc = timestamp_naive + shift; hence naive = utc - shift.
        naive_ms = ref["timestamp"].to_numpy() - shifts * stage177c.MINUTE_MS
        am = pd.DataFrame(
            {
                "timestamp_naive_ms": naive_ms,
                "open": open_ * (1.0 + 0.00002),
                "high": high * (1.0 + 0.00002),
                "low": low * (1.0 + 0.00002),
                "close": close * (1.0 + 0.00002),
                "volume": np.full(n, 11.0),
            }
        )
        train_end = int(pd.Timestamp("2025-01-01", tz="UTC").timestamp() * 1000)
        us_eval, _ = stage177c.evaluate_contract(
            contract,
            am,
            ref,
            train_end_ms=train_end,
            holdout_start_ms=train_end,
            min_overlap=1000,
        )
        fixed_eval, _ = stage177c.evaluate_contract(
            stage177c.Contract("CONSTANT_-120", -120),
            am,
            ref,
            train_end_ms=train_end,
            holdout_start_ms=train_end,
            min_overlap=1000,
        )
        self.assertGreater(us_eval["all"]["return_corr_60m"], 0.999)
        self.assertGreater(us_eval["holdout"]["return_corr_60m"], 0.999)
        self.assertLess(fixed_eval["all"]["return_corr_60m"], 0.75)
        self.assertGreater(us_eval["train_score"], fixed_eval["train_score"])

    def test_datetime_to_epoch_ms_is_resolution_stable(self):
        base = pd.date_range("2025-01-01", periods=3, freq="5min", tz="UTC")
        expected = np.array([1735689600000, 1735689900000, 1735690200000])
        for unit in ("s", "ms", "us", "ns"):
            converted = stage177c.datetime_to_epoch_ms(base.as_unit(unit))
            np.testing.assert_array_equal(converted, expected)

    def test_pairwise_corr_is_positional_and_version_stable(self):
        left = pd.Series([0.1, 0.2, 0.3, 0.4], index=[10, 11, 12, 13])
        right = pd.Series([0.2, 0.4, 0.6, 0.8], index=[20, 21, 22, 23])
        self.assertAlmostEqual(stage177c.pairwise_corr(left, right), 1.0, places=12)

        timestamps = pd.Series([0, 300_000, 600_000, 900_000], index=[4, 5, 6, 7])
        close = pd.Series([100.0, 101.0, 102.0, 103.0], index=[4, 5, 6, 7])
        result = stage177c.lagged_returns(
            close,
            timestamps,
            lag_rows=1,
            expected_interval_ms=300_000,
        )
        self.assertEqual(result.notna().sum(), 3)
        self.assertEqual(result.index.tolist(), close.index.tolist())

    def test_sqlite_writer_is_separate_and_complete(self):
        m5 = pd.DataFrame(
            {
                "timestamp": [1_000, 2_000],
                "timestamp_naive_ms": [121_000, 122_000],
                "shift_minutes": [-2, -2],
                "open": [1.0, 1.1],
                "high": [1.2, 1.3],
                "low": [0.9, 1.0],
                "close": [1.1, 1.2],
                "volume": [10.0, 11.0],
            }
        )
        h1 = m5.iloc[[0]].copy()
        derived = pd.DataFrame(
            {
                "timestamp": [0],
                "open": [1.0],
                "high": [1.3],
                "low": [0.9],
                "close": [1.2],
                "volume": [21.0],
                "m5_bar_count": [2],
            }
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "alignment.sqlite"
            stage177c.write_sqlite(path, m5, h1, derived, {"contract": "TEST"})
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM amarkets_m5_utc").fetchone()[0],
                    2,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM amarkets_h1_from_m5_utc"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    json_load(connection.execute(
                        "SELECT value FROM provenance WHERE key='stage177c_time_contract'"
                    ).fetchone()[0])["contract"],
                    "TEST",
                )


def json_load(value: str):
    import json

    return json.loads(value)


if __name__ == "__main__":
    unittest.main()
