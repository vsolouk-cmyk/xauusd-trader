
#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, math, statistics, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE='Stage135_DEMO_PROBE_RULE_DISCOVERY'
STATUS='STAGE135_COMPLETE_DEMO_PROBE_RULE_DISCOVERY_READY'
DEFAULT_DATASET='data/fundamental_event_inbox/features/stage117_joined_macro_cot_dollar_h1_research_dataset.csv'
DEFAULT_MT5_FILES='/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files'
KV_FILE='xauusd_stage135_demo_probe_rule_state_kv.csv'
LATEST_FILE='xauusd_stage135_demo_probe_rule_state_latest.csv'
HISTORY_FILE='xauusd_stage135_demo_probe_rule_state_history.csv'
RISK_BLOCKS=['DEMO_ONLY_PROBE','NO_REAL_ACCOUNT_AUTHORIZATION','NO_ORDER_SEND_IN_STAGE135','STAGE134_EXECUTES_ONLY_IF_MANUALLY_POINTED_TO_STAGE135_FILE','FEATURE_AGE_GUARD','VALIDATION_METRICS_REQUIRED','FAST_RETURN_TO_DISCOVERY_IF_DEMO_NEGATIVE']

def utc_now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def ensure_dir(p:Path)->Path: p.mkdir(parents=True,exist_ok=True); return p
def parse_float(v:Any)->Optional[float]:
    if v is None: return None
    s=str(v).strip()
    if not s or s.lower() in {'nan','none','null'}: return None
    try: x=float(s)
    except Exception: return None
    return None if math.isnan(x) or math.isinf(x) else x

def parse_date(v:Any)->Optional[datetime]:
    if v is None: return None
    s=str(v).strip().replace('Z','+00:00')
    if not s: return None
    for cand in [s, s[:19], s[:10]]:
        try:
            dt=datetime.fromisoformat(cand)
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception: pass
    return None

def load_rows(path:Path,max_rows:int=0)->List[Dict[str,str]]:
    with path.open('r',encoding='utf-8',errors='replace',newline='') as f: rows=[dict(r) for r in csv.DictReader(f)]
    return rows[-max_rows:] if max_rows and len(rows)>max_rows else rows

def find_col(cols:Iterable[str], aliases:List[str])->Optional[str]:
    lower={c.lower():c for c in cols}
    for a in aliases:
        if a.lower() in lower: return lower[a.lower()]
    for c in cols:
        lc=c.lower()
        for a in aliases:
            if a.lower() in lc: return c
    return None

def get_ret_col(cols): return find_col(cols,['fwd_ret_bps_h120','forward_ret_bps_h120','fwd_return_bps_h120','ret_bps_h120','fwd_ret_bps_120h','return_bps_h120'])
def get_date_col(cols): return find_col(cols,['feature_date','utc_time','time','date','timestamp','bar_time'])

def quantile(values:List[float],q:float)->Optional[float]:
    vals=sorted(v for v in values if v is not None and not math.isnan(v))
    if not vals: return None
    idx=(len(vals)-1)*q; lo=math.floor(idx); hi=math.ceil(idx)
    if lo==hi: return vals[int(idx)]
    return vals[lo]*(hi-idx)+vals[hi]*(idx-lo)

class RuleSpec:
    def __init__(self,rule_id,label,aliases,fn): self.rule_id=rule_id; self.label=label; self.aliases=aliases; self.fn=fn
    def bind(self,cols):
        out={}
        for k,als in self.aliases.items():
            c=find_col(cols,als)
            if not c: return None
            out[k]=c
        return out

RULES=[
 RuleSpec('D135_01_DXY_RELIEF_GOLD_TREND_PROBE','DXY relief with non-negative gold trend',{'dxy20':['dxy_ret_20d','dxy_change_20d','dxy_20d_ret'],'goldtrend':['gold_sma20_over_50','xau_sma20_over_50','gold_trend_20_50']},'r1'),
 RuleSpec('D135_02_REALYIELD_RELIEF_PROBE','Real-yield relief / not tightening',{'ry20':['real_yield_change_20d','real_yield_20d_change','real_yield_delta_20d'],'goldtrend':['gold_sma20_over_50','xau_sma20_over_50','gold_trend_20_50']},'r2'),
 RuleSpec('D135_03_DXY_AND_RY_NOT_HOSTILE_PROBE','DXY and real yield not hostile',{'dxy20':['dxy_ret_20d','dxy_change_20d','dxy_20d_ret'],'ry20':['real_yield_change_20d','real_yield_20d_change','real_yield_delta_20d']},'r3'),
 RuleSpec('D135_04_COT_DECROWDING_NOT_RY_HOSTILE_PROBE','COT decrowding with real yield not hostile',{'cotchg':['cot_mm_net_z_change_4w','mm_net_z_change_4w','cot_z_change_4w'],'ry20':['real_yield_change_20d','real_yield_20d_change','real_yield_delta_20d']},'r4'),
 RuleSpec('D135_05_SAFE_HAVEN_VIX_DOLLAR_NOT_UP_PROBE','Safe-haven VIX up while dollar not up',{'vix20':['vix_change_20d','vix_ret_20d','vix_20d_change'],'dxy20':['dxy_ret_20d','dxy_change_20d','dxy_20d_ret']},'r5'),
 RuleSpec('D135_06_SPDR_SUPPORT_DXY_NOT_HOSTILE_PROBE','SPDR/ETF support with dollar not hostile',{'spdr':['spdr_gld_tonnes_change_20d','spdr_change_20d','gld_tonnes_change_20d','etf_flow_20d'],'dxy20':['dxy_ret_20d','dxy_change_20d','dxy_20d_ret']},'r6'),
]

