#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("stage95", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_stage95_synthetic_cftc_zip() -> None:
    pkg = Path(__file__).resolve().parents[1]
    mod = load_module(pkg / "app" / "stage95_cot_official_dataset_builder.py")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        raw = root / "data" / "external_frontiers" / "raw_cot"
        raw.mkdir(parents=True)
        zip_path = raw / "com_disagg_txt_2025.zip"
        rows = []
        for i in range(180):
            year = 2021 + i // 52
            week = i % 52 + 1
            # weekly dates are synthetic but parseable
            month = min(12, (week - 1) // 4 + 1)
            day = min(28, ((week - 1) % 4) * 7 + 1)
            rows.append({
                "Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.",
                "Report_Date_as_YYYY-MM-DD": f"{year:04d}-{month:02d}-{day:02d}",
                "CFTC_Contract_Market_Code": "088691",
                "Open_Interest_All": str(300000 + i),
                "M_Money_Positions_Long_All": str(120000 + i * 10),
                "M_Money_Positions_Short_All": str(70000 + i * 5),
                "M_Money_Positions_Spread_All": str(10000),
            })
        csv_buf = []
        header = list(rows[0].keys())
        import io
        sio = io.StringIO()
        writer = csv.DictWriter(sio, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("annual.txt", sio.getvalue())
        cfg = {
            "download_official_cftc": False,
            "download_dir": "data/external_frontiers/raw_cot/cftc",
            "input_globs": ["data/external_frontiers/raw_cot/*.zip"],
            "output_csv": "data/external_frontiers/cot_positioning_normalized.csv",
            "minimum_ready_rows": 100,
            "minimum_zscore_non_null": 20,
            "rolling_z_window_reports": 52,
            "rolling_z_min_periods": 20,
            "cot_release_lag_calendar_days": 3,
            "cot_release_utc_hour": 22,
            "cot_release_utc_minute": 0,
        }
        cfg_path = root / "cfg.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        out = root / "reports" / "stage95"
        rc = mod.main(["--root", str(root), "--config", str(cfg_path), "--out", str(out), "--no-download"])
        assert rc == 0
        summary = json.loads((out / "stage95_cot_official_dataset_builder_summary.json").read_text())
        assert summary["decision"] == "STAGE95_COT_DATASET_READY_FOR_STAGE96_THESIS_DISCOVERY_NO_ORDER"
        assert summary["cot_dataset"]["normalized_rows"] >= 100
        normalized = root / "data" / "external_frontiers" / "cot_positioning_normalized.csv"
        assert normalized.exists()
        text = normalized.read_text()
        assert "managed_money_net_pct_oi" in text
        assert "088691" in text


if __name__ == "__main__":
    test_stage95_synthetic_cftc_zip()
    print("Stage95 tests passed")
