#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,math,statistics,time,re
from pathlib import Path
from datetime import datetime,timezone
from typing import Any,Dict,List,Optional,Tuple

STAGE='Stage135B_SCHEMA_ADAPTIVE_DEMO_PROBE_DISCOVERY'
STATUS='STAGE135B_COMPLETE_SCHEMA_ADAPTIVE_DEMO_PROBE_DISCOVERY_READY'
DEFAULT_DATASET='data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv'
DEFAULT_MT5_FILES='/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files'
KV_FILE='xauusd_stage135b_demo_probe_rule_state_kv.csv'
LATEST_FILE='xauusd_stage135b_demo_probe_rule_state_latest.csv'
HISTORY_FILE='xauusd_stage135b_demo_probe_rule_state_history.csv'
EXCLUDE_RE=re.compile(r'(ret|return|future|fwd|target|open|high|low|close|volume|spread|time|date|symbol|source|timeframe|label|decision|status|rule)',re.I)
RET_ALIASES=['fwd_ret_bps_h120','fwd_return_bps_h120','forward_ret_bps_h120','ret_bps_h120','fwd_ret_bps_120h','return_bps_h120']
DATE_ALIASES=['feature_date','utc_time','time','date','timestamp','bar_time']

def utc_now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def ensure(p:Path): p.mkdir(parents=True,exist_ok=True); return p
def pf(v):
    try:
        if v is None: return None
        s=str(v).strip()
        if not s or s.lower() in {'nan','none','null'}: return None
        x=float(s)
        return x if math.isfinite(x) else None
    except Exception: return None

def pdate(v):
    if v is None: return None
    s=str(v).strip().replace('Z','+00:00')
    if not s: return None
    try:
        dt=datetime.fromisoformat(s)
    except Exception:
        try: dt=datetime.strptime(s[:10],'%Y-%m-%d')
        except Exception: return None
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def find_col(cols,names):
    low={c.lower():c for c in cols}
    for n in names:
        if n.lower() in low: return low[n.lower()]
    for c in cols:
        for n in names:
            if n.lower() in c.lower(): return c
    return None

def choose_ret_col(cols):
    c=find_col(cols,RET_ALIASES)
    if c: return c
    cand=[]
    for col in cols:
        lc=col.lower()
        if ('ret' in lc or 'return' in lc) and ('bps' in lc or 'h120' in lc or '120' in lc or 'fwd' in lc): cand.append(col)
    return cand[0] if cand else None

def choose_date_col(cols): return find_col(cols,DATE_ALIASES)
def q(vals,qq):
    vals=sorted(x for x in vals if x is not None and math.isfinite(x))
    if not vals: return None
    i=(len(vals)-1)*qq; lo=math.floor(i); hi=math.ceil(i)
    return vals[lo] if lo==hi else vals[lo]*(hi-i)+vals[hi]*(i-lo)

def load_rows(path:Path,max_rows:int=0):
    with path.open('r',encoding='utf-8',errors='replace',newline='') as f: rows=[dict(r) for r in csv.DictReader(f)]
    return rows[-max_rows:] if max_rows and len(rows)>max_rows else rows

def split_rows(rows,date_col):
    if date_col: rows=sorted(rows,key=lambda r:pdate(r.get(date_col)) or datetime.min.replace(tzinfo=timezone.utc))
    n=len(rows); return rows[:int(n*.6)], rows[int(n*.6):int(n*.8)], rows[int(n*.8):]

