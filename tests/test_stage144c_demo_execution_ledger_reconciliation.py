from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stage144_demo_execution_ledger_audit import run


def test_stage144c_reconciles_headerless_deals(tmp_path):
    mt5 = tmp_path / "mt5"
    root = tmp_path / "repo"
    mt5.mkdir(parents=True)
    (root / "data/demo_execution").mkdir(parents=True)

    (mt5 / "xauusd_stage134_demo_executor_trade_log.csv").write_text(
        "time_local,time_current,symbol,event_type,signal_key,rule_id,feature_date,lot,price,sl,tp,ok,retcode,retcode_description,account_mode,demo_required,demo_orders_enabled,note\n"
        "2026.07.02 22:55:42,2026.07.02 22:25:42,XAUUSD,TIME_EXIT,,,,0.00,0.00,0.00,0.00,true,10009,done at 4108.32,DEMO,true,true,stage134_demo_only_execution_pilot\n"
        "2026.07.02 22:55:42,2026.07.02 22:25:43,XAUUSD,DEMO_BUY_ATTEMPT,2026-07-02T20:00:00Z|RULE_A,RULE_A,2026-07-02T20:00:00Z,0.01,4108.69,4096.69,4126.69,true,10009,done at 4108.68,DEMO,true,true,stage134_demo_only_execution_pilot\n",
        encoding="utf-8",
    )

    (mt5 / "xauusd_stage140_demo_deals_history.csv").write_text(
        "2026-07-03T06:36:47Z,227432474,2026-07-02T22:25:43Z,XAUUSD,250479092,0,0,0.01,4108.68,0.00,0.00,0.00,1340001,3,Stage134Demo|RULE_A\n"
        "2026-07-03T06:36:47Z,227453548,2026-07-02T23:14:17Z,XAUUSD,250479092,1,1,0.01,4119.85,11.17,0.00,0.00,0,0,\n",
        encoding="utf-8",
    )

    s = run(root, mt5)
    assert s["successful_buy_attempts"] == 1
    assert s["closed_trade_count"] == 1
    assert s["open_or_unmatched_count"] == 0
    assert s["profit_count"] == 1
    assert s["total_net_profit"] == 11.17


def test_stage144c_handles_full_sample_like_current_log(tmp_path):
    mt5 = tmp_path / "mt5"
    root = tmp_path / "repo"
    mt5.mkdir(parents=True)
    (root / "data/demo_execution").mkdir(parents=True)
    trade_rows = [
        ("2026.07.01 14:29:45","2026.07.01 13:59:45","2026-07-01T11:00:00Z|R1","R1","2026-07-01T11:00:00Z","3997.84"),
        ("2026.07.02 01:38:03","2026.07.02 01:08:02","2026-07-01T23:00:00Z|R2","R2","2026-07-01T23:00:00Z","4040.92"),
        ("2026.07.02 17:47:19","2026.07.02 17:17:20","2026-07-02T15:00:00Z|R3","R3","2026-07-02T15:00:00Z","4131.31"),
        ("2026.07.02 17:58:44","2026.07.02 17:28:44","2026-07-02T17:00:00Z|R4","R4","2026-07-02T17:00:00Z","4116.03"),
        ("2026.07.02 19:59:05","2026.07.02 19:29:05","2026-07-02T18:00:00Z|R5","R5","2026-07-02T18:00:00Z","4118.43"),
        ("2026.07.02 20:16:53","2026.07.02 19:46:53","2026-07-02T19:00:00Z|R6","R6","2026-07-02T19:00:00Z","4116.30"),
        ("2026.07.02 22:55:42","2026.07.02 22:25:43","2026-07-02T20:00:00Z|R7","R7","2026-07-02T20:00:00Z","4108.69"),
    ]
    with (mt5 / "xauusd_stage134_demo_executor_trade_log.csv").open("w", encoding="utf-8") as f:
        f.write("time_local,time_current,symbol,event_type,signal_key,rule_id,feature_date,lot,price,sl,tp,ok,retcode,retcode_description,account_mode,demo_required,demo_orders_enabled,note\n")
        for local, current, signal, rule, feat, price in trade_rows:
            f.write(f"{local},{current},XAUUSD,DEMO_BUY_ATTEMPT,{signal},{rule},{feat},0.01,{price},0,0,true,10009,done at {price},DEMO,true,true,note\n")
    deals = [
        ("1","2026-07-01T13:59:45Z","p1",0,"3997.84",0), ("2","2026-07-01T14:11:10Z","p1",1,"4015.88",18.04),
        ("3","2026-07-02T01:08:03Z","p2",0,"4040.92",0), ("4","2026-07-02T04:00:48Z","p2",1,"4059.02",18.10),
        ("5","2026-07-02T17:17:20Z","p3",0,"4131.31",0), ("6","2026-07-02T17:27:05Z","p3",1,"4119.17",-12.14),
        ("7","2026-07-02T17:28:44Z","p4",0,"4116.03",0), ("8","2026-07-02T19:29:04Z","p4",1,"4118.08",2.05),
        ("9","2026-07-02T19:29:05Z","p5",0,"4118.49",0), ("10","2026-07-02T19:31:38Z","p5",1,"4106.34",-12.15),
        ("11","2026-07-02T19:46:53Z","p6",0,"4116.29",0), ("12","2026-07-02T22:25:42Z","p6",1,"4108.32",-7.97),
        ("13","2026-07-02T22:25:43Z","p7",0,"4108.68",0), ("14","2026-07-02T23:14:17Z","p7",1,"4119.85",11.17),
    ]
    with (mt5 / "xauusd_stage140_demo_deals_history.csv").open("w", encoding="utf-8") as f:
        for ticket, time, pos, entry, price, profit in deals:
            f.write(f"2026-07-03T06:36:47Z,{ticket},{time},XAUUSD,{pos},{entry},{entry},0.01,{price},{profit:.2f},0.00,0.00,1340001,3,comment\n")
    s = run(root, mt5)
    assert s["successful_buy_attempts"] == 7
    assert s["closed_trade_count"] == 7
    assert s["open_or_unmatched_count"] == 0
    assert s["total_net_profit"] == 17.10
