from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage148_pre_market_discovery_validation import (
    split_rows_with_recent_embargo,
    rule_is_excluded,
    market_logic_statement,
)

def row(i):
    return {"utc_time": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i), "target": 1.0}

def test_recent_embargo_excludes_recent_rows():
    rows = [row(i) for i in range(1000)]
    s = split_rows_with_recent_embargo(rows, recent_embargo_bars=100)
    assert len(s["embargoed_recent"]) == 100
    assert s["scoring"][-1]["utc_time"] == row(899)["utc_time"]
    assert s["embargoed_recent"][0]["utc_time"] == row(900)["utc_time"]

def test_excluded_rule_family():
    excluded, reason = rule_is_excluded(
        "D138C_ret_48h_bps_GEQ65__trend_50_100_bps_LEQ65",
        [],
        ["D138C_ret_48h_bps_GEQ65"],
    )
    assert excluded is True
    assert reason.startswith("substring:")

def test_market_logic_statement_for_momentum_pair():
    s = market_logic_statement(
        "D138C_ret_3h_bps_GEQ65__ret_48h_bps_GEQ65",
        "ret_3h_bps >= q65 AND ret_48h_bps >= q65",
    )
    assert "Momentum-continuation" in s
    assert "demo-only" in s
