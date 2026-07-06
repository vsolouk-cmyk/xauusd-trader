#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

STAGE='Stage153_LOCKED_MTF_RULE_STATE_WRITER_TIMESTAMP_NORMALIZED'
STATUS='STAGE151B_COMPLETE_LOCKED_MTF_RULE_STATE_STALE_GUARD_READY'
DEFAULT_MT5_FILES='/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files'
BASE_FEATURE_HOURS=[1,3,6,12,24,48]
SMA_HOURS=[8,20,50,100]

def utc_now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def ensure_dir(p:Path): p.mkdir(parents=True, exist_ok=True); return p

def parse_float(v):
    if v is None: return None
    s=str(v).strip().replace(',','')
    if not s or s.lower() in {'nan','none','null'}: return None
    try: x=float(s)
    except Exception: return None
    return None if math.isnan(x) or math.isinf(x) else x

def parse_dt(v):
    if v is None: return None
    s=str(v).strip().replace('Z','+00:00')
    if not s: return None
    for fmt in ('%Y.%m.%d %H:%M:%S','%Y.%m.%d','%Y-%m-%d %H:%M:%S%z','%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S%z','%Y-%m-%dT%H:%M:%S','%Y-%m-%d'):
        try:
            dt=datetime.strptime(s,fmt)
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception: pass
    try:
        dt=datetime.fromisoformat(s)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception: return None

def clean_col(c): return str(c).strip().strip('\ufeff').strip('<>').strip().lower()
def detect_delimiter(path:Path):
    sample=path.read_text(encoding='utf-8', errors='replace')[:4096]
    first=sample.splitlines()[0] if sample.splitlines() else ''
    if '\t' in first and first.count('\t')>=first.count(','): return '\t'
    if ';' in first and first.count(';')>first.count(','): return ';'
    return ','
def read_table(path:Path):
    delim=detect_delimiter(path)
    with path.open('r', encoding='utf-8', errors='replace', newline='') as f:
        return [{clean_col(k):('' if v is None else str(v).strip()) for k,v in r.items() if k is not None} for r in csv.DictReader(f, delimiter=delim)]
def find_col(cols:Iterable[str], aliases:List[str]):
    lower={clean_col(c):c for c in cols}
    for a in aliases:
        ca=clean_col(a)
        if ca in lower: return lower[ca]
    for c in cols:
        lc=clean_col(c)
        if any(clean_col(a) in lc for a in aliases): return c
    return None

def normalize_bars(rows):
    if not rows: return []
    cols=list(rows[0].keys())
    date_col=find_col(cols,['date']); time_col=find_col(cols,['time'])
    dt_col=find_col(cols,['utc_time','time_utc','timestamp','datetime','date_time','time'])
    ocol=find_col(cols,['open']); hcol=find_col(cols,['high']); lcol=find_col(cols,['low']); ccol=find_col(cols,['close']); vcol=find_col(cols,['volume','tickvol','tick_volume'])
    if not all([ocol,hcol,lcol,ccol]): raise ValueError(f'could not bind OHLC columns. cols={cols[:30]}')
    out=[]
    for r in rows:
        dt=parse_dt(f"{r.get(date_col,'')} {r.get(time_col,'')}") if date_col and time_col and date_col!=time_col else (parse_dt(r.get(dt_col)) if dt_col else None)
        o=parse_float(r.get(ocol)); h=parse_float(r.get(hcol)); l=parse_float(r.get(lcol)); c=parse_float(r.get(ccol)); v=parse_float(r.get(vcol)) if vcol else None
        if dt is None or o is None or h is None or l is None or c is None or c<=0: continue
        out.append({'utc_time':dt,'open':o,'high':h,'low':l,'close':c,'volume':v})
    out.sort(key=lambda r:r['utc_time'])
    return out

