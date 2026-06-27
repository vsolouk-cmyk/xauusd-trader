#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


def build_synthetic_macro(path: Path) -> None:
    dates = pd.bdate_range("2011-01-03", periods=900)
    t = np.arange(len(dates), dtype=float)
    gold = 1200 + t * 0.55 + 35 * np.sin(t / 35)
    dxy = 100 - t * 0.01 + 2.0 * np.sin(t / 45)
    real_yield = 1.2 - t * 0.0008 + 0.25 * np.cos(t / 50)
    vix = 18 + 4 * np.sin(t / 25)
    etf = 10 * np.sin(t / 40) + 2
    cb = 15 * np.cos(t / 60) + 5
    df = pd.DataFrame({
        "feature_date_utc": dates.strftime("%Y-%m-%d"),
        "metadata_source": ["synthetic"] * len(dates),
        "gold_close": gold,
        "dxy": dxy,
        "real_yield": real_yield,
        "vix": vix,
        "etf_flow_tonnes_3m": etf,
        "central_bank_demand_tonnes_3m": cb,
    })
    df.to_csv(path, index=False)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "configs").mkdir()
        (root / "data/macro_regime/normalized").mkdir(parents=True)
        # Copy app from installed repo location.
        src = Path(__file__).resolve().parents[1] / "app" / "stage80_structured_thesis_discovery_expansion.py"
        dst = root / "app" / src.name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        macro = root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        build_synthetic_macro(macro)
        cfg = {
            "macro_path": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
            "date_col": "feature_date_utc",
            "price_col": "gold_close",
            "max_shortlist_size": 5,
            "max_overlap_with_stage77b_selected_pct": 100.0,
            "constraints": {
                "min_total_entries": 1,
                "min_total_mean_net_bps": -9999.0,
                "min_total_win_rate": 0.0,
                "min_locked_forward_entries": 0,
                "min_locked_forward_mean_bps": -9999.0,
                "min_final_holdout_entries": 0,
                "min_final_holdout_mean_bps": -9999.0,
                "min_post_plus_final_entries": 0,
                "min_post_plus_final_mean_bps": -9999.0,
                "max_abs_worst_loss_bps": 99999.0,
                "max_missing_required_feature_rows": 100,
                "max_lookahead_violations": 0,
            },
        }
        (root / "configs/stage80_structured_thesis_discovery_expansion.json").write_text(json.dumps(cfg), encoding="utf-8")
        result = subprocess.run([
            sys.executable,
            str(dst),
            "--root", str(root),
            "--config", "configs/stage80_structured_thesis_discovery_expansion.json",
            "--out", "reports/stage80_structured_thesis_discovery_expansion",
        ], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr + result.stdout
        out = root / "reports/stage80_structured_thesis_discovery_expansion"
        summary_path = out / "stage80_structured_thesis_discovery_expansion_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["status"] == "STAGE80_COMPLETE_NO_PROMOTION"
        assert "NO_ORDER_AUTHORIZATION_FROM_STAGE80" in summary["hard_blocks"]
        assert (out / "stage80_discovery_candidate_metrics.csv").exists()
        assert (out / "stage80_discovery_shortlist.csv").exists()
    print("Stage80 tests passed")


if __name__ == "__main__":
    main()
