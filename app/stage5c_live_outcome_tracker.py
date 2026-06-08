#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from dataclasses import dataclass,asdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Optional,Sequence,List
TOOL_VERSION='v1'; STRATEGY_ID='xauusd_long_tp24_sl15_no_london_v1'
DEFAULT_SIGNALS=Path('~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv').expanduser()
DEFAULT_M1=Path('~/Downloads/amarkets_xauusd_1m.csv').expanduser(); DEFAULT_OUT_DIR=Path('data/reports/stage5c_live_outcome_tracker')
def parse_time(s):
    if not s: return None
    s=str(s).strip()
    for fmt in ['%Y.%m.%d %H:%M:%S','%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S','%Y-%m-%dT%H:%M:%SZ']:
        try: return datetime.strptime(s,fmt).replace(tzinfo=timezone.utc)
        except Exception: pass
    try: return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception: return None
def ffloat(v,d=0.0):
    try:
        s=str(v).strip(); return float(s) if s else d
    except Exception: return d
def delim(text): return '\t' if text[:4096].count('\t')>=text[:4096].count(',') else ','
def read_csv(path):
    p=Path(path)
    if not p.exists(): return []
    text=p.read_text(encoding='utf-8-sig',errors='replace')
    if not text.strip(): return []
    return [{str(k).strip():('' if v is None else str(v).strip()) for k,v in r.items() if k is not None} for r in csv.DictReader(text.splitlines(),delimiter=delim(text))]
def infer_ohlc(rows):
    if not rows: return {}
    keys={k.lower().strip('<>').replace(' ','').replace('_',''):k for k in rows[0].keys()}
    def pick(cs):
        for c in cs:
            key=c.lower().strip('<>').replace(' ','').replace('_','')
            if key in keys: return keys[key]
        return None
    return {'time':pick(['time','datetime','date','timestamp','gmt','timegmt']),'open':pick(['open']),'high':pick(['high']),'low':pick(['low']),'close':pick(['close'])}
@dataclass
class Signal:
    row_index:int; logged_at_utc:Optional[datetime]; closed_h1_utc:Optional[datetime]; symbol:str; session_utc:str; close_h1:float; sma10:float; distance_usd:float; tp_usd:float; sl_usd:float; horizon_h1_bars:int; dry_run_only:str
@dataclass
class Outcome:
    row_index:int; symbol:str; session_utc:str; status:str; reason:str; closed_h1_utc:Optional[str]; entry_utc:Optional[str]; entry_price:Optional[float]; tp_price:Optional[float]; sl_price:Optional[float]; exit_utc:Optional[str]; exit_price:Optional[float]; net_usd_x1:Optional[float]; bars_checked_m1:int
def read_signals(path):
    out=[]
    for i,r in enumerate(read_csv(path),1):
        if r.get('strategy_id') and r.get('strategy_id')!=STRATEGY_ID: continue
        out.append(Signal(i,parse_time(r.get('logged_at_gmt','')),parse_time(r.get('signal_closed_h1_time_gmt_now','') or r.get('closed_h1_time_utc','')),r.get('symbol',''),r.get('session_utc',''),ffloat(r.get('close_h1')),ffloat(r.get('sma10')),ffloat(r.get('distance_usd')),ffloat(r.get('tp_usd'),24.0),ffloat(r.get('sl_usd'),15.0),int(ffloat(r.get('time_exit_h1_bars'),12.0)),r.get('dry_run_only','').lower()))
    return out
def read_m1(path,offset_hours):
    rows=read_csv(path); cols=infer_ohlc(rows)
    if not rows or any(not cols.get(k) for k in ['time','open','high','low','close']): return []
    off=timedelta(hours=offset_hours); out=[]
    for r in rows:
        t=parse_time(r.get(cols['time'],''))
        if t is None: continue
        out.append({'utc':(t-off).astimezone(timezone.utc),'open':ffloat(r.get(cols['open'])),'high':ffloat(r.get(cols['high'])),'low':ffloat(r.get(cols['low'])),'close':ffloat(r.get(cols['close']))})
    return sorted(out,key=lambda b:b['utc'])
