from pathlib import Path
import sys
import csv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage130_forward_shadow_telemetry_collector import collect_once, parse_kv_text

def test_parse_pipe_and_comma_kv():
    kv, fmt = parse_kv_text("status|PASS\nallow_trading|false\ncost10_mean_bps|95.1\n")
    assert kv["status"] == "PASS"
    assert fmt == "PIPE"
    kv2, fmt2 = parse_kv_text("status,PASS\nallow_trading,false\n")
    assert kv2["allow_trading"] == "false"
    assert fmt2 == "COMMA"

def test_collect_once_writes_history_and_no_order(tmp_path):
    root = tmp_path
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    (mt5 / "xauusd_stage124f_rule8_overlay_kv.csv").write_text("status|PASS_STATIC_REPLAY\nallow_trading|false\ncost10_mean_bps|95.5\n")
    (mt5 / "xauusd_stage126_rule9_frontier_status_kv.csv").write_text("status|WATCH\nallow_trading|false\ncost10_mean_bps|87.4\n")
    summary = collect_once(root, mt5, [], 999999, write_mt5_status_kv=True)
    assert summary["status"] == "STAGE130_COMPLETE_FORWARD_SHADOW_TELEMETRY_COLLECTOR_READY_NO_ORDER"
    assert summary["rule8_seen"] is True
    assert summary["rule9_seen"] is True
    assert summary["no_order_violation_count"] == 0
    hist = Path(summary["history_csv"])
    assert hist.exists()
    rows = list(csv.DictReader(hist.open()))
    assert len(rows) >= 5
    assert Path(summary["mt5_status_kv"]).exists()

def test_collect_once_detects_no_order_violation(tmp_path):
    root = tmp_path
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    (mt5 / "xauusd_stage124f_rule8_overlay_kv.csv").write_text("status|PASS\nallow_trading|true\n")
    summary = collect_once(root, mt5, [], 999999, write_mt5_status_kv=False)
    assert summary["no_order_violation_count"] >= 1
    assert "VIOLATION" in summary["decision"]
