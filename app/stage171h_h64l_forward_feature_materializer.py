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

STAGE = "Stage171H5_H64L_FORWARD_FEATURE_MATERIALIZER_ETF_SEMANTICS_FIXED"
DEFAULT_OUT = "data/forward_shadow/h64l_forward_feature_snapshots.csv"
DEFAULT_REPORT = "reports/stage171h_h64l_forward_feature_materializer"
DEFAULT_ATTEMPT_LEDGER = "data/forward_shadow/h64l_forward_feature_attempts.csv"
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
        "dxy": ["dxy", "dollar_index", "dtwex", "dx_f", "usdx"],
        "real_yield": ["real_yield", "realyield", "dfii10", "dfii5"],
    }[kind]
    roots = [root / "data", inbox]
    out: List[Path] = []
    excluded_tokens = {
        "_repair_backups", "/archive/", "\\archive\\", "backup", "inactive",
        "stage64k", "forward_shadow", "/reports/", "\\reports\\",
    }
    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".csv", ".json"}:
                continue
            try:
                low = p.relative_to(base).as_posix().lower()
            except Exception:
                low = p.name.lower()
            if any(bad in low for bad in excluded_tokens):
                continue
            if any(t in low for t in tokens):
                out.append(p)
    return sorted(set(out))


def source_priority(root: Path, inbox: Path, path: Path, kind: str) -> int:
    """Prefer canonical active outputs, then normalized/raw active data, never backups."""
    preferred = {
        "dxy": [
            root / "data/exogenous/dxy.csv",
            root / "data/macro_regime/raw/dxy_daily_2011_present.csv",
            root / "data/fundamental_event_inbox/normalized/dxy_reference_normalized.csv",
        ],
        "real_yield": [
            root / "data/exogenous/real_yield.csv",
            root / "data/macro_regime/raw/real_yield_or_proxy_daily_2011_present.csv",
        ],
    }[kind]
    rp = path.resolve()
    for idx, candidate in enumerate(preferred):
        try:
            if rp == candidate.resolve():
                return 100 - idx * 10
        except Exception:
            pass
    low = str(path).lower()
    if "/normalized/" in low or "\\normalized\\" in low:
        return 60
    if "/raw/" in low or "\\raw\\" in low:
        return 50
    if path.parent == inbox:
        return 40
    return 20



def source_contract(path: Path, kind: str, value_col: Optional[str] = None) -> str:
    """Classify source identity without silently substituting a different index."""
    if kind != "dxy":
        return "REAL_YIELD_SERIES"
    low = path.as_posix().lower()
    vc = (value_col or "").strip().lower()
    if "dtwex" in low or vc in {"dtwexbgs", "dtwexafegs"}:
        return "BROAD_TRADE_WEIGHTED_USD_PROXY_NOT_DXY"
    if any(x in low for x in ["stooq_dx_f", "dx.f", "dx_f", "usdx", "dxy"]):
        return "DXY_OR_ICE_USDX_FUTURES_SERIES"
    return "UNKNOWN_DOLLAR_SERIES"


def parse_date_series(values: pd.Series) -> pd.Series:
    raw = values.astype(str).str.strip()
    out = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns, UTC]")
    ymd = raw.str.fullmatch(r"\d{8}")
    if ymd.any():
        out.loc[ymd] = pd.to_datetime(raw.loc[ymd], format="%Y%m%d", errors="coerce", utc=True)
    rest = ~ymd
    if rest.any():
        out.loc[rest] = pd.to_datetime(raw.loc[rest], errors="coerce", utc=True)
    return out.dt.floor("D")


