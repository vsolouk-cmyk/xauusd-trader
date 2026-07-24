from __future__ import annotations

import csv
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


event = load_module("xauusd_event_context_test", ROOT / "app/xauusd_historical_event_context.py")
runtime = load_module("xauusd_runtime_event_test", ROOT / "app/xauusd_controlled_paper.py")
stage114b = load_module("stage114b_event_test", ROOT / "app/stage114b_classification_and_macro_event_hotfix.py")
stage115 = load_module("stage115_event_test", ROOT / "app/stage115_feature_grade_macro_fundamental_builder.py")
downloader = load_module("stage116_downloader_test", ROOT / "scripts/download_xauusd_official_data_batch.py")


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


class ExistingPipelineEventContextTests(unittest.TestCase):
    def test_release_name_classifier_covers_core_bls_bea(self):
        cases = {
            "Employment Situation": ("BLS", "BLS_EMPLOYMENT_SITUATION", 8, 30),
            "Consumer Price Index": ("BLS", "BLS_CPI", 8, 30),
            "Producer Price Index": ("BLS", "BLS_PPI", 8, 30),
            "Job Openings and Labor Turnover Survey": ("BLS", "BLS_JOLTS", 10, 0),
            "Employment Cost Index": ("BLS", "BLS_ECI", 8, 30),
            "Gross Domestic Product": ("BEA", "BEA_GDP", 8, 30),
            "Personal Income and Outlays": ("BEA", "BEA_PERSONAL_INCOME_OUTLAYS", 8, 30),
        }
        for name, expected in cases.items():
            policy = stage115.classify_official_release_name(name)
            self.assertIsNotNone(policy)
            self.assertEqual((policy["source"], policy["category"], policy["hour"], policy["minute"]), expected)
        self.assertIsNone(stage115.classify_official_release_name("Gross Domestic Product by State"))

    def test_canonical_et_timestamp_handles_dst(self):
        self.assertEqual(stage115.canonical_et_timestamp("2015-01-09", 8, 30), "2015-01-09T13:30:00Z")
        self.assertEqual(stage115.canonical_et_timestamp("2015-07-09", 8, 30), "2015-07-09T12:30:00Z")

    def test_fomc_normalizer_uses_decision_day_and_press_flag(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fomc_historical_2015.html"
            path.write_text(
                "<h5>January 27-28 Meeting - 2015</h5><a>Statement</a><div>Minutes</div>"
                "<h5>March 17-18 Meeting - 2015</h5><a>Statement</a><a>Press Conference</a>",
                encoding="utf-8",
            )
            rows = stage114b.normalize_fomc([path])
            self.assertEqual([row["event_date"] for row in rows], ["2015-01-28", "2015-03-18"])
            self.assertEqual([row["has_press_conference"] for row in rows], [0, 1])

    def test_stage115_builds_timestamped_calendar_from_normalized_pipeline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "normalized"
            features = root / "features"
            write_csv(
                normalized / "fred_release_calendar_normalized.csv",
                [
                    {"date": "2015-01-09", "release_name": "Employment Situation", "release_id": "1", "source_file": "fred.json"},
                    {"date": "2015-01-16", "release_name": "Consumer Price Index", "release_id": "2", "source_file": "fred.json"},
                    {"date": "2015-01-30", "release_name": "Gross Domestic Product", "release_id": "3", "source_file": "fred.json"},
                    {"date": "2015-01-30", "release_name": "Gross Domestic Product by State", "release_id": "4", "source_file": "fred.json"},
                ],
            )
            write_csv(
                normalized / "fomc_calendar_extracted.csv",
                [{"event_date": "2015-03-18", "has_statement": 1, "has_press_conference": 1, "source_file": "fomc.html"}],
            )
            rows, meta = stage115.build_official_core_event_timestamps(normalized, features)
            self.assertEqual(len(rows), 5)
            self.assertTrue((features / "stage115_official_core_event_timestamps.csv").is_file())
            self.assertEqual(meta["official_core_event_timestamp_rows"], 5)
            categories = {row["category"] for row in rows}
            self.assertNotIn("BEA_GDP_BY_STATE", categories)
            self.assertIn("FOMC_PRESS_CONFERENCE", categories)

    def test_downloader_keeps_fomc_history_inside_stage116(self):
        with tempfile.TemporaryDirectory() as td:
            sections = downloader.build_sections(
                Path(td), [2015, 2016, 2026], include_cot_xls=False, skip_wgc_direct=True,
                dry_run=True, force_refresh=False, refresh_stale_hours=None,
            )
            section = next(tasks for name, tasks in sections if "FOMC current + historical" in name)
            labels = [label for label, _ in section]
            self.assertIn("fomc_calendars_current.html", labels)
            self.assertIn("fomc_historical_2015.html", labels)
            self.assertIn("fomc_historical_2016.html", labels)
            self.assertNotIn("fomc_historical_2026.html", labels)

    def test_event_core_only_avoids_unrelated_bulk_sources(self):
        with tempfile.TemporaryDirectory() as td:
            sections = downloader.build_sections(
                Path(td), [2015, 2026], include_cot_xls=False, skip_wgc_direct=True,
                dry_run=True, force_refresh=False, refresh_stale_hours=None, event_core_only=True,
            )
            names = [name for name, _ in sections]
            self.assertEqual(len(names), 4)
            self.assertTrue(any("FRED release dates" in name for name in names))
            self.assertFalse(any("CFTC" in name or "WGC" in name or "Census" in name for name in names))

    def test_bls_download_payload_uses_requested_years_with_key(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"BLS_API_KEY": "secret"}, clear=False):
            result = downloader.post_bls(Path(td) / "bls.json", start_year=2011, end_year=2026, dry_run=True)
            self.assertEqual(result["payload"]["startyear"], "2011")
            self.assertEqual(result["payload"]["endyear"], "2026")
            self.assertEqual(result["payload"]["registrationkey"], "${BLS_API_KEY}")

    def test_build_maps_exact_146_entries_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = root / "reports/commercial_closure_sprint/commercial_closure_execution_ledger.csv"
            base = datetime(2025, 1, 1, 13, tzinfo=UTC)
            ledger_rows = []
            for i in range(168):
                status = "EVALUATED" if i < 146 else "SIGNAL_H1_TIMESTAMP_MISSING"
                entry = base + timedelta(hours=i * 24)
                ledger_rows.append({
                    "timestamp": (entry - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                    "entry_bucket_utc": entry.isoformat().replace("+00:00", "Z") if status == "EVALUATED" else "",
                    "status": status,
                    "probability_up": "0.61",
                })
            write_csv(ledger, ledger_rows)

            events_path = root / "data/fundamental_event_inbox/features/stage115_official_core_event_timestamps.csv"
            rows = []
            # Conservative completeness floors for one full year.
            categories = [
                ("BLS", "BLS_EMPLOYMENT_SITUATION", 10),
                ("BLS", "BLS_CPI", 10),
                ("BLS", "BLS_PPI", 8),
                ("BLS", "BLS_JOLTS", 8),
                ("BLS", "BLS_ECI", 4),
                ("BEA", "BEA_GDP", 9),
                ("BEA", "BEA_PERSONAL_INCOME_OUTLAYS", 9),
                ("FED", "FOMC_STATEMENT", 7),
            ]
            day = 1
            for source, category, count in categories:
                for idx in range(count):
                    dt = datetime(2025, 1, 1, 13, 30, tzinfo=UTC) + timedelta(days=day)
                    day += 1
                    rows.append({
                        "event_time_utc": dt.isoformat().replace("+00:00", "Z"),
                        "source": source,
                        "category": category,
                        "title": category,
                        "source_url": "https://official.example",
                        "source_file": "fixture",
                        "date_source": "OFFICIAL_FIXTURE",
                        "time_source": "POLICY_FIXTURE",
                        "blackout_before_minutes": 60,
                        "blackout_after_minutes": 60,
                    })
            write_csv(events_path, rows)
            config = {
                "execution_ledger": str(ledger.relative_to(root)),
                "official_events_csv": str(events_path.relative_to(root)),
                "pipeline_summary": "reports/pipeline.json",
                "stage115_summary": "reports/stage115.json",
                "report_dir": "reports/xauusd_historical_event_context",
                "sqlite_path": "data/local/historical_event_context/xauusd_historical_event_context.sqlite",
                "blackout_before_minutes": 60,
                "blackout_after_minutes": 60,
            }
            summary = event.build(root, config)
            self.assertTrue(summary["pass"])
            self.assertEqual(summary["evaluated_entry_rows"], 146)
            self.assertFalse(summary["network_access_attempted"])
            db = root / config["sqlite_path"]
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM macro_context_h1").fetchone()[0], 146)

    def test_runtime_event_guard_consumes_pipeline_bridge_sqlite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_path = root / "data/local/historical_event_context/xauusd_historical_event_context.sqlite"
            one = event.OfficialEvent(
                "2026-01-01T13:30:00Z", "BLS", "BLS_CPI", "CPI", "https://official", 2026,
                60, 60, "FRED_RELEASE_DATES_API", "POLICY", "fred.json",
            )
            rows = [{
                "utc_time": "2026-01-01T13:00:00Z", "source_row": 2, "signal_utc": "2026-01-01T12:00:00Z",
                "has_block_event": 1, "active_event_count": 1, "nearest_event_minutes": 30.0,
                "nearest_event_time_utc": one.event_time_utc, "nearest_event_title": one.title,
                "event_titles": one.title, "source_names": one.source, "event_times_utc": one.event_time_utc,
                "core_coverage_complete": 1, "universe_version": event.UNIVERSE_VERSION,
            }]
            event.persist_sqlite(db_path, [one], rows, [], {"pass": True})
            guard = runtime.EventGuard(root, {
                "required": True,
                "csv_candidates": [],
                "macro_db_candidates": ["data/local/historical_event_context/xauusd_historical_event_context.sqlite"],
                "macro_table_candidates": ["macro_context_h1"],
            })
            result = guard.evaluate(int(datetime(2026, 1, 1, 13, tzinfo=UTC).timestamp() * 1000))
            self.assertEqual(result[1], "EVENT_BLACKOUT_ACTIVE")

    def test_consumer_has_no_direct_network_or_order_path(self):
        text = (ROOT / "app/xauusd_historical_event_context.py").read_text(encoding="utf-8").lower()
        for token in ("urllib", "urlopen", "requests.", "curl", "ordersend", "place_order", "send_order"):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
