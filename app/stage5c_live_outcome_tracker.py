#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from dataclasses import dataclass,asdict
from datetime import datetime,timedelta,timezone
from pathlib import Path

TOOL_VERSION="v3"
STRATEGY_ID="xauusd_long_tp24_sl15_no_london_v1"
DEF_SIG=Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv").expanduser()
DEF_M1=Path("~/Downloads/amarkets_xauusd_1m.csv").expanduser()
DEF_OUT=Path("data/reports/stage5c_live_outcome_tracker")

def norm(k): return str(k).lower().strip().strip("<>").replace("_","").replace(" ","")
def pick(cols,names):
    mp={norm(c):c for c in cols}
    for n in names:
        if norm(n) in mp: return mp[norm(n)]
    return None
def parse_time(s):
    s=str(s or "").strip()
    if not s: return None
    for f in ("%Y.%m.%d %H:%M:%S","%Y.%m.%d %H:%M","%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%S","%Y.%m.%d","%Y-%m-%d"):
        try:
            dt=datetime.strptime(s,f)
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception: pass
    try:
        dt=datetime.fromisoformat(s.replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception: return None
def pf(v,default=0.0):
    try:
        return float(str(v).strip()) if str(v or "").strip() else default
    except Exception: return default
def delim(text): return "\t" if text[:8192].count("\t")>=text[:8192].count(",") else ","
def read_csv(path):
    if not path.exists(): return [],[],"missing",""
    text=path.read_text(encoding="utf-8-sig",errors="replace")
    if not text.strip(): return [],[],"empty",""
    d=delim(text); rows=list(csv.DictReader(text.splitlines(),delimiter=d)); cols=list(rows[0].keys()) if rows else []
    clean=[{str(k).strip():("" if v is None else str(v).strip()) for k,v in r.items() if k is not None} for r in rows]
    return clean,cols,"ok",d

@dataclass
class Outcome:
    source_row:int; symbol:str; session_utc:str; status:str; reason:str; closed_h1_utc:str|None; entry_utc:str|None
    entry_price:float|None; tp_price:float|None; sl_price:float|None; exit_utc:str|None; exit_price:float|None; net_usd_x1:float|None; m1_bars_checked:int

def load_signals(path,offset_h,dedupe=True):
    rows,cols,status,d=read_csv(path); out=[]; seen=set(); off=timedelta(hours=offset_h)
    for i,r in enumerate(rows,1):
        if r.get("strategy_id") and r.get("strategy_id")!=STRATEGY_ID: continue
        closed_server=parse_time(r.get("signal_closed_h1_time_server",""))
        closed_utc=(closed_server-off).isoformat() if closed_server else None
        key="|".join([r.get(x,"") for x in ("symbol","strategy_id","signal_closed_h1_time_server","session_utc","close_h1","sma10","distance_usd","direction")])
        if dedupe and key in seen: continue
        seen.add(key)
        out.append({"source_row":i,"symbol":r.get("symbol",""),"session_utc":r.get("session_utc",""),"closed_h1_utc":closed_utc,"tp":pf(r.get("tp_usd"),24.0),"sl":pf(r.get("sl_usd"),15.0),"bars":int(pf(r.get("time_exit_h1_bars"),12.0))})
    return out, {"raw_rows":len(rows),"skipped_duplicates":len(rows)-len(out),"status":status,"delimiter":"TAB" if d=="\t" else d,"columns":cols}

def load_m1(path,offset_h):
    rows,cols,status,d=read_csv(path)
    info={"path":str(path),"status":status,"rows_raw":len(rows),"rows_parsed":0,"bad_time_rows":0,"delimiter":"TAB" if d=="\t" else d,"columns":cols,"start_utc":None,"end_utc":None}
    if not rows: return [],info
    date_col=pick(cols,["date","<DATE>"]); time_col=pick(cols,["time","<TIME>","datetime","timestamp"]); comb_col=pick(cols,["datetime","timestamp","timegmt","time_utc"])
    open_col=pick(cols,["open","<OPEN>"]); high_col=pick(cols,["high","<HIGH>"]); low_col=pick(cols,["low","<LOW>"]); close_col=pick(cols,["close","<CLOSE>"])
    if not all([open_col,high_col,low_col,close_col]) or not (comb_col or time_col or (date_col and time_col)):
        info["status"]="missing_required_ohlc_or_time_columns"; return [],info
    out=[]; off=timedelta(hours=offset_h); bad=0
    for r in rows:
        raw=f"{r.get(date_col,'')} {r.get(time_col,'')}".strip() if date_col and time_col and date_col!=time_col else r.get(comb_col or time_col or "","")
        t=parse_time(raw)
        if not t: bad+=1; continue
        out.append({"utc":(t-off).astimezone(timezone.utc),"open":pf(r.get(open_col)),"high":pf(r.get(high_col)),"low":pf(r.get(low_col)),"close":pf(r.get(close_col))})
    out.sort(key=lambda x:x["utc"])
    info.update({"rows_parsed":len(out),"bad_time_rows":bad,"start_utc":out[0]["utc"].isoformat() if out else None,"end_utc":out[-1]["utc"].isoformat() if out else None,"status":status if out else "no_parseable_m1_rows"})
    return out,info

def resolve(s,m1,info,cost):
    if not s["closed_h1_utc"]: return Outcome(s["source_row"],s["symbol"],s["session_utc"],"UNRESOLVED","missing_closed_h1_server_time",None,None,None,None,None,None,None,None,0)
    closed=datetime.fromisoformat(s["closed_h1_utc"]); entry_t=closed+timedelta(hours=1); end_t=entry_t+timedelta(hours=s["bars"])
    if not m1: return Outcome(s["source_row"],s["symbol"],s["session_utc"],"UNRESOLVED",f"missing_m1_data:{info['status']}",s["closed_h1_utc"],entry_t.isoformat(),None,None,None,None,None,None,0)
    if m1[-1]["utc"]<entry_t: return Outcome(s["source_row"],s["symbol"],s["session_utc"],"OPEN_OR_UNRESOLVED","m1_export_ends_before_signal_entry",s["closed_h1_utc"],entry_t.isoformat(),None,None,None,None,None,None,0)
    bars=[b for b in m1 if entry_t<=b["utc"]<end_t]
    if not bars: return Outcome(s["source_row"],s["symbol"],s["session_utc"],"OPEN_OR_UNRESOLVED","no_m1_bars_in_signal_window",s["closed_h1_utc"],entry_t.isoformat(),None,None,None,None,None,None,0)
    entry=bars[0]["open"]; tp=entry+s["tp"]; sl=entry-s["sl"]; exit_t=exit_p=reason=None
    for b in bars:
        ht=b["high"]>=tp; hs=b["low"]<=sl
        if ht and hs: exit_t,exit_p,reason=b["utc"],sl,"ambiguous_tp_sl_same_m1_bar_conservative_sl"; break
        if hs: exit_t,exit_p,reason=b["utc"],sl,"stop_loss"; break
        if ht: exit_t,exit_p,reason=b["utc"],tp,"take_profit"; break
    if exit_t is None:
        if m1[-1]["utc"]<end_t-timedelta(minutes=1):
            return Outcome(s["source_row"],s["symbol"],s["session_utc"],"OPEN","horizon_not_fully_covered_by_m1_export",s["closed_h1_utc"],entry_t.isoformat(),round(entry,6),round(tp,6),round(sl,6),None,None,None,len(bars))
        last=bars[-1]; exit_t,exit_p,reason=last["utc"],last["close"],"time_exit"
    return Outcome(s["source_row"],s["symbol"],s["session_utc"],"RESOLVED",reason,s["closed_h1_utc"],entry_t.isoformat(),round(entry,6),round(tp,6),round(sl,6),exit_t.isoformat(),round(exit_p,6),round((exit_p-entry)-cost,6),len(bars))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--signals-csv",default=str(DEF_SIG)); ap.add_argument("--m1-csv",default=str(DEF_M1)); ap.add_argument("--server-utc-offset-hours",type=float,default=2.0)
    ap.add_argument("--roundtrip-cost-usd",type=float,default=0.35); ap.add_argument("--out-dir",default=str(DEF_OUT)); ap.add_argument("--no-dedupe",action="store_true")
    a=ap.parse_args(); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    sigs,smeta=load_signals(Path(a.signals_csv).expanduser(),a.server_utc_offset_hours,dedupe=not a.no_dedupe)
    m1,mi=load_m1(Path(a.m1_csv).expanduser(),a.server_utc_offset_hours)
    outs=[resolve(s,m1,mi,a.roundtrip_cost_usd) for s in sigs]
    payload={"tool_version":TOOL_VERSION,"strategy_id":STRATEGY_ID,"generated_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"signals_csv":str(Path(a.signals_csv).expanduser()),"m1_csv":str(Path(a.m1_csv).expanduser()),"server_utc_offset_hours":a.server_utc_offset_hours,"signal_meta":smeta,"m1_load_info":mi,"signals":sigs,"outcomes":[asdict(o) for o in outs]}
    (out/"stage5c_live_outcome_tracker.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    if outs:
        with (out/"stage5c_live_outcomes.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(asdict(outs[0]).keys())); w.writeheader(); [w.writerow(asdict(o)) for o in outs]
    res=[o for o in outs if o.status=="RESOLVED"]; openish=[o for o in outs if o.status!="RESOLVED"]; total=sum(o.net_usd_x1 or 0 for o in res)
    lines=["# Stage 5C Live Dry-run Outcome Tracker v3","",f"Generated UTC: `{payload['generated_utc']}`",f"Tool version: `{TOOL_VERSION}`",f"Strategy ID: `{STRATEGY_ID}`","","> Hard rule: this resolves dry-run signals only. It does not authorize demo, paper, or live orders.","","## Inputs",f"- signals_csv: `{payload['signals_csv']}`",f"- m1_csv: `{payload['m1_csv']}`",f"- server_utc_offset_hours: `{a.server_utc_offset_hours}`","","## M1 load quality",f"- status: `{mi['status']}`",f"- rows_raw: `{mi['rows_raw']}`",f"- rows_parsed: `{mi['rows_parsed']}`",f"- bad_time_rows: `{mi['bad_time_rows']}`",f"- start_utc: `{mi['start_utc']}`",f"- end_utc: `{mi['end_utc']}`","","## Summary",f"- raw_signal_rows: `{smeta['raw_rows']}`",f"- deduped_signals: `{len(sigs)}`",f"- skipped_duplicate_rows: `{smeta['skipped_duplicates']}`",f"- resolved: `{len(res)}`",f"- open_or_unresolved: `{len(openish)}`",f"- total_net_x1_resolved: `{round(total,6)}`","","## Outcomes","| Row | Status | Reason | Session | Closed H1 UTC | Entry UTC | Entry | TP | SL | Exit UTC | Exit | Net x1 |","|---:|---|---|---|---|---|---:|---:|---:|---|---:|---:|"]
    for o in outs: lines.append(f"| {o.source_row} | {o.status} | {o.reason} | {o.session_utc} | {o.closed_h1_utc or ''} | {o.entry_utc or ''} | {'' if o.entry_price is None else o.entry_price} | {'' if o.tp_price is None else o.tp_price} | {'' if o.sl_price is None else o.sl_price} | {o.exit_utc or ''} | {'' if o.exit_price is None else o.exit_price} | {'' if o.net_usd_x1 is None else o.net_usd_x1} |")
    lines+=["","## Decision","- Continue dry-run logging. Do not use this report to place orders."]
    if openish: lines.append("- Some signals are open/unresolved. Check M1 end_utc and export fresh M1 after the required horizon.")
    (out/"stage5c_live_outcome_tracker.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("Stage 5C live dry-run outcome tracker: DONE")
    print(f"raw_rows={smeta['raw_rows']} | deduped_signals={len(sigs)} | m1_rows={mi['rows_parsed']} | resolved={len(res)} | open/unresolved={len(openish)}")
    print(f"M1 range: {mi['start_utc']} -> {mi['end_utc']}")
    print(f"Markdown report: {out/'stage5c_live_outcome_tracker.md'}")
if __name__=="__main__": main()
