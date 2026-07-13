#!/usr/bin/env python3
"""Stage171H — forward-only H64L feature materializer.

Builds a fresh one-row-per-feature-date dataset for the exact locked H64L rule:
- gold_sma20_over_50 from completed AMarkets M5 daily bars
- dxy_ret_20d from the freshest valid DXY daily series
- real_yield_change_20d from the freshest valid real-yield daily series
- etf_flow_tonnes_3m from WGC total gold-ETF holdings, not the stale Stage64K label

This is a mechanical forward/as-of repair. It does not optimize thresholds, write
MT5 signals, or authorize demo/live orders.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

STAGE = "Stage171H_H64L_FORWARD_FEATURE_MATERIALIZER"
DEFAULT_OUT = "data/forward_shadow/h64l_forward_feature_snapshots.csv"
DEFAULT_REPORT = "reports/stage171h_h64l_forward_feature_materializer"
SNAPSHOT_FIELDS = [
    "feature_date_utc", "sample_available_after_utc", "gold_close",
    "gold_sma20_over_50", "dxy_ret_20d", "real_yield_change_20d",
    "etf_flow_tonnes_3m", "gold_source", "gold_source_date_utc",
    "dxy_source", "dxy_source_date_utc", "real_yield_source",
    "real_yield_source_date_utc", "etf_source", "etf_source_date_utc",
    "etf_source_available_after_utc", "data_quality_pass", "source_hash",
]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_iso(x: Optional[dt.datetime] = None) -> str:
    y = (x or utc_now()).astimezone(dt.timezone.utc).replace(microsecond=0)
    return y.isoformat().replace("+00:00", "Z")


def resolve(root: Path, value: str | Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else root / p


def detect_sep(path: Path) -> str:
    line = path.open("r", encoding="utf-8-sig", errors="replace").readline()
    seps = ["\t", ",", ";", "|"]
    return max(seps, key=line.count)


def parse_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null", "."}:
        return None
    try:
        x = float(s)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def find_amarkets_m5(root: Path, inbox: Path) -> Optional[Path]:
    candidates = [
        inbox / "amarkets_xauusd_5m.csv",
        Path("~/Downloads/amarkets_xauusd_5m.csv").expanduser(),
        root / "data" / "raw" / "amarkets_xauusd_5m.csv",
    ]
    existing = [p for p in candidates if p.exists()]
    return max(existing, key=lambda p: p.stat().st_mtime) if existing else None


def load_gold_daily(path: Path, min_bars: int = 100) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    sep = detect_sep(path)
    df = pd.read_csv(path, sep=sep, low_memory=False)
    cmap = {str(c).strip().lower(): c for c in df.columns}
    date_col = cmap.get("<date>") or cmap.get("date")
    time_col = cmap.get("<time>") or cmap.get("time")
    close_col = cmap.get("<close>") or cmap.get("close")
    if not date_col or not time_col or not close_col:
        raise ValueError(f"AMarkets schema not recognized: {list(df.columns)}")
    ts = pd.to_datetime(df[date_col].astype(str).str.strip() + " " + df[time_col].astype(str).str.strip(), errors="coerce", utc=True)
    close = pd.to_numeric(df[close_col], errors="coerce")
    x = pd.DataFrame({"ts": ts, "close": close}).dropna().sort_values("ts")
    x["date"] = x["ts"].dt.floor("D")
    daily = x.groupby("date", as_index=False).agg(close=("close", "last"), bars=("close", "size"))
    today = pd.Timestamp.now(tz="UTC").floor("D")
    daily = daily[(daily["date"] < today) & (daily["bars"] >= min_bars)].copy()
    daily["sma20"] = daily["close"].rolling(20, min_periods=20).mean()
    daily["sma50"] = daily["close"].rolling(50, min_periods=50).mean()
    daily["gold_sma20_over_50"] = daily["sma20"] / daily["sma50"] - 1.0
    daily = daily.dropna(subset=["gold_sma20_over_50"])
    if daily.empty:
        raise ValueError("No completed AMarkets daily rows with SMA20/SMA50")
    return daily, {
        "path": str(path), "separator": sep, "raw_rows": int(len(df)),
        "completed_daily_rows": int(len(daily)),
        "latest_date_utc": daily.iloc[-1]["date"].date().isoformat(),
        "latest_bars": int(daily.iloc[-1]["bars"]),
    }


def candidate_files(root: Path, inbox: Path, kind: str) -> List[Path]:
    tokens = {
        "dxy": ["dxy", "dollar_index", "dtwex"],
        "real_yield": ["real_yield", "realyield", "dfii10", "dfii5"],
    }[kind]
    roots = [root / "data", inbox]
    out: List[Path] = []
    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".csv", ".json"}:
                continue
            low = str(p).lower()
            if any(bad in low for bad in ["stage64k", "forward_shadow", "/reports/"]):
                continue
            if any(t in low for t in tokens):
                out.append(p)
    return sorted(set(out))


def normalize_series_frame(df: pd.DataFrame, path: Path, kind: str) -> Optional[pd.DataFrame]:
    if df.empty:
        return None
    lower = {str(c).strip().lower(): c for c in df.columns}
    date_names = ["timestamp", "date", "observation_date", "time", "datetime", "date_utc", "feature_date_utc"]
    date_col = next((lower[x] for x in date_names if x in lower), None)
    if date_col is None:
        date_col = next((c for c in df.columns if "date" in str(c).lower() or "time" in str(c).lower()), None)
    if date_col is None:
        return None
    preferred = (["dxy", "close", "value", "dtwexbgs", "dtwexafegs"] if kind == "dxy"
                 else ["real_yield", "close", "value", "dfii10", "dfii5"])
    value_col = next((lower[x] for x in preferred if x in lower), None)
    if value_col is None:
        numeric_candidates = [c for c in df.columns if c != date_col and pd.to_numeric(df[c], errors="coerce").notna().sum() >= 20]
        if len(numeric_candidates) == 1:
            value_col = numeric_candidates[0]
    if value_col is None:
        return None
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.floor("D"),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna().sort_values("date").drop_duplicates("date", keep="last")
    if len(out) < 25:
        return None
    out.attrs.update({"path": str(path), "date_col": str(date_col), "value_col": str(value_col)})
    return out


def load_series_file(path: Path, kind: str) -> Optional[pd.DataFrame]:
    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
            return normalize_series_frame(df, path, kind)
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            return normalize_series_frame(pd.DataFrame(obj), path, kind)
        if isinstance(obj, dict):
            for key in ["observations", "data", "series", "results"]:
                if isinstance(obj.get(key), list):
                    return normalize_series_frame(pd.DataFrame(obj[key]), path, kind)
    except Exception:
        return None
    return None


def choose_series(root: Path, inbox: Path, kind: str, cutoff: pd.Timestamp) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    options: List[Tuple[Tuple[int, int, float], pd.DataFrame]] = []
    for path in candidate_files(root, inbox, kind):
        s = load_series_file(path, kind)
        if s is None:
            continue
        usable = s[s["date"] <= cutoff].copy()
        if len(usable) < 21:
            continue
        latest = usable.iloc[-1]["date"]
        token_score = 3 if kind.replace("_", "") in path.name.lower().replace("_", "") else 1
        score = (token_score, int(len(usable)), latest.timestamp())
        options.append((score, usable))
    if not options:
        raise ValueError(f"No valid {kind} series with >=21 observations through {cutoff.date()}")
    options.sort(key=lambda x: x[0], reverse=True)
    s = options[0][1]
    meta = {
        "path": s.attrs.get("path"), "date_col": s.attrs.get("date_col"),
        "value_col": s.attrs.get("value_col"), "rows": int(len(s)),
        "latest_date_utc": s.iloc[-1]["date"].date().isoformat(),
        "latest_value": float(s.iloc[-1]["value"]),
    }
    return s, meta


def extract_wgc_series_from_normalized(path: Path) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    except Exception:
        return None
    lower = {str(c).strip().lower(): c for c in df.columns}
    # Direct extracted sheet.
    date_col = next((c for c in df.columns if str(c).strip().lower() in {"ticker", "date", "month"}), None)
    total_col = next((c for c in df.columns if "all units in tonnes" in str(c).lower()), None)
    if date_col and total_col:
        out = pd.DataFrame({"date": pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.floor("D"), "holdings": pd.to_numeric(df[total_col], errors="coerce")}).dropna().sort_values("date").drop_duplicates("date", keep="last")
        if len(out) >= 4:
            out.attrs["path"] = str(path)
            return out
    # Normalized rows with embedded JSON payload.
    sheet_col = next((c for c in df.columns if "sheet" in str(c).lower()), None)
    json_cols = [c for c in df.columns if "json" in str(c).lower() or "raw" in str(c).lower()]
    if not json_cols:
        return None
    rows = []
    for _, r in df.iterrows():
        if sheet_col and "holdings by month" not in str(r.get(sheet_col, "")).lower():
            continue
        for jc in json_cols:
            raw = r.get(jc)
            if not isinstance(raw, str) or not raw.strip().startswith("{"):
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            d = obj.get("ticker") or obj.get("date") or obj.get("Date")
            h = next((v for k, v in obj.items() if "all units in tonnes" in str(k).lower()), None)
            if d is not None and parse_num(h) is not None:
                rows.append({"date": d, "holdings": parse_num(h)})
                break
    if len(rows) < 4:
        return None
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"], errors="coerce", utc=True).dt.floor("D")
    out["holdings"] = pd.to_numeric(out["holdings"], errors="coerce")
    out = out.dropna().sort_values("date").drop_duplicates("date", keep="last")
    if len(out) >= 4:
        out.attrs["path"] = str(path)
        return out
    return None


def extract_wgc_series_from_excel(path: Path) -> Optional[pd.DataFrame]:
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return None
    for sheet in xl.sheet_names:
        if "holdings" not in sheet.lower() or "month" not in sheet.lower():
            continue
        for header in range(0, 8):
            try:
                df = pd.read_excel(path, sheet_name=sheet, header=header)
            except Exception:
                continue
            s = extract_wgc_series_from_normalized_frame(df, path)
            if s is not None:
                return s
    return None


def extract_wgc_series_from_normalized_frame(df: pd.DataFrame, path: Path) -> Optional[pd.DataFrame]:
    date_col = next((c for c in df.columns if str(c).strip().lower() in {"ticker", "date", "month"}), None)
    total_col = next((c for c in df.columns if "all units in tonnes" in str(c).lower()), None)
    if date_col is None or total_col is None:
        return None
    out = pd.DataFrame({"date": pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.floor("D"), "holdings": pd.to_numeric(df[total_col], errors="coerce")}).dropna().sort_values("date").drop_duplicates("date", keep="last")
    if len(out) < 4:
        return None
    out.attrs["path"] = str(path)
    return out


def choose_etf_series(root: Path, inbox: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    candidates: List[Path] = []
    for base in [root / "data", inbox]:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".csv", ".xlsx"}:
                low = str(p).lower()
                if ("wgc" in low or "etf_flows" in low or "etf-flows" in low) and ("etf" in low or "holdings" in low):
                    candidates.append(p)
    options = []
    for p in sorted(set(candidates)):
        s = extract_wgc_series_from_excel(p) if p.suffix.lower() == ".xlsx" else extract_wgc_series_from_normalized(p)
        if s is None or len(s) < 4:
            continue
        latest = s.iloc[-1]["date"]
        options.append(((latest.timestamp(), p.stat().st_mtime, len(s)), s, p))
    if not options:
        raise ValueError("No valid WGC total ETF holdings-by-month series found")
    options.sort(key=lambda x: x[0], reverse=True)
    s, p = options[0][1], options[0][2]
    latest = s.iloc[-1]
    target = latest["date"] - pd.DateOffset(months=3)
    prior = s[s["date"] <= target]
    if prior.empty:
        raise ValueError("WGC series lacks a 3-month prior observation")
    prior_row = prior.iloc[-1]
    flow = float(latest["holdings"] - prior_row["holdings"])
    available = dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc)
    meta = {
        "path": str(p), "rows": int(len(s)),
        "latest_data_date_utc": latest["date"].date().isoformat(),
        "prior_data_date_utc": prior_row["date"].date().isoformat(),
        "latest_holdings_tonnes": float(latest["holdings"]),
        "prior_holdings_tonnes": float(prior_row["holdings"]),
        "etf_flow_tonnes_3m": flow,
        "source_available_after_utc": utc_iso(available),
        "source_age_days": round((utc_now() - available).total_seconds() / 86400.0, 3),
    }
    return s, meta


def write_history(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, str]] = []
    if path.exists() and path.stat().st_size:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f, delimiter=detect_sep(path)))
    by_date = {str(r.get("feature_date_utc") or ""): r for r in rows if r.get("feature_date_utc")}
    by_date[str(row["feature_date_utc"])] = {k: row.get(k, "") for k in SNAPSHOT_FIELDS}
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDS)
        w.writeheader()
        for key in sorted(by_date):
            w.writerow(by_date[key])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="~/Desktop/xauusd-trader")
    ap.add_argument("--inbox", default="~/Downloads/xauusd_fundamental_event_inbox")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--report-dir", default=DEFAULT_REPORT)
    ap.add_argument("--max-gold-age-days", type=float, default=4.0)
    ap.add_argument("--max-macro-age-days", type=float, default=7.0)
    ap.add_argument("--max-etf-source-age-days", type=float, default=60.0)
    ap.add_argument("--max-abs-etf-flow-tonnes", type=float, default=2500.0)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    inbox = Path(args.inbox).expanduser().resolve()
    out = resolve(root, args.out)
    report = resolve(root, args.report_dir)
    report.mkdir(parents=True, exist_ok=True)
    generated = utc_now()
    issues: List[str] = []
    sources: Dict[str, Any] = {}
    row: Dict[str, Any] = {}

    try:
        gold_path = find_amarkets_m5(root, inbox)
        if gold_path is None:
            raise ValueError("AMarkets M5 file not found")
        gold, sources["gold"] = load_gold_daily(gold_path)
        g = gold.iloc[-1]
        feature_date = g["date"]
        row.update({
            "feature_date_utc": feature_date.date().isoformat(),
            "gold_close": float(g["close"]),
            "gold_sma20_over_50": float(g["gold_sma20_over_50"]),
            "gold_source": str(gold_path),
            "gold_source_date_utc": feature_date.date().isoformat(),
        })
        gold_age = (pd.Timestamp.now(tz="UTC").floor("D") - feature_date).days
        if gold_age > args.max_gold_age_days:
            issues.append(f"GOLD_STALE_{gold_age}D")

        macro_cutoff = feature_date - pd.Timedelta(days=1)
        dxy, sources["dxy"] = choose_series(root, inbox, "dxy", macro_cutoff)
        ry, sources["real_yield"] = choose_series(root, inbox, "real_yield", macro_cutoff)
        dxy_val = float(dxy.iloc[-1]["value"] / dxy.iloc[-21]["value"] - 1.0)
        ry_val = float(ry.iloc[-1]["value"] - ry.iloc[-21]["value"])
        row.update({
            "dxy_ret_20d": dxy_val,
            "dxy_source": sources["dxy"]["path"],
            "dxy_source_date_utc": sources["dxy"]["latest_date_utc"],
            "real_yield_change_20d": ry_val,
            "real_yield_source": sources["real_yield"]["path"],
            "real_yield_source_date_utc": sources["real_yield"]["latest_date_utc"],
        })
        dxy_age = (feature_date - dxy.iloc[-1]["date"]).days
        ry_age = (feature_date - ry.iloc[-1]["date"]).days
        if dxy_age > args.max_macro_age_days:
            issues.append(f"DXY_STALE_{dxy_age}D")
        if ry_age > args.max_macro_age_days:
            issues.append(f"REAL_YIELD_STALE_{ry_age}D")

        _, sources["etf"] = choose_etf_series(root, inbox)
        etf_flow = float(sources["etf"]["etf_flow_tonnes_3m"])
        row.update({
            "etf_flow_tonnes_3m": etf_flow,
            "etf_source": sources["etf"]["path"],
            "etf_source_date_utc": sources["etf"]["latest_data_date_utc"],
            "etf_source_available_after_utc": sources["etf"]["source_available_after_utc"],
        })
        if abs(etf_flow) > args.max_abs_etf_flow_tonnes:
            issues.append(f"ETF_FLOW_IMPLAUSIBLE_ABS_GT_{args.max_abs_etf_flow_tonnes:g}")
        if float(sources["etf"]["source_age_days"]) > args.max_etf_source_age_days:
            issues.append(f"ETF_SOURCE_STALE_{sources['etf']['source_age_days']}D")

        availability = [
            feature_date.to_pydatetime().replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1),
            pd.Timestamp(dxy.iloc[-1]["date"]).to_pydatetime() + dt.timedelta(days=1),
            pd.Timestamp(ry.iloc[-1]["date"]).to_pydatetime() + dt.timedelta(days=1),
            dt.datetime.fromisoformat(str(sources["etf"]["source_available_after_utc"]).replace("Z", "+00:00")),
        ]
        row["sample_available_after_utc"] = utc_iso(max(availability))
    except Exception as exc:
        issues.append(f"MATERIALIZATION_ERROR:{type(exc).__name__}:{exc}")

    ready = not issues and all(parse_num(row.get(x)) is not None for x in [
        "gold_sma20_over_50", "dxy_ret_20d", "real_yield_change_20d", "etf_flow_tonnes_3m"
    ])
    row["data_quality_pass"] = ready
    lineage = json.dumps({"row": row, "sources": sources}, sort_keys=True, default=str).encode()
    row["source_hash"] = hashlib.sha256(lineage).hexdigest()
    if ready:
        write_history(out, row)

    summary = {
        "stage": STAGE, "generated_utc": utc_iso(generated),
        "status": "STAGE171H_FORWARD_FEATURE_READY" if ready else "STAGE171H_FORWARD_FEATURE_BLOCKED",
        "decision": "USE_FORWARD_FEATURE_SNAPSHOT_FOR_LOG_ONLY_H64L_SHADOW" if ready else "BLOCK_SHADOW_FIX_SOURCE_DATA",
        "order_routing_allowed": False, "demo_release_allowed": False,
        "threshold_reoptimization_allowed": False, "ready": ready,
        "issues": issues, "snapshot": row, "sources": sources,
        "output_dataset": str(out),
    }
    (report / "stage171h_forward_feature_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (report / "stage171h_decision.md").write_text(
        f"# Stage171H H64L Forward Feature Materializer\n\nDecision: `{summary['decision']}`\n\nReady: `{ready}`\n\nIssues: `{issues}`\n\nNo order/demo/live authorization.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
