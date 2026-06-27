#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import shutil
import tempfile
from pathlib import Path

SRC_XLSX = Path("/mnt/data/Changes_latest_as_of_Jun2026_IFS.xlsx")
SCRIPT = Path(__file__).resolve().parents[1] / "app" / "stage67e_central_bank_changes_mapper.py"

spec = importlib.util.spec_from_file_location("stage67e", SCRIPT)
stage67e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage67e)  # type: ignore


def test_parse_uploaded_workbook_if_available():
    if not SRC_XLSX.exists():
        print("uploaded WGC changes workbook not available in this environment; parser import smoke passed")
        return
    monthly, info = stage67e.parse_monthly_changes_xlsx(SRC_XLSX, {})
    assert info["status"] == "PASS"
    assert info["selected_sheet"] == "Monthly"
    assert info["month_column_count"] >= 250
    assert info["country_row_count"] >= 100
    assert info["min_month_start"] == "2002-01-01"
    assert info["max_month_start"] >= "2026-04-01"
    assert monthly[-1]["central_bank_demand_tonnes_3m"] is not None
    assert abs(float(monthly[-1]["central_bank_demand_tonnes_3m"])) > 0


def test_macro_update_with_synthetic_macro():
    if not SRC_XLSX.exists():
        print("uploaded WGC changes workbook not available; skipping synthetic macro update")
        return
    monthly, _info = stage67e.parse_monthly_changes_xlsx(SRC_XLSX, {})
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        macro = root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        macro.parent.mkdir(parents=True, exist_ok=True)
        with macro.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["feature_date_utc", "gold_close", "central_bank_demand_tonnes_3m"])
            w.writeheader()
            w.writerow({"feature_date_utc": "2026-03-31", "gold_close": "3000", "central_bank_demand_tonnes_3m": ""})
            w.writerow({"feature_date_utc": "2026-04-30", "gold_close": "3100", "central_bank_demand_tonnes_3m": ""})
        result = stage67e.update_macro_dataset(root, monthly, {})
        assert result["status"] == "PASS"
        assert result["coverage_rows"] == 2
        rows = list(csv.DictReader(macro.open("r", encoding="utf-8")))
        assert rows[-1]["central_bank_demand_tonnes_3m"] not in ("", None)


if __name__ == "__main__":
    test_parse_uploaded_workbook_if_available()
    test_macro_update_with_synthetic_macro()
    print("Stage67E tests passed")
