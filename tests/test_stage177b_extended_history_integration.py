import csv
import gzip
import hashlib
import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = load_module(
    "stage177b_core", ROOT / "app" / "stage177b_extended_history_integration.py"
)


def gzip_csv(rows):
    raw = io.StringIO()
    writer = csv.writer(raw)
    writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
    writer.writerows(rows)
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as handle:
        handle.write(raw.getvalue().encode("utf-8"))
    return out.getvalue()


def build_artifact(path, preset, timeframe, rows, sha_override=None):
    gz = gzip_csv(rows)
    member = f"chunks/test_{timeframe}.csv.gz"
    manifest = {
        "preset": preset,
        "price_type": "bid",
        "results": [
            {
                "status": "PASS",
                "timeframe": timeframe,
                "date_from": "2020-01-01",
                "date_to": "2020-01-02",
                "csv_gz": member,
                "rows": len(rows),
                "sha256": sha_override or hashlib.sha256(gz).hexdigest(),
                "compressed_bytes": len(gz),
            }
        ],
    }
    summary = {
        "decision": "PASS_DOWNLOAD_COMPLETE",
        "chunks_fail": 0,
        "chunks_total": 1,
        "rows_total": len(rows),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, gz)
        zf.writestr("stage177a_dukascopy_manifest.json", json.dumps(manifest))
        zf.writestr("stage177a_dukascopy_summary.json", json.dumps(summary))


class Stage177BTests(unittest.TestCase):
    def test_artifact_hash_and_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "h1.zip"
            rows = [(1577836800000, 1, 2, 0.5, 1.5, 10)]
            build_artifact(path, "h1_full", "h1", rows)
            contract = core.validate_artifact(path, "h1_full", "h1")
            self.assertEqual(contract.summary["rows_total"], 1)

    def test_bad_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            rows = [(1577836800000, 1, 2, 0.5, 1.5, 10)]
            build_artifact(path, "h1_full", "h1", rows, sha_override="0" * 64)
            with self.assertRaises(ValueError):
                core.validate_artifact(path, "h1_full", "h1")

    def test_canonical_prefers_m5_inside_overlap(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite"
            con = core.create_database(db)
            try:
                con.executemany(
                    "INSERT INTO dukascopy_h1_direct VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (0, 1, 2, 0.5, 1.5, 10),
                        (core.H1_MS, 9, 9, 9, 9, 1),
                    ],
                )
                con.execute(
                    "INSERT INTO dukascopy_h1_from_m5 VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (core.H1_MS, 2, 3, 1, 2.5, 20, 12),
                )
                con.commit()
                summary = core.build_canonical_h1(con)
                row = con.execute(
                    "SELECT open, source FROM dukascopy_h1_canonical WHERE timestamp=?",
                    (core.H1_MS,),
                ).fetchone()
                self.assertEqual(row, (2.0, "M5_DERIVED"))
                self.assertEqual(summary["rows_total"], 2)
            finally:
                con.close()

    def test_parity_audit_detects_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "test.sqlite"
            csv_path = Path(temp) / "anomalies.csv"
            con = core.create_database(db)
            try:
                con.execute(
                    "INSERT INTO dukascopy_h1_direct VALUES (?, ?, ?, ?, ?, ?)",
                    (core.H1_MS, 1, 2, 0.5, 1.5, 10),
                )
                con.execute(
                    "INSERT INTO dukascopy_h1_from_m5 VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (core.H1_MS, 1.1, 2, 0.5, 1.5, 10, 12),
                )
                con.commit()
                result = core.parity_analysis(con, csv_path)
                self.assertEqual(result["ohlc_mismatch_hours"], 1)
                self.assertTrue(csv_path.exists())
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
