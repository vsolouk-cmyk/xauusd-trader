#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def build_synthetic(root: Path) -> None:
    (root / "data/macro_regime/normalized").mkdir(parents=True, exist_ok=True)
    (root / "data/external_frontiers").mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2012-01-03", "2026-06-26", tz="UTC")
    n = len(dates)
    # Upward-biased but cyclical gold series.
    gold = [1600.0]
    for i in range(1, n):
        shock = 0.00025 + (0.003 if (i % 260) > 170 else -0.001)
        gold.append(gold[-1] * (1 + shock))
    df = pd.DataFrame({
        "feature_date_utc": dates.strftime("%Y-%m-%d"),
        "gold_close": gold,
        "available_after_utc": dates.strftime("%Y-%m-%d"),
        "dxy": [100 + ((i % 180) - 90) * 0.01 for i in range(n)],
        "real_yield": [1.0 + ((i % 120) - 60) * 0.002 for i in range(n)],
        "vix": [18 + ((i % 50) - 25) * 0.05 for i in range(n)],
        "etf_flow_tonnes_3m": [10 if (i % 300) < 150 else -5 for i in range(n)],
        "central_bank_demand_tonnes_3m": [20 if (i % 400) < 260 else -10 for i in range(n)],
    })
    df["gold_sma20_over_50"] = pd.Series(gold).rolling(20).mean() / pd.Series(gold).rolling(50).mean() - 1
    df["dxy_ret_20d"] = pd.Series(df["dxy"]).pct_change(20)
    df["dxy_sma20_over_50"] = pd.Series(df["dxy"]).rolling(20).mean() / pd.Series(df["dxy"]).rolling(50).mean() - 1
    df["real_yield_change_20d"] = pd.Series(df["real_yield"]).diff(20)
    df["vix_change_20d"] = pd.Series(df["vix"]).diff(20)
    df.to_csv(root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv", index=False)

    weeks = pd.date_range("2012-01-03", "2026-01-01", freq="W-TUE", tz="UTC")
    rows = []
    for i, d in enumerate(weeks):
        oi = 200000 + (i % 40) * 1000
        cycle = ((i % 104) - 52) / 52
        net_pct = 0.15 * cycle
        net = net_pct * oi
        long = 90000 + max(net, 0)
        short = 90000 + max(-net, 0)
        rows.append({
            "report_date_utc": d.strftime("%Y-%m-%d"),
            "available_after_utc": (d + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
            "managed_money_long": long,
            "managed_money_short": short,
            "open_interest": oi,
            "managed_money_net_pct_oi": net_pct,
        })
    pd.DataFrame(rows).to_csv(root / "data/external_frontiers/cot_positioning_normalized.csv", index=False)

    cfg = json.loads((Path(__file__).resolve().parents[1] / "configs/stage96_cot_positioning_thesis_discovery.json").read_text())
    (root / "configs").mkdir(exist_ok=True)
    (root / "configs/stage96_cot_positioning_thesis_discovery.json").write_text(json.dumps(cfg), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        build_synthetic(root)
        app = Path(__file__).resolve().parents[1] / "app/stage96_cot_positioning_thesis_discovery.py"
        out = root / "reports/stage96"
        cmd = [
            sys.executable,
            str(app),
            "--root",
            str(root),
            "--config",
            "configs/stage96_cot_positioning_thesis_discovery.json",
            "--out",
            str(out),
        ]
        subprocess.run(cmd, check=True)
        summary_path = out / "stage96_cot_positioning_thesis_discovery_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert summary["status"] == "STAGE96_COMPLETE_NO_PROMOTION"
        assert summary["patch_version"] == "STAGE96D_COT_RULE_WARMUP_ACCOUNTING_FIX"
        assert summary["cot_dataset"]["normalized_rows"] > 300
        assert summary["lookahead_violations"] == 0
        assert summary["candidate_count"] == 8
        snapshot = pd.read_csv(out / "stage96_cot_joined_daily_snapshot.csv")
        assert "available_after_utc" in snapshot.columns
        metrics = pd.read_csv(out / "stage96_cot_candidate_metrics.csv")
        assert "warmup_missing_rows_ignored" in metrics.columns
        assert metrics["warmup_missing_rows_ignored"].max() >= 0
        # With Stage96D, expected COT/macro warm-up must not be counted as a hard missing DQ issue.
        assert metrics["missing_required_feature_rows"].max() == 0
        assert (out / "stage96_cot_candidate_metrics.csv").exists()
        assert (out / "stage96_cot_thesis_shortlist.csv").exists()
    print("Stage96 tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
