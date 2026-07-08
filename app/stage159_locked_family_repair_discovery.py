#!/usr/bin/env python3
"""Stage159 locked-family repair discovery for XAUUSD.

Read-only/offline repair stage. It never writes execution KV and never sends orders.

Purpose:
- Re-evaluate Stage150/155 candidate rules against the current AMarkets M5 history.
- Penalize active-router family hopping by ranking stable families, not transient rules.
- Separate technical robustness from macro-blindness.
- Produce a shortlist for review before any future locked-family demo writer.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


FEATURE_WINDOWS_HOURS = (3, 6, 12, 24, 48)
TREND_WINDOWS = ((8, 20), (20, 50), (50, 100))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_float(value: Any, default: float = math.nan) -> float:
    if value is None:
        return default
    try:
        if isinstance(value, str) and not value.strip():
            return default
        return float(value)
    except Exception:
        return default


def normalize_utc_iso(value: Any, shift_hours: float = 0.0) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        ts = pd.to_datetime(text, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        if shift_hours:
            ts = ts + pd.to_timedelta(shift_hours, unit="h")
        return ts
    except Exception:
        return None


def iso_z(ts: Any) -> str:
    if ts is None or pd.isna(ts):
        return ""
    pts = pd.Timestamp(ts)
    if pts.tzinfo is None:
        pts = pts.tz_localize("UTC")
    else:
        pts = pts.tz_convert("UTC")
    return pts.isoformat().replace("+00:00", "Z")


def detect_delimiter(path: Path) -> str:
    sample = path.read_text(errors="ignore")[:4096]
    if "\t" in sample:
        return "\t"
    try:
        return csv.Sniffer().sniff(sample).delimiter
    except Exception:
        return ","


def read_bars(path: Path, timeframe_minutes: int, timestamp_shift_hours: float) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(str(path))
    delimiter = detect_delimiter(path)
    # AMarkets exports are often headerless: date, time, open, high, low, close, tick_volume, spread...
    raw = pd.read_csv(path, sep=delimiter, header=None, engine="python", dtype=str)
    if raw.empty:
        return pd.DataFrame(columns=["utc_time", "open", "high", "low", "close", "volume", "spread"])

    # Detect header row and re-read with header if needed.
    first = [str(x).strip().lower() for x in raw.iloc[0].tolist()]
    if any(x in first for x in ("time", "date", "utc_time", "open", "high", "low", "close")):
        raw = pd.read_csv(path, sep=delimiter, header=0, engine="python", dtype=str)
        cols = {c.lower().strip(): c for c in raw.columns}
        if "utc_time" in cols:
            t = pd.to_datetime(raw[cols["utc_time"]], utc=True, errors="coerce")
        elif "time" in cols and "date" in cols:
            t = pd.to_datetime(raw[cols["date"]].astype(str) + " " + raw[cols["time"]].astype(str), utc=True, errors="coerce")
        elif "time" in cols:
            t = pd.to_datetime(raw[cols["time"]], utc=True, errors="coerce")
        else:
            t = pd.to_datetime(raw.iloc[:, 0], utc=True, errors="coerce")
        open_col = cols.get("open") or raw.columns[2]
        high_col = cols.get("high") or raw.columns[3]
        low_col = cols.get("low") or raw.columns[4]
        close_col = cols.get("close") or raw.columns[5]
        vol_col = cols.get("volume") or cols.get("tick_volume") or (raw.columns[6] if len(raw.columns) > 6 else None)
        spread_col = cols.get("spread") or (raw.columns[8] if len(raw.columns) > 8 else None)
        out = pd.DataFrame({
            "utc_time": t + pd.to_timedelta(timestamp_shift_hours, unit="h"),
            "open": pd.to_numeric(raw[open_col], errors="coerce"),
            "high": pd.to_numeric(raw[high_col], errors="coerce"),
            "low": pd.to_numeric(raw[low_col], errors="coerce"),
            "close": pd.to_numeric(raw[close_col], errors="coerce"),
            "volume": pd.to_numeric(raw[vol_col], errors="coerce") if vol_col is not None else math.nan,
            "spread": pd.to_numeric(raw[spread_col], errors="coerce") if spread_col is not None else math.nan,
        })
    else:
        if raw.shape[1] >= 6:
            combined_time = raw.iloc[:, 0].astype(str) + " " + raw.iloc[:, 1].astype(str)
            t = pd.to_datetime(combined_time, utc=True, errors="coerce")
            out = pd.DataFrame({
                "utc_time": t + pd.to_timedelta(timestamp_shift_hours, unit="h"),
                "open": pd.to_numeric(raw.iloc[:, 2], errors="coerce"),
                "high": pd.to_numeric(raw.iloc[:, 3], errors="coerce"),
                "low": pd.to_numeric(raw.iloc[:, 4], errors="coerce"),
                "close": pd.to_numeric(raw.iloc[:, 5], errors="coerce"),
                "volume": pd.to_numeric(raw.iloc[:, 6], errors="coerce") if raw.shape[1] > 6 else math.nan,
                "spread": pd.to_numeric(raw.iloc[:, 8], errors="coerce") if raw.shape[1] > 8 else math.nan,
            })
        else:
            raise ValueError(f"Unsupported bar CSV schema with {raw.shape[1]} columns: {path}")

    out = out.dropna(subset=["utc_time", "open", "high", "low", "close"]).copy()
    out = out.sort_values("utc_time").drop_duplicates("utc_time", keep="last").reset_index(drop=True)
    out["bar_index"] = range(len(out))
    out["timeframe_minutes"] = timeframe_minutes
    return out


def compute_features(bars: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
    df = bars.copy()
    close = df["close"].astype(float)
    bars_per_hour = max(1, int(round(60 / timeframe_minutes)))
    for hours in FEATURE_WINDOWS_HOURS:
        lag = hours * bars_per_hour
        df[f"ret_{hours}h_bps"] = (close / close.shift(lag) - 1.0) * 10000.0
    for fast, slow in TREND_WINDOWS:
        fast_ma = close.rolling(fast, min_periods=fast).mean()
        slow_ma = close.rolling(slow, min_periods=slow).mean()
        df[f"trend_{fast}_{slow}_bps"] = (fast_ma / slow_ma - 1.0) * 10000.0
    range_n = 24 * bars_per_hour
    rolling_high = df["high"].astype(float).rolling(range_n, min_periods=max(2, range_n // 2)).max()
    rolling_low = df["low"].astype(float).rolling(range_n, min_periods=max(2, range_n // 2)).min()
    denom = (rolling_high - rolling_low).replace(0, math.nan)
    df["range_pos_24"] = ((close - rolling_low) / denom) * 100.0
    df["abs_ret_1h_bps"] = (close / close.shift(bars_per_hour) - 1.0).abs() * 10000.0
    df["volatility_24h_bps"] = df["abs_ret_1h_bps"].rolling(24 * bars_per_hour, min_periods=4).mean()
    # UTC-session tags; execution feed timestamps have already been normalized to UTC by timestamp_shift_hours.
    hour = df["utc_time"].dt.hour
    df["session"] = "OTHER"
    df.loc[(hour >= 0) & (hour < 7), "session"] = "ASIA"
    df.loc[(hour >= 7) & (hour < 13), "session"] = "LONDON"
    df.loc[(hour >= 13) & (hour < 21), "session"] = "NY"
    df.loc[(hour >= 12) & (hour < 16), "session"] = "LONDON_NY_OVERLAP"
    try:
        df["vol_regime"] = pd.qcut(df["volatility_24h_bps"], 3, labels=["LOW_VOL", "MID_VOL", "HIGH_VOL"], duplicates="drop")
        df["vol_regime"] = df["vol_regime"].astype(str).replace("nan", "UNKNOWN_VOL")
    except Exception:
        df["vol_regime"] = "UNKNOWN_VOL"
    return df


def find_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    lower = {c.lower(): c for c in columns}
    for name in candidates:
        if name.lower() in lower:
            return lower[name.lower()]
    for c in columns:
        lc = c.lower()
        for name in candidates:
            if name.lower() in lc:
                return c
    return None


def read_candidates(score_csv: Path) -> pd.DataFrame:
    if not score_csv.exists():
        raise FileNotFoundError(str(score_csv))
    df = pd.read_csv(score_csv, dtype=str)
    if df.empty:
        return df
    rule_col = find_column(df.columns, ["rule_id", "selected_rule_id", "candidate_id", "id"])
    cond_col = find_column(df.columns, ["conditions_json", "condition_json", "selected_conditions_json", "conditions"])
    if rule_col is None:
        raise ValueError("Could not identify rule_id column in score CSV")
    if cond_col is None:
        raise ValueError("Could not identify conditions_json column in score CSV")
    df = df.copy()
    df["_rule_id"] = df[rule_col].astype(str)
    df["_conditions_json"] = df[cond_col].astype(str)
    pass_col = find_column(df.columns, ["status", "decision", "candidate_decision", "pass", "passed"])
    if pass_col:
        pass_text = df[pass_col].astype(str).str.upper()
        df["_candidate_pass"] = pass_text.str.contains("PASS|READY|TRUE|1", regex=True, na=False)
    else:
        df["_candidate_pass"] = True
    return df


def family_key_from_rule_id(rule_id: str) -> str:
    rid = str(rule_id)
    parts = rid.split("__")
    stripped: List[str] = []
    for p in parts:
        p = re.sub(r"_(GEQ|LEQ|GT|LT|EQ)\d+(?:\.\d+)?", "", p)
        stripped.append(p)
    return "__".join(stripped)


def parse_conditions(text: str) -> List[Dict[str, Any]]:
    try:
        obj = json.loads(text)
    except Exception:
        return []
    if isinstance(obj, dict):
        if "conditions" in obj and isinstance(obj["conditions"], list):
            return obj["conditions"]
        return [obj]
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    return []


def evaluate_condition_series(df: pd.DataFrame, cond: Dict[str, Any]) -> pd.Series:
    feature = str(cond.get("feature") or cond.get("name") or cond.get("column") or "").strip()
    op = str(cond.get("op") or cond.get("operator") or ">=").strip()
    threshold = parse_float(cond.get("threshold") if "threshold" in cond else cond.get("value"))
    if not feature or feature not in df.columns or math.isnan(threshold):
        return pd.Series(False, index=df.index)
    values = pd.to_numeric(df[feature], errors="coerce")
    if op in (">=", "GEQ", "geq"):
        return values >= threshold
    if op in ("<=", "LEQ", "leq"):
        return values <= threshold
    if op in (">", "GT", "gt"):
        return values > threshold
    if op in ("<", "LT", "lt"):
        return values < threshold
    if op in ("==", "=", "EQ", "eq"):
        return values == threshold
    return pd.Series(False, index=df.index)


def cooldown_indices(mask: pd.Series, cooldown_bars: int, max_events: Optional[int] = None) -> List[int]:
    idx = list(mask[mask.fillna(False)].index)
    selected: List[int] = []
    last = -10**12
    for i in idx:
        if i - last >= cooldown_bars:
            selected.append(int(i))
            last = int(i)
            if max_events is not None and len(selected) >= max_events:
                break
    return selected


def calc_metrics(values: Sequence[float]) -> Dict[str, Any]:
    arr = [float(x) for x in values if x is not None and not math.isnan(float(x))]
    if not arr:
        return {"events": 0, "mean_bps": math.nan, "median_bps": math.nan, "hit_rate": math.nan, "total_bps": 0.0}
    s = pd.Series(arr)
    return {
        "events": int(len(arr)),
        "mean_bps": float(s.mean()),
        "median_bps": float(s.median()),
        "hit_rate": float((s > 0).mean()),
        "total_bps": float(s.sum()),
    }


def read_risk_summary(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def negative_demo_families(risk_summary: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for row in risk_summary.get("per_family", []) or []:
        try:
            if parse_float(row.get("total_bps"), 0.0) < 0 or parse_float(row.get("total_net_profit"), 0.0) < 0:
                fk = str(row.get("family_key") or "").strip()
                if fk:
                    out.append(fk)
        except Exception:
            continue
    return sorted(set(out))


def macro_status(files: Dict[str, Optional[Path]], bars_latest: Optional[pd.Timestamp], stale_days: float) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    any_present = False
    stale_any = False
    for name, path in files.items():
        if path is None:
            details[name] = {"provided": False, "exists": False}
            continue
        exists = path.exists()
        any_present = any_present or exists
        item: Dict[str, Any] = {"provided": True, "exists": exists, "path": str(path)}
        if exists:
            try:
                delim = detect_delimiter(path)
                df = pd.read_csv(path, sep=delim, engine="python", dtype=str)
                if df.empty:
                    item["row_count"] = 0
                    item["latest_time"] = ""
                    item["stale"] = True
                    stale_any = True
                else:
                    time_col = find_column(df.columns, ["utc_time", "date", "time", "timestamp"])
                    if time_col:
                        t = pd.to_datetime(df[time_col], utc=True, errors="coerce").dropna()
                        latest = t.max() if len(t) else None
                    else:
                        latest = None
                    item["row_count"] = int(len(df))
                    item["latest_time"] = iso_z(latest) if latest is not None else ""
                    if bars_latest is not None and latest is not None:
                        age_days = (bars_latest - latest).total_seconds() / 86400.0
                        item["age_days_vs_bars"] = float(age_days)
                        item["stale"] = bool(age_days > stale_days)
                    else:
                        item["stale"] = True
                    stale_any = stale_any or bool(item.get("stale"))
            except Exception as exc:
                item["error"] = str(exc)
                item["stale"] = True
                stale_any = True
        details[name] = item
    return {
        "macro_files_provided": any(v is not None for v in files.values()),
        "macro_any_available": any_present,
        "macro_stale_any": stale_any,
        "macro_blind": not any_present,
        "details": details,
    }


def _main_impl(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage159 locked-family repair discovery")
    parser.add_argument("--root", default=".")
    parser.add_argument("--bars-m5", required=True)
    parser.add_argument("--score-csv", required=True)
    parser.add_argument("--risk-summary", default="")
    parser.add_argument("--timestamp-shift-hours", type=float, default=-3.0)
    parser.add_argument("--timeframe-minutes", type=int, default=5)
    parser.add_argument("--horizon-hours", type=float, default=4.0)
    parser.add_argument("--cooldown-hours", type=float, default=4.0)
    parser.add_argument("--min-events", type=int, default=20)
    parser.add_argument("--min-mean-bps", type=float, default=2.0)
    parser.add_argument("--min-hit-rate", type=float, default=0.52)
    parser.add_argument("--min-positive-folds", type=int, default=3)
    parser.add_argument("--min-session-positive", type=int, default=2)
    parser.add_argument("--max-candidates", type=int, default=800)
    parser.add_argument("--macro-dxy", default="")
    parser.add_argument("--macro-real-yield", default="")
    parser.add_argument("--macro-us10y", default="")
    parser.add_argument("--macro-required", action="store_true")
    parser.add_argument("--macro-stale-days", type=float, default=7.0)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    reports_dir = root / "reports" / "stage159_locked_family_repair_discovery"
    ensure_dir(reports_dir)

    bars_path = Path(args.bars_m5).expanduser()
    score_path = Path(args.score_csv).expanduser()
    risk_path = Path(args.risk_summary).expanduser() if args.risk_summary else None

    bars_raw = read_bars(bars_path, args.timeframe_minutes, args.timestamp_shift_hours)
    bars = compute_features(bars_raw, args.timeframe_minutes)
    bars_latest = bars["utc_time"].max() if not bars.empty else None
    bars_per_hour = max(1, int(round(60 / args.timeframe_minutes)))
    horizon_bars = max(1, int(round(args.horizon_hours * bars_per_hour)))
    cooldown_bars = max(1, int(round(args.cooldown_hours * bars_per_hour)))
    bars["future_close"] = bars["close"].shift(-horizon_bars)
    bars["future_bps"] = (bars["future_close"] / bars["close"] - 1.0) * 10000.0
    # Chronological folds for regime/era stability.
    # IMPORTANT: keep this column as object/string from the start.
    # On newer pandas/pyarrow-backed dtypes, assigning string fold labels into an int column
    # raises: TypeError: Invalid value <ArrowStringArray ...> for dtype int64.
    valid_index = bars.dropna(subset=["future_bps"]).index
    bars["fold"] = pd.Series("UNASSIGNED", index=bars.index, dtype="object")
    if len(valid_index):
        labels = pd.qcut(
            pd.Series(range(len(valid_index)), index=valid_index),
            4,
            labels=["F1_OLD", "F2", "F3", "F4_RECENT"],
            duplicates="drop",
        )
        bars.loc[valid_index, "fold"] = labels.astype(str).astype("object")

    candidates = read_candidates(score_path)
    candidates = candidates[candidates["_candidate_pass"]].head(args.max_candidates).copy()
    risk_summary = read_risk_summary(risk_path)
    blocked_negative = set(negative_demo_families(risk_summary))

    rows: List[Dict[str, Any]] = []
    session_rows: List[Dict[str, Any]] = []
    for _, cand in candidates.iterrows():
        rule_id = str(cand["_rule_id"])
        family = family_key_from_rule_id(rule_id)
        conditions = parse_conditions(str(cand["_conditions_json"]))
        if not conditions:
            continue
        mask = pd.Series(True, index=bars.index)
        for cond in conditions:
            mask = mask & evaluate_condition_series(bars, cond)
        idx = cooldown_indices(mask, cooldown_bars)
        idx = [i for i in idx if i + horizon_bars < len(bars)]
        vals = list(pd.to_numeric(bars.loc[idx, "future_bps"], errors="coerce")) if idx else []
        metrics = calc_metrics(vals)
        fold_means: Dict[str, float] = {}
        positive_folds = 0
        for fold, g in bars.loc[idx].groupby("fold") if idx else []:
            m = calc_metrics(list(pd.to_numeric(g["future_bps"], errors="coerce")))
            fold_means[str(fold)] = m["mean_bps"]
            if not math.isnan(m["mean_bps"]) and m["mean_bps"] > 0:
                positive_folds += 1
        session_positive = 0
        for session, g in bars.loc[idx].groupby("session") if idx else []:
            m = calc_metrics(list(pd.to_numeric(g["future_bps"], errors="coerce")))
            if not math.isnan(m["mean_bps"]) and m["mean_bps"] > 0:
                session_positive += 1
            session_rows.append({"rule_id": rule_id, "family_key": family, "session": session, **m})
        vol_positive = 0
        vol_means: Dict[str, float] = {}
        for regime, g in bars.loc[idx].groupby("vol_regime") if idx else []:
            m = calc_metrics(list(pd.to_numeric(g["future_bps"], errors="coerce")))
            vol_means[str(regime)] = m["mean_bps"]
            if not math.isnan(m["mean_bps"]) and m["mean_bps"] > 0:
                vol_positive += 1
        pass_repair = (
            metrics["events"] >= args.min_events
            and not math.isnan(metrics["mean_bps"])
            and metrics["mean_bps"] >= args.min_mean_bps
            and not math.isnan(metrics["hit_rate"])
            and metrics["hit_rate"] >= args.min_hit_rate
            and positive_folds >= args.min_positive_folds
            and session_positive >= args.min_session_positive
            and family not in blocked_negative
        )
        row = {
            "rule_id": rule_id,
            "family_key": family,
            "blocked_by_demo_negative_family": family in blocked_negative,
            "condition_count": len(conditions),
            "conditions_json": json.dumps(conditions, ensure_ascii=False),
            **metrics,
            "positive_folds": positive_folds,
            "session_positive_count": session_positive,
            "vol_regime_positive_count": vol_positive,
            "fold_means_json": json.dumps(fold_means, ensure_ascii=False),
            "vol_regime_means_json": json.dumps(vol_means, ensure_ascii=False),
            "repair_pass": pass_repair,
            "score": (metrics["mean_bps"] if not math.isnan(metrics["mean_bps"]) else -9999) + 3.0 * positive_folds + 2.0 * session_positive,
        }
        rows.append(row)

    cand_out = pd.DataFrame(rows)
    if not cand_out.empty:
        cand_out = cand_out.sort_values(["repair_pass", "score", "events"], ascending=[False, False, False])
    shortlist = cand_out[cand_out["repair_pass"] == True].copy() if not cand_out.empty else pd.DataFrame()

    family_rows: List[Dict[str, Any]] = []
    if not cand_out.empty:
        for family, g in cand_out.groupby("family_key"):
            best = g.sort_values(["repair_pass", "score", "events"], ascending=[False, False, False]).iloc[0]
            pass_count = int(g["repair_pass"].sum())
            family_rows.append({
                "family_key": family,
                "candidate_count": int(len(g)),
                "repair_pass_count": pass_count,
                "blocked_by_demo_negative_family": bool(best.get("blocked_by_demo_negative_family", False)),
                "best_rule_id": best["rule_id"],
                "best_events": int(best["events"]),
                "best_mean_bps": float(best["mean_bps"]) if not pd.isna(best["mean_bps"]) else math.nan,
                "best_hit_rate": float(best["hit_rate"]) if not pd.isna(best["hit_rate"]) else math.nan,
                "best_positive_folds": int(best["positive_folds"]),
                "best_session_positive_count": int(best["session_positive_count"]),
                "best_score": float(best["score"]),
                "family_repair_pass": pass_count > 0,
            })
    family_out = pd.DataFrame(family_rows)
    if not family_out.empty:
        family_out = family_out.sort_values(["family_repair_pass", "best_score"], ascending=[False, False])

    macro = macro_status(
        {
            "dxy": Path(args.macro_dxy).expanduser() if args.macro_dxy else None,
            "real_yield": Path(args.macro_real_yield).expanduser() if args.macro_real_yield else None,
            "us10y": Path(args.macro_us10y).expanduser() if args.macro_us10y else None,
        },
        bars_latest,
        args.macro_stale_days,
    )

    shortlist_csv = reports_dir / "stage159_locked_family_shortlist.csv"
    family_csv = reports_dir / "stage159_family_repair_summary.csv"
    session_csv = reports_dir / "stage159_session_repair_summary.csv"
    candidates_csv = reports_dir / "stage159_candidate_replay_scores.csv"
    summary_json = reports_dir / "stage159_locked_family_repair_discovery_summary.json"
    cand_out.to_csv(candidates_csv, index=False)
    shortlist.to_csv(shortlist_csv, index=False)
    family_out.to_csv(family_csv, index=False)
    pd.DataFrame(session_rows).to_csv(session_csv, index=False)

    if args.macro_required and (macro["macro_blind"] or macro["macro_stale_any"]):
        decision = "STAGE159_NO_DEMO_RELEASE_MACRO_REQUIRED_MISSING_OR_STALE"
        recommended = "REFRESH_MACRO_EXOGENOUS_DATA_BEFORE_ANY_LOCKED_FAMILY_DEMO"
        severity = "HIGH"
    elif shortlist.empty:
        decision = "STAGE159_NO_LOCKED_FAMILY_SHORTLIST_REPAIR_DISCOVERY_FAILED"
        recommended = "KEEP_ROUTING_FROZEN_AND_PIVOT_TO_STRICTER_DISCOVERY_OR_HIGHER_TIMEFRAME_THESIS"
        severity = "HIGH"
    elif macro["macro_blind"] or macro["macro_stale_any"]:
        decision = "STAGE159_TECHNICAL_SHORTLIST_READY_MACRO_BLIND_NO_DEMO_RELEASE"
        recommended = "REVIEW_SHORTLIST_AND_REFRESH_MACRO_OR_ADD_REGIME_FILTER_BEFORE_DEMO_WRITER"
        severity = "MEDIUM"
    else:
        decision = "STAGE159_LOCKED_FAMILY_SHORTLIST_READY_FOR_REVIEW_NO_ORDERING"
        recommended = "REVIEW_TOP_FAMILIES_THEN_BUILD_LOCKED_FAMILY_DEMO_WRITER_ONLY_IF_APPROVED"
        severity = "MEDIUM"

    summary = {
        "stage": "Stage159_LOCKED_FAMILY_REPAIR_DISCOVERY",
        "generated_utc": utc_now_iso(),
        "status": "STAGE159_COMPLETE_LOCKED_FAMILY_REPAIR_DISCOVERY_READY",
        "decision": decision,
        "recommended_action": recommended,
        "severity": severity,
        "root": str(root),
        "bars_m5": str(bars_path),
        "score_csv": str(score_path),
        "risk_summary": str(risk_path) if risk_path else "",
        "bar_count": int(len(bars)),
        "bars_first_utc": iso_z(bars["utc_time"].min()) if not bars.empty else "",
        "bars_latest_utc": iso_z(bars_latest) if bars_latest is not None else "",
        "timestamp_shift_hours": args.timestamp_shift_hours,
        "candidate_rows_loaded": int(len(candidates)),
        "candidate_rows_scored": int(len(cand_out)),
        "shortlist_count": int(len(shortlist)),
        "family_count": int(family_out["family_key"].nunique()) if not family_out.empty else 0,
        "family_repair_pass_count": int(family_out["family_repair_pass"].sum()) if not family_out.empty else 0,
        "blocked_negative_demo_families": sorted(blocked_negative),
        "macro_status": macro,
        "top_family_rows": family_out.head(10).to_dict(orient="records") if not family_out.empty else [],
        "shortlist_csv": str(shortlist_csv),
        "family_summary_csv": str(family_csv),
        "session_summary_csv": str(session_csv),
        "candidate_scores_csv": str(candidates_csv),
        "summary_json": str(summary_json),
        "next": [
            "Keep Stage157 freeze active while this offline shortlist is reviewed.",
            "Do not route active-router output directly to demo from this stage.",
            "If macro_status is macro_blind or stale, refresh macro/regime data before any Stage160 demo writer.",
            "If no robust family passes, pivot away from M5 active-router to higher-timeframe or macro-regime thesis.",
        ],
    }
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0




STAGE159_OUTPUT_FILES = [
    "stage159_locked_family_shortlist.csv",
    "stage159_family_repair_summary.csv",
    "stage159_session_repair_summary.csv",
    "stage159_candidate_replay_scores.csv",
]


def _best_effort_root_from_argv(argv: Optional[Sequence[str]]) -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", default=".")
    try:
        ns, _ = parser.parse_known_args(list(argv) if argv is not None else None)
        return Path(ns.root).expanduser()
    except Exception:
        return Path(".").expanduser()


def _write_failure_artifacts(argv: Optional[Sequence[str]], exc: BaseException) -> Dict[str, Any]:
    root = _best_effort_root_from_argv(argv)
    reports_dir = root / "reports" / "stage159_locked_family_repair_discovery"
    ensure_dir(reports_dir)
    for filename in STAGE159_OUTPUT_FILES:
        path = reports_dir / filename
        if not path.exists():
            path.write_text("stage159_status,error_type,error_message\nFAILED_BEFORE_SCORING,%s,%s\n" % (type(exc).__name__, str(exc).replace("\n", " ").replace(",", ";")))
    summary_json = reports_dir / "stage159_locked_family_repair_discovery_summary.json"
    summary = {
        "stage": "Stage159C_LOCKED_FAMILY_REPAIR_DISCOVERY_FAILURE_SAFE",
        "generated_utc": utc_now_iso(),
        "status": "STAGE159C_FAILURE_ARTIFACTS_WRITTEN",
        "decision": "STAGE159C_REPAIR_DISCOVERY_RUN_FAILED_NO_DEMO_RELEASE",
        "recommended_action": "INSPECT_STDERR_AND_FIX_INPUT_OR_SCHEMA_BEFORE_RERUN",
        "severity": "HIGH",
        "root": str(root),
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "argv": list(argv) if argv is not None else sys.argv[1:],
        "shortlist_csv": str(reports_dir / "stage159_locked_family_shortlist.csv"),
        "family_summary_csv": str(reports_dir / "stage159_family_repair_summary.csv"),
        "session_summary_csv": str(reports_dir / "stage159_session_repair_summary.csv"),
        "candidate_scores_csv": str(reports_dir / "stage159_candidate_replay_scores.csv"),
        "summary_json": str(summary_json),
        "next": [
            "Keep Stage157 freeze active.",
            "Paste or upload this summary and the terminal stderr/stdout.",
            "Do not build a demo writer from a failed Stage159 run.",
        ],
    }
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return _main_impl(argv)
    except Exception as exc:
        summary = _write_failure_artifacts(argv, exc)
        print(json.dumps(summary, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
