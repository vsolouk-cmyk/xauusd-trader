#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def make_dataset(path: Path) -> None:
    dates = pd.bdate_range("2011-01-03", periods=1800)
    rows = []
    price = 1000.0
    for i, d in enumerate(dates):
        # Create a synthetic series that rises after residual pullback/flow conditions.
        if 650 <= i < 900 or 1250 <= i < 1500:
            price *= 1.0018
        elif i % 37 == 0:
            price *= 0.98
        else:
            price *= 1.0002
        dxy = 100 + 3 * math.sin(i / 40.0) + (i / 1800.0)
        ry = 1.0 + 0.4 * math.sin(i / 70.0)
        vix = 18 + 5 * math.sin(i / 25.0)
        etf = 20 * math.sin(i / 55.0) + (25 if (i % 200) > 80 else -10)
        cb = 15 * math.sin(i / 85.0) + (20 if (i % 260) > 130 else -5)
        rows.append({
            "feature_date_utc": d.date().isoformat(),
            "gold_close": price,
            "dxy": dxy,
            "real_yield": ry,
            "vix": vix,
            "etf_flow_tonnes_3m": etf,
            "central_bank_demand_tonnes_3m": cb,
        })
    pd.DataFrame(rows).to_csv(path, index=False)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "configs").mkdir()
        (root / "data/macro_regime/normalized").mkdir(parents=True)
        shutil.copyfile(Path(__file__).parents[1] / "app/stage89_residual_regime_thesis_discovery.py", root / "app/stage89_residual_regime_thesis_discovery.py")
        shutil.copyfile(Path(__file__).parents[1] / "configs/stage89_residual_regime_thesis_discovery.json", root / "configs/stage89_residual_regime_thesis_discovery.json")
        make_dataset(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
        result = subprocess.run([
            sys.executable,
            str(root / "app/stage89_residual_regime_thesis_discovery.py"),
            "--root", str(root),
            "--config", str(root / "configs/stage89_residual_regime_thesis_discovery.json"),
            "--out", str(root / "reports/stage89"),
        ], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr + result.stdout
        summary_path = root / "reports/stage89/stage89_residual_regime_thesis_discovery_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert summary["status"] == "STAGE89_COMPLETE_NO_PROMOTION"
        assert "NO_ORDER_AUTHORIZATION_FROM_STAGE89" in summary["hard_blocks"]
        assert (root / "reports/stage89/stage89_residual_candidate_metrics.csv").exists()
        assert (root / "reports/stage89/stage89_residual_discovery_shortlist.csv").exists()
    print("Stage89 tests passed")


if __name__ == "__main__":
    main()
