from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    if spec is None or spec.loader is None:
        raise RuntimeError(rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FredCoreReleaseHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.downloader = load_module(
            "stage116c_downloader_core_history_test",
            "scripts/download_xauusd_official_data_batch.py",
        )
        cls.normalizer = load_module(
            "stage114b_core_history_test",
            "app/stage114b_classification_and_macro_event_hotfix.py",
        )
        cls.builder = load_module(
            "stage115_core_history_test",
            "app/stage115_feature_grade_macro_fundamental_builder.py",
        )

    def test_current_year_only_core_cache_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fred_core_release_dates_2009_present.json"
            rows = []
            for release_id, spec in self.downloader.FRED_CORE_RELEASES.items():
                rows.append({
                    "release_id": release_id,
                    "release_name": spec["release_name"],
                    "source": spec["source"],
                    "category": spec["category"],
                    "date": "2026-01-15",
                })
            path.write_text(json.dumps({
                "collection_mode": "CORE_RELEASE_ID_ENDPOINTS",
                "release_ids": list(self.downloader.FRED_CORE_RELEASE_IDS),
                "collection_complete": True,
                "release_dates": rows,
            }), encoding="utf-8")
            self.assertEqual(
                self.downloader.content_issue(path),
                "FRED_CORE_RELEASE_DATES_NO_2015_HISTORY",
            )
            self.assertIsNone(self.downloader.existing_valid_skip_result(path))

    def test_core_release_endpoint_downloads_each_locked_release_id(self):
        def fake_run(cmd, stdout=None, stderr=None, text=None):
            url = cmd[-3]
            output = Path(cmd[-1])
            qs = parse_qs(urlparse(url).query)
            release_id = int(qs["release_id"][0])
            self.assertIn("/fred/release/dates", url)
            payload = {
                "count": 3,
                "limit": 10000,
                "offset": 0,
                "release_dates": [
                    {"release_id": release_id, "date": "2015-01-15"},
                    {"release_id": release_id, "date": "2020-01-15"},
                    {"release_id": release_id, "date": "2026-01-15"},
                ],
            }
            output.write_text(json.dumps(payload), encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "fred_core_release_dates_2009_present.json"
            with mock.patch.object(self.downloader.subprocess, "run", side_effect=fake_run):
                result = self.downloader.download_fred_core_release_dates(
                    out,
                    api_key="secret",
                    from_year=2015,
                    to_year=2026,
                )
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "OK")
            self.assertEqual(payload["collection_mode"], "CORE_RELEASE_ID_ENDPOINTS")
            self.assertEqual(
                {int(x) for x in payload["release_ids"]},
                set(self.downloader.FRED_CORE_RELEASE_IDS),
            )
            self.assertEqual(len(payload["release_dates"]), 21)
            self.assertTrue(payload["collection_complete"])
            self.assertIsNone(self.downloader.content_issue(out))
            names = {row["release_name"] for row in payload["release_dates"]}
            self.assertIn("Employment Cost Index", names)
            self.assertIn("Personal Income and Outlays", names)

    def test_event_core_only_uses_release_id_endpoint_bundle(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"FRED_API_KEY": "secret"}, clear=False
        ):
            sections = self.downloader.build_sections(
                Path(td),
                years=[2015, 2016, 2026],
                include_cot_xls=False,
                skip_wgc_direct=True,
                dry_run=True,
                force_refresh=False,
                refresh_stale_hours=None,
                event_core_only=True,
            )
            fred = [tasks for name, tasks in sections if "FRED release dates" in name]
            self.assertEqual(len(fred), 1)
            task_names = [name for name, _ in fred[0]]
            self.assertEqual(task_names, ["fred_core_release_dates_2009_present.json"])

    def test_stage114b_to_stage115_builds_all_locked_categories_and_years(self):
        required_years = [2015, 2016, 2017, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            raw = base / "fred_core_release_dates_2009_present.json"
            normalized_dir = base / "normalized"
            feature_dir = base / "features"
            normalized_dir.mkdir()
            feature_dir.mkdir()
            rows = []
            for release_id, spec in self.downloader.FRED_CORE_RELEASES.items():
                for year in required_years:
                    rows.append({
                        "release_id": release_id,
                        "release_name": spec["release_name"],
                        "source": spec["source"],
                        "category": spec["category"],
                        "date": f"{year}-01-15",
                    })
            raw.write_text(json.dumps({
                "collection_mode": "CORE_RELEASE_ID_ENDPOINTS",
                "release_ids": list(self.downloader.FRED_CORE_RELEASE_IDS),
                "collection_complete": True,
                "release_dates": rows,
            }), encoding="utf-8")
            normalized_rows = self.normalizer.normalize_fred_release_dates([raw])
            normalized_path = normalized_dir / "fred_release_calendar_normalized.csv"
            with normalized_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(normalized_rows[0]))
                writer.writeheader()
                writer.writerows(normalized_rows)
            built, meta = self.builder.build_official_core_event_timestamps(
                normalized_dir, feature_dir
            )
            categories = {row["category"] for row in built}
            expected_categories = {
                spec["category"]
                for spec in self.downloader.FRED_CORE_RELEASES.values()
            }
            self.assertEqual(categories, expected_categories)
            for year in required_years:
                year_rows = [row for row in built if str(row["event_time_utc"]).startswith(str(year))]
                self.assertEqual(len(year_rows), len(expected_categories))
            self.assertEqual(meta["official_core_event_counts_by_source"]["BLS"], 55)
            self.assertEqual(meta["official_core_event_counts_by_source"]["BEA"], 22)
            self.assertTrue(all(row["date_source"] == "FRED_CORE_RELEASE_DATES_API" for row in built))

    def test_realistic_core_release_histories_pass_exact_coverage_floor(self):
        from datetime import datetime, timezone

        required_years = [2015, 2016, 2017, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
        monthly_ids = [10, 46, 50, 192, 54]
        quarterly_ids = [11]
        gdp_id = 53
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            raw = base / "fred_core_release_dates_2009_present.json"
            normalized_dir = base / "normalized"
            feature_dir = base / "features"
            normalized_dir.mkdir()
            feature_dir.mkdir()
            rows = []
            for year in required_years:
                months = range(1, 13) if year < 2026 else range(1, 8)
                for release_id in monthly_ids:
                    spec = self.downloader.FRED_CORE_RELEASES[release_id]
                    for month in months:
                        rows.append({
                            "release_id": release_id,
                            "release_name": spec["release_name"],
                            "source": spec["source"],
                            "category": spec["category"],
                            "date": f"{year}-{month:02d}-15",
                        })
                for release_id in quarterly_ids:
                    spec = self.downloader.FRED_CORE_RELEASES[release_id]
                    for month in ([1, 4, 7, 10] if year < 2026 else [1, 4, 7]):
                        rows.append({
                            "release_id": release_id,
                            "release_name": spec["release_name"],
                            "source": spec["source"],
                            "category": spec["category"],
                            "date": f"{year}-{month:02d}-20",
                        })
                spec = self.downloader.FRED_CORE_RELEASES[gdp_id]
                gdp_months = range(1, 13) if year < 2026 else range(1, 8)
                for month in gdp_months:
                    rows.append({
                        "release_id": gdp_id,
                        "release_name": spec["release_name"],
                        "source": spec["source"],
                        "category": spec["category"],
                        "date": f"{year}-{month:02d}-28",
                    })
            raw.write_text(json.dumps({
                "collection_mode": "CORE_RELEASE_ID_ENDPOINTS",
                "release_ids": list(self.downloader.FRED_CORE_RELEASE_IDS),
                "collection_complete": True,
                "release_dates": rows,
            }), encoding="utf-8")
            normalized_rows = self.normalizer.normalize_fred_release_dates([raw])
            normalized_path = normalized_dir / "fred_release_calendar_normalized.csv"
            with normalized_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(normalized_rows[0]))
                writer.writeheader()
                writer.writerows(normalized_rows)
            built, _ = self.builder.build_official_core_event_timestamps(normalized_dir, feature_dir)

            event_module = load_module(
                "xauusd_event_core_coverage_test",
                "app/xauusd_historical_event_context.py",
            )
            official = event_module.load_official_events(
                feature_dir / "stage115_official_core_event_timestamps.csv",
                60.0,
                60.0,
            )
            # FOMC is already sourced from the existing FED calendar branch; add
            # a minimal valid FED fixture to isolate the BLS/BEA regression.
            for year in required_years:
                count = 8 if year < 2026 else 4
                for month in range(1, count + 1):
                    official.append(event_module.OfficialEvent(
                        event_time_utc=f"{year}-{month:02d}-01T19:00:00Z",
                        source="FED",
                        category="FOMC_STATEMENT",
                        title="FOMC Statement",
                        source_url="https://www.federalreserve.gov/monetarypolicy/fomc.htm",
                        source_year=year,
                        blackout_before_minutes=60.0,
                        blackout_after_minutes=60.0,
                        date_source="FED_LOCAL_CALENDAR_PAGE",
                        time_source="POLICY",
                        source_file="fixture",
                    ))
            audit = event_module.coverage_audit(
                official,
                set(required_years),
                datetime(2026, 7, 1, tzinfo=timezone.utc),
            )
            self.assertTrue(audit["pass"], audit)
            self.assertGreaterEqual(audit["counts_by_source"]["BLS"], 40 * 10)
            self.assertGreaterEqual(audit["counts_by_source"]["BEA"], 18 * 10)
            self.assertEqual(audit["missing_required_categories"], [])


if __name__ == "__main__":
    unittest.main()
