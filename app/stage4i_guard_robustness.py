#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,math
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Dict,Sequence,Optional,List
STRATEGY_ID='xauusd_long_tp24_sl15_no_london_v1'; TOOL_VERSION='v1'
DEFAULT_OFFSET2=Path('data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv')
DEFAULT_OFFSET3=Path('data/reports/stage4g_v2_offset3/stage4g_v2_non_overlap_trades.csv')
DEFAULT_OUT_DIR=Path('data/reports/stage4i_guard_robustness')
GUARDS={
 'base_all':{'include':[],'exclude':[]},
 'no_asia':{'include':[],'exclude':['asia']},
 'overlap_newyork_other':{'include':['london_ny_overlap','new_york','other'],'exclude':[]},
 'london_ny_overlap_only':{'include':['london_ny_overlap'],'exclude':[]},
 'new_york_only':{'include':['new_york'],'exclude':[]},
 'other_only':{'include':['other'],'exclude':[]},
 'overlap_other':{'include':['london_ny_overlap','other'],'exclude':[]},
 'new_york_other':{'include':['new_york','other'],'exclude':[]},
}
@dataclass
class Metrics:
    trades:int; total_net_usd:float; avg_net_usd:float; median_net_usd:float; win_rate:float; profit_factor:float; max_drawdown_usd:float; best_net_usd:float; worst_net_usd:float
@dataclass
class GuardResult:
    guard:str; offset_label:str; status:str; include_sessions:List[str]; exclude_sessions:List[str]; metrics:Metrics; cost_stress:Dict[str,Metrics]; flags:List[str]
def pf(vals):
    g=sum(v for v in vals if v>0); l=-sum(v for v in vals if v<0)
    return (float('inf') if g>0 else 0.0) if l<=1e-12 else g/l
def med(vals):
    if not vals: return 0.0
    xs=sorted(vals); n=len(xs); m=n//2
    return xs[m] if n%2 else (xs[m-1]+xs[m])/2
def dd(vals):
    eq=peak=maxdd=0.0
    for v in vals:
        eq+=v; peak=max(peak,eq); maxdd=min(maxdd,eq-peak)
    return maxdd
def metrics(vals):
    vals=list(vals)
    if not vals: return Metrics(0,0,0,0,0,0,0,0,0)
    n=len(vals); total=sum(vals); p=pf(vals)
    return Metrics(n,round(total,6),round(total/n,6),round(med(vals),6),round(sum(1 for v in vals if v>0)/n,6),round(p,6) if math.isfinite(p) else p,round(dd(vals),6),round(max(vals),6),round(min(vals),6))
def ffloat(v):
    try: return float(str(v).strip())
    except Exception: return 0.0
def read(path):
    text=Path(path).read_text(encoding='utf-8-sig',errors='replace')
    delim='\t' if text[:4096].count('\t')>=text[:4096].count(',') else ','
    return [{str(k).strip():('' if v is None else str(v).strip()) for k,v in r.items() if k is not None} for r in csv.DictReader(text.splitlines(),delimiter=delim)]
def infer(rows,cands):
    keys={k.lower():k for k in rows[0].keys()}
    for c in cands:
        if c.lower() in keys: return keys[c.lower()]
    return None
def eval_guard(name,rows,label,session_col,net_col,cost):
    spec=GUARDS[name]; inc=set(spec['include']); exc=set(spec['exclude']); vals=[]
    for r in rows:
        s=r.get(session_col,'')
        if inc and s not in inc: continue
        if exc and s in exc: continue
        vals.append(ffloat(r.get(net_col,0)))
    m=metrics(vals); stress={}
    for x in [1,2,3,4]: stress[f'cost_x{x}']=metrics([v-(x-1)*cost for v in vals])
    flags=[]
    if m.trades<50: flags.append('low_trade_count')
    if m.total_net_usd<=0: flags.append('nonpositive_total')
    if m.profit_factor<1.10: flags.append('pf_below_1_10')
    if m.median_net_usd<0: flags.append('negative_median')
    if stress['cost_x3'].total_net_usd<=0 or stress['cost_x3'].profit_factor<=1.0: flags.append('cost_x3_not_positive')
    if stress['cost_x4'].total_net_usd<=0 or stress['cost_x4'].profit_factor<=1.0: flags.append('cost_x4_not_positive')
    severe=[f for f in flags if f!='negative_median']
    status='PASS' if not flags else ('FAIL' if 'nonpositive_total' in severe else 'WARN')
    return GuardResult(name,label,status,list(spec['include']),list(spec['exclude']),m,stress,flags)
