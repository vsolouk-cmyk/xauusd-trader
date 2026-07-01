#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, time, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage134_DEMO_EXECUTOR_PILOT_COLLECTOR"
STATUS = "STAGE134_COMPLETE_DEMO_EXECUTOR_PILOT_COLLECTOR_READY"
DEFAULT_MT5_FILES = "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"
DEFAULT_MT5_EXPERTS = "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Experts/Advisors/XAUUSD"
EA_NAME = "XAUUSD_Stage134_DemoExecutorPilot_EA.mq5"
STATUS_KV = "xauusd_stage134_demo_executor_status_kv.csv"
TRADE_LOG = "xauusd_stage134_demo_executor_trade_log.csv"
RISK_BLOCKS = ["REQUIRE_DEMO_ACCOUNT","REAL_ACCOUNT_BLOCKED","MAX_LOT_0_01_DEFAULT","MAX_OPEN_POSITIONS_1_DEFAULT","NO_MARTINGALE","NO_AVERAGING","SL_REQUIRED","TP_REQUIRED","SPREAD_GUARD_REQUIRED","FRESH_STAGE133_SIGNAL_REQUIRED"]

def utc_now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True); return p

def read_kv(path: Path) -> Tuple[Dict[str,str], str]:
    if not path.exists() or path.stat().st_size <= 0: return {}, "MISSING_OR_EMPTY"
    kv, fmt = {}, "UNKNOWN"
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line: continue
        if "|" in line: k,v=line.split("|",1); fmt="PIPE"
        elif "," in line: k,v=line.split(",",1); fmt="COMMA" if fmt=="UNKNOWN" else fmt
        else: continue
        k=k.strip().strip('"').strip("'"); v=v.strip().strip('"').strip("'")
        if k: kv[k]=v
    return kv, fmt

def read_trade_log(path: Path):
    if not path.exists() or path.stat().st_size <= 0: return 0,0,0,[]
    rows=[]
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            rows=[dict(r) for r in csv.DictReader(f)]
    except Exception:
        return 0,0,0,[]
    attempts=sum(1 for r in rows if "ATTEMPT" in str(r.get("event_type","")))
    accepted=sum(1 for r in rows if str(r.get("ok","")).lower()=="true")
    return len(rows), attempts, accepted, rows[-10:]

def write_json(path: Path, obj: Dict[str,Any]): ensure_dir(path.parent); path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
def write_rows(path: Path, rows: List[Dict[str,Any]], fields: List[str]):
    ensure_dir(path.parent); tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k:r.get(k,"") for k in fields})
    tmp.replace(path)
def append_rows(path: Path, rows: List[Dict[str,Any]], fields: List[str]):
    ensure_dir(path.parent); exists=path.exists() and path.stat().st_size>0
    with path.open("a", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        for r in rows: w.writerow({k:r.get(k,"") for k in fields})
def write_kv(path: Path, kv: Dict[str,Any]):
    ensure_dir(path.parent); tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k,v in kv.items(): f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)

def install_ea(root: Path, mt5_experts: Path) -> str:
    src=root/"mql5/Experts/Advisors/XAUUSD"/EA_NAME
    if not src.exists(): raise FileNotFoundError(f"missing EA source: {src}")
    ensure_dir(mt5_experts); dest=mt5_experts/EA_NAME
    try:
        if src.resolve()!=dest.resolve(): shutil.copy2(src,dest)
    except shutil.SameFileError: pass
    return str(dest)

FIELDS=["snapshot_utc","status_exists","status_fresh","status_age_sec","decision","reason","demo_orders_enabled","require_demo_account","account_mode","demo_account_ok","terminal_trade_allowed","mql_trade_allowed","account_trade_allowed","selected_rule_id","feature_date","any_signal_active","active_rule_count","signal_fresh","signal_age_sec","spread_ok","spread_points","open_positions","max_open_positions","lot","order_attempted","last_retcode","last_retcode_description","trade_log_rows","trade_attempts","trade_accepted"]

