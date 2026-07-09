#!/usr/bin/env python3
"""
Stage165 Macro Thesis Regime Rebuild

Read-only macro-regime thesis scan for XAUUSD/gold.
It does not write MT5 KV files and never authorizes demo/live orders.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage165_MACRO_THESIS_REGIME_REBUILD"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def normalize_col(c: Any) -> str:
    s = str(c).strip().strip("\ufeff")
    s = s.replace("<", "").replace(">", "")
    return s.lower().replace(" ", "_").replace("-", "_")


def _read_csv_auto(path: Path, nrows: Optional[int] = None) -> pd.DataFrame:
    """Read comma/semicolon/tab CSV using a small delimiter heuristic."""
    sample = path.read_text(errors="ignore", encoding="utf-8")[:4096]
    candidates = ["\t", ",", ";"]
    best_sep = ","
    best_score = -1
    for sep in candidates:
        try:
            df = pd.read_csv(path, sep=sep, nrows=5)
            score = len(df.columns)
            if score > best_score:
                best_score = score
                best_sep = sep
        except Exception:
            pass
    return pd.read_csv(path, sep=best_sep, nrows=nrows)


def load_bars(path: Path, timestamp_shift_hours: float = 0.0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Load AMarkets MT5 TSV or project-normalized OHLC CSV.

    Returns columns: time_utc, open, high, low, close, volume, spread.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))
    df = _read_csv_auto(path)
    raw_cols = list(df.columns)
    df.columns = [normalize_col(c) for c in df.columns]
    meta: Dict[str, Any] = {
        "source_path": str(path),
        "raw_row_count": int(len(df)),
        "raw_columns": raw_cols,
        "timestamp_shift_hours": timestamp_shift_hours,
    }

    # MT5 export: <DATE> <TIME> <OPEN> ... after normalization: date/time/open...
    if "date" in df.columns and "time" in df.columns:
        ts = pd.to_datetime(
            df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(),
            format="%Y.%m.%d %H:%M:%S",
            errors="coerce",
            utc=False,
        )
        # Server/broker time to UTC shift. AMarkets observed server≈UTC+3.
        ts = ts - pd.to_timedelta(timestamp_shift_hours * -1, unit="h") if False else ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        ts = pd.to_datetime(ts, utc=True, errors="coerce")
        colmap = {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "tickvol": "volume",
            "vol": "real_volume",
            "spread": "spread",
        }
        meta["parse_mode"] = "split_date_time_mt5_tsv"
    else:
        time_col = None
        for c in ["time_utc", "utc_time", "datetime", "timestamp", "server_time", "time"]:
            if c in df.columns:
                time_col = c
                break
        if not time_col:
            # fallback: first column containing date/time/utc
            for c in df.columns:
                if any(x in c for x in ["date", "time", "utc"]):
                    time_col = c
                    break
        if not time_col:
            raise ValueError(f"No parseable timestamp column in {path}; columns={list(df.columns)}")
        ts = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        if timestamp_shift_hours and time_col not in {"time_utc", "utc_time"}:
            ts = ts + pd.to_timedelta(timestamp_shift_hours, unit="h")
        colmap = {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "tick_volume": "volume",
            "real_volume": "real_volume",
            "spread_points": "spread",
            "volume": "volume",
            "spread": "spread",
        }
        meta["parse_mode"] = f"single_timestamp:{time_col}"

    out = pd.DataFrame({"time_utc": ts})
    for src, dst in colmap.items():
        if src in df.columns:
            out[dst] = pd.to_numeric(df[src], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        if c not in out.columns:
            raise ValueError(f"Missing OHLC column {c}; columns={list(df.columns)}")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    if "spread" not in out.columns:
        out["spread"] = float("nan")

    out = out.dropna(subset=["time_utc", "open", "high", "low", "close"]).copy()
    out = out.sort_values("time_utc").drop_duplicates("time_utc", keep="last").reset_index(drop=True)
    meta.update({
        "bar_count": int(len(out)),
        "min_time_utc": str(out["time_utc"].min()) if len(out) else None,
        "max_time_utc": str(out["time_utc"].max()) if len(out) else None,
    })
    return out, meta


def daily_ohlc_from_m5(bars: pd.DataFrame) -> pd.DataFrame:
    x = bars.copy()
    x = x.set_index("time_utc").sort_index()
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "spread": "mean",
    }
    out = x.resample("1d").agg(agg).dropna(subset=["open", "high", "low", "close"]).reset_index()
    out["date"] = out["time_utc"].dt.floor("1d")
    return out


def load_stage161_context(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_date_col(df: pd.DataFrame) -> Optional[str]:
    priority = ["date", "time_utc", "utc_time", "timestamp", "datetime", "observation_date"]
    cols_norm = {normalize_col(c): c for c in df.columns}
    for p in priority:
        if p in cols_norm:
            return cols_norm[p]
    best = None
    best_count = -1
    for c in df.columns:
        if any(x in normalize_col(c) for x in ["date", "time", "utc"]):
            s = pd.to_datetime(df[c], errors="coerce", utc=True)
            n = int(s.notna().sum())
            if n > best_count:
                best = c
                best_count = n
    return best


def load_macro_panel(path: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not path.exists():
        return pd.DataFrame(), {"macro_panel_path": str(path), "loaded": False, "reason": "missing"}
    df = _read_csv_auto(path)
    raw_cols = list(df.columns)
    date_col = find_date_col(df)
    meta = {"macro_panel_path": str(path), "loaded": True, "raw_row_count": int(len(df)), "raw_columns": raw_cols, "date_col": date_col}
    if not date_col:
        meta["loaded"] = False
        meta["reason"] = "no_date_col"
        return pd.DataFrame(), meta
    df.columns = [normalize_col(c) for c in df.columns]
    date_col_n = normalize_col(date_col)
    df["macro_date"] = pd.to_datetime(df[date_col_n], errors="coerce", utc=True).dt.floor("1d")
    df = df.dropna(subset=["macro_date"]).sort_values("macro_date").drop_duplicates("macro_date", keep="last")
    meta.update({
        "row_count": int(len(df)),
        "min_macro_date": str(df["macro_date"].min()) if len(df) else None,
        "max_macro_date": str(df["macro_date"].max()) if len(df) else None,
        "columns": list(df.columns),
    })
    return df, meta


def select_first_existing(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    # fuzzy fallback
    for cand in candidates:
        key = cand.lower()
        for c in df.columns:
            if key in c.lower():
                return c
    return None


def build_macro_regimes(macro: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if macro.empty:
        return macro, {"macro_feature_status": "MISSING"}
    m = macro.copy().sort_values("macro_date").reset_index(drop=True)
    col_dollar = select_first_existing(m, ["dollar_pressure_index", "dtwexbgs", "dxy", "dollar_index", "trade_weighted_dollar"])
    col_real = select_first_existing(m, ["real_yield_10y", "dfii10", "real_yield", "tips_10y"])
    col_vix = select_first_existing(m, ["vix", "vixcls"])
    col_us10y = select_first_existing(m, ["us10y", "dgs10", "nominal_yield_10y", "treasury_10y"])
    info = {"dollar_col": col_dollar, "real_yield_col": col_real, "vix_col": col_vix, "us10y_col": col_us10y}

    for c in [col_dollar, col_real, col_vix, col_us10y]:
        if c and c in m.columns:
            m[c] = pd.to_numeric(m[c], errors="coerce")

    if col_dollar:
        m["dollar_delta_10d"] = m[col_dollar].ffill().diff(10)
    else:
        m["dollar_delta_10d"] = float("nan")
    if col_real:
        m["real_yield_delta_10d"] = m[col_real].ffill().diff(10)
    else:
        m["real_yield_delta_10d"] = float("nan")
    if col_vix:
        m["vix_pct_rank_252"] = m[col_vix].rolling(252, min_periods=50).rank(pct=True)
        m["vix_delta_5d"] = m[col_vix].ffill().diff(5)
    else:
        m["vix_pct_rank_252"] = float("nan")
        m["vix_delta_5d"] = float("nan")

    def classify(row: pd.Series) -> str:
        d = row.get("dollar_delta_10d", float("nan"))
        r = row.get("real_yield_delta_10d", float("nan"))
        vp = row.get("vix_pct_rank_252", float("nan"))
        vd = row.get("vix_delta_5d", float("nan"))
        d_up = pd.notna(d) and d > 0
        d_dn = pd.notna(d) and d < 0
        r_up = pd.notna(r) and r > 0
        r_dn = pd.notna(r) and r < 0
        risk_off = pd.notna(vp) and vp >= 0.75 and pd.notna(vd) and vd > 0
        if risk_off and (d_up or r_up):
            return "SAFE_HAVEN_MIXED_DOLLAR_HEADWIND"
        if d_up and r_up:
            return "USD_REAL_YIELD_HEADWIND_FOR_GOLD"
        if d_dn and r_dn:
            return "USD_REAL_YIELD_TAILWIND_FOR_GOLD"
        if d_up and r_dn:
            return "USD_UP_REAL_YIELD_DOWN_MIXED"
        if d_dn and r_up:
            return "USD_DOWN_REAL_YIELD_UP_MIXED"
        return "MACRO_NEUTRAL_OR_INCOMPLETE"

    m["macro_regime"] = m.apply(classify, axis=1)
    m["macro_supported_side"] = m["macro_regime"].map({
        "USD_REAL_YIELD_HEADWIND_FOR_GOLD": "SHORT",
        "SAFE_HAVEN_MIXED_DOLLAR_HEADWIND": "NONE",
        "USD_REAL_YIELD_TAILWIND_FOR_GOLD": "LONG",
        "USD_UP_REAL_YIELD_DOWN_MIXED": "NONE",
        "USD_DOWN_REAL_YIELD_UP_MIXED": "NONE",
        "MACRO_NEUTRAL_OR_INCOMPLETE": "NONE",
    }).fillna("NONE")
    info["macro_feature_status"] = "READY" if (col_dollar and col_real) else "PARTIAL"
    latest = m.dropna(subset=["macro_regime"]).tail(1)
    if len(latest):
        info["latest_macro_date"] = str(latest.iloc[0]["macro_date"])
        info["latest_macro_regime"] = str(latest.iloc[0]["macro_regime"])
        info["latest_macro_supported_side"] = str(latest.iloc[0]["macro_supported_side"])
    return m, info


def join_daily_macro(daily: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy().sort_values("date")
    if macro.empty:
        d["macro_regime"] = "MACRO_MISSING"
        d["macro_supported_side"] = "NONE"
        return d
    m = macro.copy().sort_values("macro_date")
    # Use as-of join with no look-ahead; daily bar date receives latest macro date <= bar date.
    out = pd.merge_asof(d, m, left_on="date", right_on="macro_date", direction="backward")
    out["macro_regime"] = out["macro_regime"].fillna("MACRO_MISSING")
    out["macro_supported_side"] = out["macro_supported_side"].fillna("NONE")
    return out


def evaluate_regime_candidates(joined: pd.DataFrame, horizons_days: Sequence[int], min_events: int, min_mean_bps: float, min_hit_rate: float, min_recent_mean_bps: float, min_positive_folds: int) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    x = joined.copy().sort_values("date").reset_index(drop=True)
    x["fold"] = pd.qcut(pd.Series(range(len(x))), q=4, labels=["F1_OLD", "F2", "F3", "F4_RECENT"]) if len(x) >= 4 else "F1_OLD"
    regimes = sorted([r for r in x["macro_regime"].dropna().unique()])
    for horizon in horizons_days:
        future_close = x["close"].shift(-horizon)
        x[f"fwd_{horizon}d_bps"] = (future_close / x["close"] - 1.0) * 10000.0
        for regime in regimes:
            if regime in {"MACRO_MISSING", "MACRO_NEUTRAL_OR_INCOMPLETE"}:
                continue
            sub = x[x["macro_regime"] == regime].copy()
            if sub.empty:
                continue
            for side in ["LONG", "SHORT"]:
                side_bps = sub[f"fwd_{horizon}d_bps"] if side == "LONG" else -sub[f"fwd_{horizon}d_bps"]
                valid = sub.assign(side_bps=side_bps).dropna(subset=["side_bps"])
                if len(valid) < 1:
                    continue
                event_count = int(len(valid))
                mean_bps = float(valid["side_bps"].mean())
                median_bps = float(valid["side_bps"].median())
                hit_rate = float((valid["side_bps"] > 0).mean())
                recent = valid[valid["fold"].astype(str) == "F4_RECENT"]
                recent_event_count = int(len(recent))
                recent_mean_bps = float(recent["side_bps"].mean()) if len(recent) else float("nan")
                recent_hit_rate = float((recent["side_bps"] > 0).mean()) if len(recent) else float("nan")
                fold_means: Dict[str, float] = {}
                positive_folds = 0
                for f in ["F1_OLD", "F2", "F3", "F4_RECENT"]:
                    vals = valid[valid["fold"].astype(str) == f]["side_bps"]
                    mv = float(vals.mean()) if len(vals) else float("nan")
                    fold_means[f] = mv
                    if pd.notna(mv) and mv > 0:
                        positive_folds += 1
                macro_supported_side = str(valid["macro_supported_side"].mode().iloc[0]) if len(valid) else "NONE"
                macro_aligned = (macro_supported_side == side)
                passes = (
                    macro_aligned and
                    event_count >= min_events and
                    mean_bps >= min_mean_bps and
                    hit_rate >= min_hit_rate and
                    pd.notna(recent_mean_bps) and recent_mean_bps >= min_recent_mean_bps and
                    positive_folds >= min_positive_folds
                )
                rows.append({
                    "rule_id": f"D165_{regime}_{side}_{horizon}D",
                    "regime": regime,
                    "side": side,
                    "horizon_days": horizon,
                    "macro_supported_side": macro_supported_side,
                    "macro_aligned": bool(macro_aligned),
                    "event_count": event_count,
                    "mean_bps": round(mean_bps, 4),
                    "median_bps": round(median_bps, 4),
                    "hit_rate": round(hit_rate, 4),
                    "recent_event_count": recent_event_count,
                    "recent_mean_bps": round(recent_mean_bps, 4) if pd.notna(recent_mean_bps) else None,
                    "recent_hit_rate": round(recent_hit_rate, 4) if pd.notna(recent_hit_rate) else None,
                    "positive_folds": int(positive_folds),
                    "fold_F1_mean_bps": round(fold_means["F1_OLD"], 4) if pd.notna(fold_means["F1_OLD"]) else None,
                    "fold_F2_mean_bps": round(fold_means["F2"], 4) if pd.notna(fold_means["F2"]) else None,
                    "fold_F3_mean_bps": round(fold_means["F3"], 4) if pd.notna(fold_means["F3"]) else None,
                    "fold_F4_mean_bps": round(fold_means["F4_RECENT"], 4) if pd.notna(fold_means["F4_RECENT"]) else None,
                    "passes": bool(passes),
                })
    scores = pd.DataFrame(rows)
    if scores.empty:
        shortlist = scores.copy()
    else:
        shortlist = scores[scores["passes"]].sort_values(["mean_bps", "hit_rate", "event_count"], ascending=[False, False, False]).reset_index(drop=True)
    context = {
        "regime_counts": x["macro_regime"].value_counts(dropna=False).to_dict(),
        "macro_supported_side_counts": x["macro_supported_side"].value_counts(dropna=False).to_dict(),
        "daily_bar_count": int(len(x)),
        "latest_daily_date": str(x["date"].max()) if len(x) else None,
        "latest_daily_close": float(x.iloc[-1]["close"]) if len(x) else None,
    }
    return scores, shortlist, context


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    report_dir = root / "reports" / "stage165_macro_thesis_regime_rebuild"
    ensure_dir(report_dir)

    outputs = {
        "summary_json": str(report_dir / "stage165_macro_thesis_regime_rebuild_summary.json"),
        "candidate_scores_csv": str(report_dir / "stage165_macro_thesis_candidate_scores.csv"),
        "shortlist_csv": str(report_dir / "stage165_macro_thesis_shortlist.csv"),
        "regime_context_json": str(report_dir / "stage165_macro_thesis_regime_context.json"),
    }

    try:
        bars, bars_meta = load_bars(Path(args.bars_m5).expanduser(), args.timestamp_shift_hours)
        daily = daily_ohlc_from_m5(bars)
        macro_panel_path = Path(args.macro_panel).expanduser() if args.macro_panel else root / "data" / "fundamental_event_inbox" / "features" / "stage115_daily_macro_feature_panel.csv"
        macro_raw, macro_meta = load_macro_panel(macro_panel_path)
        macro, macro_feature_info = build_macro_regimes(macro_raw)
        joined = join_daily_macro(daily, macro)
        horizons = [int(x.strip()) for x in str(args.horizons_days).split(",") if x.strip()]
        scores, shortlist, context = evaluate_regime_candidates(
            joined=joined,
            horizons_days=horizons,
            min_events=args.min_events,
            min_mean_bps=args.min_mean_bps,
            min_hit_rate=args.min_hit_rate,
            min_recent_mean_bps=args.min_recent_mean_bps,
            min_positive_folds=args.min_positive_folds,
        )
        scores.to_csv(outputs["candidate_scores_csv"], index=False)
        shortlist.to_csv(outputs["shortlist_csv"], index=False)

        stage161 = load_stage161_context(Path(args.stage161_summary).expanduser()) if args.stage161_summary else {}
        latest_regime = macro_feature_info.get("latest_macro_regime") or stage161.get("macro_context", {}).get("gold_macro_pressure")
        latest_side = macro_feature_info.get("latest_macro_supported_side")
        current_shortlist = shortlist[shortlist["regime"] == latest_regime] if (not shortlist.empty and latest_regime) else shortlist.iloc[0:0] if not shortlist.empty else shortlist
        if len(shortlist) > 0 and len(current_shortlist) > 0:
            decision = "STAGE165_CURRENT_MACRO_THESIS_CANDIDATE_REVIEW_REQUIRED_NO_DEMO_RELEASE"
            severity = "WARN"
            recommended_action = "MANUALLY_REVIEW_CURRENT_REGIME_THESIS_BEFORE_ANY_EXECUTION_PATCH"
        elif len(shortlist) > 0:
            decision = "STAGE165_HISTORICAL_MACRO_THESIS_EXISTS_BUT_NOT_CURRENT_REGIME_KEEP_FREEZE"
            severity = "WARN"
            recommended_action = "WAIT_FOR_MATCHING_REGIME_OR_REBUILD_CURRENT_REGIME_THESIS"
        else:
            decision = "STAGE165_NO_ROBUST_MACRO_THESIS_CANDIDATE_KEEP_FREEZE"
            severity = "HIGH"
            recommended_action = "KEEP_STAGE157_FREEZE_AND_REBUILD_WITH_EVENT_FUNDAMENTAL_SPECIFIC_THESIS"

        regime_context = {
            **context,
            "bars_meta": bars_meta,
            "macro_meta": macro_meta,
            "macro_feature_info": macro_feature_info,
            "current_regime": latest_regime,
            "current_macro_supported_side": latest_side,
            "stage161_decision": stage161.get("decision"),
            "stage161_macro_context": stage161.get("macro_context"),
            "thresholds": {
                "horizons_days": horizons,
                "min_events": args.min_events,
                "min_mean_bps": args.min_mean_bps,
                "min_hit_rate": args.min_hit_rate,
                "min_recent_mean_bps": args.min_recent_mean_bps,
                "min_positive_folds": args.min_positive_folds,
            }
        }
        write_json(Path(outputs["regime_context_json"]), regime_context)
        summary = {
            "stage": STAGE,
            "generated_utc": now_utc_iso(),
            "root": str(root),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "status": "STAGE165_COMPLETE_MACRO_THESIS_REGIME_REBUILD_READY",
            "decision": decision,
            "severity": severity,
            "recommended_action": recommended_action,
            "bars_m5": str(Path(args.bars_m5).expanduser()),
            "macro_panel": str(macro_panel_path),
            "bar_count": int(bars_meta.get("bar_count", 0)),
            "daily_bar_count": int(context.get("daily_bar_count", 0)),
            "latest_bar_utc": bars_meta.get("max_time_utc"),
            "latest_daily_date": context.get("latest_daily_date"),
            "macro_feature_status": macro_feature_info.get("macro_feature_status"),
            "latest_macro_date": macro_feature_info.get("latest_macro_date"),
            "current_regime": latest_regime,
            "current_macro_supported_side": latest_side,
            "candidate_score_count": int(len(scores)),
            "macro_aligned_candidate_count": int(scores["macro_aligned"].sum()) if not scores.empty and "macro_aligned" in scores else 0,
            "shortlist_count": int(len(shortlist)),
            "current_regime_shortlist_count": int(len(current_shortlist)),
            "shortlist_side_counts": shortlist["side"].value_counts().to_dict() if not shortlist.empty and "side" in shortlist else {},
            "shortlist_regime_counts": shortlist["regime"].value_counts().to_dict() if not shortlist.empty and "regime" in shortlist else {},
            "top_shortlist_rule_ids": shortlist["rule_id"].head(10).tolist() if not shortlist.empty and "rule_id" in shortlist else [],
            "outputs": outputs,
            "next": [
                "Keep Stage157 freeze active.",
                "Do not release demo orders from this read-only macro thesis stage.",
                "If current_regime_shortlist_count is positive, manually review thesis mechanics before any execution patch.",
                "If shortlist_count is zero, rebuild using event/fundamental-specific thesis features or wait for regime change.",
            ],
        }
        write_json(Path(outputs["summary_json"]), summary)
        return summary
    except Exception as e:
        summary = {
            "stage": STAGE,
            "generated_utc": now_utc_iso(),
            "root": str(root),
            "order_routing_allowed": False,
            "demo_release_allowed": False,
            "status": "STAGE165_FAILURE_ARTIFACTS_WRITTEN",
            "decision": "STAGE165_RUN_FAILED_KEEP_FREEZE",
            "severity": "HIGH",
            "recommended_action": "KEEP_STAGE157_FREEZE_AND_INSPECT_ERROR",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "outputs": outputs,
        }
        write_json(Path(outputs["summary_json"]), summary)
        # Write empty CSVs with expected columns.
        pd.DataFrame(columns=["rule_id", "regime", "side", "horizon_days", "event_count", "mean_bps", "hit_rate", "passes"]).to_csv(outputs["candidate_scores_csv"], index=False)
        pd.DataFrame(columns=["rule_id", "regime", "side", "horizon_days", "event_count", "mean_bps", "hit_rate", "passes"]).to_csv(outputs["shortlist_csv"], index=False)
        write_json(Path(outputs["regime_context_json"]), {"error_type": type(e).__name__, "error_message": str(e)})
        return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage165 read-only macro thesis regime rebuild")
    p.add_argument("--root", required=True)
    p.add_argument("--bars-m5", required=True)
    p.add_argument("--stage161-summary", default="")
    p.add_argument("--macro-panel", default="")
    p.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    p.add_argument("--horizons-days", default="1,3,5")
    p.add_argument("--min-events", type=int, default=40)
    p.add_argument("--min-mean-bps", type=float, default=8.0)
    p.add_argument("--min-hit-rate", type=float, default=0.53)
    p.add_argument("--min-recent-mean-bps", type=float, default=3.0)
    p.add_argument("--min-positive-folds", type=int, default=3)
    return p


if __name__ == "__main__":
    summary = run(build_arg_parser().parse_args())
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