def consensus(results):
    out=[]
    for g,by in results.items():
        vals=list(by.values())
        min_pf=min(v.metrics.profit_factor for v in vals); min_total=min(v.metrics.total_net_usd for v in vals); min_c3=min(v.cost_stress['cost_x3'].total_net_usd for v in vals); min_c4=min(v.cost_stress['cost_x4'].total_net_usd for v in vals); max_dd=max(abs(v.metrics.max_drawdown_usd) for v in vals); min_tr=min(v.metrics.trades for v in vals); min_med=min(v.metrics.median_net_usd for v in vals)
        flags=[]
        if min_tr<100: flags.append('low_min_trades')
        if min_total<=0: flags.append('not_positive_both_offsets')
        if min_pf<1.10: flags.append('pf_below_1_10_one_offset')
        if min_c3<=0: flags.append('cost_x3_not_positive_both_offsets')
        if min_c4<=0: flags.append('cost_x4_not_positive_one_offset')
        if min_med<0: flags.append('negative_median_one_offset')
        status='ROBUST_CANDIDATE'
        if any(f in flags for f in ['not_positive_both_offsets','pf_below_1_10_one_offset','cost_x3_not_positive_both_offsets']): status='WEAK'
        elif flags: status='PROMISING_WITH_WARNINGS'
        score=min_pf*100+max(0,min_c3)/10+max(0,min_c4)/20-max_dd/25+min(min_tr,500)/20
        out.append({'guard':g,'status':status,'score':round(score,3),'min_trades':min_tr,'min_total_net_usd':round(min_total,6),'min_pf':round(min_pf,6),'min_median':round(min_med,6),'min_cost_x3_total':round(min_c3,6),'min_cost_x4_total':round(min_c4,6),'max_abs_drawdown':round(max_dd,6),'flags':flags})
    return sorted(out,key=lambda r:r['score'],reverse=True)
def table(headers,rows):
    lines=['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']
    for row in rows: lines.append('| '+' | '.join(str(x) for x in row)+' |')
    return lines
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--offset2-trades',default=str(DEFAULT_OFFSET2)); ap.add_argument('--offset3-trades',default=str(DEFAULT_OFFSET3)); ap.add_argument('--out-dir',default=str(DEFAULT_OUT_DIR)); ap.add_argument('--roundtrip-cost-usd',type=float,default=0.35); a=ap.parse_args()
    paths={'offset2':Path(a.offset2_trades),'offset3':Path(a.offset3_trades)}; results={g:{} for g in GUARDS}
    for label,path in paths.items():
        rows=read(path)
        if not rows: raise SystemExit(f'No rows parsed: {path}')
        sc=infer(rows,['session_utc','session','session_name']); nc=infer(rows,['net_usd','net','pnl_usd','profit_usd'])
        if not sc or not nc: raise SystemExit(f'Could not infer session/net columns from {path}. Columns={list(rows[0].keys())}')
        for g in GUARDS: results[g][label]=eval_guard(g,rows,label,sc,nc,a.roundtrip_cost_usd)
    cons=consensus(results); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    payload={'tool_version':TOOL_VERSION,'strategy_id':STRATEGY_ID,'generated_utc':datetime.now(timezone.utc).replace(microsecond=0).isoformat(),'inputs':{k:str(v) for k,v in paths.items()},'results':{g:{o:asdict(r) for o,r in by.items()} for g,by in results.items()},'consensus':cons}
    (out/'stage4i_guard_robustness.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    lines=['# Stage 4I Guard Robustness Comparator','',f"Generated UTC: `{payload['generated_utc']}`",f'Tool version: `{TOOL_VERSION}`',f'Strategy ID: `{STRATEGY_ID}`','', '> Hard rule: this is guard robustness research only. It does not authorize demo, paper, or live orders.','', '## Critical interpretation','- Stage 4G v2 non-overlap remains the replay basis.','- A guard must be reasonably stable across both server UTC offset assumptions.','- Do not change the current live dry-run EA ad hoc. A strategy change requires a new locked strategy version.','', '## Consensus ranking']
    lines+=table(['Rank','Guard','Status','Score','Min trades','Min total','Min PF','Min median','Min cost x3','Min cost x4','Max |DD|','Flags'],[[i+1,r['guard'],r['status'],r['score'],r['min_trades'],r['min_total_net_usd'],r['min_pf'],r['min_median'],r['min_cost_x3_total'],r['min_cost_x4_total'],r['max_abs_drawdown'],', '.join(r['flags'])] for i,r in enumerate(cons)])
    lines+=['','## Per-offset details']
    for g in GUARDS:
        lines+=[f'### {g}']
        lines+=table(['Offset','Status','Trades','Total','PF','Median','Max DD','Cost x3 total','Cost x4 total','Flags'],[[off,res.status,res.metrics.trades,res.metrics.total_net_usd,res.metrics.profit_factor,res.metrics.median_net_usd,res.metrics.max_drawdown_usd,res.cost_stress['cost_x3'].total_net_usd,res.cost_stress['cost_x4'].total_net_usd,', '.join(res.flags)] for off,res in results[g].items()])
        lines.append('')
    top=cons[0] if cons else None; lines+=['## Decision']
    if top: lines.append(f"- Top guard by robustness score: `{top['guard']}` with status `{top['status']}`.")
    lines.append('- No demo-order authorization. Continue live dry-run and run deeper exact validation before any EA change.')
    (out/'stage4i_guard_robustness.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Stage 4I guard robustness comparator: DONE')
    if top: print(f"Top guard: {top['guard']} | status={top['status']} | score={top['score']}")
    print(f"Markdown report: {out/'stage4i_guard_robustness.md'}")
if __name__=='__main__': main()
