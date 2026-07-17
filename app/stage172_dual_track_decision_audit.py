#!/usr/bin/env python3
"""Stage172 dual-track, read-only commercial decision audit.

Track A: exact H64L historical-as-of audit with a locked final 20% holdout.
Track B: three fixed AMarkets M5/H1 baseline families, long/short separated.

The program is intentionally fail-closed. It never writes orders, never changes
Stage171 infrastructure, never tunes thresholds, and never starts ML.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STAGE = "Stage172_DUAL_TRACK_DECISION_AUDIT_GOVERNANCE_FIXED"
OUT_DIR = "reports/stage172_dual_track_decision_audit"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str | Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def first_existing(root: Path, values: Sequence[str]) -> Optional[Path]:
    for v in values:
        p = resolve(root, v)
        if p.exists() and p.is_file():
            return p
    return None


def detect_sep(path: Path) -> str:
    line = path.open("r", encoding="utf-8-sig", errors="replace").readline()
    return max(["\t", ",", ";", "|"], key=line.count)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def normalize_ohlc(path: Path) -> pd.DataFrame:
    sep = detect_sep(path)
    raw = pd.read_csv(path, sep=sep, low_memory=False)
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    date_col = cmap.get("<date>") or cmap.get("date") or cmap.get("timestamp") or cmap.get("datetime")
    time_col = cmap.get("<time>") or cmap.get("time")
    if date_col is None:
        raise ValueError(f"timestamp/date column missing: {list(raw.columns)}")
    if time_col is not None and date_col != cmap.get("timestamp") and date_col != cmap.get("datetime"):
        ts = pd.to_datetime(raw[date_col].astype(str).str.strip()+" "+raw[time_col].astype(str).str.strip(), utc=True, errors="coerce")
    else:
        ts = pd.to_datetime(raw[date_col], utc=True, errors="coerce")
    def col(name: str) -> Any:
        c = cmap.get(f"<{name}>") or cmap.get(name)
        if c is None:
            raise ValueError(f"{name} column missing: {list(raw.columns)}")
        return pd.to_numeric(raw[c], errors="coerce")
    out = pd.DataFrame({"ts": ts, "open": col("open"), "high": col("high"), "low": col("low"), "close": col("close")})
    spread_col = cmap.get("<spread>") or cmap.get("spread")
    if spread_col is not None:
        out["spread"] = pd.to_numeric(raw[spread_col], errors="coerce")
    out = out.dropna(subset=["ts","open","high","low","close"]).sort_values("ts").drop_duplicates("ts", keep="last")
    bad = (out["high"] < out[["open","close","low"]].max(axis=1)) | (out["low"] > out[["open","close","high"]].min(axis=1))
    if bad.any():
        raise ValueError(f"OHLC invariant failures: {int(bad.sum())}")
    if len(out) < 500:
        raise ValueError(f"insufficient OHLC rows: {len(out)}")
    return out.reset_index(drop=True)


def locked_split(ts: pd.Series, frac: float) -> Tuple[pd.Timestamp, pd.Series]:
    if not 0 < frac < 0.5:
        raise ValueError("holdout_fraction must be between 0 and 0.5")
    unique = pd.Series(pd.to_datetime(ts, utc=True).dropna().sort_values().unique())
    if len(unique) < 10:
        raise ValueError("too few timestamps for locked split")
    idx = max(1, min(len(unique)-1, int(math.floor(len(unique)*(1-frac)))))
    cutoff = pd.Timestamp(unique.iloc[idx])
    return cutoff, pd.to_datetime(ts, utc=True) >= cutoff


def max_drawdown_bps(returns: pd.Series) -> float:
    if returns.empty: return 0.0
    eq = returns.fillna(0).cumsum(); peak = eq.cummax()
    return float((peak-eq).max())


def metrics(trades: pd.DataFrame) -> Dict[str, Any]:
    if trades.empty:
        return {"trades":0,"net_expectancy_bps":None,"win_rate":None,"profit_factor":None,"max_drawdown_bps":None}
    r = trades["net_bps"].astype(float)
    pos = float(r[r>0].sum()); neg = float(-r[r<0].sum())
    return {
        "trades": int(len(trades)),
        "net_expectancy_bps": float(r.mean()),
        "median_net_bps": float(r.median()),
        "win_rate": float((r>0).mean()),
        "profit_factor": (pos/neg if neg > 0 else None),
        "total_net_bps": float(r.sum()),
        "max_drawdown_bps": max_drawdown_bps(r),
    }


def concentration(trades: pd.DataFrame, col: str) -> Dict[str, Any]:
    if trades.empty or col not in trades: return {"max_share":None,"leader":None,"counts":{}}
    c = trades[col].astype(str).value_counts()
    return {"max_share":float(c.iloc[0]/c.sum()),"leader":str(c.index[0]),"counts":{str(k):int(v) for k,v in c.items()}}


def infer_feature_table(path: Path, etf_lag_days: int) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        rows = obj if isinstance(obj, list) else obj.get("rows") or obj.get("events") or obj.get("data")
        if not isinstance(rows, list):
            raise ValueError("JSON H64L feature source has no row list")
        raw = pd.DataFrame(rows)
    else:
        raw = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    cmap = {str(c).strip().lower(): c for c in raw.columns}
    req = ["gold_sma20_over_50","dxy_ret_20d","real_yield_change_20d","etf_flow_tonnes_3m"]
    missing = [x for x in req if x not in cmap]
    if missing: raise ValueError(f"H64L features missing: {missing}; columns={list(raw.columns)}")
    date_candidates = ["feature_date_utc","date_utc","date","timestamp","as_of_date"]
    dc = next((cmap[x] for x in date_candidates if x in cmap), None)
    if dc is None: raise ValueError("H64L feature date missing")
    out = pd.DataFrame({"date":pd.to_datetime(raw[dc], utc=True, errors="coerce").dt.floor("D")})
    for x in req: out[x] = pd.to_numeric(raw[cmap[x]], errors="coerce")
    ac = next((cmap[x] for x in ["sample_available_after_utc","available_after_utc","release_timestamp_utc"] if x in cmap), None)
    if ac is not None:
        out["available_after"] = pd.to_datetime(raw[ac], utc=True, errors="coerce")
    else:
        out["available_after"] = out["date"] + pd.to_timedelta(etf_lag_days, unit="D")
        out["availability_assumption"] = f"ETF_RELEASE_LAG_{etf_lag_days}D_APPLIED_TO_WHOLE_ROW"
    out = out.dropna(subset=["date"]+req).sort_values("date").drop_duplicates("date", keep="last")
    if (out["available_after"] < out["date"]).any(): raise ValueError("available_after precedes feature date")
    return out


def daily_from_m5(m5: pd.DataFrame) -> pd.DataFrame:
    x=m5.copy(); x["date"]=x["ts"].dt.floor("D")
    d=x.groupby("date",as_index=False).agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),bars=("close","size"))
    return d[d["bars"]>=100].reset_index(drop=True)


def build_episodes(active: pd.DataFrame, min_gap_days: int) -> pd.DataFrame:
    x=active.sort_values("date").copy(); x["active"] = x["active"].astype(bool); x["prev_active"] = x["active"].shift(1, fill_value=False).astype(bool)
    x["gap_days"] = x["date"].diff().dt.days
    x["episode_start"] = x["active"] & ((~x["prev_active"]) | (x["gap_days"] > min_gap_days))
    return x[x["episode_start"]].copy()


def run_track_a(root: Path, cfg: Dict[str,Any], m5: pd.DataFrame, out: Path) -> Dict[str,Any]:
    acfg=cfg["track_a"]; path=first_existing(root,cfg["data"]["h64l_feature_candidates"])
    if path is None: return {"status":"BLOCKED","decision":"INCONCLUSIVE_BLOCKED","issues":["H64L_HISTORICAL_ASOF_FEATURE_TABLE_NOT_FOUND"]}
    try: f=infer_feature_table(path,int(acfg["etf_release_lag_days_if_missing"]))
    except Exception as e: return {"status":"BLOCKED","decision":"INCONCLUSIVE_BLOCKED","issues":[f"FEATURE_LOAD:{type(e).__name__}:{e}"],"source":str(path)}
    d=daily_from_m5(m5); d["gold_ret_fwd_bps"]=(d["close"].shift(-int(acfg["holding_days"]))/d["close"]-1)*10000
    # Only information available by the decision date can be used.
    z=pd.merge_asof(d.sort_values("date"), f.sort_values("available_after"), left_on="date", right_on="available_after", direction="backward", suffixes=("","_feat"))
    z["active"]=(z["gold_sma20_over_50"]>0)&(z["dxy_ret_20d"]<0)&(z["real_yield_change_20d"]<0)&(z["etf_flow_tonnes_3m"]>0)
    eps=build_episodes(z[["date","active","gold_ret_fwd_bps","close"]].dropna(),int(acfg["minimum_days_between_independent_episodes"]))
    eps["entry_ts"]=eps["date"]; eps["gross_bps"]=eps["gold_ret_fwd_bps"]
    cost=float(cfg["costs"]["round_trip_cost_bps"])+float(cfg["costs"]["slippage_bps"])
    eps["net_bps"]=eps["gross_bps"]-cost; eps["year"]=eps["entry_ts"].dt.year
    eps["regime"] = pd.cut(z.loc[eps.index,"gold_sma20_over_50"],[-np.inf,0.02,0.05,np.inf],labels=["MILD","MEDIUM","STRONG"]).astype(str).values
    cutoff, mask=locked_split(d["date"],float(cfg["governance"]["holdout_fraction"])); eps["partition"]=np.where(eps["entry_ts"]>=cutoff,"HOLDOUT","DEVELOPMENT")
    drift=d.dropna(subset=["gold_ret_fwd_bps"]).copy(); drift["net_bps"]=drift["gold_ret_fwd_bps"]-cost; drift["partition"]=np.where(drift["date"]>=cutoff,"HOLDOUT","DEVELOPMENT")
    hold=eps[eps["partition"]=="HOLDOUT"].copy(); hm=metrics(hold); yc=concentration(hold,"year"); rc=concentration(hold,"regime")
    years=max(1.0,(d["date"].max()-d["date"].min()).days/365.25); freq=len(eps)/years
    gaps=eps["entry_ts"].sort_values().diff().dt.days.dropna()
    drift_hold=metrics(pd.DataFrame({"net_bps":drift.loc[drift["partition"]=="HOLDOUT","net_bps"]}))
    gates={
      "holdout_episodes":len(hold)>=int(acfg["minimum_holdout_episodes"]),
      "positive_net_expectancy":hm["net_expectancy_bps"] is not None and hm["net_expectancy_bps"]>=float(acfg["minimum_net_expectancy_bps"]),
      "drawdown":hm["max_drawdown_bps"] is not None and hm["max_drawdown_bps"]<=float(acfg["maximum_drawdown_bps"]),
      "year_concentration":yc["max_share"] is not None and yc["max_share"]<=float(acfg["maximum_single_year_share"]),
      "regime_concentration":rc["max_share"] is not None and rc["max_share"]<=float(acfg["maximum_single_regime_share"]),
      "beats_drift":hm["net_expectancy_bps"] is not None and drift_hold["net_expectancy_bps"] is not None and hm["net_expectancy_bps"]>drift_hold["net_expectancy_bps"]
    }
    if not gates["holdout_episodes"] or not gates["positive_net_expectancy"] or not gates["beats_drift"]: decision="KILL"
    elif freq < float(acfg["minimum_annual_frequency_for_shadow"]) or not all([gates["drawdown"],gates["year_concentration"],gates["regime_concentration"]]): decision="OVERLAY_ONLY"
    else: decision="SHADOW_CANDIDATE"
    eps.to_csv(out/"stage172_track_a_h64l_episodes.csv",index=False)
    return {"status":"COMPLETE","decision":decision,"source":str(path),"source_sha256":sha256(path),"holdout_cutoff_utc":str(cutoff),"holding_days":int(acfg["holding_days"]),"episode_count":int(len(eps)),"annual_frequency":float(freq),"median_gap_days":float(gaps.median()) if len(gaps) else None,"holdout_metrics":hm,"gold_drift_holdout":drift_hold,"year_concentration":yc,"regime_concentration":rc,"gates":gates,"availability_note":"Rows are joined by available_after; missing availability uses the configured conservative lag and is disclosed."}


def add_h1_features(h1: pd.DataFrame) -> pd.DataFrame:
    x=h1.copy(); x["sma50"]=x["close"].rolling(50).mean(); x["sma200"]=x["close"].rolling(200).mean(); x["h1_trend"]=np.sign(x["sma50"]-x["sma200"]); return x[["ts","h1_trend"]].dropna()


def add_m5_features(m5: pd.DataFrame) -> pd.DataFrame:
    x=m5.copy(); prev=x["close"].shift(); tr=pd.concat([(x["high"]-x["low"]),(x["high"]-prev).abs(),(x["low"]-prev).abs()],axis=1).max(axis=1)
    x["atr14"]=tr.rolling(14).mean(); x["atr_med96"]=x["atr14"].rolling(96).median(); x["ema20"]=x["close"].ewm(span=20,adjust=False).mean(); x["range12_hi"]=x["high"].shift(1).rolling(12).max(); x["range12_lo"]=x["low"].shift(1).rolling(12).min(); x["hour"]=x["ts"].dt.hour; return x


def load_daily_value(path: Path) -> pd.DataFrame:
    raw=pd.read_csv(path,sep=detect_sep(path),low_memory=False); cmap={str(c).lower().strip():c for c in raw.columns}
    dc=next((cmap[x] for x in ["date_utc","observation_date","date","timestamp"] if x in cmap),None)
    if dc is None: raise ValueError("daily series date missing")
    excluded={dc}
    numeric=[]
    for c in raw.columns:
        if c in excluded: continue
        v=pd.to_numeric(raw[c],errors="coerce")
        if v.notna().sum()>=20: numeric.append((int(v.notna().sum()),c,v))
    if not numeric: raise ValueError("daily series value missing")
    _,vc,v=max(numeric,key=lambda z:z[0])
    out=pd.DataFrame({"date":pd.to_datetime(raw[dc],utc=True,errors="coerce").dt.floor("D"),"value":v}).dropna().sort_values("date").drop_duplicates("date",keep="last")
    return out


def attach_macro_guards(root:Path,cfg:Dict[str,Any],x:pd.DataFrame)->pd.DataFrame:
    out=x.copy(); out["macro_long_safe"]=False; out["macro_short_safe"]=False
    dp=first_existing(root,cfg["data"]["dxy_candidates"]); rp=first_existing(root,cfg["data"]["real_yield_candidates"])
    if dp is None or rp is None: return out
    try:
        d=load_daily_value(dp).rename(columns={"value":"dxy"}); r=load_daily_value(rp).rename(columns={"value":"ry"})
        d["dxy_ret20"]=d["dxy"].pct_change(20); r["ry_chg20"]=r["ry"].diff(20)
        daily=pd.merge_asof(d.sort_values("date"),r.sort_values("date"),on="date",direction="backward")[["date","dxy_ret20","ry_chg20"]].dropna()
        out=pd.merge_asof(out.sort_values("ts"),daily.sort_values("date"),left_on="ts",right_on="date",direction="backward")
        out["macro_long_safe"]=~((out["dxy_ret20"]>0)&(out["ry_chg20"]>0))
        out["macro_short_safe"]=~((out["dxy_ret20"]<0)&(out["ry_chg20"]<0))
        return out
    except Exception:
        return out


def news_guard(root:Path,cfg:Dict[str,Any],ts:pd.Series)->pd.Series:
    p=first_existing(root,cfg["data"]["news_calendar_candidates"])
    if p is None: return pd.Series(False,index=ts.index)
    try:
        r=pd.read_csv(p,sep=detect_sep(p),low_memory=False); cmap={str(c).lower().strip():c for c in r.columns}; dc=next((cmap[x] for x in ["timestamp","timestamp_utc","datetime","date_utc"] if x in cmap),None)
        if dc is None: return pd.Series(False,index=ts.index)
        ev=pd.to_datetime(r[dc],utc=True,errors="coerce").dropna().sort_values().to_numpy(dtype="datetime64[ns]"); mins=int(cfg["track_b"]["news_blackout_minutes"])
        arr=ts.to_numpy(dtype="datetime64[ns]"); pos=np.searchsorted(ev,arr); safe=np.ones(len(arr),dtype=bool)
        for off in [0,-1]:
            ix=np.clip(pos+off,0,max(0,len(ev)-1));
            if len(ev): safe &= np.abs(arr-ev[ix]) > np.timedelta64(mins,"m")
        return pd.Series(safe,index=ts.index)
    except Exception: return pd.Series(False,index=ts.index)


def cooldown_filter(signal: pd.Series, bars:int) -> pd.Series:
    out=np.zeros(len(signal),dtype=bool); last=-10**9
    for i,v in enumerate(signal.fillna(False).to_numpy()):
        if v and i-last>=bars: out[i]=True; last=i
    return pd.Series(out,index=signal.index)


def strategy_trades(x:pd.DataFrame,name:str,direction:int,signal:pd.Series,cfg:Dict[str,Any],cutoff:pd.Timestamp)->pd.DataFrame:
    b=int(cfg["track_b"]["holding_bars"]); cost=float(cfg["costs"]["round_trip_cost_bps"])+float(cfg["costs"]["slippage_bps"])
    sig=cooldown_filter(signal,int(cfg["track_b"]["cooldown_bars"])); idx=np.flatnonzero(sig.to_numpy()); idx=idx[idx+b<len(x)]
    if len(idx)==0: return pd.DataFrame(columns=["strategy","direction","entry_ts","exit_ts","gross_bps","net_bps","year","session","partition"])
    ent=x.iloc[idx]; ex=x.iloc[idx+b]
    gross=direction*(ex["close"].to_numpy()/ent["close"].to_numpy()-1)*10000
    return pd.DataFrame({"strategy":name,"direction":"LONG" if direction>0 else "SHORT","entry_ts":ent["ts"].to_numpy(),"exit_ts":ex["ts"].to_numpy(),"gross_bps":gross,"net_bps":gross-cost,"year":ent["ts"].dt.year.to_numpy(),"session":np.where(ent["hour"].between(7,11),"LONDON",np.where(ent["hour"].between(13,17),"NEW_YORK","OTHER")),"partition":np.where(ent["ts"]>=cutoff,"HOLDOUT","DEVELOPMENT")})


def run_track_b(root:Path,cfg:Dict[str,Any],m5:pd.DataFrame,h1:pd.DataFrame,out:Path)->Dict[str,Any]:
    h=add_h1_features(h1); x=pd.merge_asof(add_m5_features(m5).sort_values("ts"),h.sort_values("ts"),on="ts",direction="backward"); x["news_safe"]=news_guard(root,cfg,x["ts"]); x=attach_macro_guards(root,cfg,x)
    cutoff,_=locked_split(x["ts"],float(cfg["governance"]["holdout_fraction"])); families=[]
    # Fixed family 1: H1 trend + M5 EMA20 pullback/reclaim.
    families += [("HTF_TREND_INTRADAY_PULLBACK",1,(x["h1_trend"]>0)&(x["low"]<=x["ema20"])&(x["close"]>x["ema20"])),("HTF_TREND_INTRADAY_PULLBACK",-1,(x["h1_trend"]<0)&(x["high"]>=x["ema20"])&(x["close"]<x["ema20"]))]
    # Fixed family 2: London/NY 12-bar range continuation in H1 direction.
    sess=x["hour"].isin([7,8,9,13,14,15]); families += [("LONDON_NY_RANGE_CONTINUATION",1,sess&(x["h1_trend"]>0)&(x["close"]>x["range12_hi"])),("LONDON_NY_RANGE_CONTINUATION",-1,sess&(x["h1_trend"]<0)&(x["close"]<x["range12_lo"]))]
    # Fixed family 3: volatility expansion, macro/news guard represented by H1 non-opposition + news blackout.
    vm=float(cfg["track_b"]["volatility_expansion_multiplier"]); am=float(cfg["track_b"]["atr_regime_multiplier"]); vol=(x["high"]-x["low"]>vm*x["atr14"])&(x["atr14"]>am*x["atr_med96"])&x["news_safe"]
    families += [("VOLATILITY_EXPANSION_GUARDED",1,vol&(x["close"]>x["open"])&(x["h1_trend"]>=0)&x["macro_long_safe"]),("VOLATILITY_EXPANSION_GUARDED",-1,vol&(x["close"]<x["open"])&(x["h1_trend"]<=0)&x["macro_short_safe"])]
    trades=pd.concat([strategy_trades(x,n,d,s,cfg,cutoff) for n,d,s in families],ignore_index=True)
    if not trades.empty: trades=trades.sort_values("entry_ts")
    trades.to_csv(out/"stage172_track_b_baseline_trades.csv",index=False)
    rows=[]; tcfg=cfg["track_b"]
    for (name,direction),g in trades.groupby(["strategy","direction"],dropna=False):
        hold=g[g["partition"]=="HOLDOUT"]; m=metrics(hold); yc=concentration(hold,"year"); sc=concentration(hold,"session")
        gates={"trade_count":len(hold)>=int(tcfg["minimum_holdout_trades"]),"expectancy":m["net_expectancy_bps"] is not None and m["net_expectancy_bps"]>=float(tcfg["minimum_net_expectancy_bps"]),"profit_factor":m["profit_factor"] is not None and m["profit_factor"]>=float(tcfg["minimum_profit_factor"]),"drawdown":m["max_drawdown_bps"] is not None and m["max_drawdown_bps"]<=float(tcfg["maximum_drawdown_bps"]),"year_concentration":yc["max_share"] is not None and yc["max_share"]<=float(tcfg["maximum_single_year_share"]),"session_concentration":sc["max_share"] is not None and sc["max_share"]<=float(tcfg["maximum_single_session_share"])}
        rows.append({"strategy":name,"direction":direction,"holdout_metrics":m,"year_concentration":yc,"session_concentration":sc,"gates":gates,"survives":all(gates.values())})
    # Ensure missing strategy/direction combinations are visible as failures.
    seen={(r["strategy"],r["direction"]) for r in rows}
    for n,d,_ in families:
        key=(n,"LONG" if d>0 else "SHORT")
        if key not in seen: rows.append({"strategy":key[0],"direction":key[1],"holdout_metrics":metrics(pd.DataFrame()),"gates":{"trade_count":False,"expectancy":False,"profit_factor":False,"drawdown":False,"year_concentration":False,"session_concentration":False},"survives":False})
    survivors=[r for r in rows if r["survives"]]
    return {"status":"COMPLETE","decision":"BASELINE_SURVIVOR" if survivors else "NO_BASELINE_SURVIVOR","holdout_cutoff_utc":str(cutoff),"results":rows,"survivors":[{"strategy":r["strategy"],"direction":r["direction"]} for r in survivors],"ml_allowed":bool(survivors),"ml_scope":"ON_OFF_FILTER_ONLY" if survivors else "FORBIDDEN"}


def decision_md(summary:Dict[str,Any])->str:
    a=summary["track_a"]; b=summary["track_b"]
    lines=["# Stage172 Decision",f"\nGenerated: {summary['generated_utc']}","\n## Hard controls","\n- Orders/demo/live: forbidden.","- Threshold reoptimization: forbidden.","- ML: allowed only as an ON/OFF filter after a Track B holdout survivor.","\n## Track A — H64L",f"\n**Decision: `{a.get('decision')}`**",f"\nStatus: {a.get('status')}"]
    for issue in a.get("issues",[]): lines.append(f"- {issue}")
    lines += ["\n## Track B — Primary generator shortlist",f"\n**Decision: `{b.get('decision')}`**",f"\nML allowed: `{b.get('ml_allowed',False)}`",f"\nSurvivors: `{b.get('survivors',[])}`","\n## Program decision",f"\n**`{summary['program_decision']}`**","\nStage171 remains frozen except operational defect repair. H64L is suspended as an interpretable signal while source reconciliation is unresolved; raw health logging may continue. No paper-order bridge is authorized."]
    return "\n".join(lines)+"\n"


def main(argv:Optional[List[str]]=None)->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="~/Desktop/xauusd-trader"); ap.add_argument("--config",default="configs/stage172_dual_track_decision_audit.json"); ap.add_argument("--out-dir",default=OUT_DIR); ap.add_argument("--m5",default=""); ap.add_argument("--h1",default=""); args=ap.parse_args(argv)
    root=Path(args.root).expanduser().resolve(); cfg=json.loads(resolve(root,args.config).read_text(encoding="utf-8")); out=resolve(root,args.out_dir); out.mkdir(parents=True,exist_ok=True)
    summary={"stage":STAGE,"generated_utc":utc_now(),"root":str(root),"hard_controls":cfg["governance"],"issues":[]}
    try:
        m5p=resolve(root,args.m5) if args.m5 else first_existing(root,cfg["data"]["m5_candidates"]); h1p=resolve(root,args.h1) if args.h1 else first_existing(root,cfg["data"]["h1_candidates"])
        if m5p is None or h1p is None: raise FileNotFoundError(f"AMarkets inputs missing: m5={m5p}, h1={h1p}")
        m5=normalize_ohlc(m5p); h1=normalize_ohlc(h1p); summary["inputs"]={"m5":str(m5p),"m5_sha256":sha256(m5p),"m5_rows":len(m5),"h1":str(h1p),"h1_sha256":sha256(h1p),"h1_rows":len(h1)}
        summary["track_a"]=run_track_a(root,cfg,m5,out); summary["track_b"]=run_track_b(root,cfg,m5,h1,out)
    except Exception as e:
        summary["issues"].append(f"FATAL:{type(e).__name__}:{e}"); summary["track_a"]={"status":"BLOCKED","decision":"INCONCLUSIVE_BLOCKED","issues":summary["issues"]}; summary["track_b"]={"status":"BLOCKED","decision":"NO_BASELINE_SURVIVOR","ml_allowed":False,"survivors":[],"issues":summary["issues"]}
    if summary["track_b"].get("decision") == "BASELINE_SURVIVOR":
        summary["program_decision"]="PROCEED_TO_LOCKED_BASELINE_SHADOW_DESIGN_NO_ORDERS"
    elif summary["track_a"].get("status") == "BLOCKED":
        summary["program_decision"]="KILL_STAGE172_TESTED_TECHNICAL_BASELINES_BLOCK_H64L_PENDING_VALIDATED_INPUT_NO_ML"
    else:
        summary["program_decision"]="KILL_STAGE172_TESTED_TECHNICAL_BASELINES_APPLY_TRACK_A_DECISION_NO_ML"
    write_json(out/"stage172_summary.json",summary); (out/"stage172_decision.md").write_text(decision_md(summary),encoding="utf-8")
    return 0 if not summary["issues"] and summary["track_a"].get("status")=="COMPLETE" and summary["track_b"].get("status")=="COMPLETE" else 2

if __name__=="__main__": sys.exit(main())
