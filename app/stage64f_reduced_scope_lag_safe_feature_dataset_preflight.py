#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from bisect import bisect_right
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage64F_REDUCED_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_NO_VALIDATION"
DEFAULT_STATUS = "LAG_SAFE_FEATURE_DATASET_PREFLIGHT_COMPLETE_NO_PROMOTION"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage64F reduced-scope lag-safe feature dataset preflight; no validation, no signals, no orders.")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="configs/stage64f_reduced_scope_lag_safe_feature_dataset_preflight.json")
    p.add_argument("--out", default="reports/stage64f_reduced_scope_lag_safe_feature_dataset_preflight")
    return p.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def parse_datetime_utc(value: str) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.UTC)
        if "T" in s:
            x = dt.datetime.fromisoformat(s)
            if x.tzinfo is None:
                x = x.replace(tzinfo=dt.UTC)
            return x.astimezone(dt.UTC)
        d = dt.date.fromisoformat(s[:10])
        return dt.datetime(d.year, d.month, d.day, tzinfo=dt.UTC)
    except Exception:
        return None


def parse_date(value: str) -> Optional[dt.date]:
    x = parse_datetime_utc(value)
    if x is None:
        return None
    return x.date()


def iso_date(d: Optional[dt.date]) -> str:
    return d.isoformat() if d else ""


