from pathlib import Path
import os
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage139_demo_position_outcome_collector import collect, MONITOR_KV, STAGE134_TRADE_LOG

def test_missing_monitor(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators/XAUUSD"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    summary = collect(root, mt5_files, mt5_ind, False, 240, False)
    assert summary["collector_decision"] == "STAGE139_MONITOR_NOT_CONFIRMED_ATTACH_INDICATOR"

def test_open_position_profit(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators/XAUUSD"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    (mt5_files / MONITOR_KV).write_text(
        "account_mode|DEMO\n"
        "symbol|XAUUSD\n"
        "positions_total|1\n"
        "matching_positions|1\n"
        "stage134_matching_positions|1\n"
        "position_ticket|123\n"
        "position_type|BUY\n"
        "position_volume|0.01\n"
        "position_open_price|3997.84\n"
        "position_current_price|4002.84\n"
        "position_sl|3985.84\n"
        "position_tp|4015.84\n"
        "position_profit|5.00\n"
        "position_magic|134138\n",
        encoding="utf-8"
    )
    (mt5_files / STAGE134_TRADE_LOG).write_text(
        "event_type,ok,retcode,rule_id,signal_key,price,lot\n"
        "DEMO_BUY_ATTEMPT,true,10009,D138,key,3997.84,0.01\n",
        encoding="utf-8"
    )
    summary = collect(root, mt5_files, mt5_ind, False, 240, True)
    assert summary["collector_decision"] == "STAGE139_OPEN_DEMO_POSITION_FLOATING_PROFIT"
    assert summary["has_open_position"] == "true"
    assert Path(summary["mt5_collector_status_kv"]).exists()

def test_no_open_after_accepted(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators/XAUUSD"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    (mt5_files / MONITOR_KV).write_text(
        "account_mode|DEMO\n"
        "symbol|XAUUSD\n"
        "positions_total|0\n"
        "matching_positions|0\n"
        "stage134_matching_positions|0\n"
        "position_profit|0.00\n",
        encoding="utf-8"
    )
    (mt5_files / STAGE134_TRADE_LOG).write_text(
        "event_type,ok,retcode,rule_id,signal_key,price,lot\n"
        "DEMO_BUY_ATTEMPT,true,10009,D138,key,3997.84,0.01\n",
        encoding="utf-8"
    )
    summary = collect(root, mt5_files, mt5_ind, False, 240, False)
    assert summary["collector_decision"] == "STAGE139_NO_OPEN_POSITION_AFTER_ACCEPTED_ORDER_CHECK_HISTORY_OR_CLOSED"
