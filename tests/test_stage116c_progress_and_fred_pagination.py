from __future__ import annotations

import contextlib
import importlib.util
import io
import json
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


class FredPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.downloader = load_module(
            "stage116c_downloader_pagination_test",
            "scripts/download_xauusd_official_data_batch.py",
        )

    def test_truncated_legacy_fred_file_is_not_considered_valid(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fred_releases_dates_2009_present.json"
            path.write_text(
                json.dumps(
                    {
                        "count": 2000,
                        "limit": 1000,
                        "offset": 0,
                        "release_dates": [{"release_id": 1, "date": "2015-01-01", "release_name": "Gross Domestic Product"}],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                self.downloader.content_issue(path),
                "FRED_RELEASE_DATES_TRUNCATED",
            )
            self.assertIsNone(self.downloader.existing_valid_skip_result(path))

    def test_complete_fred_release_calendar_is_paginated_and_combined(self):
        pages = {
            0: [
                {"release_id": 10, "date": "2015-01-30", "release_name": "Gross Domestic Product"},
                {"release_id": 54, "date": "2015-01-30", "release_name": "Personal Income and Outlays"},
            ],
            2: [
                {"release_id": 10, "date": "2015-02-27", "release_name": "Gross Domestic Product"},
            ],
        }

        def fake_run(cmd, stdout=None, stderr=None, text=None):
            url = cmd[-3]
            output = Path(cmd[-1])
            offset = int(parse_qs(urlparse(url).query)["offset"][0])
            payload = {
                "count": 3,
                "limit": 2,
                "offset": offset,
                "release_dates": pages[offset],
            }
            output.write_text(json.dumps(payload), encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "fred_releases_dates_2009_present.json"
            with mock.patch.object(self.downloader.subprocess, "run", side_effect=fake_run):
                result = self.downloader.download_fred_release_dates_paginated(
                    out,
                    api_key="secret",
                    page_size=2,
                )
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "OK")
            self.assertEqual(result["pages_downloaded"], 2)
            self.assertEqual(len(payload["release_dates"]), 3)
            self.assertTrue(payload["pagination_complete"])
            self.assertIsNone(self.downloader.content_issue(out))


class StreamingRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load_module(
            "stage116c_streaming_runner_test",
            "scripts/run_xauusd_fundamental_unify_normalize_pipeline.py",
        )

    def test_child_progress_is_streamed_and_retained(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            log = root / "run.jsonl"
            capture = io.StringIO()
            command = [
                sys.executable,
                "-u",
                "-c",
                "print('progress-one', flush=True); print('progress-two', flush=True)",
            ]
            with contextlib.redirect_stdout(capture):
                result = self.runner.run_cmd(
                    command,
                    root,
                    step_no=1,
                    total_steps=1,
                    name="stream-test",
                    log_jsonl=log,
                    quiet=False,
                )
            visible = capture.getvalue()
            self.assertIn("progress-one", visible)
            self.assertIn("progress-two", visible)
            self.assertIn("progress-one", result["stdout_tail"])
            self.assertEqual(result["output_mode"], "STREAMED_STDOUT_STDERR_MERGED")
            events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(row.get("event") == "step_output" and row.get("line") == "progress-one" for row in events))


if __name__ == "__main__":
    unittest.main()
