#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import tempfile
import csv
import json

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "app" / "stage67d6_download_format_aware_rebuild_macro.py"
spec = importlib.util.spec_from_file_location("stage67d6", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore

assert mod.parse_investing_date_month_first("06/12/2026").isoformat() == "2026-06-12"
assert mod.parse_fred_date("2026-06-12").isoformat() == "2026-06-12"
assert mod.excel_serial_to_date("46173").isoformat() == "2026-05-31"

with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "US Dollar Index Historical Data.csv"
    p.write_text('"Date","Price"\n"06/26/2026","101.34"\n"06/12/2026","99.75"\n', encoding="utf-8")
    parsed = mod.parse_investing_dxy(p)
    assert parsed["status"] == "PASS"
    assert parsed["max_date"] == "2026-06-26"
    assert parsed["min_date"] == "2026-06-12"

print("Stage67D6 tests passed")
