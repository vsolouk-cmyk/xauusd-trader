
#!/usr/bin/env python3
"""
Stage 4J — Shock/regime sensitivity lab.

This tool tags non-overlap replay trades by date windows such as "2026 shock",
"pre-shock", and user-defined recent windows. It is intentionally simple:
it does not predict news. It checks whether the candidate only works in a
special geopolitical/volatility regime.

Default input:
  data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv

No demo/paper/live authorization.
"""

from __future__ import annotations

import argparse, csv, json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence, Optional

TOOL_VERSION = "v1"
DEFAULT_TRADES = Path("data/reports/stage4g_v2/stage4g_v2_non_overlap_trades.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage4j_shock_regime_lab")


def parse_time(s):
    if s is None:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z","+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_float(x):
    try: return float(str(x).strip())
    except Exception: return 0.0


def read_rows(path: Path):
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    delim = "," if text[:4096].count(",") >= text[:4096].count("\t") else "\t"
    return [{str(k).strip(): ("" if v is None else str(v).strip()) for k,v in r.items()} for r in csv.DictReader(text.splitlines(), delimiter=delim)]


def infer_col(rows, candidates):
    if not rows: return None
    norm = {k.lower(): k for k in rows[0].keys()}
    for c in candidates:
        if c.lower() in norm: return norm[c.lower()]
    return None


def median(vals):
    if not vals: return 0
    xs=sorted(vals); n=len(xs); m=n//2
    return xs[m] if n%2 else (xs[m-1]+xs[m])/2


def pf(vals):
    gains=sum(v for v in vals if v>0); losses=-sum(v for v in vals if v<0)
    if losses <= 1e-12: return float("inf") if gains>0 else 0
    return gains/losses


def mdd(vals):
    eq=0; peak=0; dd=0
    for v in vals:
        eq += v; peak=max(peak,eq); dd=min(dd, eq-peak)
    return dd


def metrics(vals):
    if not vals:
        return {"trades":0,"total":0,"avg":0,"median":0,"win_rate":0,"pf":0,"max_dd":0}
    return {
        "trades": len(vals),
        "total": round(sum(vals),6),
        "avg": round(sum(vals)/len(vals),6),
        "median": round(median(vals),6),
        "win_rate": round(sum(1 for v in vals if v>0)/len(vals),6),
        "pf": round(pf(vals),6) if math.isfinite(pf(vals)) else "inf",
        "max_dd": round(mdd(vals),6),
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--trades-csv", default=str(DEFAULT_TRADES))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--shock-start", default="2026-02-28T00:00:00Z")
    ap.add_argument("--recent-start", default="2026-06-01T00:00:00Z")
    args=ap.parse_args()

    path=Path(args.trades_csv)
    rows=read_rows(path)
    time_col=infer_col(rows, ["entry_utc_time","entry_time_utc","entry_utc","entry_time","closed_h1_utc"])
    net_col=infer_col(rows, ["net_usd","net","pnl_usd"])
    session_col=infer_col(rows, ["session_utc","session","session_name"])
    if not time_col or not net_col:
        raise SystemExit(f"Could not infer time/net columns. columns={list(rows[0].keys()) if rows else []}")

    shock_start=parse_time(args.shock_start)
    recent_start=parse_time(args.recent_start)

    enriched=[]
    for r in rows:
        t=parse_time(r.get(time_col,""))
        net=parse_float(r.get(net_col))
        sess=r.get(session_col,"") if session_col else ""
        enriched.append((t, net, sess, r))

    groups = {
        "all": [x for x in enriched],
        "pre_2026": [x for x in enriched if x[0] and x[0].year < 2026],
        "year_2026": [x for x in enriched if x[0] and x[0].year == 2026],
        "pre_shock": [x for x in enriched if x[0] and shock_start and x[0] < shock_start],
        "shock_or_after": [x for x in enriched if x[0] and shock_start and x[0] >= shock_start],
        "recent_or_after": [x for x in enriched if x[0] and recent_start and x[0] >= recent_start],
    }

    report={}
    for name, items in groups.items():
        report[name]=metrics([x[1] for x in items])
        report[name]["sessions"]={}
        for s in sorted(set(x[2] for x in items)):
            report[name]["sessions"][s]=metrics([x[1] for x in items if x[2]==s])

    out=Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    payload={"tool_version":TOOL_VERSION,"generated_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"input":str(path),"time_col":time_col,"net_col":net_col,"session_col":session_col,"shock_start":args.shock_start,"recent_start":args.recent_start,"groups":report}
    (out/"stage4j_shock_regime_lab.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines=["# Stage 4J Shock / Regime Sensitivity Lab","",f"Generated UTC: `{payload['generated_utc']}`","","> Hard rule: research only. No demo, paper, or live authorization.","","## Inputs",f"- trades_csv: `{path}`",f"- shock_start: `{args.shock_start}`",f"- recent_start: `{args.recent_start}`","","## Group summary","| Group | Trades | Total | PF | Median | Win rate | Max DD |","|---|---:|---:|---:|---:|---:|---:|"]
    for k,v in report.items():
        lines.append(f"| {k} | {v['trades']} | {v['total']} | {v['pf']} | {v['median']} | {v['win_rate']} | {v['max_dd']} |")
    lines += ["","## Interpretation","- If `shock_or_after` is much better than `pre_shock`, the rule may be benefiting from conflict/energy-volatility regime.","- If `recent_or_after` has too few trades, do not infer anything from today alone.","- Keep live dry-run running, but do not place orders from this report."]
    (out/"stage4j_shock_regime_lab.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("Stage 4J shock/regime sensitivity lab: DONE")
    print(f"Markdown report: {out/'stage4j_shock_regime_lab.md'}")

if __name__=="__main__":
    main()
