#!/usr/bin/env python3
"""Unit checks for Stage66B no-lookahead helper logic.

Can be run directly:
  python3 tests/test_stage66b_no_lookahead.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from stage66_common_h64l import assert_no_lookahead, filter_rows_asof  # noqa: E402


class Stage66BNoLookaheadTests(unittest.TestCase):
    def test_filter_rows_asof_excludes_future_available_after(self):
        rows = [
            {"feature_date_utc": "2020-01-01", "sample_available_after_utc": "2020-01-02T00:00:00Z"},
            {"feature_date_utc": "2020-01-03", "sample_available_after_utc": "2020-01-10T00:00:00Z"},
        ]
        filtered = filter_rows_asof(rows, dt.date(2020, 1, 5))
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["feature_date_utc"], "2020-01-01")

    def test_assert_no_lookahead_detects_breach(self):
        rows = [
            {"feature_date_utc": "2020-01-01", "sample_available_after_utc": "2020-01-02T00:00:00Z"},
            {"feature_date_utc": "2020-01-03", "sample_available_after_utc": "2020-01-10T00:00:00Z"},
        ]
        ok, breaches = assert_no_lookahead(rows, dt.date(2020, 1, 5))
        self.assertFalse(ok)
        self.assertEqual(len(breaches), 1)

    def test_assert_no_lookahead_passes_clean_rows(self):
        rows = [
            {"feature_date_utc": "2020-01-01", "sample_available_after_utc": "2020-01-02T00:00:00Z"},
            {"feature_date_utc": "2020-01-03", "sample_available_after_utc": "2020-01-04T00:00:00Z"},
        ]
        ok, breaches = assert_no_lookahead(rows, dt.date(2020, 1, 5))
        self.assertTrue(ok)
        self.assertEqual(breaches, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