def usable_numeric_cols(rows,ret_col,date_col,min_nonnull=100):
    cols=list(rows[0].keys()); out=[]
    for c in cols:
        if c==ret_col or c==date_col or EXCLUDE_RE.search(c): continue
        vals=[pf(r.get(c)) for r in rows]
        vals=[v for v in vals if v is not None]
        if len(vals)>=min(min_nonnull,max(10,len(rows)//50)) and len(set(round(v,8) for v in vals))>=5: out.append(c)
    return out

def eval_condition(rows,ret_col,col,op,thr):
    rets=[]; total=0
    for r in rows:
        v=pf(r.get(col)); ret=pf(r.get(ret_col))
        if v is None or ret is None: continue
        ok=(v<=thr) if op=='<=' else (v>=thr)
        if ok: total+=1; rets.append(ret)
    if not rets: return {'events':0,'mean_bps':0.0,'hit_rate':0.0,'median_bps':0.0}
    return {'events':len(rets),'mean_bps':round(statistics.fmean(rets),4),'hit_rate':round(sum(1 for x in rets if x>0)/len(rets),4),'median_bps':round(statistics.median(rets),4)}

def active_now(latest,col,op,thr):
    v=pf(latest.get(col))
    if v is None: return False
    return v<=thr if op=='<=' else v>=thr

def scan(rows,ret_col,date_col,min_events,min_mean,min_hit,max_candidates):
    sel,val,tail=split_rows(rows,date_col); latest=rows[-1]
    cols=usable_numeric_cols(sel,ret_col,date_col)
    scores=[]
    for col in cols:
        vals=[pf(r.get(col)) for r in sel]; vals=[v for v in vals if v is not None]
        for qq in [.15,.25,.35,.50,.65,.75,.85]:
            thr=q(vals,qq)
            if thr is None: continue
            for op in ['<=','>=']:
                sm=eval_condition(sel,ret_col,col,op,thr); vm=eval_condition(val,ret_col,col,op,thr); tm=eval_condition(tail,ret_col,col,op,thr)
                gate=(vm['events']>=min_events and vm['mean_bps']>=min_mean and vm['hit_rate']>=min_hit and tm['events']>=max(3,min_events//3) and tm['mean_bps']>=min_mean*.25 and tm['hit_rate']>=min_hit*.9)
                cur=active_now(latest,col,op,thr)
                rid='D135B_'+re.sub('[^A-Za-z0-9]+','_',col).strip('_')[:32]+'_'+('LE' if op=='<=' else 'GE')+str(int(qq*100))
                scores.append({'rule_id':rid,'label':f'{col} {op} q{qq:.2f}','gate':'PASS' if gate else 'WATCH_OR_REJECT','current_active':cur,'feature_col':col,'op':op,'threshold':round(thr,8),'selection_events':sm['events'],'selection_mean_bps':sm['mean_bps'],'selection_hit_rate':sm['hit_rate'],'validation_events':vm['events'],'validation_mean_bps':vm['mean_bps'],'validation_hit_rate':vm['hit_rate'],'tail_events':tm['events'],'tail_mean_bps':tm['mean_bps'],'tail_hit_rate':tm['hit_rate']})
    scores.sort(key=lambda r:(r['gate']=='PASS' and r['current_active'],r['validation_mean_bps'],r['tail_mean_bps'],r['validation_events']),reverse=True)
    return scores[:max_candidates], cols

def write_csv(path,rows,fields):
    ensure(path.parent); tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); [w.writerow({k:r.get(k,'') for k in fields}) for r in rows]
    tmp.replace(path)

def append_csv(path,rows,fields):
    ensure(path.parent); exists=path.exists() and path.stat().st_size>0
    with path.open('a',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        if not exists: w.writeheader()
        [w.writerow({k:r.get(k,'') for k in fields}) for r in rows]

def write_kv(path,kv):
    ensure(path.parent); tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        for k,v in kv.items(): f.write(f'{k}|{v if v is not None else ""}\n')
    tmp.replace(path)

def run(root:Path,dataset:Path,mt5_files:Path,max_rows:int,min_events:int,min_mean_bps:float,min_hit:float,max_feature_age_days:int,write_mt5:bool,max_candidates:int):
    root=root.expanduser(); dataset=dataset.expanduser(); mt5_files=mt5_files.expanduser()
    if not dataset.is_absolute(): dataset=root/dataset
    out=ensure(root/'reports/stage135b_schema_adaptive_demo_probe_discovery'); data=ensure(root/'data/demo_execution')
    gen=utc_now()
    if not dataset.exists():
        summary={'stage':STAGE,'generated_utc':gen,'status':STATUS,'decision':'STAGE135B_DATASET_MISSING','dataset':str(dataset)}; (out/'stage135b_schema_adaptive_demo_probe_discovery_summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2)); return summary
    rows=load_rows(dataset,max_rows); cols=list(rows[0].keys()) if rows else []
    ret_col=choose_ret_col(cols); date_col=choose_date_col(cols)
    if not rows or not ret_col:
        summary={'stage':STAGE,'generated_utc':gen,'status':STATUS,'decision':'STAGE135B_SCHEMA_BLOCKED_NO_RETURN_COLUMN','dataset':str(dataset),'columns':cols[:300]}; (out/'stage135b_schema_adaptive_demo_probe_discovery_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)); print(json.dumps(summary,indent=2,ensure_ascii=False)); return summary
    scores,feature_cols=scan(rows,ret_col,date_col,min_events,min_mean_bps,min_hit,max_candidates)
    latest=rows[-1]; latest_date=latest.get(date_col,'') if date_col else ''
    reason='no current-active PASS candidate'
    selected=None
    latest_dt=pdate(latest_date) if latest_date else None
    if latest_dt and (datetime.now(timezone.utc)-latest_dt).total_seconds()/86400>max_feature_age_days: reason=f'latest feature too old: {latest_date}'
    else:
        for r in scores:
            if r['gate']=='PASS' and r['current_active']:
                selected=r; reason='selected schema-adaptive current-active PASS candidate'; break
    if selected:
        decision='STAGE135B_DEMO_PROBE_SIGNAL_READY_POINT_STAGE134_TO_STAGE135B_FILE'; any_active='true'; rid=selected['rule_id']; label=selected['label']; active_count='1'
    else:
        decision='STAGE135B_NO_DEMO_PROBE_SIGNAL_BROAD_DISCOVERY_REQUIRED'; any_active='false'; rid=''; label=''; active_count='0'
    kv={'stage':'Stage135B_SCHEMA_ADAPTIVE_DEMO_PROBE_DISCOVERY','status':'DEMO_PROBE_RULE_STATE_ALIVE_NO_ORDER_SEND_IN_STAGE135B','decision':decision,'reason':reason,'mode':'DEMO_PROBE_DISCOVERY_TO_STAGE134','feature_date':latest_date,'any_signal_active':any_active,'selected_rule_id':rid,'selected_label':label,'execution_allowed':'false','order_authorized':'false','rule_count':len(scores),'active_rule_count':active_count,'allow_trading':'false','order_send':'false','stage134_required_InpRuleStateKvFile':KV_FILE,'stage134_required_InpAllowedRules':rid,'note':'Stage135B writes rule-state only; Stage134 executes demo only if manually pointed here'}
    score_fields=['rule_id','label','gate','current_active','feature_col','op','threshold','selection_events','selection_mean_bps','selection_hit_rate','validation_events','validation_mean_bps','validation_hit_rate','tail_events','tail_mean_bps','tail_hit_rate']
    write_csv(out/'stage135b_candidate_scores.csv',scores,score_fields)
    latest_row={'time_utc':gen,'rule_id':rid,'rule_active':any_active,'feature_date':latest_date,'selected_label':label,'decision':decision,'reason':reason,'allow_trading':'false','order_send':'false'}
    write_csv(data/LATEST_FILE,[latest_row],list(latest_row.keys())); append_csv(data/HISTORY_FILE,[latest_row],list(latest_row.keys())); write_kv(data/KV_FILE,kv)
    mt5_kv=mt5_latest=''
    if write_mt5:
        mt5_kv=str(mt5_files/KV_FILE); mt5_latest=str(mt5_files/LATEST_FILE); write_kv(Path(mt5_kv),kv); write_csv(Path(mt5_latest),[latest_row],list(latest_row.keys())); append_csv(mt5_files/HISTORY_FILE,[latest_row],list(latest_row.keys()))
    summary={'stage':STAGE,'generated_utc':gen,'status':STATUS,'decision':decision,'root':str(root),'dataset':str(dataset),'dataset_rows':len(rows),'ret_col':ret_col,'date_col':date_col,'latest_feature_date':latest_date,'numeric_feature_cols_scanned':len(feature_cols),'candidate_rows':len(scores),'selected_rule_id':rid,'selected_label':label,'select_reason':reason,'stage134_instruction':{'InpRuleStateKvFile':KV_FILE,'InpAllowedRules':rid,'keep_InpEnableDemoOrders':'true only on demo account','restore_after_probe':'xauusd_stage133_unified_observer_rule_state_kv.csv'},'score_csv':str(out/'stage135b_candidate_scores.csv'),'repo_kv':str(data/KV_FILE),'repo_latest':str(data/LATEST_FILE),'mt5_kv_written':write_mt5,'mt5_kv':mt5_kv,'mt5_latest':mt5_latest,'summary_json':str(out/'stage135b_schema_adaptive_demo_probe_discovery_summary.json'),'next':['If selected_rule_id is non-empty, point Stage134 InpRuleStateKvFile to xauusd_stage135b_demo_probe_rule_state_kv.csv and InpAllowedRules to selected_rule_id.','If selected_rule_id is empty, do not wait; run broad thesis discovery/repair.']}
    (out/'stage135b_schema_adaptive_demo_probe_discovery_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8'); print(json.dumps(summary,indent=2,ensure_ascii=False)); return summary

def main():
    ap=argparse.ArgumentParser(description=STAGE); ap.add_argument('--root',default='/Users/vahid/Desktop/xauusd-trader'); ap.add_argument('--dataset',default=DEFAULT_DATASET); ap.add_argument('--mt5-files',default=DEFAULT_MT5_FILES); ap.add_argument('--max-rows',type=int,default=0); ap.add_argument('--min-events',type=int,default=20); ap.add_argument('--min-mean-bps',type=float,default=5.0); ap.add_argument('--min-hit',type=float,default=.52); ap.add_argument('--max-feature-age-days',type=int,default=10); ap.add_argument('--max-candidates',type=int,default=500); ap.add_argument('--write-mt5',action='store_true')
    a=ap.parse_args(); run(Path(a.root),Path(a.dataset),Path(a.mt5_files),a.max_rows,a.min_events,a.min_mean_bps,a.min_hit,a.max_feature_age_days,a.write_mt5,a.max_candidates); return 0
if __name__=='__main__': raise SystemExit(main())
