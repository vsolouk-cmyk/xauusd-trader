#!/usr/bin/env python3
"""
Stage 19B — Compression Expansion Breakout Exact M1 Replay

Validates the single Stage19A M15-proxy promotion with exact M1 path replay.

Candidate:
- compression_expansion_breakout_long_comp0.75_h8
- LONG
- H1 compression6 <= 0.75
- session in London/New York
- M15 close > prior rolling 16-bar local high
- entry next M15 open
- time exit after 8 M15 bars / 120 minutes
- cooldown 4 M15 bars

Research validation only. No EA change, no paper/live/order authorization.
"""
from __future__ import annotations

import argparse, json, sqlite3, warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Sequence, Tuple, List
import pandas as pd

TOOL_VERSION="v1"
DEFAULT_DB=Path("data/local/xauusd_local_store.sqlite")
DEFAULT_OUT_DIR=Path("data/reports/stage19b_compression_breakout_exact_replay")
VARIANT="compression_expansion_breakout_long_comp0.75_h8"
FAMILY="compression_expansion_breakout_long"
SIDE="LONG"
HORIZON_BARS=8
HORIZON_MINUTES=120
COOLDOWN_BARS=4
COMP_MAX=0.75

warnings.filterwarnings("ignore", message="Converting to PeriodArray/Index representation will drop timezone information.", category=UserWarning)

