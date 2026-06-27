#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def read_kv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return {row["key"]: row["value"] for row in csv.DictReader(f)}


def test_stage99_builds_six_rule_unified_observer():
    pkg_root = Path(__file__).resolve().parents[1]
    script = pkg_root / "app" / "stage99_unified_observer_cot_expansion.py"
    cfg_src = pkg_root / "configs" / "stage99_unified_observer_cot_expansion.json"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg = json.loads(cfg_src.read_text(encoding="utf-8"))
        cfg["mt5_files_dir"] = str(root / "mt5_files")
        cfg_path = root / "configs" / "stage99_unified_observer_cot_expansion.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

        stage98_path = root / cfg["stage98_summary"]
        stage98_path.parent.mkdir(parents=True, exist_ok=True)
        stage98_path.write_text(json.dumps({
            "decision": "STAGE98_COT_INCREMENT_SELECTED_FOR_UNIFIED_OBSERVER_REVIEW_NO_ORDER",
            "disposition": "COT_INCREMENT_SELECTED_FOR_STAGE99_UNIFIED_OBSERVER_EXPANSION",
            "selected_rule_ids": ["C96_07_CB_SUPPORT_NOT_CROWDED_H120"],
        }), encoding="utf-8")

        dates = pd.date_range("2026-01-01", periods=160, freq="B", tz="UTC")
        macro_rows = []
        for i, d in enumerate(dates):
            macro_rows.append({
                "feature_date_utc": d.isoformat(),
                "gold_close": 3000 + i,
                "gold_sma20_over_50": -0.01 if i == len(dates)-1 else 0.01,
                "dxy_ret_20d": 0.01,
                "dxy_sma20_over_50": 0.01,
                "real_yield_change_20d": 0.10,
                "vix_change_20d": 1.0,
                "central_bank_demand_tonnes_3m": 10.0,
                "dxy": 100 + i * 0.01,
                "real_yield": 1.0 + i * 0.001,
                "vix": 15 + i * 0.01,
            })
        # Make the latest COT rule active: not crowded, CB support, gold pullback.
        macro_rows[-1]["gold_close"] = macro_rows[-21]["gold_close"] * 0.98
        write_csv(root / cfg["macro_dataset"], macro_rows)

        cot_rows = []
        for i in range(30):
            report = pd.Timestamp("2025-07-01", tz="UTC") + pd.Timedelta(days=7*i)
            cot_rows.append({
                "report_date_utc": report.isoformat(),
                "available_after_utc": (report + pd.Timedelta(days=3)).isoformat(),
                "managed_money_net_pct_oi_z_156w": 0.5,
                "managed_money_net_pct_oi_change_4w": 0.1,
            })
        write_csv(root / cfg["cot_dataset"], cot_rows)

        out = root / "reports" / "stage99_unified_observer_cot_expansion"
        res = subprocess.run([
            sys.executable, str(script),
            "--root", str(root),
            "--config", str(cfg_path),
            "--out", str(out),
            "--copy-to-mt5-files",
        ], text=True, capture_output=True)
        assert res.returncode == 0, res.stderr + res.stdout
        summary = json.loads((out / "stage99_unified_observer_cot_expansion_summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "STAGE99_COMPLETE_NO_PROMOTION"
        assert "C96_07_CB_SUPPORT_NOT_CROWDED_H120" in summary["expanded_unified_rule_ids"]
        assert summary["bridge_csv"]["schema_version"] == "stage99_unified_observer_cot_v1"
        kv = read_kv(root / cfg["bridge_csv"])
        assert kv["rule_count"] == "6"
        assert "C96_07_rule_id" in kv
        assert kv["C96_07_active"] == "true"
        assert (root / "mt5_files" / "unified_observer_signal.csv").exists()


def test_ea_has_no_trading_tokens():
    pkg_root = Path(__file__).resolve().parents[1]
    ea = (pkg_root / "mt5" / "Unified_ObserverOnly_EA.mq5").read_text(encoding="utf-8")
    forbidden = ["OrderSend", "CTrade", ".Buy(", ".Sell(", "PositionOpen", "TRADE_ACTION_DEAL"]
    for token in forbidden:
        assert token not in ea, token


if __name__ == "__main__":
    test_stage99_builds_six_rule_unified_observer()
    test_ea_has_no_trading_tokens()
    print("Stage99 tests passed")
