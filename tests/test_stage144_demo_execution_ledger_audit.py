from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage144_demo_execution_ledger_audit import run, unique_attempts, build_position_pairs

def test_unique_attempts_dedupes():
    rows = [
        {"event_type":"DEMO_BUY_ATTEMPT","ok":"true","signal_key":"s","rule_id":"r","price":"1","retcode":"10009"},
        {"event_type":"DEMO_BUY_ATTEMPT","ok":"true","signal_key":"s","rule_id":"r","price":"1","retcode":"10009"},
    ]
    assert len(unique_attempts(rows)) == 1

def test_deal_pair_profit_tp():
    deals = [
        {"ticket":"1","position_id":"p","entry_code":"0","type_code":"0","time":"2026-01-01T00:00:00Z","price":"100","volume":"0.01","profit":"0","swap":"0","commission":"0","comment":"Stage134Demo|rule"},
        {"ticket":"2","position_id":"p","entry_code":"1","type_code":"1","time":"2026-01-01T01:00:00Z","price":"101","volume":"0.01","profit":"1","swap":"0","commission":"0","reason_code":"5","comment":"[tp 101]"},
    ]
    pairs = build_position_pairs(deals)
    assert len(pairs) == 1
    assert pairs[0]["exit_reason"] == "TP"
    assert pairs[0]["net_profit"] == 1

def test_run_reconciles_two_trades_and_flags_stage141_mismatch(tmp_path):
    root = tmp_path
    mt5 = tmp_path / "MQL5/Files"
    mt5.mkdir(parents=True)
    (mt5 / "xauusd_stage134_demo_executor_trade_log.csv").write_text(
        "event_type,ok,signal_key,rule_id,feature_date,lot,price,retcode,retcode_description,account_mode\n"
        "DEMO_BUY_ATTEMPT,true,s1,r1,fd,0.01,100,10009,done,DEMO\n"
        "DEMO_BUY_ATTEMPT,true,s2,r2,fd,0.01,200,10009,done,DEMO\n",
        encoding="utf-8"
    )
    (mt5 / "xauusd_stage140_demo_deals_history.csv").write_text(
        "generated_utc,ticket,time,symbol,position_id,entry_code,type_code,volume,price,profit,swap,commission,magic,reason_code,comment\n"
        "g,1,t1,XAUUSD,p1,0,0,0.01,100,0,0,0,1340001,3,Stage134Demo|r1\n"
        "g,2,t2,XAUUSD,p1,1,1,0.01,101,1,0,0,1340001,5,[tp 101]\n"
        "g,3,t3,XAUUSD,p2,0,0,0.01,200,0,0,0,1340001,3,Stage134Demo|r2\n"
        "g,4,t4,XAUUSD,p2,1,1,0.01,202,2,0,0,1340001,5,[tp 202]\n",
        encoding="utf-8"
    )
    raw = root / "data/demo_execution/stage141_demo_execution_outcome_ledger.csv"
    raw.parent.mkdir(parents=True)
    raw.write_text("a\n1\n2\n3\n", encoding="utf-8")
    s = run(root, mt5)
    assert s["unique_trade_attempts"] == 2
    assert s["clean_ledger_row_count"] == 2
    assert s["stage141_raw_ledger_row_count"] == 3
    assert s["ledger_count_mismatch"] is True
    assert s["profit_count"] == 2
    assert s["total_net_profit"] == 3
