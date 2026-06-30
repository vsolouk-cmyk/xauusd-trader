from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage130b_mt5_journal_and_files_telemetry_audit import run, parse_log_file

def test_parse_mt5_log_lines(tmp_path):
    log = tmp_path / "20260630.log"
    log.write_text(
        "2026.06.29 22:41:37.125\tXAUUSD_Stage124F_Rule8OverlayIndicator (XAUUSD,H1)\tStage124F fixed dashboard read complete. kv_count=18 status=PASS_STATIC_REPLAY allow_trading=false Trading remains disabled. No orders are sent.\n"
        "2026.06.29 22:41:37.182\tXAUUSD_Stage126_Rule9FrontierOverlayIndicator (XAUUSD,H1)\tStage126 fixed dashboard read complete. kv_count=17 status=PASS_STAGE127_SHADOW_REVIEW_QUEUE allow_trading=false. No orders are sent.\n"
        "2026.06.30 10:00:00.000\tUnified_ObserverOnly_EA (XAUUSD,H1)\tany_signal_active=false execution_allowed=false AllowTrading=false\n",
        encoding="utf-8"
    )
    rows = parse_log_file(log, 100000, "2026-06-30T00:00:00Z")
    assert len(rows) == 3
    assert any("rule8_stage124f" in r["category_flags"] for r in rows)
    assert any("rule9_stage126" in r["category_flags"] for r in rows)
    assert any("unified_ea" in r["category_flags"] for r in rows)

def test_run_with_fake_logs_and_stage130_snapshot(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "Terminal/MQL5/Files"
    log_dir = tmp_path / "Terminal/MQL5/Logs"
    mt5_files.mkdir(parents=True)
    log_dir.mkdir(parents=True)
    rep = root / "reports/stage130_forward_shadow_telemetry_collector"
    rep.mkdir(parents=True)
    (rep / "stage130_latest_shadow_snapshot.csv").write_text(
        "label,exists,freshness\nrule8_stage124f,true,STALE\nrule9_stage126,true,STALE\n",
        encoding="utf-8"
    )
    (log_dir / "20260630.log").write_text(
        "2026.06.30 10:00:00.000\tUnified_ObserverOnly_EA (XAUUSD,H1)\tany_signal_active=false execution_allowed=false AllowTrading=false\n",
        encoding="utf-8"
    )
    summary = run(root, mt5_files, [], 10, 100000, write_mt5_status_kv=True)
    assert summary["status"] == "STAGE130B_COMPLETE_MT5_JOURNAL_AND_FILES_TELEMETRY_READY_NO_ORDER"
    assert summary["unified_ea_log_events"] >= 1
    assert summary["order_risk_events"] == 0
    assert Path(summary["events_csv"]).exists()
    assert Path(summary["mt5_status_kv"]).exists()

def test_order_risk_is_flagged(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "Terminal/MQL5/Files"
    log_dir = tmp_path / "Terminal/MQL5/Logs"
    mt5_files.mkdir(parents=True)
    log_dir.mkdir(parents=True)
    (log_dir / "20260630.log").write_text(
        "2026.06.30 10:00:00.000\tUnified_ObserverOnly_EA (XAUUSD,H1)\tOrderSend BUY allow_trading=true\n",
        encoding="utf-8"
    )
    summary = run(root, mt5_files, [], 10, 100000, write_mt5_status_kv=False)
    assert summary["order_risk_events"] >= 1
    assert "ORDER_RISK" in summary["decision"]
