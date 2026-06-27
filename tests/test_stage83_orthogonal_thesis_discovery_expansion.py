#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def make_synthetic_macro(path: Path) -> None:
    dates = pd.bdate_range("2011-01-03", periods=900, tz="UTC")
    rows = []
    gold = 1400.0
    dxy = 100.0
    ry = 1.0
    vix = 18.0
    for i, d in enumerate(dates):
        # deterministic waves, enough to exercise all feature builders
        gold *= 1.0 + (0.001 if (i // 40) % 2 == 0 else -0.0004)
        dxy *= 1.0 + (-0.0005 if (i // 55) % 2 == 0 else 0.0006)
        ry += -0.004 if (i // 70) % 2 == 0 else 0.005
        vix += 0.03 if (i // 30) % 2 == 0 else -0.02
        rows.append({
            "feature_date_utc": d.date().isoformat(),
            "gold_close": gold,
            "dxy": dxy,
            "real_yield": ry,
            "vix": vix,
            "etf_flow_tonnes_3m": 50.0 if i % 3 else -10.0,
            "central_bank_demand_tonnes_3m": 40.0 if i % 4 else -20.0,
        })
    pd.DataFrame(rows).to_csv(path, index=False)


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app").mkdir()
        (root / "configs").mkdir()
        (root / "data/macro_regime/normalized").mkdir(parents=True)
        src_app = Path(__file__).resolve().parents[1] / "app" / "stage83_orthogonal_thesis_discovery_expansion.py"
        src_cfg = Path(__file__).resolve().parents[1] / "configs" / "stage83_orthogonal_thesis_discovery_expansion.json"
        (root / "app/stage83_orthogonal_thesis_discovery_expansion.py").write_text(src_app.read_text(encoding="utf-8"), encoding="utf-8")
        cfg = json.loads(src_cfg.read_text(encoding="utf-8"))
        cfg["macro_dataset_path"] = "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        (root / "configs/stage83_orthogonal_thesis_discovery_expansion.json").write_text(json.dumps(cfg), encoding="utf-8")
        make_synthetic_macro(root / cfg["macro_dataset_path"])

        cmd = [
            sys.executable,
            str(root / "app/stage83_orthogonal_thesis_discovery_expansion.py"),
            "--root", str(root),
            "--config", "configs/stage83_orthogonal_thesis_discovery_expansion.json",
            "--out", "reports/stage83_orthogonal_thesis_discovery_expansion",
        ]
        result = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
        assert result.returncode == 0, result.stderr + result.stdout

        out = root / "reports/stage83_orthogonal_thesis_discovery_expansion"
        summary = json.loads((out / "stage83_orthogonal_thesis_discovery_expansion_summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "STAGE83_COMPLETE_NO_PROMOTION"
        assert summary["candidate_count"] > 0
        assert (out / "stage83_orthogonal_discovery_candidate_metrics.csv").exists()
        assert (out / "stage83_orthogonal_discovery_shortlist.csv").exists()

    print("Stage83 tests passed")


if __name__ == "__main__":
    main()
