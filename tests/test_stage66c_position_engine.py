#!/usr/bin/env python3
"""Unit checks for Stage66C position engine."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from stage66c_h64l_paper_execution_simulator import (  # noqa: E402
    max_drawdown_pct,
    first_index_on_or_after,
    build_paper_positions,
)


RULE = {
    "rule_lock_payload": {
        "rule_id": "TEST_RULE",
        "conditions": [{"field": "x", "operator": ">", "threshold": 0.0}],
    },
    "rule_sha256": "not_used_by_engine_test",
}


class Stage66CPositionEngineTests(unittest.TestCase):
    def test_max_drawdown_pct(self):
        dd = max_drawdown_pct([1.0, 1.1, 1.05, 1.2, 0.96])
        self.assertAlmostEqual(dd, -20.0, places=6)

    def test_first_index_on_or_after(self):
        daily = [{"date": dt.date(2020, 1, 1)}, {"date": dt.date(2020, 1, 3)}]
        self.assertEqual(first_index_on_or_after(daily, dt.date(2020, 1, 2)), 1)
        self.assertIsNone(first_index_on_or_after(daily, dt.date(2020, 1, 4)))

    def test_non_overlapping_positions(self):
        macro_rows = [
            {"feature_date_utc": "2020-01-01", "sample_available_after_utc": "2020-01-02T00:00:00Z", "x": "1"},
            {"feature_date_utc": "2020-01-03", "sample_available_after_utc": "2020-01-04T00:00:00Z", "x": "1"},
            {"feature_date_utc": "2020-01-10", "sample_available_after_utc": "2020-01-11T00:00:00Z", "x": "1"},
        ]
        daily = []
        for i in range(20):
            d = dt.date(2020, 1, 1) + dt.timedelta(days=i)
            price = 100 + i
            daily.append({"date": d, "open": price, "high": price + 1, "low": price - 1, "close": price, "volume": None})
        positions, diag = build_paper_positions(
            macro_rows=macro_rows,
            daily=daily,
            locked_rule=RULE,
            feature_date_col="feature_date_utc",
            available_after_col="sample_available_after_utc",
            holding_period_trading_days=5,
            entry_delay_trading_days=0,
            base_round_trip_cost_bps=10,
            feed_mismatch_penalty_bps=5,
            non_overlap=True,
        )
        self.assertEqual(len(positions), 2)
        self.assertEqual(diag["skipped_overlap"], 1)
        self.assertEqual(positions[0]["cost_and_feed_penalty_bps"], 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
