from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_xauusd_fundamental_unify_normalize_pipeline.py"
DOWNLOADER = ROOT / "scripts" / "download_xauusd_official_data_batch.py"


class Stage116CEventContextBridgeCliTests(unittest.TestCase):
    def _help(self, script: Path) -> str:
        cp = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        return cp.stdout

    def test_runner_exposes_bridge_flags(self) -> None:
        output = self._help(RUNNER)
        for flag in (
            "--event-core-only",
            "--build-historical-event-context",
            "--run-replay",
        ):
            self.assertIn(flag, output)

    def test_downloader_exposes_event_core_only(self) -> None:
        output = self._help(DOWNLOADER)
        self.assertIn("--event-core-only", output)

    def test_runner_source_contains_dispatch(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('download_cmd.append("--event-core-only")', source)
        self.assertIn('event_cmd.append("--run-replay")', source)
        self.assertIn('"app/xauusd_historical_event_context.py"', source)


if __name__ == "__main__":
    unittest.main()
