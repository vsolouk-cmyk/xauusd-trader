#!/usr/bin/env python3
import csv
import json
import tempfile
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "stage68b_overlap_incremental_frequency_audit.py"

spec = importlib.util.spec_from_file_location("stage68b", APP)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

def test_smoke():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        macro = root / "data/macro_regime/normalized"
        macro.mkdir(parents=True)
        path = macro / "stage64k_full_scope_lag_safe_feature_dataset.csv"
        rows = [
            ["feature_date_utc","gold_sma20_over_50","gold_sma50_over_200","dxy_ret_20d","dxy_sma20_over_50","real_yield_change_20d","vix_change_20d","etf_flow_tonnes_3m","central_bank_demand_tonnes_3m"],
            ["2020-01-01","1","1","-1","-1","-1","1","1","1"],
            ["2020-01-02","1","1","-1","-1","-1","1","1","1"],
            ["2020-01-03","-1","1","-1","-1","-1","1","1","1"],
            ["2020-01-04","1","1","1","-1","-1","1","1","1"],
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerows(rows)
        out = root / "reports/stage68b"
        summary = mod.audit(root, {}, out)
        assert summary["status"] == "STAGE68B_COMPLETE_NO_PROMOTION"
        assert summary["combined_metrics"]["any_all_rules"]["active_days"] >= 2
        assert (out / "stage68b_pairwise_active_day_overlap.csv").exists()
        assert (out / "stage68b_overlap_incremental_frequency_audit_summary.json").exists()

if __name__ == "__main__":
    test_smoke()
    print("Stage68B tests passed")
