#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from bisect import bisect_right
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage64K_FULL_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_NO_VALIDATION"
NO_GO = "NO_GO"

FORBIDDEN_COLUMN_FRAGMENTS = [
    "target",
    "signal",
    "entry",
    "exit",
    "pnl",
    "return_fwd",
    "future",
    "label",
    "prediction",
    "validation",
    "outcome",
]

BASE_REQUIRED_FEATURES = [
    "gold_ret_20d",
    "gold_sma20_over_50",
    "gold_sma50_over_200",
    "gold_atr14_proxy_pct",
    "dxy_ret_20d",
    "dxy_sma20_over_50",
    "real_yield_change_20d",
    "vix_change_20d",
    "vix_sma20_over_50",
]

FULL_SCOPE_FEATURES = [
    "etf_flow_tonnes_1m",
    "etf_flow_tonnes_3m",
    "etf_flow_tonnes_6m",
    "etf_flow_tonnes_12m",
    "central_bank_demand_tonnes_1m",
    "central_bank_demand_tonnes_3m",
    "central_bank_demand_tonnes_6m",
    "central_bank_demand_tonnes_12m",
    "event_calendar_forward_only_governance_active",
]


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC)
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day, tzinfo=dt.UTC)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    # Keep only date part if the input is a plain yyyy-mm-dd.
    try:
        x = dt.datetime.fromisoformat(s)
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.UTC)
        return x.astimezone(dt.UTC)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            d = dt.datetime.strptime(str(value).strip(), fmt)
            return d.replace(tzinfo=dt.UTC)
        except Exception:
            continue
    return None


def iso_z(x: Optional[dt.datetime]) -> str:
    if x is None:
        return ""
    return x.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_date(x: Optional[dt.datetime]) -> str:
    if x is None:
        return ""
    return x.astimezone(dt.UTC).date().isoformat()


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        v = float(s)
    except Exception:
        return None
    if not math.isfinite(v):
        return None
    return v


