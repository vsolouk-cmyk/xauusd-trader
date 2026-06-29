import json
from pathlib import Path

from app.stage124f_rule8_indicator_overlay_pack import run, INDICATOR_SOURCE


def test_stage124f_generates_indicator_overlay(tmp_path: Path):
    root = tmp_path
    rep = root / "reports/stage124_consolidated_shadow_csv_ea_and_frontier_discovery"
    rep.mkdir(parents=True)
    kv = root / "data/shadow_observer/stage124c_xauusd_shadow_observer_signal_mt5_kv.csv"
    kv.parent.mkdir(parents=True)
    kv.write_text(
        "rule_id,S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN\n"
        "source_rule_id,S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF\n"
        "rule_status,PASS_STATIC_REPLAY\n"
        "allow_trading,false\n"
        "cost10_mean_bps,95.5793\n"
        "cost10_hit_rate,0.6\n"
        "last_signal_time_utc,2026-02-12T00:00:00Z\n",
        encoding="utf-8",
    )
    summary = {"replay_status": "PASS_STATIC_REPLAY", "selected_for_stage125_count": 0, "mt5_shadow_kv_repo": str(kv)}
    (rep / "stage124_consolidated_shadow_csv_ea_and_frontier_discovery_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    out = run(root, root / "mt5_files", root / "mt5_indicators", True, True)
    assert out["status"] == "STAGE124F_COMPLETE_RULE8_INDICATOR_OVERLAY_READY_NO_ORDER"
    assert out["rule8_runtime_surface"] == "CUSTOM_INDICATOR_OVERLAY_ON_SAME_CHART"
    assert Path(out["mt5_rule8_kv"]).exists()
    assert Path(out["mt5_indicator_source"]).exists()


def test_indicator_source_is_indicator_and_has_no_trade_calls():
    assert "#property indicator_chart_window" in INDICATOR_SOURCE
    assert "OrderSend" not in INDICATOR_SOURCE
    assert "CTrade" not in INDICATOR_SOURCE
    assert "OBJ_LABEL" in INDICATOR_SOURCE
