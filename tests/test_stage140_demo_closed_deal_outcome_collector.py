from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage140_demo_closed_deal_outcome_collector import collect, DEALS_KV, STAGE134_TRADE_LOG

def test_missing_monitor(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators/XAUUSD"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    summary = collect(root, mt5_files, mt5_ind, False, 240, False)
    assert summary["collector_decision"] == "STAGE140_DEAL_MONITOR_NOT_CONFIRMED_ATTACH_INDICATOR"

def test_closed_profit_numeric_reason(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators/XAUUSD"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    (mt5_files / DEALS_KV).write_text(
        "account_mode|DEMO\n"
        "symbol|XAUUSD\n"
        "history_select_ok|true\n"
        "history_deals_total|3\n"
        "symbol_deals|2\n"
        "stage134_like_deals|1\n"
        "latest_position_id|777\n"
        "latest_entry_deal_ticket|101\n"
        "latest_entry_price|3997.84\n"
        "latest_entry_volume|0.01\n"
        "latest_entry_type_code|0\n"
        "latest_exit_deal_ticket|102\n"
        "latest_exit_price|4015.84\n"
        "latest_exit_type_code|1\n"
        "latest_exit_reason_code|4\n"
        "latest_exit_profit|18.00\n"
        "latest_exit_swap|0.00\n"
        "latest_exit_commission|0.00\n"
        "latest_net_profit|18.00\n"
        "latest_points_move|18.00\n"
        "latest_bps_move|45.02\n",
        encoding="utf-8"
    )
    (mt5_files / STAGE134_TRADE_LOG).write_text(
        "event_type,ok,retcode,rule_id,signal_key,price,lot\n"
        "DEMO_BUY_ATTEMPT,true,10009,D138,key,3997.84,0.01\n",
        encoding="utf-8"
    )
    summary = collect(root, mt5_files, mt5_ind, False, 240, True)
    assert summary["collector_decision"] == "STAGE140_CLOSED_DEMO_DEAL_PROFIT"
    assert summary["latest_exit_reason_code"] == "4"
    assert summary["latest_exit_reason_label"] == "TP"
    assert Path(summary["mt5_collector_status_kv"]).exists()

def test_entry_no_exit(tmp_path):
    root = tmp_path
    mt5_files = tmp_path / "MQL5/Files"
    mt5_ind = tmp_path / "MQL5/Indicators/XAUUSD"
    mt5_files.mkdir(parents=True)
    mt5_ind.mkdir(parents=True)
    (mt5_files / DEALS_KV).write_text(
        "symbol|XAUUSD\n"
        "symbol_deals|1\n"
        "latest_entry_deal_ticket|101\n"
        "latest_exit_deal_ticket|0\n",
        encoding="utf-8"
    )
    (mt5_files / STAGE134_TRADE_LOG).write_text(
        "event_type,ok,retcode,rule_id,signal_key,price,lot\n"
        "DEMO_BUY_ATTEMPT,true,10009,D138,key,3997.84,0.01\n",
        encoding="utf-8"
    )
    summary = collect(root, mt5_files, mt5_ind, False, 240, False)
    assert summary["collector_decision"] == "STAGE140_ENTRY_DEAL_FOUND_BUT_NO_EXIT_DEAL"
