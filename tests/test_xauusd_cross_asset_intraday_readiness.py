from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "xauusd_cross_asset_intraday_readiness.py"
spec = importlib.util.spec_from_file_location("cross_asset", MODULE_PATH)
scan = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(scan)

HEADERS = [
    "program","generated_server_time","symbol","description","categories","selected","trade_mode","digits","point","bid","ask","spread_points","spread_bps",
    "m15_bars","m15_first_epoch","m15_last_epoch","m15_synchronized","h1_bars","h1_first_epoch","h1_last_epoch","h1_synchronized","d1_bars","d1_first_epoch","d1_last_epoch","d1_synchronized"
]


def row(symbol: str, categories: str, h1_bars: int = 6000) -> dict:
    return {
        "program": scan.PROGRAM, "generated_server_time": "1786000000", "symbol": symbol,
        "description": symbol, "categories": categories, "selected": "1", "trade_mode": "4",
        "digits": "2", "point": "0.01", "bid": "100", "ask": "100.1", "spread_points": "10", "spread_bps": "10",
        "m15_bars": "20000", "m15_first_epoch": "1420070400", "m15_last_epoch": "1786000000", "m15_synchronized": "1",
        "h1_bars": str(h1_bars), "h1_first_epoch": "1420070400", "h1_last_epoch": "1786000000", "h1_synchronized": "1",
        "d1_bars": "3000", "d1_first_epoch": "1420070400", "d1_last_epoch": "1786000000", "d1_synchronized": "1",
    }


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for rel in ["app", "mt5", "config", "reports", "inventory"]:
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        (self.root / "app" / MODULE_PATH.name).write_text(MODULE_PATH.read_text())
        mql = Path(__file__).resolve().parents[1] / "mt5" / "XAUUSD_CrossAssetInventory.mq5"
        (self.root / "mt5" / mql.name).write_text(mql.read_text())
        cfg = {
            "program": scan.PROGRAM,
            "mt5_inventory_relative_path": "inventory/mt5_cross_asset_inventory.csv",
            "mt5_inventory_snapshot_glob": "mt5_cross_asset_inventory_*.csv",
            "mt5_files_directory": str(self.root),
            "history_start_utc": "2015-01-01T00:00:00Z",
            "minimum_h1_bars": 5000,
            "freshness_days": 10,
            "required_categories": ["USD_PROXY", "US_RATES", "SILVER"],
            "optional_categories": ["VOLATILITY", "EQUITY_RISK", "ENERGY"],
        }
        (self.root / scan.CONFIG_PATH).write_text(json.dumps(cfg))

    def tearDown(self):
        self.tmp.cleanup()

    def write_inventory(self, rows, name="mt5_cross_asset_inventory.csv"):
        path = self.root / "inventory" / name
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=HEADERS)
            writer.writeheader(); writer.writerows(rows)
        return path.resolve()

    def test_preflight_no_inventory_is_non_order_pass(self):
        out = scan.preflight(self.root)
        self.assertTrue(out["pass"])
        self.assertFalse(out["paper_order_allowed"])
        self.assertEqual(out["required_next_action"], "RUN_MT5_SCRIPT_ONCE_THEN_COLLECT")

    def test_preflight_header_only_inventory_requires_rerun(self):
        self.write_inventory([])
        out = scan.preflight(self.root)
        self.assertTrue(out["pass"])
        self.assertFalse(out["mt5_inventory_valid"])
        self.assertEqual(out["required_next_action"], "RUN_MT5_SCRIPT_ONCE_THEN_COLLECT")

    def test_read_inventory_normalizes_categories_and_times(self):
        path = self.write_inventory([row("DXY", "USD_INDEX")])
        rows = scan.read_inventory(path)
        self.assertEqual(rows[0]["categories"], ["USD_INDEX"])
        self.assertTrue(rows[0]["h1_synchronized"])
        self.assertTrue(rows[0]["h1_first_utc"].startswith("2015-"))

    def test_select_valid_inventory_falls_back_from_header_only_canonical(self):
        self.write_inventory([])
        snapshot = self.write_inventory([row("DXY", "USD_INDEX")], "mt5_cross_asset_inventory_1.csv")
        cfg = scan.load_config(self.root)
        selected, rows, diagnostics = scan.select_valid_inventory(cfg)
        self.assertEqual(selected, snapshot)
        self.assertEqual(len(rows), 1)
        self.assertTrue(any(not item["valid"] for item in diagnostics))

    def test_select_valid_inventory_prefers_newest_valid_snapshot(self):
        canonical = self.write_inventory([row("OLD", "SILVER")])
        snapshot = self.write_inventory([row("NEW", "SILVER")], "mt5_cross_asset_inventory_2.csv")
        os.utime(canonical, (1, 1))
        os.utime(snapshot, (2, 2))
        selected, rows, _ = scan.select_valid_inventory(scan.load_config(self.root))
        self.assertEqual(selected, snapshot)
        self.assertEqual(rows[0]["symbol"], "NEW")

    def test_selected_inventory_uses_canonical_filesystem_identity(self):
        snapshot = self.write_inventory([row("DXY", "USD_INDEX")], "mt5_cross_asset_inventory_alias.csv")
        selected, rows, _ = scan.select_valid_inventory(scan.load_config(self.root))
        self.assertEqual(selected.resolve(), snapshot.resolve())
        self.assertTrue(os.path.samefile(selected, snapshot))
        self.assertEqual(len(rows), 1)

    def test_usd_index_satisfies_usd_proxy(self):
        rows = scan.read_inventory(self.write_inventory([row("DXY", "USD_INDEX")]))
        self.assertIn("USD_PROXY", scan.category_presence(rows))

    def test_two_fx_pairs_satisfy_usd_proxy(self):
        rows = scan.read_inventory(self.write_inventory([row("EURUSD", "USD_FX_PROXY"), row("USDJPY", "USD_FX_PROXY")]))
        self.assertIn("USD_PROXY", scan.category_presence(rows))

    def test_single_fx_pair_does_not_satisfy_usd_proxy(self):
        rows = scan.read_inventory(self.write_inventory([row("EURUSD", "USD_FX_PROXY")]))
        self.assertNotIn("USD_PROXY", scan.category_presence(rows))

    def test_core_ready_decision(self):
        rows = scan.read_inventory(self.write_inventory([row("DXY", "USD_INDEX"), row("US10Y", "US_RATES"), row("XAGUSD", "SILVER")]))
        decision, detail = scan.readiness_decision(rows, scan.load_config(self.root))
        self.assertEqual(decision, "PASS_CROSS_ASSET_INTRADAY_CORE_AVAILABLE_FOR_CAUSAL_PANEL")
        self.assertEqual(detail["missing_required_categories"], [])

    def test_history_download_required_decision(self):
        rows = scan.read_inventory(self.write_inventory([row("DXY", "USD_INDEX", 100), row("US10Y", "US_RATES"), row("XAGUSD", "SILVER")]))
        decision, detail = scan.readiness_decision(rows, scan.load_config(self.root))
        self.assertEqual(decision, "PASS_SYMBOLS_PRESENT_HISTORY_DOWNLOAD_REQUIRED")
        self.assertIn("USD_PROXY", detail["history_download_required_categories"])

    def test_missing_rates_is_partial(self):
        rows = scan.read_inventory(self.write_inventory([row("DXY", "USD_INDEX"), row("XAGUSD", "SILVER")]))
        decision, detail = scan.readiness_decision(rows, scan.load_config(self.root))
        self.assertTrue(decision.startswith("PARTIAL_"))
        self.assertIn("US_RATES", detail["missing_required_categories"])

    def test_local_scan_excludes_archive_and_symlink(self):
        (self.root / "data").mkdir()
        good = self.root / "data" / "DXY_H1.csv"; good.write_text("x")
        archived = self.root / "data" / "_archive"; archived.mkdir(); (archived / "US10Y.csv").write_text("x")
        link = self.root / "data" / "XAG_LINK.csv"; link.symlink_to(good)
        rows = scan.scan_local_files(self.root)
        paths = [r["path"] for r in rows]
        self.assertIn(str(good), paths)
        self.assertNotIn(str(archived / "US10Y.csv"), paths)
        self.assertNotIn(str(link), paths)

    def test_static_check_has_no_execution_tokens(self):
        self.assertEqual(scan.static_no_execution_check(self.root), [])

    def test_mql_uses_atomic_snapshot_publish_contract(self):
        text = (self.root / "mt5" / "XAUUSD_CrossAssetInventory.mq5").read_text()
        for token in ("UniqueInventoryPath", "FileFlush(handle)", "FileMove(snapshot_path,0,canonical_path,FILE_REWRITE)", "VALID_SNAPSHOT_FALLBACK"):
            self.assertIn(token, text)

    def test_invalid_header_only_diagnostic_contains_raw_probe(self):
        path = self.write_inventory([])
        cfg = scan.load_config(self.root)
        with self.assertRaises(scan.ReadinessError) as ctx:
            scan.select_valid_inventory(cfg)
        self.assertIn("no valid MT5 inventory CSV", str(ctx.exception))
        probe = scan.inventory_file_probe(path)
        self.assertGreater(probe["size"], 0)
        self.assertGreaterEqual(probe["line_count"], 1)
        self.assertEqual(len(probe["sha256"]), 64)

    def test_mql_uses_record_writer_and_self_validation(self):
        text = (self.root / "mt5" / "XAUUSD_CrossAssetInventory.mq5").read_text()
        for token in (
            "FILE_WRITE|FILE_CSV|FILE_ANSI",
            "uint row_bytes=FileWrite(handle",
            "CountValidatedRows(snapshot_path)",
            "FAIL_SNAPSHOT_SELF_VALIDATION",
            "validated=",
        ):
            self.assertIn(token, text)
        self.assertNotIn("FileWriteString(handle", text)

    def test_collect_creates_manifested_zip_and_selection_report(self):
        inventory = self.write_inventory([row("DXY", "USD_INDEX"), row("US10Y", "US_RATES"), row("XAGUSD", "SILVER")])
        with patch.object(scan.Path, "home", return_value=self.root):
            result = scan.collect(self.root, str(inventory))
        output = Path(result["results_zip"])
        self.assertTrue(output.is_file())
        with zipfile.ZipFile(output) as archive:
            self.assertIn("RESULTS_MANIFEST.json", archive.namelist())
            self.assertIn("mt5_inventory_selection.json", archive.namelist())
            summary = json.loads(archive.read("cross_asset_readiness_summary.json"))
            self.assertFalse(summary["live_order_allowed"])


if __name__ == "__main__":
    unittest.main()