def resolve(sig,m1,cost):
    if sig.closed_h1_utc is None: return Outcome(sig.row_index,sig.symbol,sig.session_utc,'UNRESOLVED','missing_closed_h1_time',None,None,None,None,None,None,None,None,0)
    entry=sig.closed_h1_utc+timedelta(hours=1); end=entry+timedelta(hours=sig.horizon_h1_bars)
    if not m1: return Outcome(sig.row_index,sig.symbol,sig.session_utc,'UNRESOLVED','missing_m1_data',sig.closed_h1_utc.isoformat(),entry.isoformat(),None,None,None,None,None,None,0)
    bars=[b for b in m1 if entry<=b['utc']<end]
    if not bars:
        reason='m1_export_ends_before_signal_entry' if m1[-1]['utc']<entry else 'm1_export_does_not_cover_signal_window'
        return Outcome(sig.row_index,sig.symbol,sig.session_utc,'OPEN_OR_UNRESOLVED',reason,sig.closed_h1_utc.isoformat(),entry.isoformat(),None,None,None,None,None,None,0)
    ep=bars[0]['open']; tp=ep+sig.tp_usd; sl=ep-sig.sl_usd; exit_t=exit_p=reason=None
    for b in bars:
        hit_tp=b['high']>=tp; hit_sl=b['low']<=sl
        if hit_tp and hit_sl: exit_t=b['utc']; exit_p=sl; reason='ambiguous_tp_sl_same_m1_bar_conservative_sl'; break
        if hit_sl: exit_t=b['utc']; exit_p=sl; reason='stop_loss'; break
        if hit_tp: exit_t=b['utc']; exit_p=tp; reason='take_profit'; break
    if exit_t is None:
        if m1[-1]['utc']<end-timedelta(minutes=1): return Outcome(sig.row_index,sig.symbol,sig.session_utc,'OPEN','horizon_not_fully_covered_by_m1_export',sig.closed_h1_utc.isoformat(),entry.isoformat(),round(ep,6),round(tp,6),round(sl,6),None,None,None,len(bars))
        last=bars[-1]; exit_t=last['utc']; exit_p=last['close']; reason='time_exit'
    net=(exit_p-ep)-cost
    return Outcome(sig.row_index,sig.symbol,sig.session_utc,'RESOLVED',reason,sig.closed_h1_utc.isoformat(),entry.isoformat(),round(ep,6),round(tp,6),round(sl,6),exit_t.isoformat(),round(exit_p,6),round(net,6),len(bars))
def write(out,signals_path,m1_path,outcomes,offset):
    out.mkdir(parents=True,exist_ok=True); data={'tool_version':TOOL_VERSION,'strategy_id':STRATEGY_ID,'generated_utc':datetime.now(timezone.utc).replace(microsecond=0).isoformat(),'signals_csv':str(signals_path),'m1_csv':str(m1_path),'server_utc_offset_hours':offset,'outcomes':[asdict(o) for o in outcomes]}
    (out/'stage5c_live_outcome_tracker.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    if outcomes:
        with (out/'stage5c_live_outcomes.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(asdict(outcomes[0]).keys())); w.writeheader(); [w.writerow(asdict(o)) for o in outcomes]
    res=[o for o in outcomes if o.status=='RESOLVED']; op=[o for o in outcomes if o.status!='RESOLVED']; total=sum(o.net_usd_x1 or 0 for o in res)
    lines=['# Stage 5C Live Dry-run Outcome Tracker','',f"Generated UTC: `{data['generated_utc']}`",f'Tool version: `{TOOL_VERSION}`',f'Strategy ID: `{STRATEGY_ID}`','', '> Hard rule: this resolves dry-run signals only. It does not authorize demo, paper, or live orders.','', '## Inputs',f'- signals_csv: `{signals_path}`',f'- m1_csv: `{m1_path}`',f'- server_utc_offset_hours: `{offset}`','', '## Summary',f'- signals: `{len(outcomes)}`',f'- resolved: `{len(res)}`',f'- open_or_unresolved: `{len(op)}`',f'- total_net_x1_resolved: `{round(total,6)}`','', '## Outcomes','| Row | Status | Reason | Session | Entry UTC | Entry | Exit UTC | Exit | Net x1 |','|---|---|---|---|---|---:|---|---:|---:|']
    for o in outcomes: lines.append(f'| {o.row_index} | {o.status} | {o.reason} | {o.session_utc} | {o.entry_utc or ""} | {o.entry_price if o.entry_price is not None else ""} | {o.exit_utc or ""} | {o.exit_price if o.exit_price is not None else ""} | {o.net_usd_x1 if o.net_usd_x1 is not None else ""} |')
    lines+=['','## Decision','- Continue dry-run logging. Do not use this report to place orders.']
    if op: lines.append('- Some signals are open/unresolved. Export fresh M1 data after the 12-hour horizon and rerun this tracker.')
    (out/'stage5c_live_outcome_tracker.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--signals-csv',default=str(DEFAULT_SIGNALS)); ap.add_argument('--m1-csv',default=str(DEFAULT_M1)); ap.add_argument('--server-utc-offset-hours',type=float,default=2.0); ap.add_argument('--roundtrip-cost-usd',type=float,default=0.35); ap.add_argument('--out-dir',default=str(DEFAULT_OUT_DIR)); a=ap.parse_args()
    sigs=read_signals(Path(a.signals_csv).expanduser()); m1=read_m1(Path(a.m1_csv).expanduser(),a.server_utc_offset_hours); outcomes=[resolve(s,m1,a.roundtrip_cost_usd) for s in sigs]; out=Path(a.out_dir); write(out,Path(a.signals_csv).expanduser(),Path(a.m1_csv).expanduser(),outcomes,a.server_utc_offset_hours)
    print('Stage 5C live dry-run outcome tracker: DONE'); print(f'Signals: {len(sigs)} | resolved={sum(1 for o in outcomes if o.status=="RESOLVED")} | open/unresolved={sum(1 for o in outcomes if o.status!="RESOLVED")}'); print(f'Markdown report: {out/"stage5c_live_outcome_tracker.md"}'); print(f'CSV outcomes: {out/"stage5c_live_outcomes.csv"}')
if __name__=='__main__': main()