def hours_to_bars(hours:int, timeframe_minutes:int): return max(1, int(round((hours*60)/timeframe_minutes)))
def avg(xs): return sum(xs)/len(xs) if xs else None

def compute_latest_features(bars, timeframe_minutes:int):
    if not bars: raise ValueError('no bars')
    closes=[b['close'] for b in bars]; highs=[b['high'] for b in bars]; lows=[b['low'] for b in bars]
    i=len(bars)-1; b=dict(bars[-1]); c=b['close']
    for h in BASE_FEATURE_HOURS:
        n=hours_to_bars(h,timeframe_minutes); b[f'ret_{h}h_bps']=(c/closes[i-n]-1)*10000 if i>=n and closes[i-n]>0 else None
    sma={}
    for h in SMA_HOURS:
        n=hours_to_bars(h,timeframe_minutes); sma[h]=avg(closes[i-n+1:i+1]) if i+1>=n else None; b[f'sma_{h}h']=sma[h]
    b['trend_8_20_bps']=(sma[8]/sma[20]-1)*10000 if sma[8] and sma[20] else None
    b['trend_20_50_bps']=(sma[20]/sma[50]-1)*10000 if sma[20] and sma[50] else None
    b['trend_50_100_bps']=(sma[50]/sma[100]-1)*10000 if sma[50] and sma[100] else None
    for h in (24,48):
        n=hours_to_bars(h,timeframe_minutes)
        if i>=n:
            ph=max(highs[i-n:i]); pl=min(lows[i-n:i]); rng=ph-pl
            b[f'range_pos_{h}']=(c-pl)/rng if rng>0 else None; b[f'break_high_{h}']=1.0 if c>ph else 0.0; b[f'break_low_{h}']=1.0 if c<pl else 0.0
            if h==24:
                b['dist_high_24_bps']=(c/ph-1)*10000 if ph>0 else None; b['dist_low_24_bps']=(c/pl-1)*10000 if pl>0 else None
        else:
            b[f'range_pos_{h}']=b[f'break_high_{h}']=b[f'break_low_{h}']=None
            if h==24: b['dist_high_24_bps']=b['dist_low_24_bps']=None
    return b

def condition_active(row, conds):
    for cond in conds:
        feature=cond.get('feature'); op=cond.get('op'); threshold=parse_float(cond.get('threshold')); value=parse_float(row.get(feature))
        if value is None or threshold is None: return False
        if op=='>=' and value<threshold: return False
        if op=='<=' and value>threshold: return False
    return True

def load_conditions_from_summary(summary):
    raw=(summary.get('selected_score') or {}).get('conditions_json')
    if not raw: return []
    conds=json.loads(raw)
    return [{'feature':c.get('feature'),'op':c.get('op'),'threshold':c.get('threshold')} for c in conds if c.get('feature') and c.get('op') in {'>=','<='}]

def write_kv(path, kv):
    ensure_dir(path.parent); tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        for k,v in kv.items(): f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)
def write_csv(path, rows, fields):
    ensure_dir(path.parent); tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); [w.writerow({k:r.get(k,'') for k in fields}) for r in rows]
    tmp.replace(path)