def content_block_reason(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")[:8192].strip().lower()
    except Exception as exc:
        return f"READ_ERROR:{type(exc).__name__}"
    if not text:
        return "EMPTY_FILE"
    blockers = {
        "<html": "HTML_RESPONSE_NOT_CSV",
        "<!doctype": "HTML_RESPONSE_NOT_CSV",
        "too many requests": "RATE_LIMIT_RESPONSE_NOT_CSV",
        "exceeded the daily hits": "RATE_LIMIT_RESPONSE_NOT_CSV",
        "access denied": "ACCESS_DENIED_RESPONSE_NOT_CSV",
        "cloudflare": "BOT_PROTECTION_RESPONSE_NOT_CSV",
        "no data": "NO_DATA_RESPONSE",
    }
    for token, reason in blockers.items():
        if token in text:
            return reason
    return None


def read_csv_robust(path: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    blocked = content_block_reason(path)
    if blocked:
        return None, blocked
    attempts = []
    for kwargs in [
        {"sep": detect_sep(path), "low_memory": False},
        {"sep": None, "engine": "python"},
    ]:
        try:
            df = pd.read_csv(path, **kwargs)
            attempts.append(df)
        except Exception:
            pass
    # Stooq exports can occasionally arrive without a header.
    try:
        raw = pd.read_csv(path, sep=detect_sep(path), header=None, low_memory=False)
        if raw.shape[1] in {5, 6, 7}:
            names = ["Date", "Open", "High", "Low", "Close", "Volume", "OpenInt"][:raw.shape[1]]
            raw.columns = names
            attempts.append(raw)
    except Exception:
        pass
    if not attempts:
        return None, "CSV_PARSE_FAILED"
    # Prefer a frame that exposes a recognizable date and close/value column.
    for df in attempts:
        lower = {str(c).strip().lower() for c in df.columns}
        if any(x in lower for x in {"date", "timestamp", "observation_date", "date_utc", "<date>"}) and any(x in lower for x in {"close", "value", "dxy", "dtwexbgs", "dfii10", "dfii5", "<close>"}):
            return df, None
    return attempts[0], None

def normalize_series_frame(df: pd.DataFrame, path: Path, kind: str) -> Optional[pd.DataFrame]:
    if df.empty:
        return None
    lower = {str(c).strip().lower(): c for c in df.columns}
    date_names = ["timestamp", "date", "<date>", "observation_date", "time", "datetime", "date_utc", "feature_date_utc"]
    date_col = next((lower[x] for x in date_names if x in lower), None)
    if date_col is None:
        date_col = next((c for c in df.columns if "date" in str(c).lower() or "time" in str(c).lower()), None)
    if date_col is None:
        return None
    preferred = (["dxy", "close", "<close>", "value", "dtwexbgs", "dtwexafegs"] if kind == "dxy"
                 else ["real_yield", "close", "<close>", "value", "dfii10", "dfii5"])
    value_col = next((lower[x] for x in preferred if x in lower), None)
    if value_col is None:
        numeric_candidates = [c for c in df.columns if c != date_col and pd.to_numeric(df[c], errors="coerce").notna().sum() >= 20]
        if len(numeric_candidates) == 1:
            value_col = numeric_candidates[0]
    if value_col is None:
        return None
    out = pd.DataFrame({
        "date": parse_date_series(df[date_col]),
        "value": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna().sort_values("date").drop_duplicates("date", keep="last")
    if len(out) < 25:
        return None
    out.attrs.update({"path": str(path), "date_col": str(date_col), "value_col": str(value_col), "source_contract": source_contract(path, kind, str(value_col))})
    return out


def load_series_file(path: Path, kind: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    try:
        if path.suffix.lower() == ".csv":
            df, reason = read_csv_robust(path)
            if df is None:
                return None, reason or "CSV_PARSE_FAILED"
            out = normalize_series_frame(df, path, kind)
            return (out, None) if out is not None else (None, "SCHEMA_OR_ROWS_INVALID")
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            out = normalize_series_frame(pd.DataFrame(obj), path, kind)
            return (out, None) if out is not None else (None, "SCHEMA_OR_ROWS_INVALID")
        if isinstance(obj, dict):
            for key in ["observations", "data", "series", "results"]:
                if isinstance(obj.get(key), list):
                    out = normalize_series_frame(pd.DataFrame(obj[key]), path, kind)
                    return (out, None) if out is not None else (None, "SCHEMA_OR_ROWS_INVALID")
    except Exception as exc:
        return None, f"LOAD_ERROR:{type(exc).__name__}:{exc}"
    return None, "UNSUPPORTED_FILE_STRUCTURE"


def choose_series(root: Path, inbox: Path, kind: str, cutoff: pd.Timestamp) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    # Freshness is the primary key. Canonical active-path priority only breaks ties.
    options: List[Tuple[Tuple[float, int, int], pd.DataFrame, Dict[str, Any]]] = []
    diagnostics: List[Dict[str, Any]] = []
    for path in candidate_files(root, inbox, kind):
        s, load_reason = load_series_file(path, kind)
        if s is None:
            diagnostics.append({"path": str(path), "usable": False, "reason": load_reason or "SCHEMA_OR_ROWS_INVALID"})
            continue
        contract = str(s.attrs.get("source_contract") or source_contract(path, kind, str(s.attrs.get("value_col") or "")))
        if kind == "dxy" and contract == "BROAD_TRADE_WEIGHTED_USD_PROXY_NOT_DXY":
            diagnostics.append({"path": str(path), "usable": False, "reason": "BROAD_DOLLAR_PROXY_NOT_EXACT_DXY", "source_contract": contract})
            continue
        usable = s[s["date"] <= cutoff].copy()
        if len(usable) < 21:
            diagnostics.append({"path": str(path), "usable": False, "reason": "LT_21_OBSERVATIONS", "rows": int(len(usable))})
            continue
        latest = usable.iloc[-1]["date"]
        priority = source_priority(root, inbox, path, kind)
        diag = {
            "path": str(path), "usable": True, "rows": int(len(usable)),
            "latest_date_utc": latest.date().isoformat(), "source_priority": priority, "source_contract": contract,
        }
        diagnostics.append(diag)
        score = (latest.timestamp(), priority, int(len(usable)))
        options.append((score, usable, diag))
    if not options:
        raise ValueError(f"No valid active exact {kind} series with >=21 observations through {cutoff.date()}")
    options.sort(key=lambda x: x[0], reverse=True)
    s = options[0][1]
    selected = options[0][2]
    meta = {
        "path": s.attrs.get("path"), "date_col": s.attrs.get("date_col"),
        "value_col": s.attrs.get("value_col"), "rows": int(len(s)),
        "latest_date_utc": s.iloc[-1]["date"].date().isoformat(),
        "latest_value": float(s.iloc[-1]["value"]),
        "selection_policy": "LATEST_DATE_THEN_ACTIVE_SOURCE_PRIORITY_THEN_ROWS",
        "selected_source_priority": selected["source_priority"],
        "source_contract": str(s.attrs.get("source_contract") or source_contract(Path(str(s.attrs.get("path"))), kind, str(s.attrs.get("value_col") or ""))),
        "candidate_diagnostics": sorted(diagnostics, key=lambda x: str(x.get("path"))),
    }
    return s, meta


def _is_fund_holding_key(name: Any) -> bool:
    low = str(name).strip().lower()
    return "equity" in low or low.endswith(" equity")


def _resolve_wgc_holdings_records(records: Sequence[Dict[str, Any]], path: Path) -> Optional[pd.DataFrame]:
    """Resolve global holdings by reconciling candidate totals to fund-level sums.

    WGC's multi-row spreadsheet header can normalize the gold-price column as
    "All units in tonnes unless otherwise specified" while the actual global
    holdings total appears as an unnamed/col_3 field. We therefore never trust
    that ambiguous label. A candidate total must reconcile to the sum of the
    fund-level holdings columns across many monthly rows.
    """
    rows: List[Dict[str, Any]] = []
    for obj in records:
        d = obj.get("ticker") or obj.get("date") or obj.get("Date") or obj.get("month")
        if d is None:
            continue
        fund_values = [parse_num(v) for k, v in obj.items() if _is_fund_holding_key(k)]
        fund_values = [v for v in fund_values if v is not None]
        if len(fund_values) < 5:
            continue
        row: Dict[str, Any] = {"date": d, "fund_sum": float(sum(fund_values))}
        for k, v in obj.items():
            if k in {"ticker", "date", "Date", "month"} or _is_fund_holding_key(k):
                continue
            x = parse_num(v)
            if x is not None:
                row[str(k)] = x
        rows.append(row)
    if len(rows) < 12:
        return None
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True).dt.floor("D")
    frame = frame.dropna(subset=["date", "fund_sum"]).sort_values("date").drop_duplicates("date", keep="last")
    candidates: List[Tuple[float, float, int, str]] = []
    for c in frame.columns:
        if c in {"date", "fund_sum"}:
            continue
        x = pd.to_numeric(frame[c], errors="coerce")
        valid = x.notna() & frame["fund_sum"].notna() & (frame["fund_sum"] > 0)
        if int(valid.sum()) < 12:
            continue
        rel = ((x[valid] - frame.loc[valid, "fund_sum"]).abs() / frame.loc[valid, "fund_sum"]).replace([math.inf, -math.inf], pd.NA).dropna()
        if rel.empty:
            continue
        candidates.append((float(rel.median()), float(rel.quantile(0.90)), int(valid.sum()), str(c)))
    if not candidates:
        return None
    candidates.sort(key=lambda z: (z[0], z[1], -z[2], z[3]))
    median_rel, p90_rel, coverage, selected = candidates[0]
    # The total should equal the sum of fund holdings to rounding/coverage noise.
    if median_rel > 0.02 or p90_rel > 0.05:
        return None
    out = pd.DataFrame({
        "date": frame["date"],
        "holdings": pd.to_numeric(frame[selected], errors="coerce"),
        "fund_sum": frame["fund_sum"],
    }).dropna().sort_values("date").drop_duplicates("date", keep="last")
    if len(out) < 12:
        return None
    if not out["holdings"].between(10.0, 10000.0).all():
        return None
    out.attrs.update({
        "path": str(path),
        "holdings_column": selected,
        "resolver": "FUND_SUM_RECONCILIATION",
        "median_fund_sum_relative_error": median_rel,
        "p90_fund_sum_relative_error": p90_rel,
        "reconciliation_rows": coverage,
    })
    return out


def _records_from_frame(df: pd.DataFrame) -> List[Dict[str, Any]]:
    return [{str(k): v for k, v in row.items()} for row in df.to_dict(orient="records")]


def extract_wgc_series_from_normalized(path: Path) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path, sep=detect_sep(path), low_memory=False)
    except Exception:
        return None
    # Direct extracted sheet: reconcile totals to fund-level holdings.
    direct = _resolve_wgc_holdings_records(_records_from_frame(df), path)
    if direct is not None:
        return direct
    # Normalized rows with embedded JSON payload.
    sheet_col = next((c for c in df.columns if "sheet" in str(c).lower()), None)
    json_cols = [c for c in df.columns if "json" in str(c).lower() or "raw" in str(c).lower()]
    records: List[Dict[str, Any]] = []
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
            if isinstance(obj, dict):
                records.append(obj)
                break
    return _resolve_wgc_holdings_records(records, path)


def extract_wgc_series_from_excel(path: Path) -> Optional[pd.DataFrame]:
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return None
    for sheet in xl.sheet_names:
        if "holdings" not in sheet.lower() or "month" not in sheet.lower():
            continue
        for header in range(0, 10):
            try:
                df = pd.read_excel(path, sheet_name=sheet, header=header)
            except Exception:
                continue
            s = _resolve_wgc_holdings_records(_records_from_frame(df), path)
            if s is not None:
                return s
    return None


def _load_stage173_canonical_etf(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception:
        return None
    lower = {str(c).strip().lower(): c for c in df.columns}
    dc = lower.get("date_utc") or lower.get("date")
    hc = lower.get("holdings_tonnes") or lower.get("holdings")
    if dc is None or hc is None:
        return None
    out = pd.DataFrame({
        "date": pd.to_datetime(df[dc], errors="coerce", utc=True).dt.floor("D"),
        "holdings": pd.to_numeric(df[hc], errors="coerce"),
    }).dropna().sort_values("date").drop_duplicates("date", keep="last")
    if len(out) < 12 or not out["holdings"].between(10.0, 10000.0).all():
        return None
    out.attrs.update({"path": str(path), "holdings_column": str(hc), "resolver": "STAGE173_CANONICAL_SERIES"})
    return out


def choose_etf_series(root: Path, inbox: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    canonical = root / "data/macro_regime/normalized/wgc_global_etf_holdings_monthly_stage173.csv"
    options: List[Tuple[Tuple[float, int, int], pd.DataFrame, Path]] = []
    c = _load_stage173_canonical_etf(canonical)
    if c is not None:
        options.append(((c.iloc[-1]["date"].timestamp(), 10**18, len(c)), c, canonical))
    candidates: List[Path] = []
    for base in [root / "data", inbox]:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".csv", ".xlsx"}:
                low = str(p).lower()
                if ("wgc" in low or "etf_flows" in low or "etf-flows" in low) and ("etf" in low or "holdings" in low):
                    candidates.append(p)
    for p in sorted(set(candidates)):
        s = extract_wgc_series_from_excel(p) if p.suffix.lower() == ".xlsx" else extract_wgc_series_from_normalized(p)
        if s is None or len(s) < 12:
            continue
        latest = s.iloc[-1]["date"]
        options.append(((latest.timestamp(), p.stat().st_mtime, len(s)), s, p))
    if not options:
        raise ValueError("No fund-sum-reconciled WGC total ETF holdings-by-month series found")
    options.sort(key=lambda x: x[0], reverse=True)
    s, p = options[0][1], options[0][2]
    latest = s.iloc[-1]
    target = latest["date"] - pd.DateOffset(months=3)
    prior = s[s["date"] <= target]
    if prior.empty:
        raise ValueError("WGC series lacks a 3-month prior observation")
    prior_row = prior.iloc[-1]
    flow = float(latest["holdings"] - prior_row["holdings"])
    if abs(flow) > 500.0:
        raise ValueError(f"WGC 3-month holdings change fails plausibility bound: {flow:.3f}t")
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
        "holdings_column": s.attrs.get("holdings_column"),
        "resolver": s.attrs.get("resolver"),
        "median_fund_sum_relative_error": s.attrs.get("median_fund_sum_relative_error"),
        "p90_fund_sum_relative_error": s.attrs.get("p90_fund_sum_relative_error"),
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


def append_attempt(path: Path, generated_utc: str, ready: bool, issues: Sequence[str], row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["generated_utc", "feature_date_utc", "ready", "issues"] + SNAPSHOT_FIELDS[1:]
    exists = path.exists() and path.stat().st_size > 0
    payload = {"generated_utc": generated_utc, "feature_date_utc": row.get("feature_date_utc", ""),
               "ready": ready, "issues": ";".join(issues)}
    payload.update({k: row.get(k, "") for k in SNAPSHOT_FIELDS[1:]})
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow(payload)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="~/Desktop/xauusd-trader")
    ap.add_argument("--inbox", default="~/Downloads/xauusd_fundamental_event_inbox")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--report-dir", default=DEFAULT_REPORT)
    ap.add_argument("--attempt-ledger", default=DEFAULT_ATTEMPT_LEDGER)
    ap.add_argument("--max-gold-age-days", type=float, default=4.0)
    ap.add_argument("--max-macro-age-days", type=float, default=7.0)
    ap.add_argument("--max-etf-source-age-days", type=float, default=60.0)
    ap.add_argument("--max-abs-etf-flow-tonnes", type=float, default=500.0)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    inbox = Path(args.inbox).expanduser().resolve()
    out = resolve(root, args.out)
    report = resolve(root, args.report_dir)
    attempt_ledger = resolve(root, args.attempt_ledger)
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
    append_attempt(attempt_ledger, utc_iso(generated), ready, issues, row)
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
        "attempt_ledger": str(attempt_ledger),
        "output_written": bool(ready),
    }
    (report / "stage171h_forward_feature_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (report / "stage171h_decision.md").write_text(
        f"# Stage171H5 H64L Forward Feature Materializer — ETF Semantics Fixed\n\nDecision: `{summary['decision']}`\n\nReady: `{ready}`\n\nIssues: `{issues}`\n\nNo order/demo/live authorization.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