def read_csv_dicts(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def write_csv_dicts(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_column(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    cols = list(columns)
    lower_map = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def derive_sample_available(feature_dt: dt.datetime, warnings: List[str]) -> dt.datetime:
    # Conservative daily-bar close availability when Stage64F did not preserve an explicit availability column.
    if "sample_available_after_utc_missing_derived_from_feature_date_plus_one_day" not in warnings:
        warnings.append("sample_available_after_utc_missing_derived_from_feature_date_plus_one_day")
    return dt.datetime.combine(feature_dt.date() + dt.timedelta(days=1), dt.time(0, 0), tzinfo=dt.UTC)


def rolling_sum(values: List[Optional[float]], idx: int, window: int) -> Optional[float]:
    start = max(0, idx - window + 1)
    vals = [v for v in values[start: idx + 1] if v is not None]
    if len(vals) < min(window, idx + 1):
        return None
    return sum(vals)


def rolling_z(values: List[Optional[float]], idx: int, window: int) -> Optional[float]:
    if idx < window:
        return None
    hist = [v for v in values[idx - window: idx] if v is not None]
    current = values[idx]
    if current is None or len(hist) < max(6, window // 2):
        return None
    sd = pstdev(hist)
    if sd == 0:
        return None
    return (current - mean(hist)) / sd


def aggregate_etf_rows(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        d = parse_dt(r.get("date_utc"))
        available = parse_dt(r.get("available_after_utc"))
        v = to_float(r.get("holdings_tonnes_or_flow"))
        if d is None or available is None or v is None:
            continue
        key = d.date().isoformat()
        g = grouped.setdefault(key, {"period_dt": d, "available_dt": available, "sum": 0.0, "fund_count": 0})
        g["sum"] += v
        g["fund_count"] += 1
        if available > g["available_dt"]:
            g["available_dt"] = available
    base = sorted(grouped.values(), key=lambda x: x["period_dt"])
    sums = [x["sum"] for x in base]
    out: List[Dict[str, Any]] = []
    for i, x in enumerate(base):
        rec = dict(x)
        rec["flow_1m"] = rolling_sum(sums, i, 1)
        rec["flow_3m"] = rolling_sum(sums, i, 3)
        rec["flow_6m"] = rolling_sum(sums, i, 6)
        rec["flow_12m"] = rolling_sum(sums, i, 12)
        rec["flow_12m_z36"] = rolling_z(sums, i, 36)
        out.append(rec)
    diag = {
        "raw_rows": len(rows),
        "monthly_periods": len(out),
        "first_period": iso_date(out[0]["period_dt"]) if out else None,
        "last_period": iso_date(out[-1]["period_dt"]) if out else None,
    }
    return out, diag


def aggregate_central_bank_rows(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    base = []
    for r in rows:
        pstart = parse_dt(r.get("period_start"))
        pend = parse_dt(r.get("period_end"))
        available = parse_dt(r.get("available_after_utc"))
        release = parse_dt(r.get("release_date_utc"))
        v = to_float(r.get("demand_value"))
        if pstart is None or pend is None or available is None or v is None:
            continue
        base.append({
            "period_dt": pstart,
            "period_end_dt": pend,
            "release_dt": release,
            "available_dt": available,
            "demand": v,
        })
    base.sort(key=lambda x: x["period_dt"])
    vals = [x["demand"] for x in base]
    out: List[Dict[str, Any]] = []
    for i, x in enumerate(base):
        rec = dict(x)
        rec["demand_1m"] = rolling_sum(vals, i, 1)
        rec["demand_3m"] = rolling_sum(vals, i, 3)
        rec["demand_6m"] = rolling_sum(vals, i, 6)
        rec["demand_12m"] = rolling_sum(vals, i, 12)
        rec["demand_12m_z36"] = rolling_z(vals, i, 36)
        out.append(rec)
    diag = {
        "raw_rows": len(rows),
        "monthly_periods": len(out),
        "first_period": iso_date(out[0]["period_dt"]) if out else None,
        "last_period": iso_date(out[-1]["period_dt"]) if out else None,
    }
    return out, diag


def asof_record(records: List[Dict[str, Any]], available_times: List[dt.datetime], sample_available: dt.datetime) -> Optional[Dict[str, Any]]:
    idx = bisect_right(available_times, sample_available) - 1
    if idx < 0:
        return None
    return records[idx]


def date_in_range(date_s: str, start: str, end: str) -> bool:
    return start <= date_s[:10] <= end


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage64K full-scope lag-safe feature dataset preflight. No validation/no order.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_json(cfg_path)

    generated = utc_now_iso()
    warnings: List[str] = []
    issues: List[str] = []

    j5_path = root / cfg["inputs"]["stage64j5_summary"]
    j5 = load_json(j5_path)
    if not j5.get("event_calendar_governance_decision", {}).get("accepted_for_stage64k"):
        issues.append("Stage64J5 did not accept event-calendar forward-only governance for Stage64K")
    if not j5.get("p1_full_scope_sources_preflight_ok"):
        issues.append("Stage64J5 did not mark ETF and central-bank P1 sources as preflight OK")

    feature_path = root / cfg["inputs"]["stage64f_feature_dataset"]
    etf_path = root / cfg["inputs"]["gold_etf_source"]
    cb_path = root / cfg["inputs"]["central_bank_source"]

    feature_rows, feature_cols = read_csv_dicts(feature_path)
    etf_rows, etf_cols = read_csv_dicts(etf_path)
    cb_rows, cb_cols = read_csv_dicts(cb_path)

    date_col = find_column(feature_cols, cfg.get("feature_date_columns", [])) or "feature_date_utc"
    avail_col = find_column(feature_cols, cfg.get("feature_available_after_columns", []))
    if date_col not in feature_cols:
        issues.append(f"feature date column not found. tried={cfg.get('feature_date_columns', [])}")

    missing_base = [c for c in BASE_REQUIRED_FEATURES if c not in feature_cols]
    if missing_base:
        issues.append("missing Stage64F base feature columns: " + ";".join(missing_base))

    forbidden_existing = [c for c in feature_cols if any(frag in c.lower() for frag in FORBIDDEN_COLUMN_FRAGMENTS)]
    if forbidden_existing:
        issues.append("Stage64F dataset already contains forbidden target/signal/validation-like columns: " + ";".join(forbidden_existing))

    etf_records, etf_diag = aggregate_etf_rows(etf_rows)
    cb_records, cb_diag = aggregate_central_bank_rows(cb_rows)
    etf_available = [x["available_dt"] for x in etf_records]
    cb_available = [x["available_dt"] for x in cb_records]

    if not etf_records:
        issues.append("no aggregate ETF records created")
    if not cb_records:
        issues.append("no aggregate central-bank records created")

    normalized_rows: List[Dict[str, Any]] = []
    lookahead_violations = 0
    no_etf_asof = 0
    no_cb_asof = 0
    stale_etf = 0
    stale_cb = 0
    insufficient_monthly_lookback = 0
    parse_feature_date_errors = 0

    max_etf_lag_days = int(cfg.get("max_etf_asof_lag_days", 370))
    max_cb_lag_days = int(cfg.get("max_central_bank_asof_lag_days", 460))

    for r in feature_rows:
        fdt = parse_dt(r.get(date_col))
        if fdt is None:
            parse_feature_date_errors += 1
            continue
        if avail_col and r.get(avail_col):
            sample_avail = parse_dt(r.get(avail_col))
        else:
            sample_avail = None
        if sample_avail is None:
            sample_avail = derive_sample_available(fdt, warnings)

        er = asof_record(etf_records, etf_available, sample_avail)
        cr = asof_record(cb_records, cb_available, sample_avail)
        if er is None:
            no_etf_asof += 1
            continue
        if cr is None:
            no_cb_asof += 1
            continue
        if er["available_dt"] > sample_avail or cr["available_dt"] > sample_avail:
            lookahead_violations += 1
            continue

        etf_lag = (sample_avail.date() - er["period_dt"].date()).days
        cb_lag = (sample_avail.date() - cr["period_dt"].date()).days
        if etf_lag > max_etf_lag_days:
            stale_etf += 1
            continue
        if cb_lag > max_cb_lag_days:
            stale_cb += 1
            continue

        required_monthly_values = [er.get("flow_12m"), cr.get("demand_12m")]
        if any(v is None for v in required_monthly_values):
            insufficient_monthly_lookback += 1
            continue

        out = dict(r)
        out["full_scope_feature_date_utc"] = iso_z(fdt)
        out["sample_available_after_utc"] = iso_z(sample_avail)
        out["etf_period_date_utc"] = iso_z(er["period_dt"])
        out["etf_available_after_utc"] = iso_z(er["available_dt"])
        out["etf_asof_lag_days"] = etf_lag
        out["etf_fund_count"] = er.get("fund_count", "")
        out["etf_flow_tonnes_1m"] = er.get("flow_1m", "")
        out["etf_flow_tonnes_3m"] = er.get("flow_3m", "")
        out["etf_flow_tonnes_6m"] = er.get("flow_6m", "")
        out["etf_flow_tonnes_12m"] = er.get("flow_12m", "")
        out["etf_flow_tonnes_12m_z36"] = er.get("flow_12m_z36", "")
        out["central_bank_period_start_utc"] = iso_z(cr["period_dt"])
        out["central_bank_period_end_utc"] = iso_z(cr.get("period_end_dt"))
        out["central_bank_available_after_utc"] = iso_z(cr["available_dt"])
        out["central_bank_asof_lag_days"] = cb_lag
        out["central_bank_demand_tonnes_1m"] = cr.get("demand_1m", "")
        out["central_bank_demand_tonnes_3m"] = cr.get("demand_3m", "")
        out["central_bank_demand_tonnes_6m"] = cr.get("demand_6m", "")
        out["central_bank_demand_tonnes_12m"] = cr.get("demand_12m", "")
        out["central_bank_demand_tonnes_12m_z36"] = cr.get("demand_12m_z36", "")
        out["event_calendar_forward_only_governance_active"] = "true"
        out["historical_event_calendar_feature_present"] = "false"
        normalized_rows.append(out)

    output_dataset = root / cfg["outputs"]["normalized_dataset_csv"]
    output_manifest = root / cfg["outputs"]["dataset_manifest_json"]

    output_cols = list(feature_cols)
    for c in [
        "full_scope_feature_date_utc",
        "sample_available_after_utc",
        "etf_period_date_utc",
        "etf_available_after_utc",
        "etf_asof_lag_days",
        "etf_fund_count",
        "etf_flow_tonnes_1m",
        "etf_flow_tonnes_3m",
        "etf_flow_tonnes_6m",
        "etf_flow_tonnes_12m",
        "etf_flow_tonnes_12m_z36",
        "central_bank_period_start_utc",
        "central_bank_period_end_utc",
        "central_bank_available_after_utc",
        "central_bank_asof_lag_days",
        "central_bank_demand_tonnes_1m",
        "central_bank_demand_tonnes_3m",
        "central_bank_demand_tonnes_6m",
        "central_bank_demand_tonnes_12m",
        "central_bank_demand_tonnes_12m_z36",
        "event_calendar_forward_only_governance_active",
        "historical_event_calendar_feature_present",
    ]:
        if c not in output_cols:
            output_cols.append(c)

    forbidden_output_cols = [c for c in output_cols if any(frag in c.lower() for frag in FORBIDDEN_COLUMN_FRAGMENTS)]
    # expected false-positive guard: 'historical_event_calendar_feature_present' is safe; it is a governance flag, not a historical filter.
    forbidden_output_cols = [c for c in forbidden_output_cols if c != "historical_event_calendar_feature_present"]
    if forbidden_output_cols:
        issues.append("output contains forbidden target/signal/validation-like columns: " + ";".join(forbidden_output_cols))

    write_csv_dicts(output_dataset, normalized_rows, output_cols)

    splits_cfg = cfg.get("splits", [])
    split_coverage = []
    for sp in splits_cfg:
        rows = [r for r in normalized_rows if date_in_range(str(r.get(date_col, "")), sp["start"], sp["end"])]
        split_coverage.append({
            "split_id": sp["split_id"],
            "start": sp["start"],
            "end": sp["end"],
            "row_count": len(rows),
            "min_rows": sp["min_rows"],
            "ready": len(rows) >= sp["min_rows"],
        })

    all_splits_ready = bool(split_coverage) and all(x["ready"] for x in split_coverage)
    row_count = len(normalized_rows)
    minimum_dataset_rows = int(cfg.get("minimum_dataset_rows", 3000))
    full_feature_missing = [c for c in FULL_SCOPE_FEATURES if c not in output_cols]

    if row_count < minimum_dataset_rows:
        issues.append(f"row_count below minimum_dataset_rows: {row_count} < {minimum_dataset_rows}")
    if not all_splits_ready:
        issues.append("one or more validation splits lack minimum rows")
    if lookahead_violations:
        issues.append(f"lookahead violations detected: {lookahead_violations}")
    if full_feature_missing:
        issues.append("missing full-scope feature columns: " + ";".join(full_feature_missing))

    pass_ok = not issues
    decision = "FULL_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_PASS_STAGE64L_DESIGN_ALLOWED_NO_VALIDATION" if pass_ok else "FULL_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_BLOCKED_NO_VALIDATION"

    manifest = {
        "stage": STAGE,
        "generated_utc": generated,
        "dataset_csv": str(output_dataset),
        "source_feature_dataset": str(feature_path),
        "etf_source": str(etf_path),
        "central_bank_source": str(cb_path),
        "row_count": row_count,
        "first_feature_date_utc": iso_z(parse_dt(normalized_rows[0].get(date_col))) if normalized_rows else None,
        "last_feature_date_utc": iso_z(parse_dt(normalized_rows[-1].get(date_col))) if normalized_rows else None,
        "features_added": FULL_SCOPE_FEATURES + ["etf_flow_tonnes_12m_z36", "central_bank_demand_tonnes_12m_z36"],
        "event_calendar_policy": "forward_only_governance_not_historical_feature",
        "broker_spot_alignment_policy": "required_before_commercialization_not_blocking_stage64k_research_dataset",
        "no_validation_no_order": True,
    }
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    with output_manifest.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    diagnostics = {
        "source_rows": {
            "stage64f_feature_dataset": len(feature_rows),
            "etf_raw_rows": len(etf_rows),
            "central_bank_raw_rows": len(cb_rows),
        },
        "aggregates": {
            "etf": etf_diag,
            "central_bank": cb_diag,
        },
        "blocked_rows": {
            "parse_feature_date_errors": parse_feature_date_errors,
            "no_etf_asof": no_etf_asof,
            "no_central_bank_asof": no_cb_asof,
            "stale_etf": stale_etf,
            "stale_central_bank": stale_cb,
            "insufficient_monthly_lookback": insufficient_monthly_lookback,
        },
        "lookahead_violations": lookahead_violations,
        "max_asof_lag_days": {
            "etf": max_etf_lag_days,
            "central_bank": max_cb_lag_days,
        },
        "warnings": warnings,
        "issues": issues,
    }

    source_checks = [
        {"source": "stage64f_feature_dataset", "found": feature_path.exists(), "rows": len(feature_rows), "ok": not missing_base and not forbidden_existing},
        {"source": "gold_etf_holdings_or_flows", "found": etf_path.exists(), "rows": len(etf_rows), "monthly_periods": etf_diag.get("monthly_periods"), "ok": bool(etf_records)},
        {"source": "central_bank_gold_demand", "found": cb_path.exists(), "rows": len(cb_rows), "monthly_periods": cb_diag.get("monthly_periods"), "ok": bool(cb_records)},
        {"source": "event_calendar", "found": True, "rows": 0, "ok": True, "governance": "forward_only_accepted_by_stage64j5_not_historical_feature"},
        {"source": "broker_spot_alignment", "found": False, "rows": 0, "ok": True, "governance": "not_blocking_stage64k_research_dataset_required_before_commercialization"},
    ]

    summary = {
        "stage": STAGE,
        "status": "FULL_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_order": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "validation_allowed_for_order_or_promotion": False,
        "generated_utc": generated,
        "root": str(root),
        "inputs": {
            "config": str(cfg_path),
            "stage64j5_summary": str(j5_path),
            "stage64f_feature_dataset": str(feature_path),
            "gold_etf_source": str(etf_path),
            "central_bank_source": str(cb_path),
        },
        "dataset_stats": {
            "row_count": row_count,
            "minimum_dataset_rows": minimum_dataset_rows,
            "first_feature_date_utc": manifest["first_feature_date_utc"],
            "last_feature_date_utc": manifest["last_feature_date_utc"],
            "normalized_output": str(output_dataset),
            "dataset_manifest_output": str(output_manifest),
            "target_columns_present": [c for c in output_cols if "target" in c.lower()],
            "signal_columns_present": [c for c in output_cols if "signal" in c.lower()],
            "validation_columns_present": [c for c in output_cols if "validation" in c.lower()],
        },
        "split_coverage": split_coverage,
        "source_checks": source_checks,
        "diagnostics": diagnostics,
        "event_calendar_governance": j5.get("event_calendar_governance_decision", {}),
        "broker_alignment_statement": j5.get("broker_alignment_statement", "Broker/spot D1 alignment remains required before commercialization."),
        "next_allowed_step": "Stage64L_FULL_SCOPE_WALK_FORWARD_VALIDATION_DESIGN_NO_SCAN" if pass_ok else "FIX_STAGE64K_SOURCE_OR_LAG_PREFLIGHT_NO_VALIDATION",
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_VALIDATION_SCAN_IN_STAGE64K",
            "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
            "NO_POST_HOC_EVENT_EXCLUSION",
            "NO_REDUCED_SCOPE_RETEST",
            "NO_RESCUE_FILTERING",
            "NO_NEW_INTRADAY_SCAN",
        ],
        "outputs": {
            "normalized_dataset_csv": str(output_dataset),
            "dataset_manifest_json": str(output_manifest),
            "source_checks_csv": str(out_dir / "stage64k_source_checks.csv"),
            "split_coverage_csv": str(out_dir / "stage64k_split_coverage.csv"),
            "summary_json": str(out_dir / "stage64k_full_scope_lag_safe_feature_dataset_preflight_summary.json"),
            "report_md": str(out_dir / "stage64k_full_scope_lag_safe_feature_dataset_preflight_report.md"),
        },
    }

    write_csv_dicts(out_dir / "stage64k_source_checks.csv", source_checks, ["source", "found", "rows", "monthly_periods", "ok", "governance"])
    write_csv_dicts(out_dir / "stage64k_split_coverage.csv", split_coverage, ["split_id", "start", "end", "row_count", "min_rows", "ready"])

    summary_path = out_dir / "stage64k_full_scope_lag_safe_feature_dataset_preflight_summary.json"
    report_path = out_dir / "stage64k_full_scope_lag_safe_feature_dataset_preflight_report.md"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Stage64K - Full-Scope Lag-Safe Feature Dataset Preflight (No Validation)\n\n")
        f.write(f"Generated UTC: `{generated}`\n\n")
        f.write("## Status\n\n")
        f.write("- status: `FULL_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_COMPLETE_NO_PROMOTION`\n")
        f.write(f"- decision: `{decision}`\n")
        f.write("- validation_allowed_for_order_or_promotion: `false`\n")
        f.write("- promotion/paper/live: `NO_GO`\n\n")
        f.write("## Executive conclusion\n\n")
        if pass_ok:
            f.write("A full-scope research feature dataset was built with lag-safe ETF and central-bank features plus forward-only event-calendar governance. No target, signal, validation scan, broker connection, paper-order, paper-live, live, or EA promotion is authorized. Stage64L may design the full-scope walk-forward validation protocol without running a scan.\n\n")
        else:
            f.write("The full-scope feature dataset preflight is blocked. Fix the source/lag issues before any design or validation stage.\n\n")
        f.write("## Dataset stats\n\n")
        for k, v in summary["dataset_stats"].items():
            f.write(f"- {k}: `{v}`\n")
        f.write("\n## Split coverage\n\n")
        f.write("| split_id | start | end | rows | min_rows | ready |\n")
        f.write("|---|---|---|---:|---:|---:|\n")
        for sp in split_coverage:
            f.write(f"| `{sp['split_id']}` | {sp['start']} | {sp['end']} | {sp['row_count']} | {sp['min_rows']} | {sp['ready']} |\n")
        f.write("\n## Diagnostics\n\n")
        f.write(f"- lookahead_violations: `{lookahead_violations}`\n")
        f.write(f"- blocked_rows: `{diagnostics['blocked_rows']}`\n")
        f.write(f"- source_rows: `{diagnostics['source_rows']}`\n")
        f.write("\n## Event-calendar governance\n\n")
        f.write("Historical event-calendar features remain excluded. Forward-only governance is accepted only for future operational blackout/risk control and must not be used as a historical validation feature.\n\n")
        f.write("## Broker/spot alignment\n\n")
        f.write("Broker/spot D1 alignment remains required before any commercialization or broker XAUUSD validation claim. It does not authorize broker connection and does not block this research dataset preflight.\n\n")
        f.write("## Issues\n\n")
        if issues:
            for issue in issues:
                f.write(f"- {issue}\n")
        else:
            f.write("- none\n")
        f.write("\n## Hard blocks\n\n")
        for hb in summary["hard_blocks"]:
            f.write(f"- `{hb}`\n")
        f.write("\n## Next allowed step\n\n")
        f.write(f"`{summary['next_allowed_step']}`\n")

    print(json.dumps({"status": summary["status"], "decision": decision, "row_count": row_count, "issues": issues, "summary": str(summary_path)}, indent=2))
    return 0 if pass_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