def append_csv(path, rows, fields):
    ensure_dir(path.parent); exists=path.exists() and path.stat().st_size>0
    with path.open('a', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        [w.writerow({k:r.get(k,'') for k in fields}) for r in rows]
def write_json(path,obj): ensure_dir(path.parent); path.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')

def run(root, bars_path, source_summary_path, tf, timeframe_minutes, mt5_files, write_mt5, max_feature_age_sec=7200, timestamp_shift_hours=0.0):
    root=Path(root).expanduser(); bars_path=Path(bars_path).expanduser(); source_summary_path=Path(source_summary_path).expanduser(); mt5_files=Path(mt5_files).expanduser(); generated=utc_now()
    source=json.loads(source_summary_path.read_text(encoding='utf-8'))
    rid=str(source.get('selected_rule_id') or ''); label=str(source.get('selected_label') or '')
    if not rid: raise ValueError('source summary has empty selected_rule_id')
    conds=load_conditions_from_summary(source)
    if not conds: raise ValueError('source summary has no parseable selected_score.conditions_json')
    raw=read_table(bars_path); bars=normalize_bars(raw); min_required=max(hours_to_bars(110,timeframe_minutes)+5,200)
    if len(bars)<min_required: raise ValueError(f'not enough bars: {len(bars)} < {min_required}')
    latest=compute_latest_features(bars,timeframe_minutes); raw_rule_active=condition_active(latest,conds); now_utc=datetime.now(timezone.utc)
    raw_feature_time=latest['utc_time']
    normalized_feature_time=raw_feature_time + timedelta(hours=float(timestamp_shift_hours))
    feature_age_sec=int((now_utc-normalized_feature_time).total_seconds())
    feature_fresh=(feature_age_sec>=0 and feature_age_sec<=max_feature_age_sec)
    active=(raw_rule_active and feature_fresh)
    feature_date=normalized_feature_time.isoformat().replace('+00:00','Z')
    tf_safe=''.join(ch.lower() if ch.isalnum() else '_' for ch in tf).strip('_') or f'm{timeframe_minutes}'
    kv_file=f'xauusd_stage151_{tf_safe}_locked_rule_state_kv.csv'; latest_file=f'xauusd_stage151_{tf_safe}_locked_rule_state_latest.csv'; hist_file=f'xauusd_stage151_{tf_safe}_locked_rule_state_history.csv'
    
    if active:
        decision='STAGE153_LOCKED_RULE_ACTIVE_POINT_STAGE134_TO_STAGE151_FILE'; reason='locked rule conditions are active on latest fresh bar'
    elif raw_rule_active and not feature_fresh:
        decision='STAGE153_LOCKED_RULE_STALE_OR_FUTURE_NO_ORDER'; reason='locked rule conditions are active but latest normalized feature_date is stale or in the future'
    else:
        decision='STAGE153_LOCKED_RULE_INACTIVE_NO_ORDER'; reason='locked rule conditions are not active on latest fresh bar'
    kv={'stage':STAGE,'status':'LOCKED_MTF_RULE_STATE_ALIVE_NO_ORDER_SEND_IN_STAGE153','decision':decision,'reason':reason,'mode':'LOCKED_MTF_RULE_TO_STAGE134_FAST_REFRESH','tf':tf_safe,'timeframe_minutes':timeframe_minutes,'feature_date':feature_date,'any_signal_active':'true' if active else 'false','raw_rule_active_before_stale_guard':'true' if raw_rule_active else 'false','feature_fresh':'true' if feature_fresh else 'false','feature_age_sec':feature_age_sec,'max_feature_age_sec':max_feature_age_sec,'raw_feature_date':raw_feature_time.isoformat().replace('+00:00','Z'),'timestamp_shift_hours':timestamp_shift_hours,'selected_rule_id':rid,'selected_label':label,'execution_allowed':'false','order_authorized':'false','rule_count':1,'active_rule_count':1 if active else 0,'allow_trading':'false','order_send':'false','source_summary':str(source_summary_path),'conditions_json':json.dumps(conds,sort_keys=True),'note':'Stage153 normalizes timestamp and fast-refreshes a locked Stage150 rule only; it does not rescan candidates and does not send orders.','stage134_required_InpRuleStateKvFile':kv_file,'stage134_required_InpAllowedRules':rid}
    latest_row={'time_utc':generated,'tf':tf_safe,'rule_id':rid,'rule_active':'true' if active else 'false','raw_rule_active_before_stale_guard':'true' if raw_rule_active else 'false','feature_fresh':'true' if feature_fresh else 'false','feature_age_sec':feature_age_sec,'feature_date':feature_date,'selected_label':label,'decision':decision,'reason':reason,'allow_trading':'false','order_send':'false'}
    data=ensure_dir(root/'data/demo_execution'); repo_kv=data/kv_file; repo_latest=data/latest_file; repo_hist=data/hist_file
    write_kv(repo_kv,kv); write_csv(repo_latest,[latest_row],list(latest_row.keys())); append_csv(repo_hist,[latest_row],list(latest_row.keys()))
    mt5_kv=mt5_latest=''
    if write_mt5:
        mt5_kv=str(mt5_files/kv_file); mt5_latest=str(mt5_files/latest_file); write_kv(Path(mt5_kv),kv); write_csv(Path(mt5_latest),[latest_row],list(latest_row.keys())); append_csv(mt5_files/hist_file,[latest_row],list(latest_row.keys()))
    out=ensure_dir(root/'reports/stage151_locked_mtf_rule_state_writer'/tf_safe)
    cond_rows=[{'feature':c['feature'],'op':c['op'],'threshold':c['threshold'],'current':latest.get(c['feature'])} for c in conds]
    write_csv(out/'stage151_locked_rule_conditions.csv', cond_rows, ['feature','op','threshold','current'])
    summary={'stage':STAGE,'generated_utc':generated,'status':STATUS,'decision':decision,'root':str(root),'bars_path':str(bars_path),'source_summary':str(source_summary_path),'tf':tf_safe,'timeframe_minutes':timeframe_minutes,'raw_row_count':len(raw),'bar_count':len(bars),'bar_min_utc':bars[0]['utc_time'].isoformat(),'bar_max_utc':bars[-1]['utc_time'].isoformat(),'feature_date':feature_date,'raw_feature_date':raw_feature_time.isoformat().replace('+00:00','Z'),'timestamp_shift_hours':timestamp_shift_hours,'selected_rule_id':rid,'selected_label':label,'conditions':cond_rows,'any_signal_active':active,'raw_rule_active_before_stale_guard':raw_rule_active,'feature_fresh':feature_fresh,'feature_age_sec':feature_age_sec,'max_feature_age_sec':max_feature_age_sec,'raw_feature_date':raw_feature_time.isoformat().replace('+00:00','Z'),'timestamp_shift_hours':timestamp_shift_hours,'repo_kv':str(repo_kv),'repo_latest':str(repo_latest),'mt5_kv_written':bool(write_mt5),'mt5_kv':mt5_kv,'mt5_latest':mt5_latest,'stage134_instruction':{'InpRuleStateKvFile':kv_file,'InpAllowedRules':rid,'keep_InpEnableDemoOrders':'true only on demo account'},'summary_json':str(out/'stage151_locked_mtf_rule_state_writer_summary.json'),'next':['Use Stage151 for fast post-market-open refresh of a locked Stage150 MTF rule.','Run full Stage150B scans offline only when changing or replacing the locked rule.']}
    write_json(out/'stage151_locked_mtf_rule_state_writer_summary.json', summary); print(json.dumps(summary,indent=2,ensure_ascii=False)); return summary

def main():
    ap=argparse.ArgumentParser(description=STAGE); ap.add_argument('--root',default='/Users/vahid/Desktop/xauusd-trader'); ap.add_argument('--bars',required=True); ap.add_argument('--source-summary',required=True); ap.add_argument('--tf',required=True); ap.add_argument('--timeframe-minutes',type=int,required=True); ap.add_argument('--mt5-files',default=DEFAULT_MT5_FILES); ap.add_argument('--write-mt5',action='store_true'); ap.add_argument('--max-feature-age-sec',type=int,default=7200); ap.add_argument('--timestamp-shift-hours',type=float,default=0.0); args=ap.parse_args()
    run(args.root,args.bars,args.source_summary,args.tf,args.timeframe_minutes,args.mt5_files,args.write_mt5,args.max_feature_age_sec,args.timestamp_shift_hours); return 0
if __name__=='__main__': raise SystemExit(main())
