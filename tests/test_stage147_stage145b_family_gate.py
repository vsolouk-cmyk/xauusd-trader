from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage145_clean_ledger_performance_gate import family_key, max_trades_in_window, per_family_metrics, run


def test_family_key_normalizes_threshold_variants():
    assert family_key("D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ50") == "D138C_ret_48h_bps__trend_50_100_bps"
    assert family_key("D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65") == "D138C_ret_48h_bps__trend_50_100_bps"


def test_clustering_alert_counts_four_hour_window():
    rows = [
        {"entry_time": "2026-07-02T17:00:00Z", "outcome": "LOSS"},
        {"entry_time": "2026-07-02T18:00:00Z", "outcome": "LOSS"},
        {"entry_time": "2026-07-02T20:00:00Z", "outcome": "PROFIT"},
    ]
    assert max_trades_in_window(rows, 4) == 3


def test_per_family_metrics_groups_and_flags_cluster():
    rows = [
        {"rule_id":"D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ50", "outcome":"LOSS", "net_profit":"-1", "bps_move":"-2", "entry_time":"2026-07-02T17:00:00Z"},
        {"rule_id":"D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65", "outcome":"PROFIT", "net_profit":"2", "bps_move":"4", "entry_time":"2026-07-02T18:00:00Z"},
        {"rule_id":"D138C_ret_3h_bps_GEQ65__ret_48h_bps_GEQ65", "outcome":"PROFIT", "net_profit":"3", "bps_move":"6", "entry_time":"2026-07-02T21:00:00Z"},
    ]
    fam = per_family_metrics(rows, 10, 2.0, 1)
    keys = {r["family_key"] for r in fam}
    assert "D138C_ret_48h_bps__trend_50_100_bps" in keys
    assert "D138C_ret_3h_bps__ret_48h_bps" in keys
    assert any(r["clustering_alert"] for r in fam if r["family_key"] == "D138C_ret_48h_bps__trend_50_100_bps")


def test_run_writes_per_family_csv(tmp_path):
    root = tmp_path
    ledger = root / "data/demo_execution/stage144_clean_demo_execution_ledger.csv"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        "rule_id,outcome,net_profit,bps_move,signal_key,entry_time\n"
        "D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ50,LOSS,-12,-29,s1,2026-07-02T17:00:00Z\n"
        "D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65,PROFIT,11,27,s2,2026-07-02T20:00:00Z\n",
        encoding="utf-8"
    )
    summary = run(root, ledger, 10, 0.55, 2.0, 3, 10, 2)
    assert summary["family_count"] == 1
    assert Path(summary["family_csv"]).exists()