def now_iso(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def connect(db: Path):
    if not db.exists(): raise FileNotFoundError(f"DB not found: {db}")
    c=sqlite3.connect(db); c.row_factory=sqlite3.Row; return c

def load_m1(conn)->pd.DataFrame:
    rows=conn.execute("""
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1m'
        ORDER BY utc_time
    """).fetchall()
    if not rows: raise RuntimeError("No AMarkets MT5 M1 bars found.")
    df=pd.DataFrame([dict(r) for r in rows])
    df["utc_time"]=pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open","high","low","close"]: df[c]=pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["utc_time","open","high","low","close"]).sort_values("utc_time").drop_duplicates("utc_time").set_index("utc_time")

def resample_ohlc(df, rule):
    return df.resample(rule, label="right", closed="right").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()

def period_no_tz(series, freq):
    return pd.to_datetime(series, utc=True, errors="coerce").dt.tz_localize(None).dt.to_period(freq)

def add_context(m15, h1):
    x=m15.copy()
    x["hour"]=x.index.hour
    x["session"]="other"
    x.loc[(x["hour"]>=0)&(x["hour"]<7),"session"]="asia"
    x.loc[(x["hour"]>=7)&(x["hour"]<12),"session"]="london"
    x.loc[(x["hour"]>=12)&(x["hour"]<17),"session"]="new_york"
    x.loc[(x["hour"]>=17)&(x["hour"]<22),"session"]="late_us"
    base=x.reset_index()
    base=base.rename(columns={"utc_time":"dt"} if "utc_time" in base.columns else {base.columns[0]:"dt"})
    h=h1.copy()
    h["h1_range"]=h["high"]-h["low"]
    h["atr14_h1"]=h["h1_range"].rolling(14, min_periods=5).mean()
    h["compression6"]=h["h1_range"].rolling(6, min_periods=4).mean()/h["atr14_h1"]
    ctx=pd.merge_asof(
        base.sort_values("dt"),
        h[["h1_range","atr14_h1","compression6"]].reset_index().rename(columns={"utc_time":"ctx_dt"}),
        left_on="dt", right_on="ctx_dt", direction="backward"
    ).drop(columns=["ctx_dt"])
    ctx["local_high16"]=ctx["high"].rolling(16, min_periods=8).max().shift(1)
    ctx["local_low16"]=ctx["low"].rolling(16, min_periods=8).min().shift(1)
    return ctx.sort_values("dt").reset_index(drop=True)

def signal_mask(x, comp_max):
    return (
        x["session"].isin(["london","new_york"]) &
        x["compression6"].notna() &
        (x["compression6"]<=comp_max) &
        x["local_high16"].notna() &
        (x["close"]>x["local_high16"])
    ).fillna(False)

def apply_spacing(indices, horizon_bars, cooldown_bars):
    chosen=[]; next_allowed=-1
    for i in indices:
        if i < next_allowed: continue
        chosen.append(int(i)); next_allowed=int(i)+horizon_bars+cooldown_bars
    return chosen

def get_entry_price(m15, entry_dt):
    if entry_dt in m15.index: return float(m15.loc[entry_dt]["open"]), "m15_exact_open"
    pos=m15.index.searchsorted(entry_dt)
    if pos < len(m15): return float(m15.iloc[pos]["open"]), "m15_next_open"
    return float("nan"), "entry_after_available_data"

def replay_exact_m1(ctx, m15, m1, cost_usd, comp_max):
    idxs=apply_spacing(ctx.index[signal_mask(ctx, comp_max)].tolist(), HORIZON_BARS, COOLDOWN_BARS)
    rows=[]
    for i in idxs:
        entry_i=i+1
        if entry_i>=len(ctx): continue
        signal_dt=pd.to_datetime(ctx.iloc[i]["dt"], utc=True)
        entry_dt=pd.to_datetime(ctx.iloc[entry_i]["dt"], utc=True)
        exit_dt=entry_dt+pd.Timedelta(minutes=HORIZON_MINUTES)
        entry, src=get_entry_price(m15, entry_dt)
        if pd.isna(entry): continue
        path=m1[(m1.index>entry_dt)&(m1.index<=exit_dt)]
        if path.empty: continue
        exit_price=float(path.iloc[-1]["close"])
        gross=exit_price-entry
        rows.append({
            "variant":VARIANT,"family":FAMILY,"side":SIDE,
            "horizon_bars":HORIZON_BARS,"horizon_minutes":HORIZON_MINUTES,"cooldown_bars":COOLDOWN_BARS,
            "comp_max":comp_max,"signal_dt":signal_dt,"entry_dt":entry_dt,"exit_dt":exit_dt,
            "entry_price":round(entry,6),"entry_price_source":src,"exit_price":round(exit_price,6),
            "gross_ret":round(gross,6),"net_x1":round(gross-cost_usd,6),
            "net_x2":round(gross-2*cost_usd,6),"net_x4":round(gross-4*cost_usd,6),
            "mfe":round(float(path["high"].max())-entry,6),"mae":round(entry-float(path["low"].min()),6),
            "session":str(ctx.iloc[i].get("session","")),"hour":int(ctx.iloc[i].get("hour",-1)),
            "compression6":float(ctx.iloc[i].get("compression6")) if pd.notna(ctx.iloc[i].get("compression6")) else float("nan"),
            "local_high16":float(ctx.iloc[i].get("local_high16")) if pd.notna(ctx.iloc[i].get("local_high16")) else float("nan"),
            "signal_close":float(ctx.iloc[i].get("close")),
        })
    out=pd.DataFrame(rows)
    if not out.empty:
        for c in ["signal_dt","entry_dt","exit_dt"]: out[c]=pd.to_datetime(out[c], utc=True, errors="coerce")
        out=out.sort_values("entry_dt").reset_index(drop=True)
    return out

def profit_factor(vals):
    vals=[float(v) for v in vals]
    wins=sum(v for v in vals if v>0); losses=abs(sum(v for v in vals if v<0))
    return 999.0 if losses==0 and wins>0 else (0.0 if losses==0 else round(wins/losses,6))

def max_dd(vals):
    eq=peak=0.0; dd=0.0
    for v in vals:
        eq+=float(v); peak=max(peak,eq); dd=min(dd,eq-peak)
    return round(dd,6)

def metrics(df, col="net_x1"):
    empty={"events":0,"total":0.0,"avg":0.0,"median":0.0,"wr":0.0,"pf":0.0,"dd":0.0,"pos_years":0,"years":0,"pos_quarters":0,"quarters":0,"months":0}
    if df.empty or col not in df.columns: return empty
    x=df.sort_values("entry_dt").copy()
    vals=pd.to_numeric(x[col], errors="coerce").dropna().astype(float).tolist()
    if not vals: return empty
    s=pd.Series(vals)
    years=x.groupby(x["entry_dt"].dt.year)[col].sum()
    quarters=x.groupby(period_no_tz(x["entry_dt"],"Q").astype(str))[col].sum()
    return {
        "events":len(vals),"total":round(float(s.sum()),6),"avg":round(float(s.mean()),6),
        "median":round(float(s.median()),6),"wr":round(float((s>0).mean()),6),
        "pf":profit_factor(vals),"dd":max_dd(vals),
        "pos_years":int((years>0).sum()),"years":int(len(years)),
        "pos_quarters":int((quarters>0).sum()),"quarters":int(len(quarters)),
        "months":int(period_no_tz(x["entry_dt"],"M").nunique()),
    }

def split_metrics(df, frac, col="net_x1"):
    x=df.sort_values("entry_dt").reset_index(drop=True)
    cut=int(len(x)*frac)
    return {"frac":frac,"train":metrics(x.iloc[:cut],col),"test":metrics(x.iloc[cut:],col)}

def bootstrap(df, col="net_x1", n=300, seed=19):
    if df.empty:
        return {"n":n,"total_p05":0.0,"total_p50":0.0,"pf_p05":0.0,"pf_p50":0.0,"median_p05":0.0,"prob_total_gt_0":0.0,"prob_pf_gt_1":0.0,"prob_median_gt_0":0.0}
    x=df.sort_values("entry_dt").reset_index(drop=True)
    totals=[]; pfs=[]; meds=[]
    for i in range(n):
        s=x.sample(n=len(x), replace=True, random_state=seed+i)
        vals=pd.to_numeric(s[col], errors="coerce").dropna().astype(float).tolist()
        totals.append(sum(vals)); pfs.append(profit_factor(vals)); meds.append(float(pd.Series(vals).median()) if vals else 0.0)
    ts=pd.Series(totals); ps=pd.Series(pfs); ms=pd.Series(meds)
    return {
        "n":n,"total_p05":round(float(ts.quantile(.05)),6),"total_p50":round(float(ts.quantile(.50)),6),
        "pf_p05":round(float(ps.quantile(.05)),6),"pf_p50":round(float(ps.quantile(.50)),6),
        "median_p05":round(float(ms.quantile(.05)),6),
        "prob_total_gt_0":round(float((ts>0).mean()),6),
        "prob_pf_gt_1":round(float((ps>1).mean()),6),
        "prob_median_gt_0":round(float((ms>0).mean()),6),
    }

def period_table(trades, period):
    if trades.empty: return pd.DataFrame()
    x=trades.copy()
    if period=="year": x["period"]=x["entry_dt"].dt.year.astype(str)
    elif period=="quarter": x["period"]=period_no_tz(x["entry_dt"],"Q").astype(str)
    elif period=="month": x["period"]=period_no_tz(x["entry_dt"],"M").astype(str)
    rows=[]
    for p,g in x.groupby("period"):
        r={"period":p}; r.update(metrics(g,"net_x1")); rows.append(r)
    return pd.DataFrame(rows).sort_values("period")

def decide(m1,m2,m4,s80,s70,y2026,boot):
    if m1["events"]<80: return "EXACT_REPLAY_REJECT_TOO_FEW_EVENTS", ["Exact M1 event count < 80."]
    promote=(
        m1["events"]>=100 and m1["total"]>0 and m1["pf"]>=1.15 and m1["median"]>0 and
        m2["total"]>0 and m2["pf"]>=1.08 and m4["pf"]>=1.00 and
        s80["test"]["events"]>=20 and s80["test"]["total"]>0 and s80["test"]["pf"]>=1.05 and
        s70["test"]["total"]>0 and
        (y2026["events"]<15 or (y2026["total"]>0 and y2026["pf"]>=1.00)) and
        m1["pos_years"]>=max(3, round(m1["years"]*.55)) and
        boot["prob_total_gt_0"]>=.90 and boot["pf_p05"]>=1.00
    )
    if promote: return "EXACT_REPLAY_PROMOTE_TO_FORWARD_SHADOW_DESIGN", ["Candidate survived exact M1 replay, cost stress, splits, 2026, year breadth, and bootstrap."]
    watch=(m1["events"]>=80 and m1["total"]>0 and m1["pf"]>=1.05 and s80["test"]["events"]>=15 and s80["test"]["total"]>0 and boot["prob_total_gt_0"]>=.75)
    if watch: return "EXACT_REPLAY_KEEP_WATCHLIST_ONLY", ["Exact M1 replay is positive but not strong enough for forward-shadow design."]
    return "EXACT_REPLAY_REJECT_WEAK", ["Exact M1 replay does not preserve enough robust edge."]

def run(db, out_dir, cost_usd, comp_max, bootstrap_n):
    generated=now_iso(); out_dir.mkdir(parents=True, exist_ok=True)
    conn=connect(db)
    try: m1=load_m1(conn)
    finally: conn.close()
    m15=resample_ohlc(m1,"15min"); h1=resample_ohlc(m1,"1h")
    ctx=add_context(m15,h1)
    trades=replay_exact_m1(ctx,m15,m1,cost_usd,comp_max)
    mx1=metrics(trades,"net_x1"); mx2=metrics(trades,"net_x2"); mx4=metrics(trades,"net_x4")
    s70=split_metrics(trades,.70); s80=split_metrics(trades,.80)
    y2026=metrics(trades[trades["entry_dt"].dt.year==2026],"net_x1") if not trades.empty else metrics(trades)
    boot=bootstrap(trades,"net_x1",bootstrap_n)
    final_decision,reasons=decide(mx1,mx2,mx4,s80,s70,y2026,boot)
    by_year=period_table(trades,"year"); by_quarter=period_table(trades,"quarter"); by_month=period_table(trades,"month")
    trades_csv=out_dir/"stage19b_exact_trades.csv"; by_year_csv=out_dir/"stage19b_exact_by_year.csv"; by_quarter_csv=out_dir/"stage19b_exact_by_quarter.csv"; by_month_csv=out_dir/"stage19b_exact_by_month.csv"
    json_path=out_dir/"stage19b_compression_breakout_exact_replay.json"; md_path=out_dir/"stage19b_compression_breakout_exact_replay.md"
    trades.to_csv(trades_csv,index=False); by_year.to_csv(by_year_csv,index=False); by_quarter.to_csv(by_quarter_csv,index=False); by_month.to_csv(by_month_csv,index=False)
    payload={
        "tool_version":TOOL_VERSION,"generated_utc":generated,
        "candidate":{"variant":VARIANT,"family":FAMILY,"side":SIDE,"horizon_bars":HORIZON_BARS,"horizon_minutes":HORIZON_MINUTES,"cooldown_bars":COOLDOWN_BARS,"comp_max":comp_max,"cost_usd":cost_usd},
        "source":{"m1_rows":len(m1),"m15_rows":len(m15),"h1_rows":len(h1),"m1_first":m1.index.min().isoformat(),"m1_last":m1.index.max().isoformat()},
        "metrics":{"net_x1":mx1,"net_x2":mx2,"net_x4":mx4,"split70":s70,"split80":s80,"year2026":y2026,"bootstrap":boot},
        "final_decision":final_decision,"reasons":reasons,
        "authorization_flags":{"trade_authorization":False,"ea_change_authorization":False,"paper_order_authorization":False,"live_order_authorization":False,"automatic_trading":False},
    }
    json_path.write_text(json.dumps(payload,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    lines=[
        "# Stage 19B Compression Expansion Breakout Exact M1 Replay","",
        f"Generated UTC: `{generated}`",f"Tool version: `{TOOL_VERSION}`","",
        "> Hard rule: research validation only. No EA change, no automatic trading, no paper/live authorization.","",
        "## Candidate",f"- variant: `{VARIANT}`",f"- family: `{FAMILY}`",f"- side: `{SIDE}`",
        f"- condition: `compression6 <= {comp_max}` and M15 close breaks prior local high16 during London/New York",
        f"- horizon_bars: `{HORIZON_BARS}`",f"- horizon_minutes: `{HORIZON_MINUTES}`",f"- cooldown_bars: `{COOLDOWN_BARS}`",f"- cost_usd: `{cost_usd}`","",
        "## Source",f"- db: `{db}`",f"- m1_rows: `{len(m1)}`",f"- m15_rows: `{len(m15)}`",f"- h1_rows: `{len(h1)}`",f"- m1_first: `{m1.index.min().isoformat()}`",f"- m1_last: `{m1.index.max().isoformat()}`","",
        "## Final decision",f"- final_decision: `{final_decision}`","",
        "## Reasons"]+[f"- {r}" for r in reasons]+[
        "",
        "## Exact M1 time-exit metrics",
        "| Cost model | Events | Total | Avg | Median | WR | PF | DD | Pos years | Years | Pos quarters | Quarters |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| net_x1 | {mx1['events']} | {mx1['total']} | {mx1['avg']} | {mx1['median']} | {mx1['wr']} | {mx1['pf']} | {mx1['dd']} | {mx1['pos_years']} | {mx1['years']} | {mx1['pos_quarters']} | {mx1['quarters']} |",
        f"| net_x2 | {mx2['events']} | {mx2['total']} | {mx2['avg']} | {mx2['median']} | {mx2['wr']} | {mx2['pf']} | {mx2['dd']} | {mx2['pos_years']} | {mx2['years']} | {mx2['pos_quarters']} | {mx2['quarters']} |",
        f"| net_x4 | {mx4['events']} | {mx4['total']} | {mx4['avg']} | {mx4['median']} | {mx4['wr']} | {mx4['pf']} | {mx4['dd']} | {mx4['pos_years']} | {mx4['years']} | {mx4['pos_quarters']} | {mx4['quarters']} |",
        "",
        "## Chronological splits","| Split | Segment | Events | Total | Median | PF | DD |","|---|---|---:|---:|---:|---:|---:|",
        f"| 70/30 | train | {s70['train']['events']} | {s70['train']['total']} | {s70['train']['median']} | {s70['train']['pf']} | {s70['train']['dd']} |",
        f"| 70/30 | test | {s70['test']['events']} | {s70['test']['total']} | {s70['test']['median']} | {s70['test']['pf']} | {s70['test']['dd']} |",
        f"| 80/20 | train | {s80['train']['events']} | {s80['train']['total']} | {s80['train']['median']} | {s80['train']['pf']} | {s80['train']['dd']} |",
        f"| 80/20 | test | {s80['test']['events']} | {s80['test']['total']} | {s80['test']['median']} | {s80['test']['pf']} | {s80['test']['dd']} |",
        "",
        "## 2026 segment",f"- events: `{y2026['events']}`",f"- total: `{y2026['total']}`",f"- median: `{y2026['median']}`",f"- pf: `{y2026['pf']}`",f"- dd: `{y2026['dd']}`","",
        "## Bootstrap",f"- n: `{boot['n']}`",f"- total_p05: `{boot['total_p05']}`",f"- total_p50: `{boot['total_p50']}`",f"- pf_p05: `{boot['pf_p05']}`",f"- pf_p50: `{boot['pf_p50']}`",f"- median_p05: `{boot['median_p05']}`",f"- prob_total_gt_0: `{boot['prob_total_gt_0']}`",f"- prob_pf_gt_1: `{boot['prob_pf_gt_1']}`",f"- prob_median_gt_0: `{boot['prob_median_gt_0']}`","",
        "## Interpretation","- Stage19B is exact historical validation, not forward proof.","- Promotion here only allows later forward-shadow collector design.","- Do not add this candidate to Stage18A unless the final decision is promotion.","- No paper/live/order escalation is authorized.","",
        "## Output files",f"- trades_csv: `{trades_csv}`",f"- by_year_csv: `{by_year_csv}`",f"- by_quarter_csv: `{by_quarter_csv}`",f"- by_month_csv: `{by_month_csv}`",f"- json: `{json_path}`",f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("Stage 19B compression breakout exact M1 replay: DONE")
    print(f"final_decision={final_decision}")
    print(f"events={mx1['events']} total={mx1['total']} pf={mx1['pf']} median={mx1['median']}")
    print(f"Report: {md_path}")
    return 0

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB)); p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35); p.add_argument("--comp-max", type=float, default=COMP_MAX)
    p.add_argument("--bootstrap-n", type=int, default=300)
    a=p.parse_args()
    return run(Path(a.db), Path(a.out_dir), float(a.cost_usd), float(a.comp_max), int(a.bootstrap_n))
if __name__=="__main__":
    raise SystemExit(main())
