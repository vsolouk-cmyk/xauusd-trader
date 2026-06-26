#!/usr/bin/env python3
import datetime as dt
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

import stage66d_limited_complementary_thesis_scan as s66d


class Stage66DTests(unittest.TestCase):
    def test_condition_eval(self):
        row = {"x": "1.5", "y": "-0.1"}
        ok, detail = s66d.eval_condition(row, {"field": "x", "operator": ">", "threshold": 1.0})
        self.assertTrue(ok)
        self.assertEqual(detail["field"], "x")
        ok, _ = s66d.eval_condition(row, {"field": "y", "operator": "<", "threshold": 0.0})
        self.assertTrue(ok)

    def test_first_external_on_or_after(self):
        rows = [
            {"__external_date": dt.date(2020, 1, 1)},
            {"__external_date": dt.date(2020, 1, 3)},
            {"__external_date": dt.date(2020, 1, 6)},
        ]
        self.assertEqual(s66d.first_external_idx_on_or_after(rows, dt.date(2020, 1, 2)), 1)
        self.assertEqual(s66d.first_external_idx_on_or_after(rows, dt.date(2020, 1, 6)), 2)
        self.assertIsNone(s66d.first_external_idx_on_or_after(rows, dt.date(2020, 1, 7)))

    def test_non_overlapping_positions(self):
        events = [
            {"entry_idx": 1, "exit_idx": 5, "net_return_bps": 100},
            {"entry_idx": 2, "exit_idx": 6, "net_return_bps": 200},
            {"entry_idx": 7, "exit_idx": 10, "net_return_bps": -50},
        ]
        selected, skipped = s66d.select_non_overlapping_positions(events)
        self.assertEqual(len(selected), 2)
        self.assertEqual(skipped, 1)
        self.assertEqual(selected[0]["position_id"], 1)
        self.assertEqual(selected[1]["position_id"], 2)


if __name__ == "__main__":
    unittest.main()
