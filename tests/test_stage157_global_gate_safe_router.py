from pathlib import Path

from app.stage154_active_shortlist_rule_router import (
    global_freeze_triggered,
    normalize_family_key,
)


def test_global_freeze_triggered_from_stage145_freeze_gate():
    active, info = global_freeze_triggered(
        {
            "closed_trade_count": 12,
            "gate_decision": "STAGE145_FREEZE_REPAIR_RULE_NEGATIVE_EXPECTANCY",
            "recommended_action": "FREEZE_CURRENT_RULE_AND_REPAIR_DISCOVERY",
            "severity": "HIGH",
            "total_bps": -9.72,
            "mean_bps": -0.81,
            "win_rate": 0.5,
        },
        min_global_gate_trades=10,
    )
    assert active is True
    assert info["global_gate_freeze_active"] is True
    assert info["global_closed_trade_count"] == 12
    assert "FREEZE" in info["global_gate_decision"]


def test_global_freeze_not_triggered_below_min_trade_count():
    active, info = global_freeze_triggered(
        {
            "closed_trade_count": 9,
            "gate_decision": "STAGE145_FREEZE_REPAIR_RULE_NEGATIVE_EXPECTANCY",
            "recommended_action": "FREEZE_CURRENT_RULE_AND_REPAIR_DISCOVERY",
            "severity": "HIGH",
            "total_bps": -20,
            "mean_bps": -2,
        },
        min_global_gate_trades=10,
    )
    assert active is False
    assert info["global_gate_freeze_active"] is False


def test_global_freeze_high_negative_without_explicit_freeze_word():
    active, info = global_freeze_triggered(
        {
            "closed_trade_count": 11,
            "gate_decision": "CUSTOM_GATE",
            "recommended_action": "CHECK",
            "severity": "HIGH",
            "total_bps": -1,
            "mean_bps": -0.1,
        },
        min_global_gate_trades=10,
    )
    assert active is True


def test_family_normalization_threshold_tokens():
    assert normalize_family_key("D150C_M5_ret_12h_bps_GEQ35__trend_50_100_bps_GEQ35") == "D150C_M5_ret_12h_bps__trend_50_100_bps"
    assert normalize_family_key("D150C_M5_ret_6h_bps_LEQ50__trend_8_20_bps_GEQ65") == "D150C_M5_ret_6h_bps__trend_8_20_bps"