def collect(root: Path, mt5_files: Path, mt5_experts: Path, install: bool, stale_after_sec: float, write_mt5_status_kv: bool) -> Dict[str,Any]:
    root=root.expanduser(); mt5_files=mt5_files.expanduser(); mt5_experts=mt5_experts.expanduser()
    out=ensure_dir(root/"reports/stage134_demo_executor_pilot"); data=ensure_dir(root/"data/demo_execution"); snapshot_utc=utc_now()
    installed_to = install_ea(root, mt5_experts) if install else ""
    status_path=mt5_files/STATUS_KV; kv, fmt=read_kv(status_path)
    exists=status_path.exists() and status_path.stat().st_size>0
    age=max(0.0, time.time()-status_path.stat().st_mtime) if exists else None
    fresh=bool(exists and age is not None and age<=stale_after_sec)
    trade_rows, trade_attempts, trade_accepted, recent_trades = read_trade_log(mt5_files/TRADE_LOG)
    decision=kv.get("decision", "STAGE134_STATUS_NOT_FOUND_INSTALL_COMPILE_ATTACH_REQUIRED" if not exists else "")
    account_mode=kv.get("account_mode",""); demo_orders_enabled=kv.get("demo_orders_enabled","")
    live_risk = account_mode == "REAL" and demo_orders_enabled.lower() == "true"
    if live_risk: collector_decision="STAGE134_REAL_ACCOUNT_RISK_REVIEW_REQUIRED"
    elif exists and fresh and trade_accepted>0: collector_decision="STAGE134_DEMO_ORDER_ACCEPTED_COLLECT_PNL"
    elif exists and fresh and trade_attempts>0: collector_decision="STAGE134_DEMO_ORDER_ATTEMPTED_REVIEW_RETCODE"
    elif exists and fresh: collector_decision="STAGE134_DEMO_EXECUTOR_RUNNING_WAIT_FOR_ACTIVE_SIGNAL"
    else: collector_decision="STAGE134_DEMO_EXECUTOR_NOT_CONFIRMED"
    row={"snapshot_utc":snapshot_utc,"status_exists":exists,"status_fresh":fresh,"status_age_sec":round(age,2) if age is not None else "","decision":decision,"reason":kv.get("reason",""),"demo_orders_enabled":demo_orders_enabled,"require_demo_account":kv.get("require_demo_account",""),"account_mode":account_mode,"demo_account_ok":kv.get("demo_account_ok",""),"terminal_trade_allowed":kv.get("terminal_trade_allowed",""),"mql_trade_allowed":kv.get("mql_trade_allowed",""),"account_trade_allowed":kv.get("account_trade_allowed",""),"selected_rule_id":kv.get("selected_rule_id",""),"feature_date":kv.get("feature_date",""),"any_signal_active":kv.get("any_signal_active",""),"active_rule_count":kv.get("active_rule_count",""),"signal_fresh":kv.get("signal_fresh",""),"signal_age_sec":kv.get("signal_age_sec",""),"spread_ok":kv.get("spread_ok",""),"spread_points":kv.get("spread_points",""),"open_positions":kv.get("open_positions",""),"max_open_positions":kv.get("max_open_positions",""),"lot":kv.get("lot",""),"order_attempted":kv.get("order_attempted",""),"last_retcode":kv.get("last_retcode",""),"last_retcode_description":kv.get("last_retcode_description",""),"trade_log_rows":trade_rows,"trade_attempts":trade_attempts,"trade_accepted":trade_accepted}
    latest=out/"stage134_latest_demo_executor_snapshot.csv"; history=data/"stage134_demo_executor_snapshots.csv"; risk_manifest=out/"stage134_demo_risk_manifest.csv"
    write_rows(latest,[row],FIELDS); append_rows(history,[row],FIELDS); write_rows(risk_manifest,[{"risk_block":b,"status":"ACTIVE"} for b in RISK_BLOCKS],["risk_block","status"])
    collector_kv={"stage":STAGE,"status":STATUS,"collector_decision":collector_decision,"generated_utc":snapshot_utc,"status_exists":str(exists).lower(),"status_fresh":str(fresh).lower(),"account_mode":account_mode,"demo_orders_enabled":demo_orders_enabled,"trade_attempts":trade_attempts,"trade_accepted":trade_accepted,"installed_to":installed_to}
    status_kv_repo=data/"stage134_demo_executor_collector_status_kv.csv"; status_kv_report=out/"stage134_demo_executor_collector_status_kv.csv"
    write_kv(status_kv_repo,collector_kv); write_kv(status_kv_report,collector_kv)
    mt5_collector_kv=""
    if write_mt5_status_kv:
        mt5_collector_kv=str(mt5_files/"xauusd_stage134_demo_executor_collector_status_kv.csv"); write_kv(Path(mt5_collector_kv),collector_kv)
    summary={"stage":STAGE,"generated_utc":snapshot_utc,"status":STATUS,"collector_decision":collector_decision,"root":str(root),"mt5_files":str(mt5_files),"mt5_experts":str(mt5_experts),"ea_name":EA_NAME,"installed_to":installed_to,"status_kv":str(status_path),"trade_log":str(mt5_files/TRADE_LOG),"status_format":fmt,**row,"recent_trades":recent_trades,"latest_snapshot_csv":str(latest),"history_csv":str(history),"risk_manifest_csv":str(risk_manifest),"status_kv_repo":str(status_kv_repo),"status_kv_report":str(status_kv_report),"mt5_collector_status_kv":mt5_collector_kv,"summary_json":str(out/"stage134_demo_executor_pilot_summary.json"),"report_md":str(out/"stage134_demo_executor_pilot_report.md"),"next":["Compile XAUUSD_Stage134_DemoExecutorPilot_EA in MetaEditor and attach it to XAUUSD,H1 demo chart.","Set InpEnableDemoOrders=true only on demo account when ready to arm demo execution.","When a Stage133 selected rule becomes active, collect retcode/fill/PnL from demo logs."]}
    write_json(out/"stage134_demo_executor_pilot_summary.json", summary)
    (out/"stage134_demo_executor_pilot_report.md").write_text(f"# Stage134 Demo Executor Pilot\n\nCollector decision: `{collector_decision}`\n\n- status exists: {exists}\n- status fresh: {fresh}\n- EA decision: `{decision}`\n- account mode: `{account_mode}`\n- demo orders enabled: `{demo_orders_enabled}`\n- trade attempts: {trade_attempts}\n- trade accepted: {trade_accepted}\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False)); return summary

def main():
    ap=argparse.ArgumentParser(description=STAGE); ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader"); ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES); ap.add_argument("--mt5-experts", default=DEFAULT_MT5_EXPERTS); ap.add_argument("--install-ea", action="store_true"); ap.add_argument("--stale-after-sec", type=float, default=180.0); ap.add_argument("--write-mt5-status-kv", action="store_true")
    args=ap.parse_args(); collect(Path(args.root), Path(args.mt5_files), Path(args.mt5_experts), args.install_ea, args.stale_after_sec, args.write_mt5_status_kv); return 0
if __name__ == "__main__": raise SystemExit(main())
