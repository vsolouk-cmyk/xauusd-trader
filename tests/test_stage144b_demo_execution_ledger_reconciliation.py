from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage144_demo_execution_ledger_audit import reconcile, summarize


def test_time_exit_is_not_counted_as_entry_and_blank_magic_exit_pairs():
    trade = [
        {"time_current":"2026-07-02T19:46:53Z","symbol":"XAUUSD","event_type":"DEMO_BUY_ATTEMPT","signal_key":"2026-07-02T19:00:00Z|R","rule_id":"R","feature_date":"2026-07-02T19:00:00Z","lot":"0.01","price":"4116.30","ok":"true","retcode":"10009","retcode_description":"done at 4116.29","account_mode":"DEMO"},
        {"time_current":"2026-07-02T22:25:42Z","symbol":"XAUUSD","event_type":"TIME_EXIT","signal_key":"","rule_id":"","feature_date":"","lot":"0.00","price":"0.00","ok":"true","retcode":"10009","retcode_description":"done at 4108.32","account_mode":"DEMO"},
        {"time_current":"2026-07-02T22:25:43Z","symbol":"XAUUSD","event_type":"DEMO_BUY_ATTEMPT","signal_key":"2026-07-02T20:00:00Z|R","rule_id":"R","feature_date":"2026-07-02T20:00:00Z","lot":"0.01","price":"4108.69","ok":"true","retcode":"10009","retcode_description":"done at 4108.68","account_mode":"DEMO"},
    ]
    deals = [
        {"ticket":"227383293","time":"2026-07-02T19:46:53Z","symbol":"XAUUSD","position_id":"250427922","entry":"0","volume":"0.01","price":"4116.29","profit":"0.00","magic":"1340001","reason":"3","comment":"Stage134Demo|R"},
        {"ticket":"227432473","time":"2026-07-02T22:25:42Z","symbol":"XAUUSD","position_id":"250427922","entry":"1","volume":"0.01","price":"4108.32","profit":"-7.97","magic":"1340001","reason":"3","comment":""},
        {"ticket":"227432474","time":"2026-07-02T22:25:43Z","symbol":"XAUUSD","position_id":"250479092","entry":"0","volume":"0.01","price":"4108.68","profit":"0.00","magic":"1340001","reason":"3","comment":"Stage134Demo|R"},
        {"ticket":"227453548","time":"2026-07-02T23:14:17Z","symbol":"XAUUSD","position_id":"250479092","entry":"1","volume":"0.01","price":"4119.85","profit":"11.17","magic":"0","reason":"0","comment":""},
    ]
    ledger = reconcile(trade, deals)
    assert len(ledger) == 2
    assert ledger[0]["outcome"] == "LOSS"
    assert ledger[0]["net_profit"] == -7.97
    assert ledger[1]["outcome"] == "PROFIT"
    assert ledger[1]["signal_key"] == "2026-07-02T20:00:00Z|R"
    assert ledger[1]["position_id"] == "250479092"
    assert ledger[1]["exit_deal_ticket"] == "227453548"
    assert ledger[1]["net_profit"] == 11.17


def test_summary_counts_only_successful_buy_attempts(tmp_path):
    ledger = [
        {"outcome":"PROFIT","net_profit":"18.04","bps_move":"45.12"},
        {"outcome":"LOSS","net_profit":"-12.14","bps_move":"-29.39"},
    ]
    s = summarize(tmp_path, ledger, raw_trade_rows=3, raw_deal_rows=4, stage141_count=0)
    assert s["unique_trade_attempts"] == 2
    assert s["closed_trade_count"] == 2
    assert s["open_or_unmatched_count"] == 0
    assert s["profit_count"] == 1
    assert s["loss_count"] == 1
