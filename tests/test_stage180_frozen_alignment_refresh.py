from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "stage180_refresh_frozen_amarkets_alignment.py"
)
SPEC = importlib.util.spec_from_file_location("stage180_refresh", MODULE_PATH)
refresh = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["stage180_refresh"] = refresh
SPEC.loader.exec_module(refresh)


class Stage180FrozenRefreshTests(unittest.TestCase):
    def test_read_frozen_contract_rejects_failed_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "x.sqlite"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE provenance(key TEXT PRIMARY KEY, value TEXT)")
                con.execute(
                    "INSERT INTO provenance VALUES (?, ?)",
                    (
                        "stage177c_time_contract",
                        json.dumps(
                            {
                                "decision": "BLOCK_AMARKETS_TIME_CONTRACT_UNRESOLVED",
                                "contract": "EU_DST_GMT_OFFSET_PAIR",
                                "standard_shift_minutes": -120,
                                "selection_used_holdout": False,
                            }
                        ),
                    ),
                )
            with self.assertRaises(RuntimeError):
                refresh.read_frozen_contract(db)

    def test_existing_floor_is_preserved_by_filter_contract(self):
        floor = int(pd.Timestamp("2015-01-01T00:00:00Z").timestamp() * 1000)
        frame = pd.DataFrame(
            {
                "timestamp": [floor - 300_000, floor, floor + 300_000],
                "close": [1.0, 1.0, 1.0],
            }
        )
        filtered = frame[frame["timestamp"] >= floor]
        self.assertEqual(filtered["timestamp"].min(), floor)
        self.assertEqual(len(filtered), 2)

    def test_overlap_diagnostics_passes_identical_history(self):
        timestamps = [1, 2, 3, 4]
        old = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [10.0] * 4,
                "high": [11.0] * 4,
                "low": [9.0] * 4,
                "close": [10.0, 10.1, 10.2, 10.3],
            }
        )
        result = refresh.overlap_diagnostics(
            old,
            old.copy(),
            minimum_overlap_rows=4,
            max_median_close_diff_bps=0.1,
            max_p99_close_diff_bps=0.1,
        )
        self.assertEqual(result["overlap_rows"], 4)
        self.assertEqual(result["median_close_diff_bps"], 0.0)

    def test_safe_import_registers_dataclass_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "module.py"
            path.write_text(
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True)\n"
                "class Contract:\n"
                "    value: int\n",
                encoding="utf-8",
            )
            module = refresh.safe_import(path, "refresh_dataclass_probe")
            self.assertEqual(module.Contract(3).value, 3)
            sys.modules.pop("refresh_dataclass_probe", None)


if __name__ == "__main__":
    unittest.main()
