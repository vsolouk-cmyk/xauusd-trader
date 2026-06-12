#!/usr/bin/env python3
"""
Stage 15B — Exact Replay Validation for Reclaim-lt-q50 Sweep Regime

Candidate from Stage 15A:
- setup: prev_day_low_sweep_rejection
- side: LONG
- horizon_bars: 4 M15 bars ≈ 60 minutes
- branch: sweep_depth_ge_q50
- regime condition: reclaim_lt_q50

Purpose:
- Validate the single top Stage 15A pre-trade regime condition.
- Use M1 path replay when available.
- Compare time-exit behavior and limited TP/SL geometries.
- Stress with costs, chronological splits, year distribution, and 2026 segment.

Hard rules:
- Research validation only.
- No EA change.
- No automatic trading.
- No paper/live/order authorization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd


TOOL_VERSION = "v1"
DEFAULT_DB = Path("data/local/xauusd_local_store.sqlite")
DEFAULT_FEATURES = Path("data/reports/stage15a_regime_conditional_sweep_discovery/stage15a_filtered_branch_features.csv")
DEFAULT_OUT_DIR = Path("data/reports/stage15b_reclaim_lt_q50_exact_replay")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {db}")
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def load_m1(conn: sqlite3.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT utc_time, open, high, low, close
        FROM bars
        WHERE source='amarkets_mt5' AND symbol='XAUUSD' AND timeframe='1m'
        ORDER BY utc_time
        """
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["utc_time", "open", "high", "low", "close"]).sort_values("utc_time").drop_duplicates("utc_time").set_index("utc_time")


def profit_factor(vals: Sequence[float]) -> float:
    vals = [float(v) for v in vals]
    wins = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    if losses == 0:
        return 999.0 if wins > 0 else 0.0
    return round(wins / losses, 6)


def max_dd(vals: Sequence[float]) -> float:
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += float(v)
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 6)


def metrics(df: pd.DataFrame, ret_col: str) -> Dict:
    if df.empty:
        return {
            "events": 0, "total": 0.0, "avg": 0.0, "median": 0.0,
            "win_rate": 0.0, "pf": 0.0, "max_dd": 0.0,
            "pos_years": 0, "years": 0, "pos_quarters": 0, "quarters": 0,
        }
    x = df.sort_values("entry_dt").copy()
    vals = x[ret_col].astype(float).tolist()
    s = pd.Series(vals)
    by_year = x.groupby(x["entry_dt"].dt.year)[ret_col].sum()
    by_quarter = x.groupby(x["entry_dt"].dt.to_period("Q").astype(str))[ret_col].sum()
    return {
        "events": int(len(vals)),
        "total": round(float(s.sum()), 6),
        "avg": round(float(s.mean()), 6),
        "median": round(float(s.median()), 6),
        "win_rate": round(float((s > 0).mean()), 6),
        "pf": profit_factor(vals),
        "max_dd": max_dd(vals),
        "pos_years": int((by_year > 0).sum()),
        "years": int(len(by_year)),
        "pos_quarters": int((by_quarter > 0).sum()),
        "quarters": int(len(by_quarter)),
    }