def rule_eval(fn,row,b,th):
    vals={k:parse_float(row.get(c)) for k,c in b.items()}
    if any(v is None for v in vals.values()): return False,'missing_numeric_value'
    def t(k): return th.get(k)
    if fn=='r1': return vals['dxy20']<=t('dxy20_p50') and vals['goldtrend']>=t('goldtrend_p40'), f"dxy20<={t('dxy20_p50'):.4f};goldtrend>={t('goldtrend_p40'):.4f}"
    if fn=='r2': return vals['ry20']<=t('ry20_p50') and vals['goldtrend']>=t('goldtrend_p35'), f"ry20<={t('ry20_p50'):.4f};goldtrend>={t('goldtrend_p35'):.4f}"
    if fn=='r3': return vals['dxy20']<=t('dxy20_p55') and vals['ry20']<=t('ry20_p55'), f"dxy20<={t('dxy20_p55'):.4f};ry20<={t('ry20_p55'):.4f}"
    if fn=='r4': return vals['cotchg']<=t('cotchg_p45') and vals['ry20']<=t('ry20_p60'), f"cotchg<={t('cotchg_p45'):.4f};ry20<={t('ry20_p60'):.4f}"
    if fn=='r5': return vals['vix20']>=t('vix20_p60') and vals['dxy20']<=t('dxy20_p60'), f"vix20>={t('vix20_p60'):.4f};dxy20<={t('dxy20_p60'):.4f}"
    if fn=='r6': return vals['spdr']>=t('spdr_p55') and vals['dxy20']<=t('dxy20_p60'), f"spdr>={t('spdr_p55'):.4f};dxy20<={t('dxy20_p60'):.4f}"
    return False,'unknown_rule'

def build_thresholds(rows,bindings):
    values={}
    for b in bindings:
        for key,col in b.items():
            values.setdefault(key,[])
            for r in rows:
                v=parse_float(r.get(col))
                if v is not None: values[key].append(v)
    th={}
    for key,vals in values.items():
        for q,name in [(0.35,'p35'),(0.40,'p40'),(0.45,'p45'),(0.50,'p50'),(0.55,'p55'),(0.60,'p60')]:
            qv=quantile(vals,q)
            if qv is not None: th[f'{key}_{name}']=qv
    return th

def metrics(rows,ret_col,spec,b,th):
    xs=[]; cond=''
    for r in rows:
        ok,cond=rule_eval(spec.fn,r,b,th)
        if ok:
            ret=parse_float(r.get(ret_col))
            if ret is not None: xs.append(ret)
    if not xs: return {'events':0,'mean_bps':0.0,'hit_rate':0.0,'condition':cond}
    return {'events':len(xs),'mean_bps':round(statistics.fmean(xs),4),'hit_rate':round(sum(1 for x in xs if x>0)/len(xs),4),'condition':cond}

def split_rows(rows,date_col):
    if date_col: rows=sorted(rows,key=lambda r: parse_date(r.get(date_col)) or datetime.min.replace(tzinfo=timezone.utc))
    n=len(rows); return rows[:int(n*.6)], rows[int(n*.6):int(n*.8)], rows[int(n*.8):]

def pass_gate(m,min_events,min_mean,min_hit): return m['events']>=min_events and m['mean_bps']>=min_mean and m['hit_rate']>=min_hit

def write_csv(path,rows,fields):
    ensure_dir(path.parent); tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k:r.get(k,'') for k in fields})
    tmp.replace(path)

