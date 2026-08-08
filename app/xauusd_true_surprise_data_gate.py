from __future__ import annotations
import argparse, csv, hashlib, json, math, re
from pathlib import Path
import pandas as pd

PROGRAM = "XAUUSD_TRUE_SURPRISE_DATA_GATE_V1_POINT_IN_TIME_CONSENSUS"

class GateError(RuntimeError):
    pass

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def parse_number(value):
    if value is None or (isinstance(value,float) and math.isnan(value)):
        return None
    s=str(value).strip().replace(',', '')
    if not s or s.lower() in {'nan','na','n/a','none','null','-'}:
        return None
    pct=s.endswith('%')
    if pct: s=s[:-1]
    mult=1.0
    if s and s[-1:].upper() in {'K','M','B','T'}:
        mult={'K':1e3,'M':1e6,'B':1e9,'T':1e12}[s[-1].upper()]
        s=s[:-1]
    s=s.strip()
    try: return float(s)*mult
    except ValueError: return None

def load_config(path: Path):
    return json.loads(path.read_text())

def group_event(name: str, groups: dict[str,list[str]]):
    n=str(name).strip().lower()
    for gid, aliases in groups.items():
        for a in aliases:
            if n==a.lower(): return gid
    return None

def read_inputs(inbox: Path):
    files=sorted([p for p in inbox.glob('*.csv') if p.is_file()])
    if not files: raise GateError(f"no CSV files found in {inbox}")
    frames=[]
    for p in files:
        df=pd.read_csv(p, dtype='string', low_memory=False)
        df['_source_file']=p.name
        frames.append(df)
    return pd.concat(frames, ignore_index=True), files

def validate(inbox: Path, config_path: Path, outdir: Path):
    cfg=load_config(config_path)
    df, files=read_inputs(inbox)
    missing=[c for c in cfg['required_columns'] if c not in df.columns]
    if missing: raise GateError(f"missing required columns: {missing}")
    if 'TEForecast' in df.columns:
        # Presence is allowed; substitution is not. Forecast must be independently populated.
        pass
    df=df[df['Country'].fillna('').str.strip().eq(cfg['country'])].copy()
    if df.empty: raise GateError("no United States rows")
    df['release_time_utc']=pd.to_datetime(df['Date'], utc=True, errors='coerce')
    df['last_update_utc']=pd.to_datetime(df['LastUpdate'], utc=True, errors='coerce')
    start=pd.Timestamp(cfg['reference_start_utc'])
    end=pd.Timestamp(cfg['reference_end_utc'])
    df=df[(df.release_time_utc>=start)&(df.release_time_utc<end)].copy()
    df['event_group']=[group_event(x,cfg['required_event_groups']) for x in df['Event']]
    df=df[df.event_group.notna()].copy()
    if df.empty: raise GateError("no configured CPI/Core CPI/NFP rows in reference window")
    df['actual_value']=[parse_number(x) for x in df['Actual']]
    df['forecast_value']=[parse_number(x) for x in df['Forecast']]
    df['previous_value']=[parse_number(x) for x in df['Previous']]
    df['datespan_numeric']=pd.to_numeric(df['DateSpan'], errors='coerce')
    df['valid_time']=df.release_time_utc.notna()
    df['valid_datespan']=df.datespan_numeric.eq(0)
    df['valid_lastupdate']=df.last_update_utc.notna() & (df.last_update_utc>=df.release_time_utc)
    df['valid_actual_forecast']=df.actual_value.notna() & df.forecast_value.notna()
    df['valid_row']=df.valid_time & df.valid_datespan & df.valid_lastupdate & df.valid_actual_forecast
    valid=df[df.valid_row].copy()
    # De-duplicate exact calendar IDs, then exact event/release/group duplicates.
    if 'CalendarId' in valid.columns:
        valid=valid.sort_values(['last_update_utc']).drop_duplicates(['CalendarId'], keep='first')
    valid=valid.drop_duplicates(['event_group','release_time_utc','Event'], keep='first')
    valid['surprise_raw']=valid.actual_value-valid.forecast_value
    counts=valid.groupby('event_group').size().to_dict()
    group_diag=[]
    failed=[]
    for gid in cfg['required_event_groups']:
        n=int(counts.get(gid,0))
        ok=n>=int(cfg['minimum_valid_rows_per_group'])
        if not ok: failed.append(f"{gid}_valid_rows_lt_{cfg['minimum_valid_rows_per_group']}")
        group_diag.append({'event_group':gid,'valid_rows':n,'pass':ok})
    # Unit consistency: multiple units are allowed only if numeric scale is directly comparable within the group.
    unit_diag=[]
    for gid,g in valid.groupby('event_group'):
        units=sorted(set(g['Unit'].dropna().astype(str).str.strip())-set(['']))
        unit_diag.append({'event_group':gid,'units':units,'unit_count':len(units)})
        if len(units)>1: failed.append(f"{gid}_multiple_units")
    summary={
        'program':PROGRAM,
        'decision':'PASS_TRUE_SURPRISE_DATA_READY_FOR_LOCKED_SCAN' if not failed else 'TRUE_SURPRISE_DATA_GATE_FAIL_CLOSED',
        'pass':not failed,
        'input_files':[{'name':p.name,'size':p.stat().st_size,'sha256':sha256(p)} for p in files],
        'raw_rows_after_country_filter_reference':int(len(df)),
        'valid_rows':int(len(valid)),
        'groups':group_diag,
        'unit_diagnostics':unit_diag,
        'failed_gates':sorted(set(failed)),
        'reference_start_utc':cfg['reference_start_utc'],
        'reference_end_utc':cfg['reference_end_utc'],
        'selection_used_2025_plus':False,
        'paper_order_allowed':False,'demo_order_allowed':False,'live_order_allowed':False,
        'required_next_action':'BUILD_LOCKED_TRUE_SURPRISE_SCAN' if not failed else 'REPAIR_OR_REPLACE_CONSENSUS_SOURCE'
    }
    outdir.mkdir(parents=True,exist_ok=True)
    cols=['event_group','CalendarId','release_time_utc','Event','Actual','Forecast','Previous','actual_value','forecast_value','previous_value','surprise_raw','Importance','Unit','last_update_utc','_source_file']
    valid[cols].sort_values('release_time_utc').to_csv(outdir/'true_surprise_events_normalized.csv',index=False)
    (outdir/'true_surprise_data_gate_summary.json').write_text(json.dumps(summary,indent=2,default=str))
    # compact diagnostics for invalid rows
    diag_cols=['event_group','Date','Event','Actual','Forecast','Previous','DateSpan','LastUpdate','valid_time','valid_datespan','valid_lastupdate','valid_actual_forecast','valid_row','_source_file']
    df[diag_cols].to_csv(outdir/'true_surprise_row_diagnostics.csv',index=False)
    return summary

