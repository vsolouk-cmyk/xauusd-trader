from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage138_broker_technical_demo_discovery import rule_is_excluded, detect_delimiter, read_table

def test_rule_is_excluded_by_substring():
    excluded, reason = rule_is_excluded(
        "D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65",
        [],
        ["D138C_ret_48h_bps_GEQ65"],
    )
    assert excluded is True
    assert reason == "substring:D138C_ret_48h_bps_GEQ65"

def test_rule_is_not_excluded_when_substring_absent():
    excluded, reason = rule_is_excluded(
        "D138C_trend_20_50_bps_LEQ35__range_pos_24_LEQ35",
        [],
        ["D138C_ret_48h_bps_GEQ65"],
    )
    assert excluded is False
    assert reason == ""

def test_mt5_tab_table_still_parses(tmp_path):
    p = tmp_path / "bars.csv"
    p.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n2026.07.01\t11:00:00\t1\t2\t0.5\t1.5\n", encoding="utf-8")
    assert detect_delimiter(p) == "\t"
    rows = read_table(p)
    assert rows[0]["date"] == "2026.07.01"
    assert rows[0]["close"] == "1.5"