def append_csv(path,rows,fields):
    ensure_dir(path.parent); exists=path.exists() and path.stat().st_size>0
    with path.open('a',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        if not exists: w.writeheader()
        for r in rows: w.writerow({k:r.get(k,'') for k in fields})

def write_kv(path,kv):
    ensure_dir(path.parent); tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        for k,v in kv.items(): f.write(f'{k}|{v if v is not None else ""}\n')
    tmp.replace(path)

def write_json(path,obj): ensure_dir(path.parent); path.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')

def run(root:Path,dataset:Path,mt5_files:Path,max_rows:int,min_events:int,min_mean_bps:float,min_hit:float,max_feature_age_days:int,write_mt5:bool):
    root=root.expanduser(); dataset=dataset.expanduser(); mt5_files=mt5_files.expanduser()
    if not dataset.is_absolute(): dataset=root/dataset
    out=ensure_dir(root/'reports/stage135_demo_probe_rule_discovery'); data=ensure_dir(root/'data/demo_execution'); generated=utc_now()
    if not dataset.exists():
        summary={'stage':STAGE,'generated_utc':generated,'status':STATUS,'decision':'STAGE135_DATASET_MISSING_NO_DEMO_PROBE','dataset':str(dataset)}
        write_json(out/'stage135_demo_probe_rule_discovery_summary.json',summary); print(json.dumps(summary,indent=2,ensure_ascii=False)); return summary
    rows=load_rows(dataset,max_rows); cols=list(rows[0].keys()); ret_col=get_ret_col(cols); date_col=get_date_col(cols)
    if not ret_col: raise ValueError('could not find forward return column such as fwd_ret_bps_h120')
    bound=[(s,s.bind(cols)) for s in RULES if s.bind(cols)]
    if not bound: raise ValueError('no Stage135 rule spec could bind to available columns')
    sel,val,tail=split_rows(rows,date_col); th=build_thresholds(sel,[b for _,b in bound]); latest=rows[-1]
    scores=[]
    for spec,b in bound:
        sm=metrics(sel,ret_col,spec,b,th); vm=metrics(val,ret_col,spec,b,th); tm=metrics(tail,ret_col,spec,b,th)
        cur,cond=rule_eval(spec.fn,latest,b,th)
        gate='PASS' if pass_gate(vm,min_events,min_mean_bps,min_hit) and pass_gate(tm,max(3,min_events//3),min_mean_bps*.25,min_hit*.9) else 'WATCH_OR_REJECT'
        scores.append({'rule_id':spec.rule_id,'label':spec.label,'gate':gate,'current_active':cur,'current_condition':cond,'selection_events':sm['events'],'selection_mean_bps':sm['mean_bps'],'selection_hit_rate':sm['hit_rate'],'validation_events':vm['events'],'validation_mean_bps':vm['mean_bps'],'validation_hit_rate':vm['hit_rate'],'tail_events':tm['events'],'tail_mean_bps':tm['mean_bps'],'tail_hit_rate':tm['hit_rate'],'bound_columns':json.dumps(b,sort_keys=True)})
    feature_date=latest.get(date_col,'') if date_col else ''
    reason='no current-active candidate passed validation gates'; selected=None
    latest_dt=parse_date(feature_date) if feature_date else None
    if latest_dt:
        age=(datetime.now(timezone.utc)-latest_dt).total_seconds()/86400
        if age>max_feature_age_days: reason=f'latest_feature_age_days={age:.2f} exceeds guard {max_feature_age_days}'
        else:
            active=[r for r in scores if r['gate']=='PASS' and r['current_active'] is True]
            if active:
                active.sort(key=lambda r:(float(r['validation_mean_bps']),float(r['tail_mean_bps']),int(r['validation_events'])),reverse=True); selected=active[0]; reason='selected highest validation/tail mean among current-active PASS candidates'
    else:
        active=[r for r in scores if r['gate']=='PASS' and r['current_active'] is True]
        if active:
            active.sort(key=lambda r:(float(r['validation_mean_bps']),float(r['tail_mean_bps']),int(r['validation_events'])),reverse=True); selected=active[0]; reason='selected current-active PASS candidate; feature date unavailable'
    if selected:
        decision='STAGE135_DEMO_PROBE_SIGNAL_READY_POINT_STAGE134_TO_STAGE135_FILE'; any_active='true'; rid=selected['rule_id']; label=selected['label']; active_count='1'
    else:
        decision='STAGE135_NO_DEMO_PROBE_SIGNAL_FAST_DISCOVERY_CONTINUE'; any_active='false'; rid=''; label=''; active_count='0'
    kv={'stage':'Stage135_DEMO_PROBE_RULE_DISCOVERY','status':'DEMO_PROBE_RULE_STATE_ALIVE_NO_ORDER_SEND_IN_STAGE135','decision':decision,'reason':reason,'mode':'DEMO_PROBE_DISCOVERY_TO_STAGE134','feature_date':feature_date,'any_signal_active':any_active,'selected_rule_id':rid,'selected_label':label,'execution_allowed':'false','order_authorized':'false','rule_count':len(scores),'active_rule_count':active_count,'allow_trading':'false','order_send':'false','note':'Stage135 writes rule-state only; Stage134 demo executor must be manually pointed to this file','stage134_required_InpRuleStateKvFile':KV_FILE,'stage134_required_InpAllowedRules':rid if rid else 'D135_* candidate IDs after PASS'}
    latest_rule=[{'time_utc':generated,'rule_id':rid,'rule_active':any_active,'feature_date':feature_date,'selected_label':label,'decision':decision,'reason':reason,'allow_trading':'false','order_send':'false'}]
    score_fields=['rule_id','label','gate','current_active','current_condition','selection_events','selection_mean_bps','selection_hit_rate','validation_events','validation_mean_bps','validation_hit_rate','tail_events','tail_mean_bps','tail_hit_rate','bound_columns']
    write_csv(out/'stage135_candidate_scores.csv',scores,score_fields); write_csv(data/LATEST_FILE,latest_rule,list(latest_rule[0].keys())); append_csv(data/HISTORY_FILE,latest_rule,list(latest_rule[0].keys())); write_kv(data/KV_FILE,kv); write_csv(out/'stage135_risk_manifest.csv',[{'risk_block':b,'status':'ACTIVE'} for b in RISK_BLOCKS],['risk_block','status'])
    mt5_kv=''; mt5_latest=''
    if write_mt5:
        mt5_kv=str(mt5_files/KV_FILE); mt5_latest=str(mt5_files/LATEST_FILE); write_kv(Path(mt5_kv),kv); write_csv(Path(mt5_latest),latest_rule,list(latest_rule[0].keys())); append_csv(mt5_files/HISTORY_FILE,latest_rule,list(latest_rule[0].keys()))
    summary={'stage':STAGE,'generated_utc':generated,'status':STATUS,'decision':decision,'root':str(root),'dataset':str(dataset),'dataset_rows':len(rows),'ret_col':ret_col,'date_col':date_col,'latest_feature_date':feature_date,'candidate_count':len(scores),'passed_current_active_count':len([r for r in scores if r['gate']=='PASS' and r['current_active'] is True]),'selected_rule_id':rid,'selected_label':label,'select_reason':reason,'stage134_instruction':{'InpRuleStateKvFile':KV_FILE,'InpAllowedRules':rid if rid else '','keep_InpEnableDemoOrders':'true only on demo account','restore_path':'set InpRuleStateKvFile back to xauusd_stage133_unified_observer_rule_state_kv.csv after probe or negative result'},'score_csv':str(out/'stage135_candidate_scores.csv'),'repo_kv':str(data/KV_FILE),'repo_latest':str(data/LATEST_FILE),'repo_history':str(data/HISTORY_FILE),'mt5_kv_written':bool(write_mt5),'mt5_kv':mt5_kv,'mt5_latest':mt5_latest,'risk_manifest_csv':str(out/'stage135_risk_manifest.csv'),'summary_json':str(out/'stage135_demo_probe_rule_discovery_summary.json'),'next':['If selected_rule_id is non-empty, point Stage134 InpRuleStateKvFile to xauusd_stage135_demo_probe_rule_state_kv.csv and InpAllowedRules to selected_rule_id.','If no selected rule is produced, run broader thesis discovery instead of waiting on inactive observer rules.','After any demo attempt, review retcode/fill/PnL quickly; negative evidence returns to discovery/repair.']}
    write_json(out/'stage135_demo_probe_rule_discovery_summary.json',summary); print(json.dumps(summary,indent=2,ensure_ascii=False)); return summary

def main():
    ap=argparse.ArgumentParser(description=STAGE); ap.add_argument('--root',default='/Users/vahid/Desktop/xauusd-trader'); ap.add_argument('--dataset',default=DEFAULT_DATASET); ap.add_argument('--mt5-files',default=DEFAULT_MT5_FILES); ap.add_argument('--max-rows',type=int,default=0); ap.add_argument('--min-events',type=int,default=20); ap.add_argument('--min-mean-bps',type=float,default=5.0); ap.add_argument('--min-hit',type=float,default=0.52); ap.add_argument('--max-feature-age-days',type=int,default=10); ap.add_argument('--write-mt5',action='store_true')
    a=ap.parse_args(); run(Path(a.root),Path(a.dataset),Path(a.mt5_files),a.max_rows,a.min_events,a.min_mean_bps,a.min_hit,a.max_feature_age_days,a.write_mt5); return 0
if __name__=='__main__': raise SystemExit(main())
