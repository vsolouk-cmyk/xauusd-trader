from pathlib import Path
import os, time, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.stage134_demo_executor_pilot_collector import collect, STATUS_KV, TRADE_LOG

def test_missing_status(tmp_path):
    root=tmp_path; mt5=root/'MQL5/Files'; exp=root/'MQL5/Experts/Advisors/XAUUSD'; mt5.mkdir(parents=True); exp.mkdir(parents=True)
    s=collect(root,mt5,exp,False,180,False)
    assert s['status_exists'] is False
    assert s['collector_decision']=='STAGE134_DEMO_EXECUTOR_NOT_CONFIRMED'

def test_trade_log_accepted_overrides_stale_status(tmp_path):
    root=tmp_path; mt5=root/'MQL5/Files'; exp=root/'MQL5/Experts/Advisors/XAUUSD'; mt5.mkdir(parents=True); exp.mkdir(parents=True)
    st=mt5/STATUS_KV; st.write_text('decision|BLOCKED_NOT_ARMED\ndemo_orders_enabled|false\naccount_mode|DEMO\n',encoding='utf-8')
    old=time.time()-10000; os.utime(st,(old,old))
    (mt5/TRADE_LOG).write_text('time_local,time_current,symbol,event_type,signal_key,rule_id,feature_date,lot,price,sl,tp,ok,retcode,retcode_description,account_mode,demo_required,demo_orders_enabled,note\n2026.07.01 14:29:45,2026.07.01 13:59:45,XAUUSD,DEMO_BUY_ATTEMPT,2026-07-01T11:00:00Z|D138,D138,2026-07-01T11:00:00Z,0.01,3997.84,3985.84,4015.84,true,10009,done at 3997.84,DEMO,true,true,stage134_demo_only_execution_pilot\n',encoding='utf-8')
    s=collect(root,mt5,exp,False,180,True)
    assert s['status_fresh'] is False
    assert s['trade_accepted']==1
    assert s['collector_decision']=='STAGE134_DEMO_ORDER_ACCEPTED_COLLECT_PNL'
    assert s['latest_trade_retcode']=='10009'
    assert Path(s['mt5_collector_status_kv']).exists()

def test_trade_log_rejected_review_retcode(tmp_path):
    root=tmp_path; mt5=root/'MQL5/Files'; exp=root/'MQL5/Experts/Advisors/XAUUSD'; mt5.mkdir(parents=True); exp.mkdir(parents=True)
    (mt5/TRADE_LOG).write_text('event_type,ok,retcode,retcode_description,rule_id,signal_key\nDEMO_BUY_ATTEMPT,false,10018,market closed,D138,key\n',encoding='utf-8')
    s=collect(root,mt5,exp,False,180,False)
    assert s['trade_attempts']==1
    assert s['collector_decision']=='STAGE134_DEMO_ORDER_ATTEMPTED_REVIEW_RETCODE'
