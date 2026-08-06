#!/usr/bin/env python3
"""Reference-only XAUUSD long-side volatility-expansion attribution audit.

This program investigates one pre-registered clue from the rejected successor scan:
the LONG leg of the fixed 48-hour volatility-expansion rule. It does not access
2025+ data, does not select a new trading system, and has no broker/order path.
It tests whether the apparent long-side result exceeds a matched bull-drift
control and is reproducible on both AMarkets and Dukascopy H1 feeds.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

UTC = timezone.utc
MS_HOUR = 3_600_000
PROGRAM = "XAUUSD_LONG_ONLY_VOL_EXPANSION_ATTRIBUTION_V1_REFERENCE_ONLY"
PASS_DECISION = "LONG_ONLY_EDGE_ATTRIBUTION_PASS_FOR_MACRO_OVERLAY_DESIGN"
FAIL_DECISION = "REJECT_LONG_ONLY_ATTRIBUTION_AND_PIVOT_MACRO_DATA"

class AuditError(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as h:
        h.write(text)
        tmp = h.name
    os.replace(tmp, path)


def write_json(path: Path, obj: Any) -> None:
    atomic_write(path, json.dumps(obj, indent=2, sort_keys=True, default=json_default) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as h:
        for block in iter(lambda: h.read(1024 * 1024), b""):
            d.update(block)
    return d.hexdigest()


def resolve(root: Path, value: str | Path) -> Path:
    p = Path(os.path.expanduser(str(value)))
    if not p.is_absolute():
        p = root / p
    return p.resolve()


def to_ms(value: str | pd.Timestamp) -> int:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    if hasattr(stamp, "as_unit"):
        stamp = stamp.as_unit("ns")
    return int(stamp.value // 1_000_000)


def load_h1_bounded(path: Path, table: str, start_ms: int, end_ms: int, minimum_m5: int | None = None) -> pd.DataFrame:
    if not path.is_file():
        raise AuditError(f"database missing: {path}")
    with closing(sqlite3.connect(path)) as con:
        columns = [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]
        required = {"timestamp", "open", "high", "low", "close"}
        missing = sorted(required - set(columns))
        if missing:
            raise AuditError(f"{table} missing columns: {missing}")
        volume_expr = "volume" if "volume" in columns else "NULL AS volume"
        predicates = ["timestamp >= ?", "timestamp < ?"]
        params: list[Any] = [start_ms, end_ms]
        if minimum_m5 is not None and "m5_bar_count" in columns:
            predicates.append("m5_bar_count >= ?")
            params.append(int(minimum_m5))
        frame = pd.read_sql_query(
            f'''SELECT timestamp, open, high, low, close, {volume_expr}
                FROM "{table}" WHERE {' AND '.join(predicates)} ORDER BY timestamp''',
            con,
            params=tuple(params),
        )
    if frame.empty:
        raise AuditError(f"no bounded rows in {table}")
    for c in ["timestamp", "open", "high", "low", "close", "volume"]:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    if int(frame["timestamp"].min()) < start_ms or int(frame["timestamp"].max()) >= end_ms:
        raise AuditError("bounded data query leaked outside reference interval")
    frame["dt"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    invariant = (frame["high"] >= frame[["open", "close", "low"]].max(axis=1)) & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
    if not bool(invariant.all()):
        raise AuditError(f"OHLC invariant failure in {table}")
    return frame.reset_index(drop=True)


def load_events_bounded(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    columns = ["event_dt", "before", "after"]
    if not path.is_file():
        return pd.DataFrame(columns=columns)
    with closing(sqlite3.connect(path)) as con:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "official_events" not in tables:
            return pd.DataFrame(columns=columns)
        raw = pd.read_sql_query(
            """SELECT event_time_utc, blackout_before_minutes, blackout_after_minutes
               FROM official_events
               WHERE event_time_utc >= ? AND event_time_utc < ?
               ORDER BY event_time_utc""",
            con,
            params=(start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")),
        )
    if raw.empty:
        return pd.DataFrame(columns=columns)
    dt = pd.to_datetime(raw["event_time_utc"], utc=True, errors="coerce")
    out = pd.DataFrame({
        "event_dt": dt,
        "before": pd.to_numeric(raw["blackout_before_minutes"], errors="coerce").fillna(60.0),
        "after": pd.to_numeric(raw["blackout_after_minutes"], errors="coerce").fillna(60.0),
    }).dropna(subset=["event_dt"])
    out = out[(out.event_dt >= start) & (out.event_dt < end)]
    return out.drop_duplicates("event_dt").sort_values("event_dt").reset_index(drop=True)


def add_event_blackout(frame: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
    result = np.zeros(len(frame), dtype=bool)
    if events.empty:
        return pd.Series(result, index=frame.index)
    signal_ms = frame["timestamp"].to_numpy(np.int64) + MS_HOUR
    event_ms = np.array([to_ms(v) for v in events.event_dt], dtype=np.int64)
    before = events.before.to_numpy(float) * 60_000
    after = events.after.to_numpy(float) * 60_000
    for i, t in enumerate(signal_ms):
        pos = int(np.searchsorted(event_ms, t, side="right"))
        for j in (pos - 1, pos):
            if 0 <= j < len(event_ms) and event_ms[j] - before[j] <= t <= event_ms[j] + after[j]:
                result[i] = True
                break
    return pd.Series(result, index=frame.index)


def build_features(frame: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    x = frame.copy()
    close = x.close.astype(float)
    prev = close.shift(1)
    tr = pd.concat([(x.high-x.low), (x.high-prev).abs(), (x.low-prev).abs()], axis=1).max(axis=1)
    x["atr14"] = tr.rolling(14, min_periods=14).mean()
    x["atr120"] = tr.rolling(120, min_periods=120).mean()
    x["atr_ratio"] = x.atr14 / x.atr120
    x["sma240"] = close.rolling(240, min_periods=240).mean()
    x["sma_gap_240"] = close / x.sma240 - 1.0
    x["body_pct"] = close / x.open - 1.0
    x["range_to_atr"] = (x.high - x.low) / x.atr14
    x["event_blackout"] = add_event_blackout(x, events)
    x["signal_time"] = x.dt + pd.Timedelta(hours=1)
    x["signal_hour"] = x.signal_time.dt.hour
    x["signal_dow"] = x.signal_time.dt.dayofweek
    # Resolution-invariant deterministic quintiles within the bounded reference set.
    rank = x.atr_ratio.rank(method="first", pct=True)
    x["atr_quintile"] = np.minimum(4, np.floor(rank.fillna(0.0) * 5).astype(int))
    return x


def outcomes(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    ts = frame.timestamp.to_numpy(np.int64)
    op = frame.open.to_numpy(float)
    cl = frame.close.to_numpy(float)
    index = {int(v): i for i, v in enumerate(ts)}
    rows=[]
    for signal_pos, signal_ts in enumerate(ts):
        entry_ts = int(signal_ts + MS_HOUR)
        exit_bar_ts = int(entry_ts + (horizon-1)*MS_HOUR)
        ep=index.get(entry_ts); xp=index.get(exit_bar_ts)
        if ep is None or xp is None:
            continue
        rows.append({"signal_timestamp":int(signal_ts),"entry_timestamp":entry_ts,"exit_time":exit_bar_ts+MS_HOUR,"entry_open":float(op[ep]),"exit_close":float(cl[xp])})
    return pd.DataFrame(rows)


def signal_series(frame: pd.DataFrame, side: int) -> pd.Series:
    expansion = frame.range_to_atr >= 1.8
    trend = frame.sma_gap_240 > 0
    if side == 1:
        condition = expansion & trend & (frame.body_pct > 0)
    elif side == -1:
        condition = expansion & (frame.sma_gap_240 < 0) & (frame.body_pct < 0)
    else:
        raise AuditError("side must be +1 or -1")
    condition &= ~frame.event_blackout.fillna(False)
    condition &= frame.signal_dow < 5
    return condition.fillna(False)


def make_trades(frame: pd.DataFrame, side: int, severe_cost: float, horizon: int = 48) -> pd.DataFrame:
    sig = signal_series(frame, side)
    out = outcomes(frame, horizon)
    if out.empty:
        return pd.DataFrame(columns=["signal_timestamp","entry_timestamp","exit_time","signal_utc","entry_utc","exit_utc","direction","entry_open","exit_close","gross_bps","severe_net_bps","signal_hour","atr_quintile","sma_gap_240","range_to_atr"])
    sigmap = dict(zip(frame.timestamp.astype(int), sig.astype(bool)))
    feature_map = frame.set_index("timestamp")[["signal_hour","atr_quintile","sma_gap_240","range_to_atr"]].to_dict("index")
    rows=[]; next_allowed=-2**63
    for row in out.itertuples(index=False):
        if not sigmap.get(int(row.signal_timestamp), False) or int(row.entry_timestamp) < next_allowed:
            continue
        gross = side*(row.exit_close/row.entry_open-1)*10000
        f=feature_map[int(row.signal_timestamp)]
        rows.append({"signal_timestamp":int(row.signal_timestamp),"entry_timestamp":int(row.entry_timestamp),"exit_time":int(row.exit_time),"signal_utc":pd.to_datetime(row.signal_timestamp,unit="ms",utc=True),"entry_utc":pd.to_datetime(row.entry_timestamp,unit="ms",utc=True),"exit_utc":pd.to_datetime(row.exit_time,unit="ms",utc=True),"direction":side,"entry_open":row.entry_open,"exit_close":row.exit_close,"gross_bps":gross,"severe_net_bps":gross-severe_cost,**f})
        next_allowed=int(row.exit_time)
    return pd.DataFrame(rows, columns=["signal_timestamp","entry_timestamp","exit_time","signal_utc","entry_utc","exit_utc","direction","entry_open","exit_close","gross_bps","severe_net_bps","signal_hour","atr_quintile","sma_gap_240","range_to_atr"])


def eligible_control_pool(frame: pd.DataFrame, severe_cost: float, horizon: int = 48) -> pd.DataFrame:
    out = outcomes(frame, horizon)
    if out.empty:
        return pd.DataFrame()
    f = frame.set_index("timestamp")
    rows=[]
    for row in out.itertuples(index=False):
        feat=f.loc[int(row.signal_timestamp)]
        if not (feat.sma_gap_240 > 0) or bool(feat.event_blackout) or int(feat.signal_dow) >= 5:
            continue
        # Exclude actual expansion-long signals from the drift control pool.
        if feat.range_to_atr >= 1.8 and feat.body_pct > 0:
            continue
        gross=(row.exit_close/row.entry_open-1)*10000
        rows.append({"signal_timestamp":int(row.signal_timestamp),"entry_timestamp":int(row.entry_timestamp),"exit_time":int(row.exit_time),"signal_utc":pd.to_datetime(row.signal_timestamp,unit="ms",utc=True),"entry_utc":pd.to_datetime(row.entry_timestamp,unit="ms",utc=True),"exit_utc":pd.to_datetime(row.exit_time,unit="ms",utc=True),"entry_open":row.entry_open,"exit_close":row.exit_close,"gross_bps":gross,"severe_net_bps":gross-severe_cost,"signal_hour":int(feat.signal_hour),"atr_quintile":int(feat.atr_quintile)})
    return pd.DataFrame(rows)


def fold_name(ts: pd.Timestamp, folds: Sequence[Mapping[str,str]]) -> str | None:
    for fold in folds:
        if pd.Timestamp(fold["start"]) <= ts < pd.Timestamp(fold["end"]):
            return str(fold["name"])
    return None


def match_controls(candidate: pd.DataFrame, pool: pd.DataFrame, folds: Sequence[Mapping[str,str]], max_days: int = 120) -> pd.DataFrame:
    if candidate.empty or pool.empty:
        return pd.DataFrame()
    p=pool.copy().sort_values("signal_utc")
    p["fold"]=[fold_name(t,folds) for t in p.signal_utc]
    used=set(); rows=[]
    for c in candidate.sort_values("signal_utc").itertuples(index=False):
        fold=fold_name(c.signal_utc,folds)
        eligible=p[(p.fold==fold)&(p.signal_hour==int(c.signal_hour))&(p.atr_quintile==int(c.atr_quintile))&(p.signal_utc<c.signal_utc)]
        if eligible.empty:
            continue
        eligible=eligible[(c.signal_utc-eligible.signal_utc)<=pd.Timedelta(days=max_days)]
        eligible=eligible[~eligible.signal_timestamp.isin(used)]
        if eligible.empty:
            continue
        q=eligible.iloc[-1]
        used.add(int(q.signal_timestamp))
        rows.append({"candidate_signal_utc":c.signal_utc,"control_signal_utc":q.signal_utc,"candidate_severe_net_bps":float(c.severe_net_bps),"control_severe_net_bps":float(q.severe_net_bps),"paired_excess_bps":float(c.severe_net_bps-q.severe_net_bps),"fold":fold,"signal_hour":int(c.signal_hour),"atr_quintile":int(c.atr_quintile)})
    return pd.DataFrame(rows)


def profit_factor(values: Iterable[float]) -> float | None:
    v=np.asarray(list(values),float); gains=float(v[v>0].sum()); losses=float(-v[v<0].sum())
    if losses==0: return None if gains==0 else 999.0
    return gains/losses


def bootstrap(values: Sequence[float], block: int, reps: int, seed: int) -> dict[str,Any]:
    v=np.asarray(values,float)
    if not len(v): return {"p10":None,"p_le_zero":None}
    b=max(1,min(int(block),len(v))); rng=np.random.default_rng(seed); k=math.ceil(len(v)/b); offs=np.arange(b); means=[]
    for s in range(0,reps,256):
        m=min(256,reps-s); starts=rng.integers(0,len(v),size=(m,k)); idx=((starts[:,:,None]+offs)%len(v)).reshape(m,-1)[:,:len(v)]; means.extend(v[idx].mean(axis=1))
    means=np.asarray(means)
    return {"p10":float(np.quantile(means,.1)),"p_le_zero":float(np.mean(means<=0))}


def metric(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, cfg: Mapping[str,Any]) -> dict[str,Any]:
    if trades.empty: return {"trades":0}
    v=trades.severe_net_bps.to_numpy(float); b=bootstrap(v,cfg["block_length"],cfg["replications"],cfg["random_state"]); w=np.delete(v,int(np.argmax(v)))
    eq=1.0
    for x in trades.sort_values("exit_time").severe_net_bps: eq*=max(1e-6,1+x/10000*float(cfg["risk_ratio"]))
    years=max((end-start).total_seconds()/(365.2425*86400),1e-9)
    return {"trades":int(len(v)),"mean_severe_net_bps":float(v.mean()),"median_severe_net_bps":float(np.median(v)),"profit_factor_severe":profit_factor(v),"bootstrap_p10_mean_bps":b["p10"],"bootstrap_probability_mean_le_zero":b["p_le_zero"],"remove_largest_winner_mean_bps":float(w.mean()) if len(w) else None,"remove_largest_winner_profit_factor":profit_factor(w),"strict_replay_cagr":float(eq**(1/years)-1),"final_equity":float(eq),"first_trade_utc":trades.entry_utc.min().isoformat(),"last_trade_utc":trades.entry_utc.max().isoformat()}


def fold_metrics(trades: pd.DataFrame, folds: Sequence[Mapping[str,str]]) -> list[dict[str,Any]]:
    rows=[]
    if trades.empty or "entry_utc" not in trades.columns:
        return [{"fold":f["name"],"trades":0,"mean_severe_net_bps":None,"profit_factor_severe":None} for f in folds]
    for f in folds:
        s=pd.Timestamp(f["start"]); e=pd.Timestamp(f["end"]); q=trades[(trades.entry_utc>=s)&(trades.entry_utc<e)]
        v=q.severe_net_bps.to_numpy(float) if not q.empty else np.array([])
        rows.append({"fold":f["name"],"trades":int(len(q)),"mean_severe_net_bps":float(v.mean()) if len(v) else None,"profit_factor_severe":profit_factor(v)})
    return rows


def paired_metric(pairs: pd.DataFrame, cfg: Mapping[str,Any]) -> dict[str,Any]:
    if pairs.empty: return {"pairs":0}
    v=pairs.paired_excess_bps.to_numpy(float); b=bootstrap(v,cfg["block_length"],cfg["replications"],cfg["random_state"]+77)
    return {"pairs":int(len(v)),"mean_paired_excess_bps":float(v.mean()),"median_paired_excess_bps":float(np.median(v)),"bootstrap_p10_paired_excess_bps":b["p10"],"bootstrap_probability_paired_excess_le_zero":b["p_le_zero"]}


def crossfeed(am: pd.DataFrame, du: pd.DataFrame) -> dict[str,Any]:
    a=set(am.signal_timestamp.astype(int)) if not am.empty else set(); d=set(du.signal_timestamp.astype(int)) if not du.empty else set(); union=a|d; inter=a&d
    agreement=float(len(inter)/len(union)) if union else None
    merged=am[["entry_timestamp","gross_bps"]].merge(du[["entry_timestamp","gross_bps"]],on="entry_timestamp",suffixes=("_am","_du")) if not am.empty and not du.empty else pd.DataFrame()
    corr=float(merged.gross_bps_am.corr(merged.gross_bps_du)) if len(merged)>=3 else None
    diff=(merged.gross_bps_am-merged.gross_bps_du).abs() if not merged.empty else pd.Series(dtype=float)
    return {"amarkets_signals":len(a),"dukascopy_signals":len(d),"intersection":len(inter),"union":len(union),"signal_jaccard":agreement,"matched_trade_returns":int(len(merged)),"return_correlation":corr,"median_absolute_return_difference_bps":float(diff.median()) if len(diff) else None,"p95_absolute_return_difference_bps":float(diff.quantile(.95)) if len(diff) else None}


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); frame.to_csv(path,index=False)


def run(root: Path, config_path: Path, out: Path) -> dict[str,Any]:
    cfg=read_json(config_path); out.mkdir(parents=True,exist_ok=True)
    start=pd.Timestamp(cfg["reference_start"]); end=pd.Timestamp(cfg["reference_end"])
    if start.tzinfo is None: start=start.tz_localize("UTC")
    if end.tzinfo is None: end=end.tz_localize("UTC")
    if end > pd.Timestamp("2025-01-01T00:00:00Z"):
        raise AuditError("reference_end may not exceed 2025-01-01")
    start_ms=to_ms(start); end_ms=to_ms(end)
    events=load_events_bounded(resolve(root,cfg["event_db"]),start,end)
    feeds={
        "AMARKETS": load_h1_bounded(resolve(root,cfg["amarkets_db"]),cfg["amarkets_table"],start_ms,end_ms,int(cfg["minimum_m5_bar_count"])),
        "DUKASCOPY": load_h1_bounded(resolve(root,cfg["dukascopy_db"]),cfg["dukascopy_table"],start_ms,end_ms,None),
    }
    rows=[]; folds=[]; pair_rows=[]; long_trades={}; short_trades={}; pairs_by_feed={}
    for name, raw in feeds.items():
        feat=build_features(raw,events)
        long=make_trades(feat,1,float(cfg["severe_cost_bps"])); short=make_trades(feat,-1,float(cfg["severe_cost_bps"])); pool=eligible_control_pool(feat,float(cfg["severe_cost_bps"])); pairs=match_controls(long,pool,cfg["folds"],int(cfg["control_max_lookback_days"]))
        long_trades[name]=long; short_trades[name]=short; pairs_by_feed[name]=pairs
        lm=metric(long,start,end,{**cfg["bootstrap"],"risk_ratio":cfg["maximum_notional_to_equity"]}); sm=metric(short,start,end,{**cfg["bootstrap"],"risk_ratio":cfg["maximum_notional_to_equity"]}); pm=paired_metric(pairs,cfg["bootstrap"])
        rows.extend([{ "feed":name,"leg":"LONG",**lm},{"feed":name,"leg":"SHORT",**sm}])
        for f in fold_metrics(long,cfg["folds"]): folds.append({"feed":name,"leg":"LONG",**f})
        for f in fold_metrics(short,cfg["folds"]): folds.append({"feed":name,"leg":"SHORT",**f})
        if not pairs.empty: pair_rows.append(pairs.assign(feed=name))
    cf=crossfeed(long_trades["AMARKETS"],long_trades["DUKASCOPY"])
    gates={}
    for name in ["AMARKETS","DUKASCOPY"]:
        lm=next(r for r in rows if r["feed"]==name and r["leg"]=="LONG"); pm=paired_metric(pairs_by_feed[name],cfg["bootstrap"]); fm=[f for f in folds if f["feed"]==name and f["leg"]=="LONG"]; pos=sum((f["mean_severe_net_bps"] or 0)>0 for f in fm)/len(fm)
        gates[name]={"minimum_trades":lm.get("trades",0)>=int(cfg["gates"]["minimum_trades"]),"mean_positive":lm.get("mean_severe_net_bps",-1)>0,"profit_factor":lm.get("profit_factor_severe",0)>=float(cfg["gates"]["minimum_profit_factor"]),"bootstrap_p10_positive":lm.get("bootstrap_p10_mean_bps",-1)>0,"positive_without_largest":lm.get("remove_largest_winner_mean_bps",-1)>0,"positive_fold_share":pos>=float(cfg["gates"]["minimum_positive_fold_share"]),"paired_control_count":pm.get("pairs",0)>=int(cfg["gates"]["minimum_control_pairs"]),"paired_excess_p10_positive":pm.get("bootstrap_p10_paired_excess_bps",-1)>0}
    gates["CROSSFEED"]={"signal_jaccard":cf.get("signal_jaccard") is not None and cf["signal_jaccard"]>=float(cfg["gates"]["minimum_signal_jaccard"]),"return_correlation":cf.get("return_correlation") is not None and cf["return_correlation"]>=float(cfg["gates"]["minimum_return_correlation"])}
    passed=all(all(v.values()) for v in gates.values())
    decision=PASS_DECISION if passed else FAIL_DECISION
    summary={"program":PROGRAM,"generated_utc":now_utc(),"decision":decision,"pass":passed,"paper_order_allowed":False,"demo_order_allowed":False,"live_order_allowed":False,"selection_used_2025_plus":False,"reference_start_utc":start.isoformat(),"reference_end_utc":end.isoformat(),"candidate_contract":{"family":"volatility_expansion","side":"LONG_ONLY","horizon_hours":48,"range_atr_multiple":1.8,"trend_window":240,"entry":"NEXT_EXACT_H1_OPEN","exit":"EXACT_48H_CLOSE","severe_cost_bps":cfg["severe_cost_bps"]},"feed_rows":{k:int(len(v)) for k,v in feeds.items()},"official_event_rows":int(len(events)),"feed_leg_metrics":rows,"paired_control_metrics":{k:paired_metric(v,cfg["bootstrap"]) for k,v in pairs_by_feed.items()},"crossfeed":cf,"gates":gates,"required_next_action":"DESIGN_MACRO_REGIME_OVERLAY_WITHOUT_USING_2025_PLUS" if passed else "CLOSE_PRICE_ONLY_H1_PATH_AND_INVENTORY_MACRO_DATA"}
    write_json(out/"long_only_attribution_summary.json",summary)
    write_json(out/"long_only_attribution_contract.json",{"program":PROGRAM,"generated_utc":now_utc(),"config_sha256":sha256_file(config_path),"reference_boundary":"2025-01-01T00:00:00Z","selection_used_2025_plus":False,"execution_allowed":False})
    write_json(out/"long_only_crossfeed_agreement.json",cf)
    write_csv(out/"long_only_feed_metrics.csv",pd.DataFrame(rows)); write_csv(out/"long_only_fold_metrics.csv",pd.DataFrame(folds)); write_csv(out/"long_only_control_pairs.csv",pd.concat(pair_rows,ignore_index=True) if pair_rows else pd.DataFrame())
    trade_frames=[]
    for name in long_trades:
        if not long_trades[name].empty: trade_frames.append(long_trades[name].assign(feed=name,leg="LONG"))
        if not short_trades[name].empty: trade_frames.append(short_trades[name].assign(feed=name,leg="SHORT"))
    write_csv(out/"long_only_attribution_trades.csv",pd.concat(trade_frames,ignore_index=True) if trade_frames else pd.DataFrame())
    md=["# XAUUSD Long-Only Volatility-Expansion Attribution","",f"Decision: `{decision}`","","- Reference-only: no row at or after 2025-01-01 is queried.","- Fixed candidate inherited from the rejected scan; no parameter search.","- Long leg is compared with its short leg, matched bull-drift controls, and Dukascopy cross-feed.","- No paper/demo/live order path exists.",""]
    atomic_write(out/"long_only_attribution_decision.md","\n".join(md))
    return summary


def collect(root: Path, config_path: Path, out: Path, destination: Path) -> dict[str,Any]:
    summary=out/"long_only_attribution_summary.json"
    if not summary.is_file(): raise AuditError(f"summary missing: {summary}")
    names=["long_only_attribution_summary.json","long_only_attribution_contract.json","long_only_crossfeed_agreement.json","long_only_feed_metrics.csv","long_only_fold_metrics.csv","long_only_control_pairs.csv","long_only_attribution_trades.csv","long_only_attribution_decision.md"]
    files=[out/n for n in names if (out/n).is_file()]+[config_path]
    destination.parent.mkdir(parents=True,exist_ok=True); manifest={"program":PROGRAM,"generated_utc":now_utc(),"files":[]}
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arc=("reports/"+p.name) if p.parent==out else ("config/"+p.name); z.write(p,arc); manifest["files"].append({"archive_path":arc,"sha256":sha256_file(p),"size":p.stat().st_size})
        z.writestr("RESULTS_MANIFEST.json",json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return {"program":PROGRAM,"generated_utc":now_utc(),"decision":"PASS_LONG_ONLY_ATTRIBUTION_RESULTS_PACK_CREATED","pass":True,"paper_order_allowed":False,"demo_order_allowed":False,"live_order_allowed":False,"output_zip":str(destination),"sha256":sha256_file(destination),"files":len(files)}


def preflight(root: Path, config_path: Path) -> dict[str,Any]:
    cfg=read_json(config_path); start=pd.Timestamp(cfg["reference_start"]); end=pd.Timestamp(cfg["reference_end"])
    if end > pd.Timestamp("2025-01-01T00:00:00Z"): raise AuditError("reference_end exceeds holdout boundary")
    paths={k:str(resolve(root,cfg[k])) for k in ["amarkets_db","dukascopy_db","event_db"]}
    checks={k:Path(v).is_file() for k,v in paths.items()}
    if not all(checks.values()): raise AuditError(f"missing inputs: {checks}")
    return {"program":PROGRAM,"generated_utc":now_utc(),"decision":"PASS_LONG_ONLY_ATTRIBUTION_PREFLIGHT_REFERENCE_ONLY","pass":True,"paper_order_allowed":False,"demo_order_allowed":False,"live_order_allowed":False,"selection_used_2025_plus":False,"reference_start_utc":start.isoformat(),"reference_end_utc":end.isoformat(),"paths":paths,"checks":checks}


def main(argv: Sequence[str] | None=None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("command",choices=["preflight","run","collect"]); p.add_argument("--root",default=str(Path(__file__).resolve().parents[1])); p.add_argument("--config",default="configs/xauusd_long_only_attribution_v1.json"); p.add_argument("--out",default="reports/xauusd_long_only_attribution"); p.add_argument("--results-zip",default="~/Downloads/XAUUSD_LONG_ONLY_ATTRIBUTION_RESULTS.zip"); args=p.parse_args(argv)
    root=Path(args.root).expanduser().resolve(); config=resolve(root,args.config); out=resolve(root,args.out)
    try:
        if args.command=="preflight": result=preflight(root,config)
        elif args.command=="run": result=run(root,config,out)
        else: result=collect(root,config,out,Path(os.path.expanduser(args.results_zip)).resolve())
        print(json.dumps(result,indent=2,default=json_default)); return 0 if result.get("pass") else 2
    except Exception as exc:
        failure={"program":PROGRAM,"generated_utc":now_utc(),"decision":"LONG_ONLY_ATTRIBUTION_FAIL_CLOSED","pass":False,"paper_order_allowed":False,"demo_order_allowed":False,"live_order_allowed":False,"error":f"{type(exc).__name__}: {exc}"}
        out.mkdir(parents=True,exist_ok=True); write_json(out/"long_only_attribution_failure.json",failure); print(json.dumps(failure,indent=2)); return 2

if __name__=="__main__": raise SystemExit(main())