def period_metrics(df: pd.DataFrame, ret_col: str, period: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    x = df.sort_values("entry_dt").copy()
    if period == "year":
        x["period"] = x["entry_dt"].dt.year.astype(str)
    elif period == "quarter":
        x["period"] = x["entry_dt"].dt.to_period("Q").astype(str)
    elif period == "month":
        x["period"] = x["entry_dt"].dt.to_period("M").astype(str)
    else:
        raise ValueError(period)
    rows = []
    for p, g in x.groupby("period"):
        m = metrics(g, ret_col)
        m["period"] = p
        rows.append(m)
    return pd.DataFrame(rows).sort_values("period") if rows else pd.DataFrame()


def split_metrics(df: pd.DataFrame, ret_col: str, frac: float) -> Dict:
    x = df.sort_values("entry_dt").reset_index(drop=True)
    cut = int(len(x) * frac)
    return {
        "train_frac": float(frac),
        "train": metrics(x.iloc[:cut], ret_col),
        "test": metrics(x.iloc[cut:], ret_col),
    }


def bootstrap(df: pd.DataFrame, ret_col: str, n: int = 500, seed: int = 15) -> Dict:
    if df.empty:
        return {}
    x = df.sort_values("entry_dt").reset_index(drop=True)
    totals, pfs, meds = [], [], []
    for i in range(n):
        s = x.sample(n=len(x), replace=True, random_state=seed + i)
        vals = s[ret_col].astype(float).tolist()
        totals.append(sum(vals))
        pfs.append(profit_factor(vals))
        meds.append(float(pd.Series(vals).median()))
    ts, ps, ms = pd.Series(totals), pd.Series(pfs), pd.Series(meds)
    return {
        "n": int(n),
        "total_p05": round(float(ts.quantile(0.05)), 6),
        "total_p50": round(float(ts.quantile(0.50)), 6),
        "total_p95": round(float(ts.quantile(0.95)), 6),
        "pf_p05": round(float(ps.quantile(0.05)), 6),
        "pf_p50": round(float(ps.quantile(0.50)), 6),
        "median_p05": round(float(ms.quantile(0.05)), 6),
        "median_p50": round(float(ms.quantile(0.50)), 6),
        "prob_total_gt_0": round(float((ts > 0).mean()), 6),
        "prob_pf_gt_1": round(float((ps > 1.0).mean()), 6),
        "prob_median_gt_0": round(float((ms > 0).mean()), 6),
    }


def normalize_features(path: Path, cost_usd: float) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Features CSV not found: {path}")
    x = pd.read_csv(path)
    for c in ["entry_utc", "event_utc"]:
        if c in x.columns:
            x[c.replace("_utc", "_dt")] = pd.to_datetime(x[c], utc=True, errors="coerce")
    if "entry_dt" not in x.columns:
        raise RuntimeError("features CSV must include entry_utc")
    for c in ["ret_usd", "entry_price", "sweep_depth", "reclaim_above_ref"]:
        if c in x.columns:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    required = ["entry_dt", "ret_usd", "entry_price", "sweep_depth", "reclaim_above_ref"]
    missing = [c for c in required if c not in x.columns]
    if missing:
        raise RuntimeError(f"features CSV missing required columns: {missing}")
    x = x.dropna(subset=required).sort_values("entry_dt").reset_index(drop=True)
    x["net_x1_original"] = x["ret_usd"] - cost_usd
    return x


def filter_candidate(features: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    # Stage15A branch already contains sweep_depth_ge_q50. Recalculate reclaim q50 inside this branch.
    reclaim_q50 = float(features["reclaim_above_ref"].quantile(0.50))
    out = features[features["reclaim_above_ref"] < reclaim_q50].copy().reset_index(drop=True)
    return out, {"reclaim_q50": round(reclaim_q50, 6), "events": int(len(out))}


def replay_one(m1: pd.DataFrame, row: pd.Series, horizon_min: int) -> Dict:
    entry_dt = row["entry_dt"]
    entry = float(row["entry_price"])
    end_dt = entry_dt + pd.Timedelta(minutes=horizon_min)

    # Include M1 bars after entry through exit.
    path = m1[(m1.index > entry_dt) & (m1.index <= end_dt)]
    if path.empty:
        # Fallback to original M15 result.
        return {
            "replay_status": "missing_m1_path",
            "exit_dt": end_dt.isoformat(),
            "time_exit_price": float("nan"),
            "time_exit_ret": float(row["ret_usd"]),
            "mfe": float("nan"),
            "mae": float("nan"),
        }

    exit_price = float(path.iloc[-1]["close"])
    mfe = float(path["high"].max()) - entry
    mae = entry - float(path["low"].min())

    return {
        "replay_status": "ok",
        "exit_dt": path.index[-1].isoformat(),
        "time_exit_price": round(exit_price, 6),
        "time_exit_ret": round(exit_price - entry, 6),
        "mfe": round(mfe, 6),
        "mae": round(mae, 6),
    }


def apply_replay(features: pd.DataFrame, m1: pd.DataFrame, horizon_min: int, cost_usd: float) -> pd.DataFrame:
    rows = []
    for _, row in features.iterrows():
        r = dict(row)
        rep = replay_one(m1, row, horizon_min)
        r.update(rep)
        rows.append(r)
    out = pd.DataFrame(rows)
    out["time_exit_net_x1"] = pd.to_numeric(out["time_exit_ret"], errors="coerce") - cost_usd
    out["time_exit_net_x2"] = pd.to_numeric(out["time_exit_ret"], errors="coerce") - (2 * cost_usd)
    out["time_exit_net_x4"] = pd.to_numeric(out["time_exit_ret"], errors="coerce") - (4 * cost_usd)
    return out


def resolve_geometry(row: pd.Series, tp: float, sl: float, horizon_min: int, m1: pd.DataFrame) -> Dict:
    entry_dt = row["entry_dt"]
    entry = float(row["entry_price"])
    end_dt = entry_dt + pd.Timedelta(minutes=horizon_min)
    path = m1[(m1.index > entry_dt) & (m1.index <= end_dt)]
    if path.empty:
        return {"reason": "missing_path", "ret": float(row.get("time_exit_ret", row.get("ret_usd", 0.0))), "ambiguous": 0}

    tp_price = entry + tp
    sl_price = entry - sl
    for ts, b in path.iterrows():
        hit_tp = float(b["high"]) >= tp_price
        hit_sl = float(b["low"]) <= sl_price
        if hit_tp and hit_sl:
            # Conservative: if both in one minute, count SL for long.
            return {"reason": "ambiguous_same_m1_sl_first", "ret": -sl, "ambiguous": 1}
        if hit_sl:
            return {"reason": "sl", "ret": -sl, "ambiguous": 0}
        if hit_tp:
            return {"reason": "tp", "ret": tp, "ambiguous": 0}

    exit_price = float(path.iloc[-1]["close"])
    return {"reason": "time_exit", "ret": exit_price - entry, "ambiguous": 0}


def geometry_eval(replayed: pd.DataFrame, m1: pd.DataFrame, cost_usd: float, horizon_min: int) -> pd.DataFrame:
    geometries = [
        ("time_exit_60m", 0.0, 0.0),
        ("tp6_sl6", 6.0, 6.0),
        ("tp8_sl6", 8.0, 6.0),
        ("tp10_sl8", 10.0, 8.0),
        ("tp12_sl10", 12.0, 10.0),
        ("tp15_sl12", 15.0, 12.0),
    ]
    rows = []
    for name, tp, sl in geometries:
        x = replayed.copy()
        if name == "time_exit_60m":
            x["geom_ret"] = x["time_exit_ret"].astype(float)
            x["geom_reason"] = "time_exit"
            x["ambiguous"] = 0
        else:
            outs = [resolve_geometry(r, tp, sl, horizon_min, m1) for _, r in x.iterrows()]
            x["geom_ret"] = [o["ret"] for o in outs]
            x["geom_reason"] = [o["reason"] for o in outs]
            x["ambiguous"] = [o["ambiguous"] for o in outs]
        x["geom_net_x1"] = x["geom_ret"].astype(float) - cost_usd
        m = metrics(x, "geom_net_x1")
        reasons = x["geom_reason"].value_counts().to_dict()
        rows.append({
            "geometry": name,
            "tp": tp,
            "sl": sl,
            **m,
            "tp_count": int(reasons.get("tp", 0)),
            "sl_count": int(reasons.get("sl", 0) + reasons.get("ambiguous_same_m1_sl_first", 0)),
            "time_exit_count": int(reasons.get("time_exit", 0)),
            "ambiguous_count": int(x["ambiguous"].sum()),
        })
    return pd.DataFrame(rows).sort_values(["pf", "median", "total"], ascending=[False, False, False])


def decide(time_m: Dict, splits: List[Dict], year: pd.DataFrame, boot: Dict, geom: pd.DataFrame, current_2026: Dict) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if time_m["events"] < 60:
        return "REJECT_TOO_FEW_EXACT_REPLAY_EVENTS", ["Filtered regime has too few events for exact replay."]

    if not (time_m["total"] > 0 and time_m["pf"] >= 1.25 and time_m["median"] > 0.25 and time_m["win_rate"] >= 0.55):
        return "REJECT_TIME_EXIT_EXACT_REPLAY_WEAK", ["M1 exact time-exit replay does not preserve strong net edge."]

    for sp in splits:
        test = sp["test"]
        if not (test["events"] >= 15 and test["total"] > 0 and test["pf"] >= 1.05):
            return "SPLIT_FRAGILE_EXACT_REPLAY", [f"Chronological split {sp['train_frac']} test segment fails."]

    if not year.empty:
        pos_years = int((year["total"] > 0).sum())
        years = int(len(year))
        if pos_years < max(3, round(years * 0.60)):
            return "YEAR_FRAGILE_EXACT_REPLAY", ["Year distribution is not broad enough."]

    if current_2026.get("events", 0) >= 10 and current_2026.get("total", 0) < 0:
        reasons.append("2026 segment remains negative; candidate is not safe as current-regime automatic rule.")
        current_fragile = True
    else:
        current_fragile = False

    if boot and (boot.get("prob_total_gt_0", 0) < 0.90 or boot.get("pf_p05", 0) < 1.0):
        reasons.append("Bootstrap lower tail remains fragile.")
        boot_fragile = True
    else:
        boot_fragile = False

    best_geom = geom.iloc[0].to_dict() if not geom.empty else {}
    if best_geom and best_geom.get("geometry") != "time_exit_60m" and best_geom.get("pf", 0) > time_m["pf"]:
        reasons.append(f"Limited geometry `{best_geom.get('geometry')}` improves over time exit; replay validation may continue for that geometry.")
    else:
        reasons.append("Time-exit geometry remains acceptable or best among limited geometries.")

    if current_fragile or boot_fragile:
        return "EXACT_REPLAY_CANDIDATE_BUT_CURRENT_REGIME_FRAGILE", reasons

    reasons.append("Exact replay preserves candidate quality. Still no EA/paper/live authorization.")
    return "EXACT_REPLAY_VALIDATED_RESEARCH_CANDIDATE", reasons


def run(db: Path, features_path: Path, out_dir: Path, cost_usd: float, horizon_min: int, bootstrap_n: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now_iso()

    features = normalize_features(features_path, cost_usd)
    cand, threshold_info = filter_candidate(features)

    conn = connect(db)
    m1 = load_m1(conn)
    conn.close()
    if m1.empty:
        raise RuntimeError("M1 bars are required for Stage 15B exact replay, but none were found in local store.")

    replayed = apply_replay(cand, m1, horizon_min, cost_usd)
    # Use replayed time-exit return as the primary exact replay result.
    time_m = metrics(replayed, "time_exit_net_x1")
    x2 = metrics(replayed, "time_exit_net_x2")
    x4 = metrics(replayed, "time_exit_net_x4")
    orig_m = metrics(cand.assign(entry_dt=cand["entry_dt"], original_net_x1=cand["net_x1_original"]), "original_net_x1")

    splits = [
        split_metrics(replayed, "time_exit_net_x1", 0.60),
        split_metrics(replayed, "time_exit_net_x1", 0.70),
        split_metrics(replayed, "time_exit_net_x1", 0.80),
    ]
    year = period_metrics(replayed, "time_exit_net_x1", "year")
    quarter = period_metrics(replayed, "time_exit_net_x1", "quarter")
    month = period_metrics(replayed, "time_exit_net_x1", "month")
    boot = bootstrap(replayed, "time_exit_net_x1", bootstrap_n)
    geom = geometry_eval(replayed, m1, cost_usd, horizon_min)
    current_2026 = metrics(replayed[replayed["entry_dt"].dt.year == 2026], "time_exit_net_x1")

    final_decision, reasons = decide(time_m, splits, year, boot, geom, current_2026)

    replay_csv = out_dir / "stage15b_exact_replay_trades.csv"
    geometry_csv = out_dir / "stage15b_geometry_summary.csv"
    year_csv = out_dir / "stage15b_by_year.csv"
    quarter_csv = out_dir / "stage15b_by_quarter.csv"
    month_csv = out_dir / "stage15b_by_month.csv"
    split_csv = out_dir / "stage15b_splits.csv"
    json_path = out_dir / "stage15b_reclaim_lt_q50_exact_replay.json"
    md_path = out_dir / "stage15b_reclaim_lt_q50_exact_replay.md"

    replayed.to_csv(replay_csv, index=False)
    geom.to_csv(geometry_csv, index=False)
    year.to_csv(year_csv, index=False)
    quarter.to_csv(quarter_csv, index=False)
    month.to_csv(month_csv, index=False)

    split_rows = []
    for sp in splits:
        for seg in ["train", "test"]:
            row = {"train_frac": sp["train_frac"], "segment": seg}
            row.update(sp[seg])
            split_rows.append(row)
    split_df = pd.DataFrame(split_rows)
    split_df.to_csv(split_csv, index=False)

    payload = {
        "tool_version": TOOL_VERSION,
        "generated_utc": generated,
        "inputs": {
            "db": str(db),
            "features_path": str(features_path),
            "cost_usd": float(cost_usd),
            "horizon_min": int(horizon_min),
            "bootstrap_n": int(bootstrap_n),
        },
        "candidate": {
            "setup": "prev_day_low_sweep_rejection",
            "side": "LONG",
            "branch": "sweep_depth_ge_q50",
            "regime": "reclaim_lt_q50",
            **threshold_info,
        },
        "final_decision": final_decision,
        "reasons": reasons,
        "original_m15_net_x1": orig_m,
        "exact_time_exit_net_x1": time_m,
        "exact_time_exit_net_x2": x2,
        "exact_time_exit_net_x4": x4,
        "current_2026_net_x1": current_2026,
        "splits": splits,
        "bootstrap": boot,
        "geometry_summary": geom.to_dict(orient="records"),
        "authorization_flags": {
            "trade_authorization": False,
            "ea_change_authorization": False,
            "paper_order_authorization": False,
            "live_order_authorization": False,
            "automatic_trading": False,
        },
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    lines = [
        "# Stage 15B Reclaim-lt-q50 Exact Replay",
        "",
        f"Generated UTC: `{generated}`",
        f"Tool version: `{TOOL_VERSION}`",
        "",
        "> Hard rule: exact replay research only. No EA change, no automatic trading, no paper/live authorization.",
        "",
        "## Candidate",
        "- setup: `prev_day_low_sweep_rejection`",
        "- side: `LONG`",
        "- branch: `sweep_depth_ge_q50`",
        "- regime: `reclaim_lt_q50`",
        f"- reclaim_q50: `{threshold_info['reclaim_q50']}`",
        f"- events: `{threshold_info['events']}`",
        f"- horizon_min: `{horizon_min}`",
        f"- cost_usd: `{cost_usd}`",
        "",
        "## Final decision",
        f"- final_decision: `{final_decision}`",
        "",
        "## Reasons",
    ]
    for r in reasons:
        lines.append(f"- {r}")

    lines += [
        "",
        "## M15 original vs M1 exact replay",
        "| Result set | Events | Total | Avg | Median | WR | PF | DD | Pos years | Pos quarters |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| original_m15_net_x1 | {orig_m['events']} | {orig_m['total']} | {orig_m['avg']} | {orig_m['median']} | {orig_m['win_rate']} | {orig_m['pf']} | {orig_m['max_dd']} | {orig_m['pos_years']}/{orig_m['years']} | {orig_m['pos_quarters']}/{orig_m['quarters']} |",
        f"| exact_m1_time_exit_net_x1 | {time_m['events']} | {time_m['total']} | {time_m['avg']} | {time_m['median']} | {time_m['win_rate']} | {time_m['pf']} | {time_m['max_dd']} | {time_m['pos_years']}/{time_m['years']} | {time_m['pos_quarters']}/{time_m['quarters']} |",
        f"| exact_m1_time_exit_net_x2 | {x2['events']} | {x2['total']} | {x2['avg']} | {x2['median']} | {x2['win_rate']} | {x2['pf']} | {x2['max_dd']} | {x2['pos_years']}/{x2['years']} | {x2['pos_quarters']}/{x2['quarters']} |",
        f"| exact_m1_time_exit_net_x4 | {x4['events']} | {x4['total']} | {x4['avg']} | {x4['median']} | {x4['win_rate']} | {x4['pf']} | {x4['max_dd']} | {x4['pos_years']}/{x4['years']} | {x4['pos_quarters']}/{x4['quarters']} |",
        "",
        "## Current 2026 exact replay net x1",
        "| Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {current_2026['events']} | {current_2026['total']} | {current_2026['avg']} | {current_2026['median']} | {current_2026['win_rate']} | {current_2026['pf']} | {current_2026['max_dd']} |",
        "",
        "## Chronological splits - exact M1 time-exit net x1",
        "| Train frac | Segment | Events | Total | Avg | Median | WR | PF | DD |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in split_df.to_dict(orient="records"):
        lines.append(
            f"| {r['train_frac']} | {r['segment']} | {r['events']} | {r['total']} | {r['avg']} | "
            f"{r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Limited geometry summary - M1 path, net x1",
        "| Geometry | Events | Total | Avg | Median | WR | PF | DD | TP | SL | Time exit | Ambiguous |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in geom.to_dict(orient="records"):
        lines.append(
            f"| {r['geometry']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | "
            f"{r['win_rate']} | {r['pf']} | {r['max_dd']} | {r['tp_count']} | {r['sl_count']} | {r['time_exit_count']} | {r['ambiguous_count']} |"
        )

    lines += [
        "",
        "## Year distribution - exact M1 time-exit net x1",
        "| Year | Events | Total | Avg | Median | WR | PF | DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in year.to_dict(orient="records"):
        lines.append(
            f"| {r['period']} | {r['events']} | {r['total']} | {r['avg']} | {r['median']} | {r['win_rate']} | {r['pf']} | {r['max_dd']} |"
        )

    lines += [
        "",
        "## Bootstrap - exact M1 time-exit net x1",
        "```json",
        json.dumps(boot, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Interpretation",
        "- `EXACT_REPLAY_VALIDATED_RESEARCH_CANDIDATE` permits the next research-only step: forward-shadow design, not orders.",
        "- `EXACT_REPLAY_CANDIDATE_BUT_CURRENT_REGIME_FRAGILE` means historical edge exists but current-regime use remains unsafe.",
        "- Any rejection closes this branch; it does not reject XAUUSD as a market.",
        "- No EA/paper/live/order authorization is granted.",
        "",
        "## Output files",
        f"- replay_csv: `{replay_csv}`",
        f"- geometry_csv: `{geometry_csv}`",
        f"- year_csv: `{year_csv}`",
        f"- quarter_csv: `{quarter_csv}`",
        f"- month_csv: `{month_csv}`",
        f"- split_csv: `{split_csv}`",
        f"- json: `{json_path}`",
        f"- md: `{md_path}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Stage 15B reclaim-lt-q50 exact replay: DONE")
    print(f"final_decision={final_decision}")
    print(f"events={time_m['events']} net_total={time_m['total']} net_pf={time_m['pf']} net_median={time_m['median']}")
    print(f"current_2026_total={current_2026['total']} current_2026_pf={current_2026['pf']}")
    print(f"Report: {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--features", default=str(DEFAULT_FEATURES))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-usd", type=float, default=0.35)
    p.add_argument("--horizon-min", type=int, default=60)
    p.add_argument("--bootstrap-n", type=int, default=500)
    args = p.parse_args()
    return run(
        db=Path(args.db),
        features_path=Path(args.features),
        out_dir=Path(args.out_dir),
        cost_usd=args.cost_usd,
        horizon_min=args.horizon_min,
        bootstrap_n=args.bootstrap_n,
    )


if __name__ == "__main__":
    raise SystemExit(main())
