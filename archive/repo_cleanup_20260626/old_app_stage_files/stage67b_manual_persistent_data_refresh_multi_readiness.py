#!/usr/bin/env python3
"""Stage67B manual persistent data refresh + multi-readiness runner.

Local-only stage. It never downloads from the internet. It ingests user-downloaded
files from ~/Downloads, persistently merges them into canonical local CSVs,
rebuilds the macro feature dataset, and optionally runs Stage66J2.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE67B",
    "NO_INTERNET_DOWNLOAD_FROM_STAGE67B",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DATA_REFRESH_ONLY",
]

DEFAULT_CONFIG = {
    "download_dir": "~/Downloads",
    "manual_sources": {
        "gold_m5": {
            "filename": "amarkets_xauusd_5m.csv",
            "target": "data/manual_sources/amarkets_xauusd_5m_last.csv",
        },
        "dxy": {"filename": "dxy.csv", "target": "data/exogenous/dxy.csv"},
        "real_yield": {"filename": "real_yield.csv", "target": "data/exogenous/real_yield.csv"},
        "vix": {"filename": "vix.csv", "target": "data/exogenous/vix.csv"},
        "etf_flow": {"filename": "etf_flow.csv", "target": "data/exogenous/etf_flow.csv"},
        "central_bank_demand": {
            "filename": "central_bank_demand.csv",
            "target": "data/exogenous/central_bank_demand.csv",
        },
    },
    "canonical_outputs": {
        "external_d1": "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv",
        "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "ledger_csv": "data/forward_shadow/stage67b_manual_persistent_data_refresh_ledger.csv",
    },
    "readiness": {
        "enabled": True,
        "script": "app/stage66j2_multi_readiness_daily_ops.py",
        "config": "configs/stage66j2_multi_readiness_daily_ops.json",
        "out": "reports/stage66j2_multi_readiness_daily_ops",
    },
    "freshness": {"max_macro_lag_days": 7},
    "anti_truncation": {
        "min_existing_retention_ratio": 0.98,
        "stop_if_canonical_rows_drop": True,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_read_csv(path: Path) -> pd.DataFrame:
    last_err: Optional[Exception] = None
    for kwargs in (
        {},
        {"sep": ";"},
        {"sep": "\t"},
        {"encoding": "utf-16"},
        {"encoding": "latin1"},
    ):
        try:
            return pd.read_csv(path, **kwargs)
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_err = exc
    raise RuntimeError(f"could not read csv {path}: {last_err}")


def norm_col(c: str) -> str:
    x = str(c).strip().lower()
    x = x.replace("<", "").replace(">", "")
    x = x.replace("%", "pct")
    for ch in [" ", "-", "/", "\\", ".", "(", ")"]:
        x = x.replace(ch, "_")
    while "__" in x:
        x = x.replace("__", "_")
    return x.strip("_")


def normalize_numeric(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    return pd.to_numeric(
        s.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip()
        .replace({".": None, "": None, "nan": None, "None": None}),
        errors="coerce",
    )


def first_col(cols: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    cols = list(cols)
    for cand in candidates:
        if cand in cols:
            return cand
    return None


def parse_any_date(series: pd.Series) -> pd.Series:
    # Try mixed/dateutil first; then common Investing format.
    out = pd.to_datetime(series, errors="coerce", utc=True)
    if out.notna().sum() == 0:
        out = pd.to_datetime(series, errors="coerce", utc=True, format="%m/%d/%Y")
    if out.notna().sum() == 0:
        out = pd.to_datetime(series, errors="coerce", utc=True, format="%b %d, %Y")
    return out


def read_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return safe_read_csv(path)
    except Exception:
        return pd.DataFrame()


def normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    ncols = {c: norm_col(c) for c in df.columns}
    df = df.rename(columns=ncols)
    date_col = first_col(df.columns, ["date_utc", "feature_date_utc", "date", "datetime", "time", "timestamp"])
    if not date_col:
        raise ValueError(f"date column not found; columns={list(df.columns)}")
    dt = parse_any_date(df[date_col])
    df["date_utc"] = dt.dt.strftime("%Y-%m-%d")
    return df[df["date_utc"].notna()].copy()


def merge_by_date(existing: pd.DataFrame, incoming: pd.DataFrame, key: str = "date_utc") -> pd.DataFrame:
    if existing.empty:
        merged = incoming.copy()
    elif incoming.empty:
        merged = existing.copy()
    else:
        existing = normalize_date_column(existing) if key not in existing.columns else existing.copy()
        incoming = normalize_date_column(incoming) if key not in incoming.columns else incoming.copy()
        # Prefer incoming values for overlapping dates but preserve all historical dates.
        merged = pd.concat([existing, incoming], ignore_index=True, sort=False)
        merged[key] = merged[key].astype(str)
        merged = merged.drop_duplicates(subset=[key], keep="last")
    if key in merged.columns:
        merged = merged.sort_values(key).reset_index(drop=True)
    return merged


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def import_gold_m5_to_d1(source_path: Path, target_path: Path) -> Dict[str, Any]:
    before_hash = sha256_file(target_path)
    existing = read_existing(target_path)
    existing_rows = int(len(existing))
    if not source_path.exists():
        return {"status": "SKIP_MISSING_SOURCE", "source": str(source_path), "target": str(target_path), "rows_existing": existing_rows}

    raw = safe_read_csv(source_path)
    original_columns = list(raw.columns)
    raw = raw.rename(columns={c: norm_col(c) for c in raw.columns})
    cols = list(raw.columns)

    date_col = first_col(cols, ["date", "date_utc"])
    time_col = first_col(cols, ["time", "time_utc"])
    dt_col = first_col(cols, ["datetime", "timestamp", "utc_time", "time_utc"])

    open_col = first_col(cols, ["open", "o"])
    high_col = first_col(cols, ["high", "h"])
    low_col = first_col(cols, ["low", "l"])
    close_col = first_col(cols, ["close", "price", "last", "c"])
    vol_col = first_col(cols, ["tickvol", "tick_volume", "volume", "vol"])
    spread_col = first_col(cols, ["spread"])

    missing = [name for name, col in [("open", open_col), ("high", high_col), ("low", low_col), ("close", close_col)] if col is None]
    if missing:
        return {
            "status": "FAIL",
            "error": f"OHLC columns not found in {source_path}; missing={missing}; columns={original_columns}",
            "source": str(source_path),
            "target": str(target_path),
        }

    if date_col and time_col:
        dt = pd.to_datetime(raw[date_col].astype(str).str.strip() + " " + raw[time_col].astype(str).str.strip(), errors="coerce", utc=True)
    elif dt_col:
        dt = pd.to_datetime(raw[dt_col], errors="coerce", utc=True)
    else:
        return {"status": "FAIL", "error": f"date/time columns not found in {source_path}; columns={original_columns}"}

    df = pd.DataFrame({
        "datetime_utc": dt,
        "open": normalize_numeric(raw[open_col]),
        "high": normalize_numeric(raw[high_col]),
        "low": normalize_numeric(raw[low_col]),
        "close": normalize_numeric(raw[close_col]),
    })
    if vol_col:
        df["volume"] = normalize_numeric(raw[vol_col])
    if spread_col:
        df["spread"] = normalize_numeric(raw[spread_col])
    df = df.dropna(subset=["datetime_utc", "open", "high", "low", "close"])
    if df.empty:
        return {"status": "FAIL", "error": f"no valid OHLC rows after parsing {source_path}"}
    df["date_utc"] = df["datetime_utc"].dt.strftime("%Y-%m-%d")

    agg: Dict[str, Any] = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    if "spread" in df.columns:
        agg["spread"] = "mean"
    d1 = df.sort_values("datetime_utc").groupby("date_utc", as_index=False).agg(agg)
    d1.insert(1, "source", "amarkets_mt5_m5_resampled_d1")

    merged = merge_by_date(existing, d1, key="date_utc")
    after_rows = int(len(merged))
    # Anti-truncation: merge should never reduce canonical rows.
    if existing_rows and after_rows < existing_rows:
        return {"status": "FAIL_ANTI_TRUNCATION", "rows_before": existing_rows, "rows_after": after_rows}
    write_csv(target_path, merged)
    after_hash = sha256_file(target_path)
    return {
        "status": "PASS",
        "source": str(source_path),
        "target": str(target_path),
        "source_rows": int(len(raw)),
        "parsed_m5_rows": int(len(df)),
        "incoming_d1_rows": int(len(d1)),
        "rows_before": existing_rows,
        "rows_after": after_rows,
        "latest_before": latest_date(existing),
        "latest_after": latest_date(merged),
        "hash_before": before_hash,
        "hash_after": after_hash,
        "hash_changed": before_hash != after_hash,
    }


def latest_date(df: pd.DataFrame, col: str = "date_utc") -> Optional[str]:
    if df is None or df.empty or col not in df.columns:
        return None
    vals = pd.to_datetime(df[col], errors="coerce")
    if vals.notna().sum() == 0:
        return None
    return vals.max().strftime("%Y-%m-%d")


def normalize_exogenous(source_path: Path, target_path: Path, series_name: str) -> Dict[str, Any]:
    before_hash = sha256_file(target_path)
    existing = read_existing(target_path)
    existing_rows = int(len(existing))
    if not source_path.exists():
        return {
            "status": "SKIP_MISSING_SOURCE",
            "source": str(source_path),
            "target": str(target_path),
            "exists_existing": target_path.exists(),
            "target_sha256": before_hash,
        }

    raw = safe_read_csv(source_path)
    raw = raw.rename(columns={c: norm_col(c) for c in raw.columns})
    cols = list(raw.columns)
    date_col = first_col(cols, ["date_utc", "date", "observation_date", "datetime", "timestamp"])
    if not date_col:
        return {"status": "FAIL", "error": f"date column not found; columns={list(raw.columns)}", "source": str(source_path)}

    preferred_value_cols = {
        "dxy": ["close", "price", "last", "value", "dxy", "usdollar", "usd_index"],
        "real_yield": ["dfii10", "real_yield", "value", "close", "price"],
        "vix": ["vixcls", "vix", "value", "close", "price"],
        "etf_flow": ["etf_flow_tonnes", "flow_tonnes", "tonnes", "value", "net_flow", "fund_flows_tonnes", "demand"],
        "central_bank_demand": ["central_bank_demand_tonnes", "demand_tonnes", "tonnes", "value", "net_purchases", "change"],
    }.get(series_name, ["value", "close", "price"])
    value_col = first_col(cols, preferred_value_cols)
    if value_col is None:
        # Fallback: first numeric-looking non-date column.
        candidates = [c for c in cols if c != date_col]
        numeric_scores = []
        for c in candidates:
            numeric_scores.append((normalize_numeric(raw[c]).notna().sum(), c))
        numeric_scores.sort(reverse=True)
        value_col = numeric_scores[0][1] if numeric_scores and numeric_scores[0][0] > 0 else None
    if value_col is None:
        return {"status": "FAIL", "error": f"value column not found; columns={list(raw.columns)}", "source": str(source_path)}

    dt = parse_any_date(raw[date_col])
    incoming = pd.DataFrame({"date_utc": dt.dt.strftime("%Y-%m-%d"), series_name: normalize_numeric(raw[value_col])})
    incoming = incoming.dropna(subset=["date_utc", series_name])
    if incoming.empty:
        return {"status": "FAIL", "error": f"no valid rows in {source_path}", "source": str(source_path)}

    if existing.empty:
        existing_norm = pd.DataFrame()
    else:
        existing_norm = normalize_date_column(existing)
        if series_name not in existing_norm.columns:
            # Try to map existing close/value to series_name.
            ecols = list(existing_norm.columns)
            existing_value = first_col(ecols, [series_name, "close", "price", "value"])
            if existing_value and existing_value != series_name:
                existing_norm = existing_norm.rename(columns={existing_value: series_name})
        keep_cols = ["date_utc"] + ([series_name] if series_name in existing_norm.columns else [])
        existing_norm = existing_norm[keep_cols] if series_name in existing_norm.columns else pd.DataFrame()

    merged = merge_by_date(existing_norm, incoming, key="date_utc")
    after_rows = int(len(merged))
    if existing_rows and after_rows < existing_rows:
        return {"status": "FAIL_ANTI_TRUNCATION", "rows_before": existing_rows, "rows_after": after_rows}
    write_csv(target_path, merged)
    after_hash = sha256_file(target_path)
    return {
        "status": "PASS",
        "series": series_name,
        "source": str(source_path),
        "target": str(target_path),
        "source_rows": int(len(raw)),
        "incoming_rows": int(len(incoming)),
        "rows_before": existing_rows,
        "rows_after": after_rows,
        "latest_before": latest_date(existing_norm) if not existing_norm.empty else None,
        "latest_after": latest_date(merged),
        "hash_before": before_hash,
        "hash_after": after_hash,
        "hash_changed": before_hash != after_hash,
    }


def read_series(root: Path, rel_path: str, name: str) -> pd.DataFrame:
    p = root / rel_path
    if not p.exists():
        return pd.DataFrame(columns=["date_utc", name])
    df = normalize_date_column(safe_read_csv(p))
    if name not in df.columns:
        val = first_col(df.columns, [name, "close", "price", "value"])
        if val:
            df = df.rename(columns={val: name})
    if name not in df.columns:
        return pd.DataFrame(columns=["date_utc", name])
    out = df[["date_utc", name]].copy()
    out[name] = normalize_numeric(out[name])
    out = out.dropna(subset=["date_utc", name]).drop_duplicates("date_utc", keep="last")
    return out.sort_values("date_utc")


def rebuild_macro_dataset(root: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    macro_rel = config["canonical_outputs"]["macro_dataset"]
    external_rel = config["canonical_outputs"]["external_d1"]
    macro_path = root / macro_rel
    external_path = root / external_rel
    before_hash = sha256_file(macro_path)
    before = read_existing(macro_path)

    if not external_path.exists():
        return {"status": "FAIL", "error": f"external D1 not found: {external_path}"}
    gold = normalize_date_column(safe_read_csv(external_path))
    if "close" not in gold.columns:
        return {"status": "FAIL", "error": f"gold close column missing in {external_path}"}
    gold = gold[["date_utc", "open", "high", "low", "close"]].copy()
    for c in ["open", "high", "low", "close"]:
        gold[c] = normalize_numeric(gold[c])
    gold = gold.dropna(subset=["date_utc", "close"]).drop_duplicates("date_utc", keep="last")
    gold = gold.sort_values("date_utc").reset_index(drop=True)

    df = gold.rename(columns={"close": "gold_close", "open": "gold_open", "high": "gold_high", "low": "gold_low"})
    paths = config["manual_sources"]
    for name in ["dxy", "real_yield", "vix", "etf_flow", "central_bank_demand"]:
        s = read_series(root, paths[name]["target"], name)
        df = df.merge(s, on="date_utc", how="left")

    df = df.sort_values("date_utc").reset_index(drop=True)
    for name in ["dxy", "real_yield", "vix", "etf_flow", "central_bank_demand"]:
        if name in df.columns:
            df[name] = pd.to_numeric(df[name], errors="coerce").ffill()

    df["feature_date_utc"] = df["date_utc"]
    df["sample_available_after_utc"] = pd.to_datetime(df["date_utc"], utc=True).dt.strftime("%Y-%m-%dT00:00:00Z")
    df["gold_sma20"] = df["gold_close"].rolling(20, min_periods=20).mean()
    df["gold_sma50"] = df["gold_close"].rolling(50, min_periods=50).mean()
    df["gold_sma200"] = df["gold_close"].rolling(200, min_periods=200).mean()
    df["gold_sma20_over_50"] = (df["gold_sma20"] / df["gold_sma50"] - 1.0)
    df["gold_sma50_over_200"] = (df["gold_sma50"] / df["gold_sma200"] - 1.0)

    if "dxy" in df.columns:
        df["dxy_ret_20d"] = df["dxy"].pct_change(20)
        dxy_sma20 = df["dxy"].rolling(20, min_periods=20).mean()
        dxy_sma50 = df["dxy"].rolling(50, min_periods=50).mean()
        df["dxy_sma20_over_50"] = (dxy_sma20 / dxy_sma50 - 1.0)
    if "real_yield" in df.columns:
        df["real_yield_change_20d"] = df["real_yield"].diff(20)
    if "vix" in df.columns:
        df["vix_change_20d"] = df["vix"].diff(20)
    if "etf_flow" in df.columns:
        df["etf_flow_tonnes_3m"] = df["etf_flow"].rolling(63, min_periods=1).sum()
    if "central_bank_demand" in df.columns:
        df["central_bank_demand_tonnes_3m"] = df["central_bank_demand"].rolling(63, min_periods=1).sum()
        df["central_bank_demand_tonnes_6m"] = df["central_bank_demand"].rolling(126, min_periods=1).sum()

    # Preserve any columns from old macro that we do not rebuild, keyed by date.
    if not before.empty:
        try:
            before_norm = normalize_date_column(before)
            before_extra_cols = [c for c in before_norm.columns if c not in df.columns and c != "date_utc"]
            if before_extra_cols:
                df = df.merge(before_norm[["date_utc"] + before_extra_cols], on="date_utc", how="left")
        except Exception:
            pass

    # Sort user-facing canonical columns first.
    preferred = [
        "feature_date_utc", "date_utc", "sample_available_after_utc",
        "gold_open", "gold_high", "gold_low", "gold_close",
        "dxy", "real_yield", "vix", "etf_flow", "central_bank_demand",
        "gold_sma20_over_50", "gold_sma50_over_200", "dxy_ret_20d", "dxy_sma20_over_50",
        "real_yield_change_20d", "vix_change_20d", "etf_flow_tonnes_3m",
        "central_bank_demand_tonnes_3m", "central_bank_demand_tonnes_6m",
    ]
    ordered = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[ordered]

    before_rows = int(len(before))
    after_rows = int(len(df))
    if before_rows and after_rows < before_rows * float(config.get("anti_truncation", {}).get("min_existing_retention_ratio", 0.98)):
        return {
            "status": "FAIL_ANTI_TRUNCATION",
            "rows_before": before_rows,
            "rows_after": after_rows,
            "error": "macro rebuild would materially reduce row count",
        }

    write_csv(macro_path, df)
    after_hash = sha256_file(macro_path)
    series_info = {}
    for name in ["dxy", "real_yield", "vix", "etf_flow", "central_bank_demand"]:
        exists = name in df.columns and df[name].notna().sum() > 0
        coverage_rows = int(df[name].notna().sum()) if name in df.columns else 0
        series_info[name] = {
            "exists": bool(exists),
            "coverage_rows": coverage_rows,
            "coverage_pct": round(100 * coverage_rows / max(len(df), 1), 3),
            "path": str(root / config["manual_sources"][name]["target"]),
        }
    return {
        "status": "PASS",
        "macro_path": str(macro_path),
        "rows_before": before_rows,
        "rows": after_rows,
        "latest_before": latest_date(normalize_date_column(before)) if not before.empty else None,
        "latest_after": latest_date(df),
        "latest_advanced": (latest_date(df) or "") > (latest_date(normalize_date_column(before)) or "") if not before.empty else True,
        "hash_before": before_hash,
        "hash_after": after_hash,
        "hash_changed": before_hash != after_hash,
        "series_info": series_info,
    }


def run_readiness(root: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    rconf = config.get("readiness", {})
    if not rconf.get("enabled", True):
        return {"attempted": False, "status": "DISABLED"}
    script = root / rconf["script"]
    cfg = root / rconf["config"]
    out = root / rconf["out"]
    if not script.exists():
        return {"attempted": False, "status": "SKIP_MISSING_SCRIPT", "script": str(script)}
    cmd = [sys.executable, str(script), "--root", str(root), "--config", str(cfg), "--out", str(out)]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    summary_path = out / "stage66j2_multi_readiness_daily_ops_summary.json"
    summary = None
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary = None
    return {
        "attempted": True,
        "cmd": cmd,
        "returncode": proc.returncode,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "stdout_tail": proc.stdout[-1200:],
        "stderr_tail": proc.stderr[-1200:],
        "summary_found": summary_path.exists(),
        "summary_path": str(summary_path.relative_to(root)) if summary_path.exists() else str(summary_path),
        "summary_decision": summary.get("decision") if isinstance(summary, dict) else None,
        "summary_classification": summary.get("classification") if isinstance(summary, dict) else None,
        "summary_sha256": sha256_file(summary_path),
    }


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dr = summary.get("data_refresh", {})
    rr = summary.get("readiness_run", {})
    lines = [
        "# Stage67B Manual Persistent Data Refresh + Multi-Readiness Runner",
        "",
        "## Decision",
        "",
        f"- status: `{summary.get('status')}`",
        f"- decision: `{summary.get('decision')}`",
        f"- classification: `{summary.get('classification')}`",
        "",
        "## Data refresh",
        "",
        "```json",
        json.dumps(dr, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Readiness runner",
        "",
        "```json",
        json.dumps(rr, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Issues",
        "",
    ]
    issues = summary.get("issues", [])
    if issues:
        lines.extend([f"- `{x}`" for x in issues])
    else:
        lines.append("- none")
    lines.extend(["", "## Hard blocks", ""])
    lines.extend([f"- `{x}`" for x in summary.get("hard_blocks", HARD_BLOCKS)])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_ledger(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "generated_utc": summary.get("generated_utc"),
        "decision": summary.get("decision"),
        "classification": summary.get("classification"),
        "macro_latest": summary.get("data_refresh", {}).get("macro_build", {}).get("latest_after"),
        "gold_status": summary.get("data_refresh", {}).get("gold_import", {}).get("status"),
        "readiness_decision": summary.get("readiness_run", {}).get("summary_decision"),
        "issues": ";".join(summary.get("issues", [])),
    }
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)


def load_config(path: Path) -> Dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    def deep_update(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                deep_update(a[k], v)
            else:
                a[k] = v
        return a
    return deep_update(merged, cfg)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage67b_manual_persistent_data_refresh_multi_readiness.json")
    ap.add_argument("--out", default="reports/stage67b_manual_persistent_data_refresh_multi_readiness")
    ap.add_argument("--force-readiness", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    cfg_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    cfg = load_config(cfg_path)
    download_dir = Path(cfg.get("download_dir", "~/Downloads")).expanduser()

    issues: List[str] = []
    data_refresh: Dict[str, Any] = {"download_dir": str(download_dir), "manual_sources": {}}

    # Gold import first.
    gold_src = download_dir / cfg["manual_sources"]["gold_m5"]["filename"]
    gold_target = root / cfg["canonical_outputs"]["external_d1"]
    gold_result = import_gold_m5_to_d1(gold_src, gold_target)
    data_refresh["gold_import"] = gold_result
    if gold_result.get("status") not in {"PASS", "SKIP_MISSING_SOURCE"}:
        issues.append("GOLD_IMPORT_FAILED")

    # Exogenous imports.
    for name in ["dxy", "real_yield", "vix", "etf_flow", "central_bank_demand"]:
        src = download_dir / cfg["manual_sources"][name]["filename"]
        target = root / cfg["manual_sources"][name]["target"]
        result = normalize_exogenous(src, target, name)
        data_refresh["manual_sources"][name] = result
        if result.get("status") == "FAIL" or str(result.get("status", "")).startswith("FAIL_"):
            issues.append(f"{name.upper()}_IMPORT_FAILED")

    macro_result = rebuild_macro_dataset(root, cfg)
    data_refresh["macro_build"] = macro_result
    if macro_result.get("status") != "PASS":
        issues.append("MACRO_BUILD_FAILED")

    imported_new_data = False
    for res in [gold_result] + list(data_refresh["manual_sources"].values()) + [macro_result]:
        if res.get("hash_changed") or res.get("latest_advanced"):
            imported_new_data = True
    data_refresh["imported_new_data"] = bool(imported_new_data)
    data_refresh["macro_latest"] = macro_result.get("latest_after")

    readiness_run = {"attempted": False, "status": "SKIP_NO_NEW_DATA"}
    if not issues and (imported_new_data or args.force_readiness):
        readiness_run = run_readiness(root, cfg)
        if readiness_run.get("status") != "PASS":
            issues.append("READINESS_RUN_FAILED")
    elif issues and args.force_readiness:
        readiness_run = run_readiness(root, cfg)

    if issues:
        decision = "STAGE67B_STOP_INPUT_OR_REFRESH_FAILURE_NO_ORDER"
        classification = "S67B_STOP"
        status = "STAGE67B_COMPLETE_WITH_ISSUES_NO_PROMOTION"
        rc = 2
    elif not imported_new_data and not args.force_readiness:
        decision = "STAGE67B_NO_NEW_MANUAL_DATA_IMPORTED_NO_FORWARD_READINESS_RUN"
        classification = "S67B_NO_NEW_DATA"
        status = "STAGE67B_COMPLETE_NO_PROMOTION"
        rc = 0
    else:
        rd = readiness_run.get("summary_decision") or "READINESS_NOT_AVAILABLE"
        if rd == "STAGE66J2_ALL_READINESS_WAIT_SIGNALS_NO_ORDER":
            decision = "STAGE67B_REFRESH_COMPLETE_STAGE66J2_ALL_READINESS_WAIT_SIGNALS_NO_ORDER"
        elif "BACKUP_SIGNAL_ACTIVE" in rd:
            decision = "STAGE67B_REFRESH_COMPLETE_STAGE66J2_BACKUP_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER"
        else:
            decision = f"STAGE67B_REFRESH_COMPLETE_{rd}"
        classification = "S67B_REFRESH_COMPLETE"
        status = "STAGE67B_COMPLETE_NO_PROMOTION"
        rc = 0

    summary = {
        "stage": "Stage67B_MANUAL_PERSISTENT_DATA_REFRESH_MULTI_READINESS",
        "status": status,
        "decision": decision,
        "classification": classification,
        "generated_utc": utc_now(),
        "root": str(root),
        "config": str(cfg_path.relative_to(root)) if str(cfg_path).startswith(str(root)) else str(cfg_path),
        "data_refresh": data_refresh,
        "readiness_run": readiness_run,
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str((out_dir / "stage67b_manual_persistent_data_refresh_multi_readiness_summary.json").relative_to(root)) if str(out_dir).startswith(str(root)) else str(out_dir / "stage67b_manual_persistent_data_refresh_multi_readiness_summary.json"),
            "report_md": str((out_dir / "stage67b_manual_persistent_data_refresh_multi_readiness_report.md").relative_to(root)) if str(out_dir).startswith(str(root)) else str(out_dir / "stage67b_manual_persistent_data_refresh_multi_readiness_report.md"),
            "ledger_csv": cfg["canonical_outputs"].get("ledger_csv"),
        },
        "next_step": "If refreshed and all readiness waits, continue manual data refresh cadence. If any dry-run ticket appears, review only; real paper order requires a later explicit authorization package.",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "stage67b_manual_persistent_data_refresh_multi_readiness_summary.json"
    report_path = out_dir / "stage67b_manual_persistent_data_refresh_multi_readiness_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(report_path, summary)
    append_ledger(root / cfg["canonical_outputs"]["ledger_csv"], summary)
    print(json.dumps({"stage": summary["stage"], "status": status, "decision": decision, "classification": classification, "summary_json": str(summary_path), "report_md": str(report_path)}, indent=2, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