def iso_dt(x: Optional[dt.datetime]) -> str:
    if x is None:
        return ""
    return x.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fnum(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in {".", "nan", "NaN", "None"}:
        return None
    try:
        x = float(s)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b - 1.0


def safe_mean(xs: Iterable[Optional[float]]) -> Optional[float]:
    vals = [x for x in xs if x is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def safe_min(xs: Iterable[float]) -> Optional[float]:
    vals = list(xs)
    return min(vals) if vals else None


def safe_max(xs: Iterable[float]) -> Optional[float]:
    vals = list(xs)
    return max(vals) if vals else None


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def source_check(path: Path, required: List[str], key_cols: List[str]) -> Dict[str, Any]:
    check: Dict[str, Any] = {
        "path": str(path),
        "found": path.exists(),
        "required_columns": required,
        "missing_columns": [],
        "row_count": 0,
        "duplicate_key_count": 0,
        "date_parse_error_count": None,
        "available_after_parse_error_count": None,
        "first_date_utc": None,
        "last_date_utc": None,
        "schema_ok": False,
        "source_ok": False,
        "issues": [],
    }
    if not path.exists():
        check["issues"].append("file missing")
        return check
    try:
        rows = load_csv(path)
    except Exception as e:
        check["issues"].append(f"read error: {e}")
        return check
    check["row_count"] = len(rows)
    cols = list(rows[0].keys()) if rows else []
    missing = [c for c in required if c not in cols]
    check["missing_columns"] = missing
    check["schema_ok"] = not missing
    if missing:
        check["issues"].append("missing columns: " + ",".join(missing))
    if not rows:
        check["issues"].append("no data rows")
        return check
    seen = set()
    dup = 0
    dates: List[dt.date] = []
    date_err = 0
    avail_err = 0
    for r in rows:
        key = tuple(r.get(c, "") for c in key_cols)
        if key in seen:
            dup += 1
        seen.add(key)
        d = parse_date(r.get("date_utc", ""))
        if d is None:
            date_err += 1
        else:
            dates.append(d)
        a = parse_datetime_utc(r.get("available_after_utc", ""))
        if a is None:
            avail_err += 1
    check["duplicate_key_count"] = dup
    check["date_parse_error_count"] = date_err
    check["available_after_parse_error_count"] = avail_err
    if dates:
        check["first_date_utc"] = min(dates).isoformat() + "T00:00:00Z"
        check["last_date_utc"] = max(dates).isoformat() + "T00:00:00Z"
    if dup:
        check["issues"].append(f"duplicate key count: {dup}")
    if date_err:
        check["issues"].append(f"date parse errors: {date_err}")
    if avail_err:
        check["issues"].append(f"available_after_utc parse errors: {avail_err}")
    check["source_ok"] = check["schema_ok"] and len(rows) > 0 and dup == 0 and date_err == 0 and avail_err == 0
    return check


def rolling_mean(values: List[Optional[float]], window: int, idx: int) -> Optional[float]:
    if idx + 1 < window:
        return None
    vals = values[idx - window + 1 : idx + 1]
    if any(v is None for v in vals):
        return None
    return safe_mean(vals)


def enrich_ohlc(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    for r in rows:
        d = parse_date(r.get("date_utc", ""))
        aa = parse_datetime_utc(r.get("available_after_utc", ""))
        op, hi, lo, cl = fnum(r.get("open")), fnum(r.get("high")), fnum(r.get("low")), fnum(r.get("close"))
        if d is None or aa is None or op is None or hi is None or lo is None or cl is None:
            continue
        parsed.append({
            "date": d,
            "available_after": aa,
            "open": op,
            "high": hi,
            "low": lo,
            "close": cl,
            "volume": fnum(r.get("volume")) or 0.0,
            "source": r.get("source", ""),
            "range_pct": (hi - lo) / cl if cl else None,
        })
    parsed.sort(key=lambda x: x["date"])
    closes = [x["close"] for x in parsed]
    ranges = [x["range_pct"] for x in parsed]
    for i, x in enumerate(parsed):
        x["gold_ret_1d"] = pct(closes[i], closes[i - 1]) if i >= 1 else None
        x["gold_ret_5d"] = pct(closes[i], closes[i - 5]) if i >= 5 else None
        x["gold_ret_20d"] = pct(closes[i], closes[i - 20]) if i >= 20 else None
        x["gold_sma20"] = rolling_mean(closes, 20, i)
        x["gold_sma50"] = rolling_mean(closes, 50, i)
        x["gold_sma200"] = rolling_mean(closes, 200, i)
        x["gold_atr14_proxy_pct"] = rolling_mean(ranges, 14, i)
        x["gold_sma20_over_50"] = pct(x["gold_sma20"], x["gold_sma50"]) if x.get("gold_sma20") and x.get("gold_sma50") else None
        x["gold_sma50_over_200"] = pct(x["gold_sma50"], x["gold_sma200"]) if x.get("gold_sma50") and x.get("gold_sma200") else None
    return parsed


def enrich_daily_value(rows: List[Dict[str, str]], value_col: str, prefix: str) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    for r in rows:
        d = parse_date(r.get("date_utc", ""))
        aa = parse_datetime_utc(r.get("available_after_utc", ""))
        val = fnum(r.get(value_col))
        if d is None or aa is None or val is None:
            continue
        parsed.append({
            "date": d,
            "available_after": aa,
            "value": val,
            "source": r.get("source", ""),
            "proxy_method": r.get("proxy_method", ""),
        })
    parsed.sort(key=lambda x: x["date"])
    vals = [x["value"] for x in parsed]
    for i, x in enumerate(parsed):
        x[f"{prefix}_ret_1d"] = pct(vals[i], vals[i - 1]) if i >= 1 else None
        x[f"{prefix}_ret_5d"] = pct(vals[i], vals[i - 5]) if i >= 5 else None
        x[f"{prefix}_ret_20d"] = pct(vals[i], vals[i - 20]) if i >= 20 else None
        x[f"{prefix}_change_5d"] = vals[i] - vals[i - 5] if i >= 5 else None
        x[f"{prefix}_change_20d"] = vals[i] - vals[i - 20] if i >= 20 else None
        x[f"{prefix}_sma20"] = rolling_mean(vals, 20, i)
        x[f"{prefix}_sma50"] = rolling_mean(vals, 50, i)
        x[f"{prefix}_sma20_over_50"] = pct(x.get(f"{prefix}_sma20"), x.get(f"{prefix}_sma50")) if x.get(f"{prefix}_sma20") and x.get(f"{prefix}_sma50") else None
    return parsed


def asof_lookup(series: List[Dict[str, Any]]) -> Tuple[List[dt.datetime], List[Dict[str, Any]]]:
    s = sorted(series, key=lambda x: x["available_after"])
    return [x["available_after"] for x in s], s


def get_asof(times: List[dt.datetime], rows: List[Dict[str, Any]], at: dt.datetime) -> Optional[Dict[str, Any]]:
    idx = bisect_right(times, at) - 1
    if idx < 0:
        return None
    return rows[idx]


def finite_row(row: Dict[str, Any], required_feature_cols: List[str]) -> bool:
    for c in required_feature_cols:
        v = row.get(c)
        if v is None or v == "":
            return False
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return False
    return True


def build_dataset(root: Path, cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw_dir = root / cfg.get("raw_dir", "data/macro_regime/raw")
    files = cfg["source_files"]

    gold = enrich_ohlc(load_csv(raw_dir / files["gold_d1_ohlc"]))
    dxy = enrich_daily_value(load_csv(raw_dir / files["dxy_daily"]), "close", "dxy")
    real_yield = enrich_daily_value(load_csv(raw_dir / files["real_yield_daily"]), "value", "real_yield")
    vix = enrich_daily_value(load_csv(raw_dir / files["vix_daily"]), "close", "vix")

    dxy_t, dxy_rows = asof_lookup(dxy)
    ry_t, ry_rows = asof_lookup(real_yield)
    vix_t, vix_rows = asof_lookup(vix)

    required_feature_cols = cfg.get("required_feature_columns", [
        "gold_ret_20d", "gold_sma20_over_50", "gold_sma50_over_200", "gold_atr14_proxy_pct",
        "dxy_ret_20d", "dxy_sma20_over_50", "real_yield_change_20d", "vix_change_20d", "vix_sma20_over_50"
    ])
    max_asof_lag_days = int(cfg.get("max_asof_lag_days", 10))

    rows: List[Dict[str, Any]] = []
    blocked = {"no_dxy_asof": 0, "no_real_yield_asof": 0, "no_vix_asof": 0, "stale_asof": 0, "insufficient_lookback_or_missing_feature": 0}
    lookahead_violations = 0

    for g in gold:
        at = g["available_after"]
        d = get_asof(dxy_t, dxy_rows, at)
        r = get_asof(ry_t, ry_rows, at)
        v = get_asof(vix_t, vix_rows, at)
        if d is None:
            blocked["no_dxy_asof"] += 1
            continue
        if r is None:
            blocked["no_real_yield_asof"] += 1
            continue
        if v is None:
            blocked["no_vix_asof"] += 1
            continue
        if d["available_after"] > at or r["available_after"] > at or v["available_after"] > at:
            lookahead_violations += 1
            continue
        asof_lags = {
            "dxy_asof_lag_days": (at.date() - d["available_after"].date()).days,
            "real_yield_asof_lag_days": (at.date() - r["available_after"].date()).days,
            "vix_asof_lag_days": (at.date() - v["available_after"].date()).days,
        }
        if any(x > max_asof_lag_days for x in asof_lags.values()):
            blocked["stale_asof"] += 1
            continue

        row: Dict[str, Any] = {
            "feature_date_utc": iso_date(g["date"]),
            "sample_available_after_utc": iso_dt(at),
            "dataset_role": "FEATURES_ONLY_NO_TARGET_NO_SIGNAL_NO_VALIDATION",
            "gold_proxy_source": g.get("source", ""),
            "gold_proxy_date_utc": iso_date(g["date"]),
            "gold_proxy_available_after_utc": iso_dt(g["available_after"]),
            "gold_open": g["open"],
            "gold_high": g["high"],
            "gold_low": g["low"],
            "gold_close": g["close"],
            "gold_volume": g["volume"],
            "gold_range_pct": g["range_pct"],
            "gold_ret_1d": g["gold_ret_1d"],
            "gold_ret_5d": g["gold_ret_5d"],
            "gold_ret_20d": g["gold_ret_20d"],
            "gold_sma20": g["gold_sma20"],
            "gold_sma50": g["gold_sma50"],
            "gold_sma200": g["gold_sma200"],
            "gold_sma20_over_50": g["gold_sma20_over_50"],
            "gold_sma50_over_200": g["gold_sma50_over_200"],
            "gold_atr14_proxy_pct": g["gold_atr14_proxy_pct"],
            "dxy_source": d.get("source", ""),
            "dxy_date_utc": iso_date(d["date"]),
            "dxy_available_after_utc": iso_dt(d["available_after"]),
            "dxy_close": d["value"],
            "dxy_ret_5d": d.get("dxy_ret_5d"),
            "dxy_ret_20d": d.get("dxy_ret_20d"),
            "dxy_sma20_over_50": d.get("dxy_sma20_over_50"),
            "real_yield_source": r.get("source", ""),
            "real_yield_proxy_method": r.get("proxy_method", ""),
            "real_yield_date_utc": iso_date(r["date"]),
            "real_yield_available_after_utc": iso_dt(r["available_after"]),
            "real_yield_value": r["value"],
            "real_yield_change_5d": r.get("real_yield_change_5d"),
            "real_yield_change_20d": r.get("real_yield_change_20d"),
            "vix_source": v.get("source", ""),
            "vix_date_utc": iso_date(v["date"]),
            "vix_available_after_utc": iso_dt(v["available_after"]),
            "vix_close": v["value"],
            "vix_change_5d": v.get("vix_change_5d"),
            "vix_change_20d": v.get("vix_change_20d"),
            "vix_sma20_over_50": v.get("vix_sma20_over_50"),
            **asof_lags,
        }
        if not finite_row(row, required_feature_cols):
            blocked["insufficient_lookback_or_missing_feature"] += 1
            continue
        rows.append(row)

    diagnostics = {
        "raw_rows": {"gold": len(gold), "dxy": len(dxy), "real_yield": len(real_yield), "vix": len(vix)},
        "blocked_rows": blocked,
        "lookahead_violations": lookahead_violations,
        "required_feature_columns": required_feature_cols,
        "max_asof_lag_days": max_asof_lag_days,
    }
    return rows, diagnostics


def split_coverage(rows: List[Dict[str, Any]], splits: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out = []
    dates = [parse_date(r["feature_date_utc"]) for r in rows]
    dates = [d for d in dates if d]
    for s in splits:
        start = dt.date.fromisoformat(s["start"])
        end = dt.date.fromisoformat(s["end"])
        cnt = sum(1 for d in dates if start <= d <= end)
        out.append({
            "split_id": s["split_id"],
            "start": s["start"],
            "end": s["end"],
            "row_count": cnt,
            "ready": cnt >= int(s.get("min_rows", 200)),
            "min_rows": int(s.get("min_rows", 200)),
        })
    return out


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    cfg_path = root / args.config
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_json(cfg_path)
    generated = utc_now_iso()
    normalized_path = root / cfg.get("normalized_output", "data/macro_regime/normalized/stage64f_reduced_scope_lag_safe_feature_dataset.csv")
    manifest_path = root / cfg.get("dataset_manifest_output", "data/macro_regime/manifests/stage64f_lag_safe_feature_dataset_manifest.json")

    source_files = cfg["source_files"]
    raw_dir = root / cfg.get("raw_dir", "data/macro_regime/raw")
    source_checks = []
    source_specs = {
        "gold_d1_ohlc": (["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc"], ["date_utc", "source"]),
        "dxy_daily": (["date_utc", "close", "source", "available_after_utc"], ["date_utc", "source"]),
        "real_yield_daily": (["date_utc", "value", "source", "available_after_utc", "proxy_method"], ["date_utc", "source", "proxy_method"]),
        "vix_daily": (["date_utc", "close", "source", "available_after_utc"], ["date_utc", "source"]),
    }
    for key, (required, key_cols) in source_specs.items():
        c = source_check(raw_dir / source_files[key], required, key_cols)
        c["source_key"] = key
        source_checks.append(c)

    if not all(c["source_ok"] for c in source_checks):
        decision = "BLOCK_STAGE64F_UNTIL_REDUCED_SCOPE_RAW_SOURCES_PASS_PREFLIGHT_NO_VALIDATION"
        rows: List[Dict[str, Any]] = []
        diagnostics = {"source_blocked": True}
        splits = []
    else:
        rows, diagnostics = build_dataset(root, cfg)
        write_csv(normalized_path, rows)
        splits = split_coverage(rows, cfg.get("validation_splits", []))
        min_dataset_rows = int(cfg.get("min_dataset_rows", 2500))
        split_ok = all(x["ready"] for x in splits) if splits else False
        dataset_ok = len(rows) >= min_dataset_rows and split_ok and diagnostics.get("lookahead_violations", 1) == 0
        decision = "LAG_SAFE_FEATURE_DATASET_PREFLIGHT_PASS_STAGE64G_DESIGN_ALLOWED_NO_VALIDATION" if dataset_ok else "BLOCK_STAGE64G_UNTIL_FEATURE_DATASET_PREFLIGHT_PASSES_NO_VALIDATION"

    dataset_stats: Dict[str, Any] = {
        "row_count": len(rows),
        "first_feature_date_utc": rows[0]["feature_date_utc"] + "T00:00:00Z" if rows else None,
        "last_feature_date_utc": rows[-1]["feature_date_utc"] + "T00:00:00Z" if rows else None,
        "normalized_output": str(normalized_path),
        "dataset_manifest_output": str(manifest_path),
        "target_columns_present": [],
        "signal_columns_present": [],
        "validation_columns_present": [],
    }

    source_warning = "Gold D1 source is COMEX continuous futures reference if source contains GC_F; dataset must remain proxy/reference only until broker/spot D1 is acquired."
    manifest = {
        "stage": STAGE,
        "generated_utc": generated,
        "dataset_role": "FEATURES_ONLY_NO_TARGET_NO_SIGNAL_NO_VALIDATION",
        "scope_id": cfg.get("scope_id", "P0_PLUS_VIX_NO_ETF_NO_CENTRAL_BANK_NO_EVENT_CALENDAR"),
        "normalized_output": str(normalized_path),
        "source_files": {k: str(raw_dir / v) for k, v in source_files.items()},
        "source_checks": source_checks,
        "dataset_stats": dataset_stats,
        "diagnostics": diagnostics,
        "split_coverage": splits,
        "source_warnings": [source_warning],
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_HISTORICAL_VALIDATION_SCAN_IN_STAGE64F",
            "NO_TARGET_OR_SIGNAL_COLUMNS_IN_STAGE64F",
        ],
    }
    if rows:
        write_json(manifest_path, manifest)

    source_checks_csv = out_dir / "stage64f_source_checks.csv"
    split_csv = out_dir / "stage64f_split_coverage.csv"
    write_csv(source_checks_csv, source_checks)
    write_csv(split_csv, splits, ["split_id", "start", "end", "row_count", "min_rows", "ready"])

    summary = {
        "stage": STAGE,
        "status": DEFAULT_STATUS,
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed": False,
        "generated_utc": generated,
        "root": str(root),
        "inputs": {
            "config": str(cfg_path),
            "stage64e_summary": str(root / cfg.get("stage64e_summary", "reports/stage64e_reduced_scope_predeclaration/stage64e_reduced_scope_predeclaration_summary.json")),
        },
        "source_checks_ok": all(c.get("source_ok") for c in source_checks),
        "dataset_stats": dataset_stats,
        "split_coverage": splits,
        "diagnostics": diagnostics,
        "source_warnings": [source_warning],
        "next_allowed_step": "Stage64G_WALK_FORWARD_VALIDATION_DESIGN_NO_SCAN" if decision.startswith("LAG_SAFE_FEATURE_DATASET_PREFLIGHT_PASS") else "FIX_STAGE64F_FEATURE_DATASET_PREFLIGHT_BLOCKERS_NO_VALIDATION",
        "hard_blocks": manifest["hard_blocks"],
        "outputs": {
            "normalized_dataset_csv": str(normalized_path),
            "dataset_manifest_json": str(manifest_path),
            "source_checks_csv": str(source_checks_csv),
            "split_coverage_csv": str(split_csv),
            "summary_json": str(out_dir / "stage64f_reduced_scope_lag_safe_feature_dataset_preflight_summary.json"),
            "report_md": str(out_dir / "stage64f_reduced_scope_lag_safe_feature_dataset_preflight_report.md"),
        },
    }
    write_json(out_dir / "stage64f_reduced_scope_lag_safe_feature_dataset_preflight_summary.json", summary)

    report_path = out_dir / "stage64f_reduced_scope_lag_safe_feature_dataset_preflight_report.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Stage64F - Reduced-Scope Lag-Safe Feature Dataset Preflight\n\n")
        f.write(f"Generated UTC: `{generated}`\n\n")
        f.write("## Status\n\n")
        f.write(f"- status: `{DEFAULT_STATUS}`\n")
        f.write(f"- decision: `{decision}`\n")
        f.write("- validation_allowed: `false`\n")
        f.write("- promotion/paper/live: `NO_GO`\n\n")
        f.write("## Executive conclusion\n\n")
        if decision.startswith("LAG_SAFE_FEATURE_DATASET_PREFLIGHT_PASS"):
            f.write("The reduced-scope P0+VIX raw sources were converted into a lag-safe feature-only dataset. No target, signal, validation, order, or promotion path is authorized. The next stage may specify a walk-forward validation design, but not run a validation scan yet.\n\n")
        else:
            f.write("The reduced-scope feature dataset preflight did not pass. No validation design or scan is authorized until blockers are fixed.\n\n")
        f.write("## Dataset stats\n\n")
        for k, v in dataset_stats.items():
            f.write(f"- {k}: `{v}`\n")
        f.write("\n## Source checks\n\n")
        f.write("| source_key | found | rows | first | last | source_ok | issues |\n")
        f.write("|---|---:|---:|---|---|---:|---|\n")
        for c in source_checks:
            f.write(f"| `{c.get('source_key')}` | {c.get('found')} | {c.get('row_count')} | {c.get('first_date_utc')} | {c.get('last_date_utc')} | {c.get('source_ok')} | {'; '.join(c.get('issues') or [])} |\n")
        f.write("\n## Split coverage\n\n")
        f.write("| split_id | start | end | rows | min_rows | ready |\n")
        f.write("|---|---|---|---:|---:|---:|\n")
        for s in splits:
            f.write(f"| `{s['split_id']}` | {s['start']} | {s['end']} | {s['row_count']} | {s['min_rows']} | {s['ready']} |\n")
        f.write("\n## Lag-safety statement\n\n")
        f.write("For each gold feature date, external DXY, real-yield, and VIX rows are selected only if their `available_after_utc` is less than or equal to the gold sample `available_after_utc`. Stage64F reports lookahead violations and blocks the next stage if any are found.\n\n")
        f.write("## Source warning\n\n")
        f.write(f"- {source_warning}\n\n")
        f.write("## Operational decision\n\n")
        f.write("No historical validation scan, signal generation, paper-order, paper-live, live, EA promotion, or broker connection is authorized by Stage64F.\n")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
