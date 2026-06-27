from pathlib import Path
import csv
import json
import shutil
import subprocess
import sys


def test_stage108_smoke(tmp_path: Path):
    root = tmp_path / "repo"
    if root.exists():
        shutil.rmtree(root)
    (root / "app").mkdir(parents=True)
    shutil.copy(Path(__file__).parents[1] / "app" / "stage108_unified_observer_second_order_expansion.py", root / "app" / "stage108_unified_observer_second_order_expansion.py")
    (root / "configs").mkdir()
    (root / "data/macro_regime/normalized").mkdir(parents=True)
    (root / "data/external_frontiers").mkdir(parents=True)
    (root / "reports/stage107_second_order_portfolio_increment_review").mkdir(parents=True)
    (root / "mt5files").mkdir()
    cfg = {
        "macro_dataset_path": "data/macro_regime/normalized/macro.csv",
        "cot_dataset_path": "data/external_frontiers/cot.csv",
        "stage107_summary_path": "reports/stage107_second_order_portfolio_increment_review/stage107_second_order_portfolio_increment_review_summary.json",
        "bridge_csv_path": "data/mt5_bridge/unified_observer_signal.csv",
        "mt5_files_dir": str(root / "mt5files"),
    }
    (root / "configs/stage108_unified_observer_second_order_expansion.json").write_text(json.dumps(cfg), encoding="utf-8")
    (root / "reports/stage107_second_order_portfolio_increment_review/stage107_second_order_portfolio_increment_review_summary.json").write_text(json.dumps({"decision":"OK","selected_rule_ids":["S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120"]}), encoding="utf-8")
    with (root / "data/macro_regime/normalized/macro.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date_utc","available_after_utc","gold_close","gold_sma20_over_50","dxy_ret_20d","real_yield_change_20d","vix_change_20d","dxy_sma20_over_50","real_yield_change_120d","dxy_ret_120d","gold_ret_20d","central_bank_demand_tonnes_3m"])
        w.writeheader()
        w.writerow({"date_utc":"2025-01-03","available_after_utc":"","gold_close":2000,"gold_sma20_over_50":1,"dxy_ret_20d":1,"real_yield_change_20d":-1,"vix_change_20d":1,"dxy_sma20_over_50":-1,"real_yield_change_120d":-1,"dxy_ret_120d":-1,"gold_ret_20d":-1,"central_bank_demand_tonnes_3m":10})
    with (root / "data/external_frontiers/cot.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["report_date_utc","available_after_utc","managed_money_net_pct_oi_z_156w","managed_money_net_pct_oi_change_4w"])
        w.writeheader()
        w.writerow({"report_date_utc":"2024-12-31","available_after_utc":"2025-01-02","managed_money_net_pct_oi_z_156w":0.5,"managed_money_net_pct_oi_change_4w":-0.2})
    cmd = [sys.executable, str(root / "app/stage108_unified_observer_second_order_expansion.py"), "--root", str(root), "--config", "configs/stage108_unified_observer_second_order_expansion.json", "--out", "reports/stage108_unified_observer_second_order_expansion", "--copy-to-mt5-files"]
    res = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    summary = json.loads((root / "reports/stage108_unified_observer_second_order_expansion/stage108_unified_observer_second_order_expansion_summary.json").read_text())
    assert summary["status"] == "STAGE108_COMPLETE_NO_PROMOTION"
    assert "S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120" in summary["expanded_unified_rule_ids"]
    assert summary["bridge_csv"]["written"] is True
    assert summary["csv_copy"]["status"] == "COPIED"
    csv_text = (root / "data/mt5_bridge/unified_observer_signal.csv").read_text()
    assert "S105_03_active" in csv_text
    assert "execution_allowed" in csv_text and "false" in csv_text


if __name__ == "__main__":
    test_stage108_smoke(Path("/tmp/stage108_smoke_test"))
    print("Stage108 tests passed")



def test_stage108_derives_missing_legacy_macro_features(tmp_path: Path):
    root = tmp_path / "repo2"
    if root.exists():
        shutil.rmtree(root)
    (root / "app").mkdir(parents=True)
    shutil.copy(Path(__file__).parents[1] / "app" / "stage108_unified_observer_second_order_expansion.py", root / "app" / "stage108_unified_observer_second_order_expansion.py")
    (root / "configs").mkdir()
    (root / "data/macro_regime/normalized").mkdir(parents=True)
    (root / "data/external_frontiers").mkdir(parents=True)
    (root / "reports/stage107_second_order_portfolio_increment_review").mkdir(parents=True)
    cfg = {
        "macro_dataset_path": "data/macro_regime/normalized/macro.csv",
        "cot_dataset_path": "data/external_frontiers/cot.csv",
        "stage107_summary_path": "reports/stage107_second_order_portfolio_increment_review/stage107_second_order_portfolio_increment_review_summary.json",
        "bridge_csv_path": "data/mt5_bridge/unified_observer_signal.csv",
        "mt5_files_dir": "",
    }
    (root / "configs/stage108_unified_observer_second_order_expansion.json").write_text(json.dumps(cfg), encoding="utf-8")
    (root / "reports/stage107_second_order_portfolio_increment_review/stage107_second_order_portfolio_increment_review_summary.json").write_text(json.dumps({"decision":"OK","selected_rule_ids":["S105_03_COT_DECROWDING_CB_SUPPORT_RY_RELIEF_H120"]}), encoding="utf-8")
    with (root / "data/macro_regime/normalized/macro.csv").open("w", newline="", encoding="utf-8") as f:
        fields=["date_utc","gold_close","dxy_close","real_yield","vix_close","central_bank_demand_tonnes_3m"]
        w=csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i in range(140):
            w.writerow({
                "date_utc": f"2025-01-{(i%28)+1:02d}" if i < 28 else f"2025-{(i//28)+1:02d}-{(i%28)+1:02d}",
                "gold_close": 2000 - i,
                "dxy_close": 100 + i * 0.01,
                "real_yield": 1.5 + i * 0.001,
                "vix_close": 15 + i * 0.01,
                "central_bank_demand_tonnes_3m": -10,
            })
    # rewrite with actual monotonic dates to avoid month formatting edge cases
    import datetime as _dt
    with (root / "data/macro_regime/normalized/macro.csv").open("w", newline="", encoding="utf-8") as f:
        fields=["date_utc","gold_close","dxy_close","real_yield","vix_close","central_bank_demand_tonnes_3m"]
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
        start=_dt.date(2025,1,1)
        for i in range(140):
            w.writerow({"date_utc": (start+_dt.timedelta(days=i)).isoformat(), "gold_close": 2000-i, "dxy_close": 100+i*0.01, "real_yield": 1.5+i*0.001, "vix_close": 15+i*0.01, "central_bank_demand_tonnes_3m": -10})
    with (root / "data/external_frontiers/cot.csv").open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["report_date_utc","available_after_utc","managed_money_net_pct_oi_z_156w","managed_money_net_pct_oi_change_4w"])
        w.writeheader()
        w.writerow({"report_date_utc":"2025-05-10","available_after_utc":"2025-05-11","managed_money_net_pct_oi_z_156w":0.5,"managed_money_net_pct_oi_change_4w":-0.2})
    cmd=[sys.executable, str(root / "app/stage108_unified_observer_second_order_expansion.py"), "--root", str(root), "--config", "configs/stage108_unified_observer_second_order_expansion.json", "--out", "reports/stage108_unified_observer_second_order_expansion"]
    res=subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    summary=json.loads((root / "reports/stage108_unified_observer_second_order_expansion/stage108_unified_observer_second_order_expansion_summary.json").read_text())
    by_id={r["rule_id"]: r for r in summary["rule_results"]}
    assert "real_yield_change_120d" not in by_id["S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120"]["missing_columns"]
    assert "dxy_ret_120d" not in by_id["S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120"]["missing_columns"]
    assert "gold_ret_20d" not in by_id["C96_07_CB_SUPPORT_NOT_CROWDED_H120"]["missing_columns"]
