from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "stage66j3_direct_readiness_after_refresh.py"
spec = importlib.util.spec_from_file_location("stage66j3", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore[union-attr]


def write_macro(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "feature_date_utc", "gold_sma20_over_50", "gold_sma50_over_200",
        "dxy_ret_20d", "dxy_sma20_over_50", "real_yield_change_20d",
        "vix_change_20d", "etf_flow_tonnes_3m", "central_bank_demand_tonnes_3m",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerow({
            "feature_date_utc": "2026-06-26",
            "gold_sma20_over_50": "-0.05",
            "gold_sma50_over_200": "-0.007",
            "dxy_ret_20d": "0.02",
            "dxy_sma20_over_50": "0.009",
            "real_yield_change_20d": "0.16",
            "vix_change_20d": "2.0",
            "etf_flow_tonnes_3m": "10.0",
            "central_bank_demand_tonnes_3m": "",
        })


def test_wait_all_inactive_nonfatal():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        macro = root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        write_macro(macro)
        cfg = root / "configs/stage66j3_direct_readiness_after_refresh.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"macro_dataset": str(macro.relative_to(root))}), encoding="utf-8")
        out = root / "reports/stage66j3_direct_readiness_after_refresh"
        summary = mod.run(root, cfg, out)
        assert summary["status"] == "STAGE66J3_COMPLETE_NO_PROMOTION"
        assert summary["decision"] == "STAGE66J3_DIRECT_READINESS_WAIT_SIGNALS_NO_ORDER"
        assert summary["rule_results"]["d3_h60"]["signal_active"] is False
        assert summary["rule_results"]["d1_backup"]["signal_active"] is False
        assert (out / "stage66j3_direct_readiness_after_refresh_summary.json").exists()
        assert (root / "data/forward_shadow/stage66j3_direct_readiness_after_refresh_ledger.csv").exists()


if __name__ == "__main__":
    test_wait_all_inactive_nonfatal()
    print("Stage66J3 tests passed")
