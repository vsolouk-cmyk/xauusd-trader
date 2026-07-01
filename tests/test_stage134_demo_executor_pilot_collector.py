from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.stage134_demo_executor_pilot_collector import collect, install_ea, STATUS_KV, TRADE_LOG

def test_missing_status(tmp_path):
    root=tmp_path; mt5_files=tmp_path/"MQL5/Files"; mt5_experts=tmp_path/"MQL5/Experts/Advisors/XAUUSD"; mt5_files.mkdir(parents=True); mt5_experts.mkdir(parents=True)
    summary=collect(root, mt5_files, mt5_experts, False, 180, False)
    assert summary["status_exists"] is False
    assert summary["collector_decision"] == "STAGE134_DEMO_EXECUTOR_NOT_CONFIRMED"

def test_collect_status_and_trade_log(tmp_path):
    root=tmp_path; mt5_files=tmp_path/"MQL5/Files"; mt5_experts=tmp_path/"MQL5/Experts/Advisors/XAUUSD"; mt5_files.mkdir(parents=True); mt5_experts.mkdir(parents=True)
    (mt5_files/STATUS_KV).write_text("stage|Stage134_DEMO_EXECUTOR_PILOT\nstatus|DEMO_EXECUTOR_RUNTIME_ALIVE\ndecision|DEMO_BUY_SENT\ndemo_orders_enabled|true\nrequire_demo_account|true\naccount_mode|DEMO\ndemo_account_ok|true\nselected_rule_id|K06\nany_signal_active|true\norder_attempted|true\n", encoding="utf-8")
    (mt5_files/TRADE_LOG).write_text("event_type,ok,retcode\nDEMO_BUY_ATTEMPT,true,10009\n", encoding="utf-8")
    summary=collect(root, mt5_files, mt5_experts, False, 999999, True)
    assert summary["status_exists"] is True
    assert summary["status_fresh"] is True
    assert summary["trade_attempts"] == 1
    assert summary["trade_accepted"] == 1
    assert summary["collector_decision"] == "STAGE134_DEMO_ORDER_ACCEPTED_COLLECT_PNL"
    assert Path(summary["mt5_collector_status_kv"]).exists()

def test_real_account_risk_flagged(tmp_path):
    root=tmp_path; mt5_files=tmp_path/"MQL5/Files"; mt5_experts=tmp_path/"MQL5/Experts/Advisors/XAUUSD"; mt5_files.mkdir(parents=True); mt5_experts.mkdir(parents=True)
    (mt5_files/STATUS_KV).write_text("account_mode|REAL\ndemo_orders_enabled|true\n", encoding="utf-8")
    summary=collect(root, mt5_files, mt5_experts, False, 999999, False)
    assert summary["collector_decision"] == "STAGE134_REAL_ACCOUNT_RISK_REVIEW_REQUIRED"

def test_install_ea(tmp_path):
    root=tmp_path; repo=root/"mql5/Experts/Advisors/XAUUSD"; mt5_experts=tmp_path/"Terminal/MQL5/Experts/Advisors/XAUUSD"; repo.mkdir(parents=True)
    ea=repo/"XAUUSD_Stage134_DemoExecutorPilot_EA.mq5"; ea.write_text("// ea\n", encoding="utf-8")
    dest=install_ea(root, mt5_experts)
    assert Path(dest).exists()
