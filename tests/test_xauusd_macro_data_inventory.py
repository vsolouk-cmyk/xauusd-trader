from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "xauusd_macro_data_inventory.py"
SPEC = importlib.util.spec_from_file_location("macro_inventory", MODULE_PATH)
inv = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(inv)


class MacroInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "inbox").mkdir()
        (self.root / "config").mkdir()
        self.config = self.root / "config" / "inventory.json"
        self.config.write_text(json.dumps({
            "search_roots": ["inbox"],
            "max_files_per_root": 500,
            "max_file_size_bytes": 20_000_000,
        }))

    def tearDown(self):
        self.temp.cleanup()

    def write_csv(self, name: str, header: str, rows: str = "2024-01-01,1\n") -> Path:
        path = self.root / "inbox" / name
        path.write_text(header + "\n" + rows)
        return path

    def populate_core(self):
        self.write_csv("DTWEXBGS.csv", "DATE,DTWEXBGS")
        self.write_csv("DFII10.csv", "DATE,DFII10")
        self.write_csv("DGS10.csv", "DATE,DGS10")
        self.write_csv("T10YIE.csv", "DATE,T10YIE")
        self.write_csv("VIX_History.csv", "DATE,VIX")
        self.write_csv("GVZ_History.csv", "DATE,GVZ")
        self.write_csv(
            "fut_disagg_2024.csv",
            "Market_and_Exchange_Names,Report_Date_as_YYYY-MM-DD,Prod_Merc_Positions_Long_All",
            "GOLD - COMMODITY EXCHANGE INC.,2024-01-02,100\n",
        )
        self.write_csv(
            "official_event_calendar.csv",
            "event_time_utc,source,category,title",
            "2024-01-01T13:30:00Z,BLS,BLS_CPI,CPI\n",
        )

    def test_resolution_invariant_series_classification(self):
        path = self.write_csv("DTWEXBGS.csv", "DATE,DTWEXBGS")
        summary = inv.summarize_file(path)
        classes = {x["series"]: x for x in inv.classify(path, summary)}
        self.assertIn("usd_broad_daily", classes)
        self.assertGreaterEqual(classes["usd_broad_daily"]["confidence"], 0.5)

    def test_cftc_gold_classification(self):
        path = self.write_csv(
            "fut_disagg_xls_2024.csv",
            "Market_and_Exchange_Names,Report_Date_as_YYYY-MM-DD",
            "GOLD - COMMODITY EXCHANGE INC.,2024-01-02\n",
        )
        classes = {x["series"] for x in inv.classify(path, inv.summarize_file(path))}
        self.assertIn("cftc_gold_weekly", classes)

    def test_official_event_calendar_classification(self):
        path = self.write_csv(
            "official_event_calendar.csv",
            "event_time_utc,source,category,title",
            "2024-01-01T13:30:00Z,FED,FOMC,FOMC\n",
        )
        classes = {x["series"] for x in inv.classify(path, inv.summarize_file(path))}
        self.assertIn("official_event_calendar", classes)

    def test_sqlite_schema_is_inspected_read_only(self):
        path = self.root / "inbox" / "macro.sqlite"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE macro(date TEXT, DFII10 REAL)")
        conn.execute("INSERT INTO macro VALUES('2024-01-01', 1.2)")
        conn.commit()
        conn.close()
        summary = inv.summarize_file(path)
        self.assertEqual(summary["kind"], "sqlite")
        self.assertEqual(summary["tables"]["macro"]["row_count"], 1)
        self.assertEqual(summary["tables"]["macro"]["date_ranges"]["date"]["min"], "2024-01-01")

    def test_xlsx_sheet_and_content_are_inspected(self):
        from openpyxl import Workbook
        path = self.root / "inbox" / "wgc_gold_demand.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Gold Demand Trends"
        ws.append(["Quarter", "Central banks"])
        ws.append(["2024Q1", 100])
        wb.save(path)
        summary = inv.summarize_file(path)
        classes = {x["series"] for x in inv.classify(path, summary)}
        self.assertIn("wgc_quarterly_demand", classes)

    def test_complete_core_returns_ready(self):
        self.populate_core()
        out = self.root / "out"
        result = inv.run_inventory(self.root, self.config, out)
        self.assertTrue(result["pass"])
        self.assertEqual(result["required_missing"], [])
        self.assertEqual(result["decision"], "PASS_CORE_MACRO_DATA_READY_FOR_CAUSAL_PANEL_BUILD")

    def test_missing_core_is_explicit(self):
        self.write_csv("DFII10.csv", "DATE,DFII10")
        result = inv.run_inventory(self.root, self.config, self.root / "out")
        self.assertFalse(result["pass"])
        self.assertIn("usd_broad_daily", result["required_missing"])
        self.assertEqual(result["decision"], "PARTIAL_CORE_MACRO_DATA_REQUIRES_DOWNLOADS")

    def test_symlink_is_not_followed(self):
        outside = self.root / "outside.csv"
        outside.write_text("DATE,DTWEXBGS\n2024-01-01,100\n")
        link = self.root / "inbox" / "linked.csv"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlink unavailable")
        result = inv.run_inventory(self.root, self.config, self.root / "out")
        self.assertIn("usd_broad_daily", result["required_missing"])

    def test_collect_packages_only_current_outputs(self):
        self.populate_core()
        out = self.root / "out"
        inv.run_inventory(self.root, self.config, out)
        extra = out / "stale.txt"
        extra.write_text("stale")
        package = inv.collect(self.root, out, self.root / "downloads")
        with zipfile.ZipFile(package) as zf:
            names = set(zf.namelist())
        self.assertNotIn("reports/stale.txt", names)
        self.assertIn("reports/macro_data_readiness_summary.json", names)
        self.assertIn("RESULTS_MANIFEST.json", names)

    def test_results_manifest_hashes_match(self):
        self.populate_core()
        out = self.root / "out"
        inv.run_inventory(self.root, self.config, out)
        package = inv.collect(self.root, out, self.root / "downloads")
        import hashlib
        with zipfile.ZipFile(package) as zf:
            manifest = json.loads(zf.read("RESULTS_MANIFEST.json"))
            for item in manifest["files"]:
                data = zf.read(item["archive_path"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
                self.assertEqual(len(data), item["size"])

    def test_source_has_no_network_or_execution_modules(self):
        text = MODULE_PATH.read_text()
        forbidden = [
            "MetaTrader5", "OrderSend", "WebRequest", "requests.",
            "urllib.request", "subprocess.", "socket.", "demo_order_allowed\": true",
            "live_order_allowed\": true",
        ]
        for token in forbidden:
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
