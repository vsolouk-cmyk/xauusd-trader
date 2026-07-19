from __future__ import annotations

import csv
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


purge = load_module("purge", "app/stage177a_actions_storage_purge.py")
duka = load_module("duka", "app/stage177a_dukascopy_history.py")


class FakeAPI:
    def __init__(self):
        self.artifacts = [
            {"id": 1, "name": "a", "size_in_bytes": 100},
            {"id": 2, "name": "b", "size_in_bytes": 200},
        ]
        self.caches = [{"id": 7, "key": "cache", "size_in_bytes": 300}]

    def list_artifacts(self, page=1):
        return list(self.artifacts) if page == 1 else []

    def delete_artifact(self, artifact_id):
        self.artifacts = [item for item in self.artifacts if item["id"] != artifact_id]

    def list_caches(self, page=1):
        return list(self.caches) if page == 1 else []

    def delete_cache(self, cache_id):
        self.caches = [item for item in self.caches if item["id"] != cache_id]


class StoragePurgeTests(unittest.TestCase):
    def test_repeated_page1_deletes_without_pagination_skip(self):
        api = FakeAPI()
        stats = purge.PurgeStats(dry_run=False)
        purge.purge_artifacts(api, stats, dry_run=False)
        self.assertEqual(stats.artifacts_deleted, 2)
        self.assertEqual(api.artifacts, [])

    def test_cache_purge(self):
        api = FakeAPI()
        stats = purge.PurgeStats(dry_run=False)
        purge.purge_caches(api, stats, dry_run=False)
        self.assertEqual(stats.caches_deleted, 1)
        self.assertEqual(api.caches, [])

    def test_dry_run_is_non_destructive(self):
        api = FakeAPI()
        stats = purge.PurgeStats(dry_run=True)
        purge.purge_artifacts(api, stats, dry_run=True)
        self.assertEqual(len(api.artifacts), 2)
        self.assertEqual(stats.artifacts_deleted, 0)


class DukascopyValidationTests(unittest.TestCase):
    def make_csv(self, path: Path, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            writer.writerows(rows)

    def test_month_chunking_has_no_overlap(self):
        chunks = list(duka.iter_chunks(dt.date(2024, 1, 1), dt.date(2025, 1, 1), 3))
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[0], (dt.date(2024, 1, 1), dt.date(2024, 4, 1)))
        for previous, current in zip(chunks, chunks[1:]):
            self.assertEqual(previous[1], current[0])

    def test_valid_csv_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            self.make_csv(path, [
                [1704067200000, 2000, 2002, 1999, 2001, 10],
                [1704070800000, 2001, 2003, 2000, 2002, 12],
            ])
            metrics = duka.validate_csv(path, "h1")
            self.assertEqual(metrics["rows"], 2)

    def test_duplicate_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            self.make_csv(path, [
                [1704067200000, 2000, 2002, 1999, 2001, 10],
                [1704067200000, 2001, 2003, 2000, 2002, 12],
            ])
            with self.assertRaises(ValueError):
                duka.validate_csv(path, "h1")

    def test_ohlc_violation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            self.make_csv(path, [[1704067200000, 2000, 1998, 1999, 2001, 10]])
            with self.assertRaises(ValueError):
                duka.validate_csv(path, "h1")

    def test_config_forbids_execution(self):
        config = json.loads((ROOT / "configs/stage177a_dukascopy_history.json").read_text())
        self.assertFalse(config["orders_allowed"])
        self.assertFalse(config["paper_allowed"])
        self.assertFalse(config["demo_allowed"])
        self.assertFalse(config["live_allowed"])

    def test_workflow_retention_is_one_day(self):
        workflow = (ROOT / ".github/workflows/xauusd_stage177a_dukascopy_history.yml").read_text()
        self.assertIn("retention-days: 1", workflow)
        self.assertNotIn("schedule:", workflow)

    def test_gdelt_active_workflow_not_packaged(self):
        self.assertFalse((ROOT / ".github/workflows/xauusd_stage166f_gdelt_backfill.yml").exists())
        self.assertTrue((ROOT / "archive/disabled_workflows/xauusd_stage166f_gdelt_backfill.yml.disabled").exists())


if __name__ == "__main__":
    unittest.main()