def collect(outdir: Path, dest: Path):
    import zipfile
    required=['true_surprise_data_gate_summary.json','true_surprise_events_normalized.csv','true_surprise_row_diagnostics.csv']
    paths=[outdir/x for x in required]
    for p in paths:
        if not p.is_file(): raise GateError(f"missing output: {p}")
    manifest={'program':PROGRAM,'files':[]}
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            b=p.read_bytes(); manifest['files'].append({'path':p.name,'size':len(b),'sha256':hashlib.sha256(b).hexdigest()}); z.writestr(p.name,b)
        z.writestr('RESULTS_MANIFEST.json',json.dumps(manifest,indent=2))
    return dest

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('validate'); p.add_argument('--inbox',required=True); p.add_argument('--config',default='configs/xauusd_true_surprise_data_gate.json'); p.add_argument('--outdir',default='reports/xauusd_true_surprise_data_gate')
    c=sub.add_parser('collect'); c.add_argument('--outdir',default='reports/xauusd_true_surprise_data_gate'); c.add_argument('--dest',required=True)
    a=ap.parse_args()
    try:
        if a.cmd=='validate':
            s=validate(Path(a.inbox),Path(a.config),Path(a.outdir)); print(json.dumps(s,indent=2)); raise SystemExit(0 if s['pass'] else 2)
        else:
            print(collect(Path(a.outdir),Path(a.dest)))
    except GateError as e:
        print(json.dumps({'program':PROGRAM,'decision':'TRUE_SURPRISE_DATA_GATE_FAIL_CLOSED','pass':False,'error':f'{type(e).__name__}: {e}','paper_order_allowed':False,'demo_order_allowed':False,'live_order_allowed':False},indent=2)); raise SystemExit(2)
if __name__=='__main__': main()
