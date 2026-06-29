import csv
import json
from pathlib import Path

from app.stage124e_unified_combo_8rule_chart_status import run, EA_SOURCE


def test_stage124e_generates_8_rule_status_and_chart_kv(tmp_path: Path):
    root = tmp_path
    rep = root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery"
    rep.mkdir(parents=True)
    kv = root / "data/shadow_observer/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv"
    kv.parent.mkdir(parents=True)
    kv.write_text(
        "rule_id,S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN\n"
        "source_rule_id,S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF\n"
        "rule_status,PASS_STATIC_REPLAY\n"
        "cost10_mean_bps,95.5793\n"
        "cost10_hit_rate,0.6\n"
        "last_signal_time_utc,2026-02-12T00:00:00Z\n",
        encoding="utf-8",
    )
    summary = {
        "replay_status": "PASS_STATIC_REPLAY",
        "selected_for_stage125_count": 0,
        "mt5_shadow_kv_repo": str(kv),
    }
    (rep / "stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    out = run(root, root / "mt5_files", root / "mt5_experts", True, True)
    assert out["status"] == "STAGE124E_COMPLETE_8RULE_CHART_STATUS_READY_NO_ORDER"
    assert out["unified_display_rule_count"] == 8
    with open(out["repo_status_table"], newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 8
    assert rows[-1]["rule_status"] == "PASS_STATIC_REPLAY"
    assert Path(out["mt5_chart_status_kv"]).exists()
    assert Path(out["mt5_ea_source"]).exists()


def test_ea_source_has_chart_comment_and_no_trade_calls():
    assert "Comment(text)" in EA_SOURCE
    assert "OrderSend" not in EA_SOURCE
    assert "CTrade" not in EA_SOURCE
