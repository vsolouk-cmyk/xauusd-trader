#!/usr/bin/env python3
from __future__ import annotations
import csv
import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import stage66k_complementary_backup_readiness_expansion as s66k


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_evaluate_signal_false_and_true():
    row = {"feature_date_utc": "2026-01-01", "sample_available_after_utc": "2026-01-02T00:00:00Z", "a": "1", "b": "-1"}
    conds = [{"field": "a", "operator": ">", "threshold": 0}, {"field": "b", "operator": "<", "threshold": 0}]
    out = s66k.evaluate_signal(row, "feature_date_utc", conds)
    assert out["signal_active"] is True
    out2 = s66k.evaluate_signal(row, "feature_date_utc", [{"field": "a", "operator": "<", "threshold": 0}])
    assert out2["signal_active"] is False


def test_audit_candidate_passes_for_stage66d_like_item():
    item = {
        "classification": "PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER",
        "diagnostics": {"lookahead_breaches": 0, "active_rows": 100, "closed_positions": 30, "skipped_overlap": 70},
        "position_stats": {
            "trade_count": 33,
            "mean_net_return_bps": 200,
            "win_rate": 0.60,
            "max_year_trade_share": 0.12,
            "payoff_ratio_win_mean_abs_loss_mean": 1.2,
            "min_net_return_bps": -1000,
            "sizing_band_stats": [{"band": "D_base", "max_drawdown_pct": -2.7}],
        },
    }
    thresholds = {
        "min_trade_count": 25,
        "min_mean_net_return_bps": 150,
        "min_win_rate": 0.58,
        "max_abs_base_drawdown_pct": 6,
        "max_year_trade_share": 0.2,
        "min_payoff_ratio": 1.05,
        "kill_if_single_trade_loss_bps_lt": -1800,
        "require_zero_lookahead_breaches": True,
    }
    out = s66k.audit_candidate(item, thresholds)
    assert out["all_gates_ok"] is True


def test_main_synthetic_wait():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg_src = ROOT / "configs" / "stage66k_complementary_backup_readiness_expansion.json"
        cfg_dst = root / "configs" / cfg_src.name
        cfg_dst.parent.mkdir(parents=True, exist_ok=True)
        cfg_dst.write_text(cfg_src.read_text(), encoding="utf-8")
        write_json(root / "reports/stage66j_dual_readiness_daily_ops/stage66j_dual_readiness_daily_ops_summary.json", {"decision": "STAGE66J_DUAL_READINESS_WAIT_SIGNALS_NO_ORDER"})
        base_item = {
            "classification": "PASS_FAST_COMPLEMENTARY_CANDIDATE_NO_ORDER",
            "conditions": [{"field": "gold_sma20_over_50", "operator": ">", "threshold": 0}],
            "diagnostics": {"lookahead_breaches": 0, "active_rows": 100, "closed_positions": 30, "skipped_overlap": 70},
            "position_stats": {"trade_count": 33, "mean_net_return_bps": 200, "win_rate": 0.60, "max_year_trade_share": 0.12, "payoff_ratio_win_mean_abs_loss_mean": 1.2, "min_net_return_bps": -1000, "sizing_band_stats": [{"band": "D_base", "max_drawdown_pct": -2.7}]},
            "hypothesis": "synthetic"
        }
        d1 = dict(base_item, thesis_id="D1_DXY_REALYIELD_GOLD_TREND_SHORT_HORIZON_LONG", horizon_trading_days=60)
        d4 = dict(base_item, thesis_id="D4_VOL_RISK_OFF_REALYIELD_GOLD_LONG", horizon_trading_days=60)
        write_json(root / "reports/stage66d_limited_complementary_thesis_scan/stage66d_limited_complementary_thesis_scan_summary.json", {"decision": "STAGE66D_PASS_FAST_COMPLEMENTARY_SHORTLIST_NO_ORDER", "all_results": [d1, d4]})
        macro = root / "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"
        macro.parent.mkdir(parents=True, exist_ok=True)
        with macro.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["feature_date_utc", "sample_available_after_utc", "gold_sma20_over_50"])
            w.writeheader(); w.writerow({"feature_date_utc": "2026-06-24", "sample_available_after_utc": "2026-06-25T00:00:00Z", "gold_sma20_over_50": "-0.1"})
        rc = s66k.main(["--root", str(root), "--config", str(cfg_dst), "--out", str(root / "reports/out")])
        assert rc == 0
        summ = json.loads((root / "reports/out/stage66k_complementary_backup_readiness_expansion_summary.json").read_text())
        assert summ["decision"] == "STAGE66K_BACKUP_RULE_LOCKS_READY_WAIT_SIGNALS_NO_ORDER"


if __name__ == "__main__":
    test_evaluate_signal_false_and_true()
    test_audit_candidate_passes_for_stage66d_like_item()
    test_main_synthetic_wait()
    print("Stage66K tests passed")
