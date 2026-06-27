#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path


def write_macro(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "feature_date_utc", "gold_close", "gold_sma20_over_50", "gold_sma50_over_200",
        "dxy_ret_20d", "dxy_sma20_over_50", "real_yield_change_20d", "vix_change_20d",
        "etf_flow_tonnes_3m", "central_bank_demand_tonnes_3m",
    ]
    start = date(2020, 1, 1)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i in range(260):
            d = start + timedelta(days=i)
            active_block = 20 <= i < 95
            w.writerow({
                "feature_date_utc": d.isoformat(),
                "gold_close": 1500 + i,
                "gold_sma20_over_50": 1 if active_block else -1,
                "gold_sma50_over_200": 1 if active_block else -1,
                "dxy_ret_20d": -1 if active_block else 1,
                "dxy_sma20_over_50": -1 if active_block else 1,
                "real_yield_change_20d": -1 if active_block else 1,
                "vix_change_20d": 1 if active_block else -1,
                "etf_flow_tonnes_3m": 1 if active_block else -1,
                "central_bank_demand_tonnes_3m": 1 if active_block else -1,
            })


def main() -> int:
    repo_script = Path(__file__).resolve().parents[1] / "app" / "stage68c_return_incremental_value_audit.py"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        macro = root / "data" / "macro_regime" / "normalized" / "stage64k_full_scope_lag_safe_feature_dataset.csv"
        write_macro(macro)
        cfg = root / "configs" / "stage68c_return_incremental_value_audit.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({
            "macro_dataset_path": str(macro.relative_to(root)),
            "cost_bps_total": 10.0,
            "cluster_window_calendar_days": 60,
        }), encoding="utf-8")
        out = root / "reports" / "stage68c"
        subprocess.check_call([sys.executable, str(repo_script), "--root", str(root), "--config", str(cfg.relative_to(root)), "--out", str(out)])
        summary = json.loads((out / "stage68c_return_incremental_value_audit_summary.json").read_text())
        assert summary["status"] == "STAGE68C_COMPLETE_NO_PROMOTION"
        assert summary["rule_return_metrics"]["h64l_v2"]["entry_count"] >= 1
        assert (out / "stage68c_rule_entry_returns.csv").exists()
        assert (out / "stage68c_entry_clusters.csv").exists()
    print("Stage68C tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
