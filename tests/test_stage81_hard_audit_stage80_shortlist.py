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


def make_macro(path: Path) -> None:
    dates = pd.bdate_range("2011-01-03", "2026-06-26", tz="UTC")
    n = len(dates)
    rows = []
    for i, d in enumerate(dates):
        # Smooth upward gold with cyclical macro features to create some triggers.
        gold = 1200 + i * 0.75 + 80 * math.sin(i / 90.0)
        dxy = 100 + 2 * math.sin(i / 60.0) - i * 0.0005
        real_yield = 1.5 + 0.3 * math.sin(i / 70.0)
        vix = 18 + 4 * math.sin(i / 30.0)
        etf = 10 * math.sin(i / 100.0)
        cb = 20 * math.cos(i / 130.0)
        rows.append({
            "feature_date_utc": d.date().isoformat(),
            "gold_close": gold,
            "dxy": dxy,
            "real_yield": real_yield,
            "vix": vix,
            "etf_flow_tonnes_3m": etf,
            "central_bank_demand_tonnes_3m": cb,
        })
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        root = tmp
        for d in ["app", "configs", "docs", "tests"]:
            (root / d).mkdir(parents=True, exist_ok=True)
        src_root = Path(__file__).resolve().parents[1]
        shutil.copy(src_root / "app" / "stage81_hard_audit_stage80_shortlist.py", root / "app")
        shutil.copy(src_root / "configs" / "stage81_hard_audit_stage80_shortlist.json", root / "configs")

        make_macro(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")

        rep = root / "reports/stage80_structured_thesis_discovery_expansion"
        rep.mkdir(parents=True, exist_ok=True)
        (rep / "stage80_structured_thesis_discovery_expansion_summary.json").write_text(json.dumps({
            "decision": "NEW_DISCOVERY_SHORTLIST_READY_FOR_HARD_AUDIT_NO_ORDER"
        }), encoding="utf-8")
        pd.DataFrame([
            {
                "rule_id": "S80_TEST_A",
                "label": "TEST_A",
                "bucket": "test",
                "horizon_trading_days": 120,
                "cooldown_trading_days": 120,
                "condition_text": "gold_ret_60d>0.0 AND dxy_ret_60d<0.0",
                "max_overlap_with_stage77b_selected_pct": 10.0,
            },
            {
                "rule_id": "S80_TEST_B",
                "label": "TEST_B",
                "bucket": "test",
                "horizon_trading_days": 60,
                "cooldown_trading_days": 60,
                "condition_text": "real_yield_change_60d<0.0 AND etf_flow_tonnes_3m>0.0",
                "max_overlap_with_stage77b_selected_pct": 10.0,
            },
        ]).to_csv(rep / "stage80_discovery_shortlist.csv", index=False)

        result = subprocess.run(
            [
                sys.executable,
                str(root / "app/stage81_hard_audit_stage80_shortlist.py"),
                "--root", str(root),
                "--config", "configs/stage81_hard_audit_stage80_shortlist.json",
                "--out", "reports/stage81_hard_audit_stage80_shortlist",
            ],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        summary = json.loads((root / "reports/stage81_hard_audit_stage80_shortlist/stage81_hard_audit_stage80_shortlist_summary.json").read_text())
        assert summary["status"] == "STAGE81_COMPLETE_NO_PROMOTION"
        assert summary["candidate_count"] == 2
        assert "NO_ORDER_AUTHORIZATION_FROM_STAGE81" in summary["hard_blocks"]
        assert (root / "reports/stage81_hard_audit_stage80_shortlist/stage81_hard_audit_metrics.csv").exists()
        assert (root / "reports/stage81_hard_audit_stage80_shortlist/stage81_selected_for_stage82.csv").exists()
        print("Stage81 tests passed")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
