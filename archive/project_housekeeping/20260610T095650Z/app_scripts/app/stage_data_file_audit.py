#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timezone,timedelta
from pathlib import Path

TOOL_VERSION="v1"
DEF_H1=Path("~/Downloads/amarkets_xauusd_1h.csv").expanduser()
DEF_M1=Path("~/Downloads/amarkets_xauusd_1m.csv").expanduser()
DEF_SIG=Path("~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files/XAUUSD_DryRun_v1_signals.csv").expanduser()
DEF_OUT=Path("data/reports/stage_data_file_audit")

def delim(text): return "\t" if text[:8192].count("\t")>=text[:8192].count(",") else ","
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
def read_csv(path):
    if not path.exists(): return [],[],"missing",""
    text=path.read_text(encoding="utf-8-sig",errors="replace")
    if not text.strip(): return [],[],"empty",""
    d=delim(text)
    rows=list(csv.DictReader(text.splitlines(),delimiter=d))
    cols=list(rows[0].keys()) if rows else []
    clean=[{str(k).strip():("" if v is None else str(v).strip()) for k,v in r.items() if k is not None} for r in rows]
    return clean,cols,"ok",d
def times(rows,cols,kind,offset_h):
    date_col=pick(cols,["date","<DATE>"])
    time_col=pick(cols,["time","<TIME>","datetime","timestamp"])
    comb_col=pick(cols,["datetime","timestamp","timegmt","time_utc"])
    out=[]; off=timedelta(hours=offset_h)
    for r in rows:
        if kind in ("h1","m1"):
            raw=(f"{r.get(date_col,'')} {r.get(time_col,'')}".strip() if date_col and time_col and date_col!=time_col else r.get(comb_col or time_col or "", ""))
            t=parse_time(raw)
            if t: out.append((t-off).astimezone(timezone.utc))
        else:
            raw=r.get("signal_closed_h1_time_server") or r.get("logged_at_gmt") or r.get("signal_closed_h1_time_gmt_now") or ""
            t=parse_time(raw)
            if t: out.append(t.astimezone(timezone.utc))
    return sorted(out)
def audit(path,kind,offset_h):
    rows,cols,status,d=read_csv(path)
    ts=times(rows,cols,kind,offset_h)
    return {"path":str(path),"kind":kind,"status":status,"delimiter":"TAB" if d=="\t" else d,"rows":len(rows),"columns":cols,"start_utc":ts[0].isoformat() if ts else None,"end_utc":ts[-1].isoformat() if ts else None}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--h1-csv",default=str(DEF_H1)); ap.add_argument("--m1-csv",default=str(DEF_M1)); ap.add_argument("--signals-csv",default=str(DEF_SIG))
    ap.add_argument("--server-utc-offset-hours",type=float,default=2.0); ap.add_argument("--out-dir",default=str(DEF_OUT))
    a=ap.parse_args(); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    payload={"tool_version":TOOL_VERSION,"generated_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"server_utc_offset_hours":a.server_utc_offset_hours,
             "files":{"h1":audit(Path(a.h1_csv).expanduser(),"h1",a.server_utc_offset_hours),"m1":audit(Path(a.m1_csv).expanduser(),"m1",a.server_utc_offset_hours),"signals":audit(Path(a.signals_csv).expanduser(),"signals",a.server_utc_offset_hours)},
             "hard_rule":"Read-only. No database update. No orders."}
    (out/"stage_data_file_audit.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# Stage Data File Audit","",f"Generated UTC: `{payload['generated_utc']}`",f"Tool version: `{TOOL_VERSION}`","","> Hard rule: read-only audit. This does not update SQLite/database and does not authorize orders.","","## Files","| Kind | Status | Rows | Start UTC | End UTC | Path |","|---|---|---:|---|---|---|"]
    for k,f in payload["files"].items(): lines.append(f"| {k} | {f['status']} | {f['rows']} | {f['start_utc'] or ''} | {f['end_utc'] or ''} | `{f['path']}` |")
    lines+=["","## Decision","- If M1 end UTC is before signal entry/horizon, Stage 5C must remain open/unresolved.","- If M1 rows are zero but file size is large, the parser/export format is the issue."]
    (out/"stage_data_file_audit.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("Stage data file audit: DONE")
    for k,f in payload["files"].items(): print(f"{k}: rows={f['rows']} start={f['start_utc']} end={f['end_utc']}")
    print(f"Markdown report: {out/'stage_data_file_audit.md'}")
if __name__=="__main__": main()
