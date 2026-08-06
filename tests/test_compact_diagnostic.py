from __future__ import annotations

import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import xauusd_cross_asset_panel_compact_diagnostic as diag


class CompactDiagnosticTests(unittest.TestCase):
    def test_end_to_end_compact_pack(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = root / "reports/xauusd_cross_asset_intraday_panel"
            report.mkdir(parents=True)
            export_dir = root / "exports"
            export_dir.mkdir()

            feature_cols = [
                "decision_time_utc", "sample_role", "xauusd_h1_ret4",
                "xauusd_h1_available_time_utc", "daily_real_yield"
            ]
            target_cols = ["decision_time_utc", "entry_open", "target_return_4h"]
            with (report / diag.FEATURE_NAME).open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=feature_cols); w.writeheader()
                w.writerow({"decision_time_utc":"2024-01-01T00:00:00+00:00","sample_role":"REFERENCE","xauusd_h1_ret4":"0.1","xauusd_h1_available_time_utc":"2023-12-31T23:00:00+00:00","daily_real_yield":"1"})
                w.writerow({"decision_time_utc":"2025-01-01T00:00:00+00:00","sample_role":"DIAGNOSTIC","xauusd_h1_ret4":"","xauusd_h1_available_time_utc":"","daily_real_yield":"2"})
            with (report / diag.TARGET_NAME).open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=target_cols); w.writeheader()
                w.writerow({"decision_time_utc":"2024-01-01T00:00:00+00:00","entry_open":"2000","target_return_4h":"0.01"})
                w.writerow({"decision_time_utc":"2025-01-01T00:00:00+00:00","entry_open":"2100","target_return_4h":"0.02"})
            source = export_dir / "xauusd__h1.csv"
            with source.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh); w.writerow(["time_utc","open"]); w.writerow(["2024-01-01T00:00:00+00:00","2000"])
            source_hash = diag.sha256_file(source)
            with (report / "cross_asset_source_manifest.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=["symbol","timeframe","path","rows","first_utc","last_utc","sha256"]); w.writeheader()
                w.writerow({"symbol":"XAUUSD","timeframe":"H1","path":str(source),"rows":1,"first_utc":"2024-01-01T00:00:00+00:00","last_utc":"2024-01-01T00:00:00+00:00","sha256":source_hash})
            for name in ("cross_asset_panel_summary.json","cross_asset_panel_quality.json","cross_asset_panel_contract.json"):
                (report / name).write_text(json.dumps({"ok": True}), encoding="utf-8")

            output = root / "diag.zip"
            diag.run(root, output)
            self.assertTrue(output.is_file())
            with zipfile.ZipFile(output) as zf:
                names = set(zf.namelist())
                self.assertIn("features_profile.json", names)
                self.assertIn("features_column_coverage.csv", names)
                self.assertIn("features_key_columns.csv.gz", names)
                self.assertIn("source_export_profile.csv", names)
                self.assertNotIn(diag.FEATURE_NAME, names)
                alignment = json.loads(zf.read("feature_target_alignment.json"))
                self.assertTrue(alignment["decision_time_sequence_match"])


if __name__ == "__main__":
    unittest.main()
