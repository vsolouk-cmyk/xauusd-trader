from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage131_mt5_runtime_heartbeat_indicator_and_collector import collect, read_kv, INDICATOR_NAME

def test_missing_heartbeat_decision(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    summary = collect(root, mt5_files, 180, False, False, mt5_ind)
    assert summary["heartbeat_exists"] is False
    assert "HEARTBEAT_NOT_FOUND" in summary["decision"]

def test_fresh_heartbeat_collected(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    (mt5_files / "xauusd_stage131_runtime_heartbeat_kv.csv").write_text(
        "stage|Stage131_MT5_RUNTIME_HEARTBEAT_INDICATOR\n"
        "status|HEARTBEAT_ALIVE_NO_ORDER\n"
        "allow_trading|false\n"
        "order_send|false\n"
        "symbol|XAUUSD\n"
        "period|16385\n",
        encoding="utf-8"
    )
    summary = collect(root, mt5_files, 999999, True, False, mt5_ind)
    assert summary["heartbeat_exists"] is True
    assert summary["heartbeat_fresh"] is True
    assert summary["kv_count"] >= 5
    assert Path(summary["mt5_status_kv"]).exists()
    assert Path(summary["latest_snapshot_csv"]).exists()

def test_indicator_install(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators"
    repo_ind = root / "mql5/Indicators"
    mt5_files.mkdir(parents=True)
    repo_ind.mkdir(parents=True)
    (repo_ind / INDICATOR_NAME).write_text("// test indicator\n", encoding="utf-8")
    summary = collect(root, mt5_files, 180, False, True, mt5_ind)
    assert len(summary["indicator_written"]) == 2
    assert (mt5_ind / INDICATOR_NAME).exists()
    assert (mt5_ind / "Advisors/XAUUSD" / INDICATOR_NAME).exists()

def test_indicator_install_samefile_guard(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = root / "mql5/Indicators"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    (mt5_ind / INDICATOR_NAME).write_text("// same file source target\n", encoding="utf-8")
    summary = collect(root, mt5_files, 180, False, True, mt5_ind)
    assert len(summary["indicator_written"]) == 2
    assert (mt5_ind / INDICATOR_NAME).exists()
    assert (mt5_ind / "Advisors/XAUUSD" / INDICATOR_NAME).exists()
