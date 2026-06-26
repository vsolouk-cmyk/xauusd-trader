#!/usr/bin/env python3
"""
Stage64D - Macro-Regime Data Contract and Loader Audit

Report-only audit for the Stage64 Daily/Weekly Macro-Regime Gold Thesis.
No state mutation, no order generation, no promotion path.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ISO_Z = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime(ISO_Z)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: scalar_to_csv(row.get(k)) for k in fieldnames})


def scalar_to_csv(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return v


def parse_datetime_any(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s
    # Unix timestamp support if field is purely numeric and plausible.
    try:
        if s.replace(".", "", 1).isdigit():
            num = float(s)
            if num > 1_000_000_000:
                return dt.datetime.fromtimestamp(num, tz=dt.timezone.utc)
    except Exception:
        pass
    candidates = [
        s2,
        s2.replace("/", "-"),
    ]
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
    ]
    for cand in candidates:
        for fmt in formats:
            try:
                parsed = dt.datetime.strptime(cand, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                else:
                    parsed = parsed.astimezone(dt.timezone.utc)
                return parsed
            except ValueError:
                continue
    try:
        parsed = dt.datetime.fromisoformat(s2)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        else:
            parsed = parsed.astimezone(dt.timezone.utc)
        return parsed
    except Exception:
        return None


def iso_or_none(x: Optional[dt.datetime]) -> Optional[str]:
    if x is None:
        return None
    return x.astimezone(dt.timezone.utc).strftime(ISO_Z)


def years_between(start: Optional[dt.datetime], end: Optional[dt.datetime]) -> Optional[float]:
    if start is None or end is None or end < start:
        return None
    return round((end - start).days / 365.25, 3)


def detect_delimiter(path: Path) -> str:
    try:
        sample = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except Exception:
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except Exception:
        if "\t" in sample:
            return "\t"
        if ";" in sample:
            return ";"
        return ","


def audit_csv_file(path: Path, name: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "source_id": name,
        "path": str(path),
        "found": path.exists(),
        "file_size": None,
        "row_count_sampled": 0,
        "row_count_full": None,
        "columns": [],
        "timestamp_column": None,
        "first_time_utc": None,
        "last_time_utc": None,
        "coverage_years": None,
        "numeric_columns": [],
        "status": "MISSING",
        "error": None,
    }
    if not path.exists():
        return result
    result["file_size"] = path.stat().st_size
    delim = detect_delimiter(path)
    first: Optional[dt.datetime] = None
    last: Optional[dt.datetime] = None
    timestamp_col: Optional[str] = None
    numeric_counts: Dict[str, int] = {}
    rows = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f, delimiter=delim)
            fieldnames = list(reader.fieldnames or [])
            result["columns"] = fieldnames
            candidates = [
                "utc_time", "time_utc", "datetime_utc", "timestamp_utc", "timestamp", "datetime", "date", "time", "Date", "DATE", "Time", "TIME"
            ]
            # If separate date/time columns exist, handle that first.
            date_cols = [c for c in fieldnames if c.lower() in {"date", "day"}]
            time_cols = [c for c in fieldnames if c.lower() in {"time", "hour"}]
            for row in reader:
                rows += 1
                parsed: Optional[dt.datetime] = None
                if date_cols and time_cols:
                    parsed = parse_datetime_any(str(row.get(date_cols[0], "")) + " " + str(row.get(time_cols[0], "")))
                    if parsed is not None:
                        timestamp_col = f"{date_cols[0]}+{time_cols[0]}"
                if parsed is None:
                    for c in candidates:
                        if c in row:
                            parsed = parse_datetime_any(row.get(c))
                            if parsed is not None:
                                timestamp_col = c
                                break
                if parsed is not None:
                    first = parsed if first is None or parsed < first else first
                    last = parsed if last is None or parsed > last else last
                for k, v in row.items():
                    if v is None:
                        continue
                    s = str(v).strip().replace(",", "")
                    if not s:
                        continue
                    try:
                        float(s)
                        numeric_counts[k] = numeric_counts.get(k, 0) + 1
                    except Exception:
                        pass
            result["row_count_full"] = rows
            result["row_count_sampled"] = rows
            result["timestamp_column"] = timestamp_col
            result["first_time_utc"] = iso_or_none(first)
            result["last_time_utc"] = iso_or_none(last)
            result["coverage_years"] = years_between(first, last)
            result["numeric_columns"] = [k for k, v in numeric_counts.items() if v >= max(1, rows // 10)]
            result["status"] = "OK" if rows > 0 else "EMPTY"
    except Exception as exc:
        result["status"] = "ERROR"
        result["error"] = repr(exc)
    return result


def sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()]


def quote_ident(x: str) -> str:
    return '"' + x.replace('"', '""') + '"'


def audit_broker_sqlite(db_path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "source_id": "broker_normalized_sqlite",
        "path": str(db_path),
        "found": db_path.exists(),
        "schema_ok": False,
        "tables": [],
        "bars_table": None,
        "columns": [],
        "time_column": None,
        "timeframe_column": None,
        "symbol_column": None,
        "source_column": None,
        "timeframe_inventory": [],
        "derived_daily_coverage_from_best_intraday": None,
        "status": "MISSING",
        "error": None,
    }
    if not db_path.exists():
        return out
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        tables = sqlite_tables(conn)
        out["tables"] = tables
        bars_table = "bars" if "bars" in tables else (tables[0] if tables else None)
        out["bars_table"] = bars_table
        if not bars_table:
            out["status"] = "ERROR"
            out["error"] = "no sqlite tables found"
            return out
        cols = table_columns(conn, bars_table)
        out["columns"] = cols
        time_col = next((c for c in ["utc_time", "time_utc", "timestamp_utc", "datetime_utc", "timestamp", "time"] if c in cols), None)
        timeframe_col = next((c for c in ["timeframe", "tf", "interval"] if c in cols), None)
        symbol_col = next((c for c in ["symbol", "ticker"] if c in cols), None)
        source_col = next((c for c in ["source", "feed"] if c in cols), None)
        out.update({"time_column": time_col, "timeframe_column": timeframe_col, "symbol_column": symbol_col, "source_column": source_col})
        if not time_col:
            out["status"] = "ERROR"
            out["error"] = "no recognized time column"
            return out
        out["schema_ok"] = True
        if timeframe_col:
            q = f"SELECT {quote_ident(timeframe_col)} AS timeframe, COUNT(*) AS n, MIN({quote_ident(time_col)}) AS first_t, MAX({quote_ident(time_col)}) AS last_t FROM {quote_ident(bars_table)} GROUP BY {quote_ident(timeframe_col)} ORDER BY n DESC"
            rows = conn.execute(q).fetchall()
        else:
            q = f"SELECT 'UNKNOWN' AS timeframe, COUNT(*) AS n, MIN({quote_ident(time_col)}) AS first_t, MAX({quote_ident(time_col)}) AS last_t FROM {quote_ident(bars_table)}"
            rows = conn.execute(q).fetchall()
        inv = []
        for r in rows:
            first = parse_datetime_any(r["first_t"])
            last = parse_datetime_any(r["last_t"])
            inv.append({
                "timeframe": r["timeframe"],
                "rows": int(r["n"]),
                "first_time_utc": iso_or_none(first),
                "last_time_utc": iso_or_none(last),
                "coverage_years": years_between(first, last),
            })
        out["timeframe_inventory"] = inv
        # Prefer H1 for D1/W1 derivation, then M30, M15, M5, M1.
        priority = ["H1", "1H", "M30", "30M", "M15", "15M", "M5", "5M", "M1", "1M"]
        best = None
        for tf in priority:
            best = next((x for x in inv if str(x.get("timeframe", "")).upper() == tf), None)
            if best:
                break
        if best is None and inv:
            best = inv[0]
        out["derived_daily_coverage_from_best_intraday"] = best
        out["status"] = "OK"
    except Exception as exc:
        out["status"] = "ERROR"
        out["error"] = repr(exc)
    finally:
        try:
            conn.close()  # type: ignore[name-defined]
        except Exception:
            pass
    return out


def load_feature_contract(root: Path, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = []
    for key in ["feature_contract_json", "feature_contract_csv"]:
        val = config.get("inputs", {}).get(key)
        if val:
            candidates.append(root / val)
    candidates.extend([
        root / "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_feature_contract.json",
        root / "reports/stage64c_macro_regime_gold_thesis_spec/stage64c_macro_regime_feature_contract.csv",
    ])
    for path in candidates:
        if path.suffix.lower() == ".json" and path.exists():
            data = read_json(path, [])
            if isinstance(data, dict):
                if "features" in data and isinstance(data["features"], list):
                    return data["features"]
                if "rows" in data and isinstance(data["rows"], list):
                    return data["rows"]
            if isinstance(data, list):
                return data
        if path.suffix.lower() == ".csv" and path.exists():
            with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
                return list(csv.DictReader(f))
    return default_feature_contract()


def default_feature_contract() -> List[Dict[str, Any]]:
    return [
        {"feature_id": "gold_d1_trend", "source_type": "broker_ohlcv", "timeframe": "D1", "role": "timing_filter", "minimum_history": "5y", "lag_policy": "bar_close_only"},
        {"feature_id": "gold_w1_trend", "source_type": "broker_ohlcv", "timeframe": "W1", "role": "regime_filter", "minimum_history": "10y_preferred", "lag_policy": "week_close_only"},
        {"feature_id": "dxy_trend_acceleration", "source_type": "external_market", "timeframe": "D1/W1", "role": "macro_pressure", "minimum_history": "10y_preferred", "lag_policy": "published_or_session_close_available"},
        {"feature_id": "real_yield_or_proxy", "source_type": "macro_rate", "timeframe": "D1/W1", "role": "opportunity_cost_pressure", "minimum_history": "10y_preferred", "lag_policy": "publication_lag_respected"},
        {"feature_id": "etf_flow_divergence", "source_type": "ETF_flow_or_holdings", "timeframe": "D1/W1", "role": "flow_confirmation_or_divergence", "minimum_history": "5y_preferred", "lag_policy": "next_session_after_publication"},
        {"feature_id": "central_bank_demand_regime", "source_type": "official_or_wgc_monthly_quarterly", "timeframe": "M/Q", "role": "slow_regime_prior", "minimum_history": "10y_preferred", "lag_policy": "release_lag_explicit_no_lookahead"},
        {"feature_id": "volatility_regime", "source_type": "gold_range_or_vix_proxy", "timeframe": "D1/W1", "role": "sizing_and_entry_quality", "minimum_history": "5y", "lag_policy": "bar_close_only"},
        {"feature_id": "event_calendar_risk", "source_type": "macro_calendar", "timeframe": "event", "role": "entry_suppression_or_risk_filter", "minimum_history": "event_archive_if_available", "lag_policy": "known_before_event_only"},
    ]


def required_years(min_history: str) -> Optional[float]:
    s = str(min_history or "").lower()
    if "10" in s:
        return 10.0
    if "5" in s:
        return 5.0
    return None


def source_mapping(config: Dict[str, Any]) -> Dict[str, Any]:
    return config.get("source_mapping", {})


def feature_source_ids(feature_id: str, mapping: Dict[str, Any]) -> List[str]:
    val = mapping.get(feature_id, [])
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        return [str(x) for x in val]
    return []


def evaluate_feature(feature: Dict[str, Any], broker_audit: Dict[str, Any], csv_audits: Dict[str, Dict[str, Any]], mapping: Dict[str, Any]) -> Dict[str, Any]:
    fid = str(feature.get("feature_id", ""))
    source_type = str(feature.get("source_type", ""))
    lag_policy = str(feature.get("lag_policy", ""))
    min_hist = str(feature.get("minimum_history", ""))
    req_years = required_years(min_hist)
    ids = feature_source_ids(fid, mapping)
    source_status = "MISSING"
    coverage_years: Optional[float] = None
    first_time = None
    last_time = None
    source_details: List[Dict[str, Any]] = []
    lag_status = "NEEDS_MANUAL_CONFIRMATION"
    loader_status = "BLOCK_VALIDATION"
    issues: List[str] = []

    if source_type == "broker_ohlcv" or fid.startswith("gold_"):
        source_details.append({"source_id": "broker_normalized_sqlite", "status": broker_audit.get("status"), "detail": broker_audit.get("derived_daily_coverage_from_best_intraday")})
        best = broker_audit.get("derived_daily_coverage_from_best_intraday") or {}
        coverage_years = best.get("coverage_years")
        first_time = best.get("first_time_utc")
        last_time = best.get("last_time_utc")
        source_status = "OK" if broker_audit.get("status") == "OK" else broker_audit.get("status", "ERROR")
        if lag_policy in {"bar_close_only", "week_close_only"}:
            lag_status = "MECHANICALLY_ENFORCEABLE_FROM_BARS"
        if coverage_years is None:
            issues.append("broker coverage unknown")
        elif req_years is not None and coverage_years < req_years:
            issues.append(f"history below minimum: {coverage_years}y < {req_years}y")
    else:
        if not ids:
            issues.append("no source mapping configured")
        for sid in ids:
            aud = csv_audits.get(sid)
            if aud:
                source_details.append(aud)
        present = [x for x in source_details if x.get("found") and x.get("status") == "OK"]
        if present:
            source_status = "OK"
            firsts = [parse_datetime_any(x.get("first_time_utc")) for x in present]
            lasts = [parse_datetime_any(x.get("last_time_utc")) for x in present]
            firsts2 = [x for x in firsts if x]
            lasts2 = [x for x in lasts if x]
            first = min(firsts2) if firsts2 else None
            last = max(lasts2) if lasts2 else None
            first_time, last_time = iso_or_none(first), iso_or_none(last)
            coverage_years = years_between(first, last)
            if coverage_years is None:
                issues.append("timestamp coverage not parsed")
            elif req_years is not None and coverage_years < req_years:
                issues.append(f"history below minimum: {coverage_years}y < {req_years}y")
        else:
            source_status = "MISSING"
            issues.append("mapped source files missing or not readable")
        # Lag status by policy. Some policies are source dependent.
        if lag_policy in {"bar_close_only", "week_close_only"}:
            lag_status = "MECHANICALLY_ENFORCEABLE_FROM_BARS"
        elif lag_policy in {"published_or_session_close_available", "publication_lag_respected", "next_session_after_publication", "release_lag_explicit_no_lookahead", "known_before_event_only"}:
            lag_status = "REQUIRES_SOURCE_TIMESTAMP_OR_EXPLICIT_RELEASE_LAG"
            # If timestamp columns exist but no release timestamp, still not enough.
            issues.append("lag policy requires explicit release/availability timestamp audit")
        else:
            issues.append("unknown lag policy")

    if source_status == "OK" and not issues:
        loader_status = "READY_FOR_REGIME_JOIN_AUDIT"
    elif source_status == "OK":
        loader_status = "SOURCE_PRESENT_BUT_BLOCKED_BY_COVERAGE_OR_LAG"
    else:
        loader_status = "BLOCK_VALIDATION"

    return {
        "feature_id": fid,
        "source_type": source_type,
        "timeframe": feature.get("timeframe"),
        "role": feature.get("role"),
        "minimum_history": min_hist,
        "required_years": req_years,
        "lag_policy": lag_policy,
        "mapped_sources": ids if ids else (["broker_normalized_sqlite"] if source_type == "broker_ohlcv" or fid.startswith("gold_") else []),
        "source_status": source_status,
        "coverage_years": coverage_years,
        "first_time_utc": first_time,
        "last_time_utc": last_time,
        "lag_status": lag_status,
        "loader_status": loader_status,
        "issues": issues,
        "source_details_count": len(source_details),
    }


def build_validation_split_audit(feature_rows: List[Dict[str, Any]], splits: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for split in splits:
        sid = split["split_id"]
        start = parse_datetime_any(split["start"])
        end = parse_datetime_any(split["end"])
        available_features = 0
        blocking_features: List[str] = []
        for f in feature_rows:
            first = parse_datetime_any(f.get("first_time_utc"))
            last = parse_datetime_any(f.get("last_time_utc"))
            ok = first is not None and last is not None and start is not None and end is not None and first <= start and last >= end and f.get("loader_status") == "READY_FOR_REGIME_JOIN_AUDIT"
            if ok:
                available_features += 1
            else:
                blocking_features.append(str(f.get("feature_id")))
        rows.append({
            "split_id": sid,
            "start": split["start"],
            "end": split["end"],
            "ready_feature_count": available_features,
            "total_feature_count": len(feature_rows),
            "all_features_ready": available_features == len(feature_rows),
            "blocking_features": blocking_features,
        })
    return rows


def markdown_table(rows: List[Dict[str, Any]], cols: List[str]) -> str:
    if not rows:
        return ""
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---" for _ in cols]) + "|"]
    for r in rows:
        vals = []
        for c in cols:
            v = r.get(c, "")
            if isinstance(v, list):
                v = ", ".join(map(str, v))
            vals.append(str(v).replace("|", "\\|"))
        out.append("| " + " | ".join(vals) + " |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage64d_macro_regime_data_contract_loader_audit.json")
    ap.add_argument("--out", default="reports/stage64d_macro_regime_data_contract_loader_audit")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = read_json(cfg_path, default={}) or {}

    feature_contract = load_feature_contract(root, config)
    mapping = source_mapping(config)
    db_rel = config.get("inputs", {}).get("broker_db", "data/broker_normalized/amarkets_multitf.sqlite")
    broker_audit = audit_broker_sqlite(root / db_rel)

    csv_audits: Dict[str, Dict[str, Any]] = {}
    for sid, rel in (config.get("source_files", {}) or {}).items():
        csv_audits[str(sid)] = audit_csv_file(root / str(rel), str(sid))

    inventory_rows: List[Dict[str, Any]] = []
    inventory_rows.append({
        "source_id": "broker_normalized_sqlite",
        "source_type": "sqlite_bars",
        "path": broker_audit.get("path"),
        "found": broker_audit.get("found"),
        "status": broker_audit.get("status"),
        "rows_or_tables": json.dumps(broker_audit.get("timeframe_inventory"), ensure_ascii=False),
        "first_time_utc": (broker_audit.get("derived_daily_coverage_from_best_intraday") or {}).get("first_time_utc"),
        "last_time_utc": (broker_audit.get("derived_daily_coverage_from_best_intraday") or {}).get("last_time_utc"),
        "coverage_years": (broker_audit.get("derived_daily_coverage_from_best_intraday") or {}).get("coverage_years"),
        "error": broker_audit.get("error"),
    })
    for sid, aud in csv_audits.items():
        inventory_rows.append({
            "source_id": sid,
            "source_type": "csv",
            "path": aud.get("path"),
            "found": aud.get("found"),
            "status": aud.get("status"),
            "rows_or_tables": aud.get("row_count_full"),
            "first_time_utc": aud.get("first_time_utc"),
            "last_time_utc": aud.get("last_time_utc"),
            "coverage_years": aud.get("coverage_years"),
            "error": aud.get("error"),
        })

    feature_rows = [evaluate_feature(f, broker_audit, csv_audits, mapping) for f in feature_contract]
    splits = config.get("validation_splits", [
        {"split_id": "2011_2015", "start": "2011-01-01", "end": "2015-12-31"},
        {"split_id": "2016_2019", "start": "2016-01-01", "end": "2019-12-31"},
        {"split_id": "2020_2022", "start": "2020-01-01", "end": "2022-12-31"},
        {"split_id": "2023_present", "start": "2023-01-01", "end": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")},
    ])
    split_rows = build_validation_split_audit(feature_rows, splits)

    ready_features = [r for r in feature_rows if r.get("loader_status") == "READY_FOR_REGIME_JOIN_AUDIT"]
    blocked_features = [r for r in feature_rows if r.get("loader_status") != "READY_FOR_REGIME_JOIN_AUDIT"]
    lag_blocked = [r for r in feature_rows if "REQUIRES" in str(r.get("lag_status")) or any("lag" in str(x).lower() for x in r.get("issues", []))]
    coverage_blocked = [r for r in feature_rows if any("history below" in str(x) for x in r.get("issues", []))]
    missing_features = [r for r in feature_rows if r.get("source_status") == "MISSING"]
    validation_ready = len(blocked_features) == 0 and all(x.get("all_features_ready") for x in split_rows)

    if validation_ready:
        decision = "DATA_CONTRACT_READY_FOR_HISTORICAL_REGIME_VALIDATION_NO_ORDER"
        next_step = "Stage64E_HISTORICAL_REGIME_VALIDATION_DESIGN_NO_ORDER"
    else:
        decision = "BLOCK_HISTORICAL_VALIDATION_UNTIL_DATA_LAG_AND_COVERAGE_GAPS_FIXED_NO_ORDER"
        next_step = "Stage64D2_MACRO_REGIME_DATA_GAP_REMEDIATION_PLAN_NO_ORDER"

    outputs = {
        "inventory_csv": "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_macro_regime_data_inventory.csv",
        "inventory_json": "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_macro_regime_data_inventory.json",
        "feature_lag_audit_csv": "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_feature_lag_policy_audit.csv",
        "feature_lag_audit_json": "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_feature_lag_policy_audit.json",
        "validation_split_audit_csv": "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_validation_split_coverage_audit.csv",
        "validation_split_audit_json": "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_validation_split_coverage_audit.json",
        "summary_json": "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_macro_regime_data_contract_loader_audit_summary.json",
        "report_md": "reports/stage64d_macro_regime_data_contract_loader_audit/stage64d_macro_regime_data_contract_loader_audit_report.md",
    }

    write_csv(out_dir / "stage64d_macro_regime_data_inventory.csv", inventory_rows)
    write_json(out_dir / "stage64d_macro_regime_data_inventory.json", inventory_rows)
    write_csv(out_dir / "stage64d_feature_lag_policy_audit.csv", feature_rows)
    write_json(out_dir / "stage64d_feature_lag_policy_audit.json", feature_rows)
    write_csv(out_dir / "stage64d_validation_split_coverage_audit.csv", split_rows)
    write_json(out_dir / "stage64d_validation_split_coverage_audit.json", split_rows)

    summary = {
        "stage": "Stage64D_MACRO_REGIME_DATA_CONTRACT_AND_LOADER_AUDIT_NO_PROMOTION",
        "status": "DATA_CONTRACT_LOADER_AUDIT_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "mutation_mode": "report_only_no_state_mutation",
        "generated_utc": utc_now(),
        "root": str(root),
        "config": str(cfg_path),
        "out": str(out_dir),
        "counts": {
            "feature_contract_rows": len(feature_rows),
            "ready_features": len(ready_features),
            "blocked_features": len(blocked_features),
            "missing_features": len(missing_features),
            "lag_blocked_features": len(lag_blocked),
            "coverage_blocked_features": len(coverage_blocked),
            "validation_splits": len(split_rows),
            "validation_ready_splits": sum(1 for x in split_rows if x.get("all_features_ready")),
        },
        "broker_audit": broker_audit,
        "feature_status_summary": {
            "ready_feature_ids": [x["feature_id"] for x in ready_features],
            "blocked_feature_ids": [x["feature_id"] for x in blocked_features],
            "missing_feature_ids": [x["feature_id"] for x in missing_features],
            "lag_blocked_feature_ids": [x["feature_id"] for x in lag_blocked],
            "coverage_blocked_feature_ids": [x["feature_id"] for x in coverage_blocked],
        },
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_HISTORICAL_VALIDATION_SCAN_UNTIL_STAGE64D_DATA_CONTRACT_READY",
        ],
        "next_allowed_step": next_step,
        "outputs": outputs,
    }
    write_json(out_dir / "stage64d_macro_regime_data_contract_loader_audit_summary.json", summary)

    report_lines = [
        "# Stage64D - Macro-Regime Data Contract and Loader Audit",
        "",
        f"Generated UTC: `{summary['generated_utc']}`",
        "",
        "## Status",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{decision}`",
        "- promotion: `NO_GO`",
        "- paper_order: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "- mutation_mode: `report_only_no_state_mutation`",
        "",
        "## Executive conclusion",
        "",
    ]
    if validation_ready:
        report_lines.append("The macro-regime data contract is ready for the next no-order historical regime-validation design stage.")
    else:
        report_lines.append("The macro-regime data contract is not ready for historical validation. Data availability, explicit lag policy, or split coverage gaps must be remediated first.")
    report_lines.extend([
        "",
        "## Counts",
        "",
        markdown_table([summary["counts"]], list(summary["counts"].keys())),
        "",
        "## Feature lag and coverage audit",
        "",
        markdown_table(feature_rows, ["feature_id", "source_status", "coverage_years", "lag_status", "loader_status", "issues"]),
        "",
        "## Data inventory",
        "",
        markdown_table(inventory_rows, ["source_id", "found", "status", "rows_or_tables", "first_time_utc", "last_time_utc", "coverage_years", "error"]),
        "",
        "## Validation split coverage",
        "",
        markdown_table(split_rows, ["split_id", "start", "end", "ready_feature_count", "total_feature_count", "all_features_ready", "blocking_features"]),
        "",
        "## Operational decision",
        "",
        "No paper-order, paper-live, live, EA promotion, or historical validation scan is authorized by this audit unless all data-contract and lag-policy blockers are cleared.",
        "",
        "## Next allowed step",
        "",
        f"`{next_step}`",
        "",
    ])
    (out_dir / "stage64d_macro_regime_data_contract_loader_audit_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    print(json.dumps({"stage": summary["stage"], "status": summary["status"], "decision": decision, "counts": summary["counts"], "out": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
