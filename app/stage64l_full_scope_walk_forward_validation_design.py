#!/usr/bin/env python3
"""
Stage64L - Full-Scope Walk-Forward Validation Design (No Scan)

This stage predeclares the full-scope daily/weekly macro-regime validation design.
It reads the Stage64K full-scope feature dataset only to inspect schema, feature
availability, row counts, and split coverage. It does NOT compute forward outcomes,
does NOT run validation, does NOT generate signals, and does NOT authorize orders.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


NO_GO = "NO_GO"
STAGE = "Stage64L_FULL_SCOPE_WALK_FORWARD_VALIDATION_DESIGN_NO_SCAN"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames))
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def parse_time(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s
    try:
        out = dt.datetime.fromisoformat(s2)
        if out.tzinfo is None:
            out = out.replace(tzinfo=dt.UTC)
        return out.astimezone(dt.UTC)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.UTC)
        except Exception:
            continue
    return None


def normalize_col(s: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in s).strip("_")


def choose_first(columns: Sequence[str], exact: Sequence[str] = (), contains_all: Sequence[str] = (), contains_any: Sequence[str] = ()) -> Optional[str]:
    colset = {c: normalize_col(c) for c in columns}
    exact_norm = [normalize_col(x) for x in exact]
    for c, n in colset.items():
        if n in exact_norm:
            return c
    all_norm = [normalize_col(x) for x in contains_all]
    any_norm = [normalize_col(x) for x in contains_any]
    for c, n in colset.items():
        if all(x in n for x in all_norm) and (not any_norm or any(x in n for x in any_norm)):
            return c
    return None


def load_dataset_schema(path: Path, max_preview_rows: int = 5) -> Tuple[List[str], int, Dict[str, Any], List[Dict[str, str]]]:
    if not path.exists():
        return [], 0, {"found": False, "path": str(path)}, []
    rows_preview: List[Dict[str, str]] = []
    row_count = 0
    first_dt: Optional[dt.datetime] = None
    last_dt: Optional[dt.datetime] = None
    columns: List[str] = []
    date_col: Optional[str] = None
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        date_col = choose_first(columns, exact=[
            "feature_date_utc", "date_utc", "utc_time", "time_utc", "timestamp_utc", "date"
        ], contains_any=["date", "time"])
        for row in reader:
            row_count += 1
            if len(rows_preview) < max_preview_rows:
                rows_preview.append(dict(row))
            if date_col:
                t = parse_time(row.get(date_col))
                if t is not None:
                    if first_dt is None or t < first_dt:
                        first_dt = t
                    if last_dt is None or t > last_dt:
                        last_dt = t
    meta = {
        "found": True,
        "path": str(path),
        "date_column": date_col,
        "first_feature_date_utc": first_dt.isoformat().replace("+00:00", "Z") if first_dt else None,
        "last_feature_date_utc": last_dt.isoformat().replace("+00:00", "Z") if last_dt else None,
    }
    return columns, row_count, meta, rows_preview


def split_coverage(dataset_path: Path, date_col: Optional[str], splits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not dataset_path.exists() or not date_col:
        for sp in splits:
            out.append({
                "split_id": sp["split_id"],
                "start": sp["start"],
                "end": sp["end"],
                "row_count": 0,
                "min_rows": int(sp.get("min_rows", 0)),
                "ready": False,
            })
        return out
    parsed_splits = []
    for sp in splits:
        start = parse_time(sp["start"])
        end = parse_time(sp["end"])
        parsed_splits.append((sp, start, end))
    counts = {sp["split_id"]: 0 for sp in splits}
    with dataset_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = parse_time(row.get(date_col))
            if t is None:
                continue
            for sp, start, end in parsed_splits:
                if start is not None and end is not None and start <= t <= end:
                    counts[sp["split_id"]] += 1
    for sp in splits:
        min_rows = int(sp.get("min_rows", 0))
        rc = counts.get(sp["split_id"], 0)
        out.append({
            "split_id": sp["split_id"],
            "start": sp["start"],
            "end": sp["end"],
            "row_count": rc,
            "min_rows": min_rows,
            "ready": rc >= min_rows,
        })
    return out


def forbidden_columns(columns: Sequence[str]) -> Dict[str, List[str]]:
    prefix_hits: List[str] = []
    contains_hits: List[str] = []
    prefixes = ("target", "signal", "label", "outcome", "fwd", "forward_return", "validation")
    contains = ("future_return", "future_ret", "resolved_", "trade_", "pnl", "profit")
    for c in columns:
        n = normalize_col(c)
        if any(n == p or n.startswith(p + "_") for p in prefixes):
            prefix_hits.append(c)
        elif any(x in n for x in contains):
            contains_hits.append(c)
    return {"prefix_or_exact": prefix_hits, "contains": contains_hits}


def detect_feature_map(columns: Sequence[str]) -> Dict[str, Optional[str]]:
    return {
        "gold_ret_20d": choose_first(columns, exact=["gold_ret_20d"], contains_all=["gold", "ret", "20"]),
        "gold_sma20_over_50": choose_first(columns, exact=["gold_sma20_over_50"], contains_all=["gold", "sma20", "50"]),
        "gold_sma50_over_200": choose_first(columns, exact=["gold_sma50_over_200"], contains_all=["gold", "sma50", "200"]),
        "gold_atr14_proxy_pct": choose_first(columns, exact=["gold_atr14_proxy_pct"], contains_all=["gold", "atr"], contains_any=["pct", "14"]),
        "dxy_ret_20d": choose_first(columns, exact=["dxy_ret_20d"], contains_all=["dxy", "ret", "20"]),
        "dxy_sma20_over_50": choose_first(columns, exact=["dxy_sma20_over_50"], contains_all=["dxy", "sma20", "50"]),
        "real_yield_change_20d": choose_first(columns, exact=["real_yield_change_20d"], contains_all=["real", "yield"], contains_any=["20", "change"]),
        "vix_change_20d": choose_first(columns, exact=["vix_change_20d"], contains_all=["vix"], contains_any=["20", "change"]),
        "vix_sma20_over_50": choose_first(columns, exact=["vix_sma20_over_50"], contains_all=["vix", "sma20", "50"]),
        "etf_flow_1m": choose_first(columns, exact=["etf_flow_1m_tonnes", "etf_demand_1m_tonnes"], contains_all=["etf"], contains_any=["1m", "flow_1", "demand_1"]),
        "etf_flow_3m": choose_first(columns, exact=["etf_flow_3m_tonnes", "etf_demand_3m_tonnes"], contains_all=["etf"], contains_any=["3m", "flow_3", "demand_3"]),
        "etf_flow_6m": choose_first(columns, exact=["etf_flow_6m_tonnes", "etf_demand_6m_tonnes"], contains_all=["etf"], contains_any=["6m", "flow_6", "demand_6"]),
        "etf_flow_12m": choose_first(columns, exact=["etf_flow_12m_tonnes", "etf_demand_12m_tonnes"], contains_all=["etf"], contains_any=["12m", "flow_12", "demand_12"]),
        "etf_asof_lag_days": choose_first(columns, exact=["etf_asof_lag_days"], contains_all=["etf", "lag"]),
        "central_bank_demand_3m": choose_first(columns, exact=["central_bank_demand_3m_tonnes", "cb_demand_3m_tonnes"], contains_all=["central", "bank"], contains_any=["3m", "demand_3"]),
        "central_bank_demand_6m": choose_first(columns, exact=["central_bank_demand_6m_tonnes", "cb_demand_6m_tonnes"], contains_all=["central", "bank"], contains_any=["6m", "demand_6"]),
        "central_bank_demand_12m": choose_first(columns, exact=["central_bank_demand_12m_tonnes", "cb_demand_12m_tonnes"], contains_all=["central", "bank"], contains_any=["12m", "demand_12"]),
        "central_bank_asof_lag_days": choose_first(columns, exact=["central_bank_asof_lag_days", "cb_asof_lag_days"], contains_all=["central", "bank", "lag"]),
    }


def missing_required_features(feature_map: Dict[str, Optional[str]], required_groups: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    misses: List[Dict[str, Any]] = []
    for grp in required_groups:
        feature_keys = grp.get("feature_keys", [])
        min_present = int(grp.get("min_present", len(feature_keys)))
        present = [k for k in feature_keys if feature_map.get(k)]
        if len(present) < min_present:
            misses.append({
                "group_id": grp.get("group_id", ""),
                "required": ";".join(feature_keys),
                "present": ";".join(present),
                "min_present": min_present,
                "missing_count": max(0, min_present - len(present)),
            })
    return misses


def build_benchmarks(feature_map: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
    g20 = feature_map.get("gold_sma20_over_50") or "<gold_sma20_over_50>"
    g50 = feature_map.get("gold_sma50_over_200") or "<gold_sma50_over_200>"
    dxy = feature_map.get("dxy_ret_20d") or "<dxy_ret_20d>"
    ry = feature_map.get("real_yield_change_20d") or "<real_yield_change_20d>"
    return [
        {
            "hypothesis_id": "H64L_B0_ALWAYS_LONG_REFERENCE",
            "role": "benchmark",
            "description": "Always-long daily gold reference benchmark.",
            "rule_expression": "always_true",
            "primary": False,
        },
        {
            "hypothesis_id": "H64L_B1_GOLD_TREND_ONLY_REFERENCE",
            "role": "benchmark",
            "description": "Predeclared primary benchmark: gold D1 trend filter only.",
            "rule_expression": f"({g20} > 0) and ({g50} > 0)",
            "primary": True,
        },
        {
            "hypothesis_id": "H64L_B2_P0_MACRO_TAILWIND_REFERENCE",
            "role": "benchmark_reference_only",
            "description": "Reduced-scope P0 macro tailwind reference, retained only as comparison control after Stage64H failure.",
            "rule_expression": f"({g20} > 0) and ({g50} > 0) and ({dxy} < 0) and ({ry} < 0)",
            "primary": False,
        },
    ]


def build_candidates(feature_map: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
    g20 = feature_map.get("gold_sma20_over_50") or "<gold_sma20_over_50>"
    g50 = feature_map.get("gold_sma50_over_200") or "<gold_sma50_over_200>"
    dxy = feature_map.get("dxy_ret_20d") or "<dxy_ret_20d>"
    ry = feature_map.get("real_yield_change_20d") or "<real_yield_change_20d>"
    vix = feature_map.get("vix_change_20d") or "<vix_change_20d>"
    etf3 = feature_map.get("etf_flow_3m") or feature_map.get("etf_flow_1m") or "<etf_flow_3m>"
    etf6 = feature_map.get("etf_flow_6m") or feature_map.get("etf_flow_3m") or "<etf_flow_6m>"
    cb6 = feature_map.get("central_bank_demand_6m") or feature_map.get("central_bank_demand_3m") or "<central_bank_demand_6m>"
    cb12 = feature_map.get("central_bank_demand_12m") or feature_map.get("central_bank_demand_6m") or "<central_bank_demand_12m>"
    return [
        {
            "hypothesis_id": "H64L_H1_FULL_MACRO_TAILWIND_LONG",
            "role": "candidate",
            "description": "Trend-long only when dollar, real-yield, ETF-flow, and central-bank prior all align.",
            "rule_expression": f"({g20} > 0) and ({g50} > 0) and ({dxy} < 0) and ({ry} < 0) and ({etf3} > 0) and ({cb6} > 0)",
            "rationale": "Tests whether full-scope macro confirmation repairs the reduced-scope P0 failure without retuning old thresholds.",
        },
        {
            "hypothesis_id": "H64L_H2_ETF_CONFIRMED_TREND_LONG",
            "role": "candidate",
            "description": "Trend-long with ETF demand confirmation and no dollar headwind.",
            "rule_expression": f"({g20} > 0) and ({g50} > 0) and ({etf3} > 0) and ({etf6} > 0) and ({dxy} <= 0)",
            "rationale": "Tests ETF-flow demand as an incremental confirmation layer over the primary trend benchmark.",
        },
        {
            "hypothesis_id": "H64L_H3_CENTRAL_BANK_PRIOR_TREND_LONG",
            "role": "candidate",
            "description": "Trend-long under positive central-bank slow prior and non-adverse real-yield impulse.",
            "rule_expression": f"({g20} > 0) and ({g50} > 0) and ({cb6} > 0) and ({cb12} > 0) and ({ry} <= 0)",
            "rationale": "Tests whether official-sector accumulation acts as a slow regime prior, not a timing signal.",
        },
        {
            "hypothesis_id": "H64L_H4_FULL_SCOPE_RISK_SUPPRESSED_TAILWIND_LONG",
            "role": "candidate",
            "description": "Full macro tailwind only when volatility impulse is not adverse.",
            "rule_expression": f"({g20} > 0) and ({g50} > 0) and ({dxy} < 0) and ({ry} < 0) and ({etf3} > 0) and ({cb6} > 0) and ({vix} <= 0)",
            "rationale": "Tests whether avoiding volatility-shock conditions improves macro tailwind persistence.",
        },
    ]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".", help="Repository root")
    p.add_argument("--config", required=True, help="Stage64L config JSON")
    p.add_argument("--out", required=True, help="Output reports directory")
    args = p.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = read_json(config_path)

    stage64k_summary_path = root / cfg["inputs"]["stage64k_summary"]
    dataset_path = root / cfg["inputs"]["stage64k_dataset"]

    k_summary: Dict[str, Any] = {}
    if stage64k_summary_path.exists():
        k_summary = read_json(stage64k_summary_path)

    columns, row_count, dataset_meta, _preview = load_dataset_schema(dataset_path)
    date_col = dataset_meta.get("date_column")
    split_rows = split_coverage(dataset_path, date_col, cfg["validation_design"]["splits"])
    forbid = forbidden_columns(columns)
    feature_map = detect_feature_map(columns)
    required_misses = missing_required_features(feature_map, cfg["validation_design"]["required_feature_groups"])

    horizons = list(cfg["validation_design"]["horizons_trading_days"])
    benchmarks = build_benchmarks(feature_map)
    candidates = build_candidates(feature_map)
    effective_test_count = len(candidates) * len(horizons)

    design_rows: List[Dict[str, Any]] = []
    for row in benchmarks + candidates:
        for h in horizons:
            design_rows.append({
                "hypothesis_id": row["hypothesis_id"],
                "role": row["role"],
                "horizon_trading_days": h,
                "primary_benchmark_id": "H64L_B1_GOLD_TREND_ONLY_REFERENCE",
                "description": row.get("description", ""),
                "rule_expression": row.get("rule_expression", ""),
                "rationale": row.get("rationale", ""),
            })

    minimum_rows = int(cfg["validation_design"].get("minimum_dataset_rows", 3000))
    dataset_ok = bool(dataset_meta.get("found")) and row_count >= minimum_rows and bool(date_col)
    splits_ready = all(bool(x["ready"]) for x in split_rows)
    forbidden_ok = not forbid["prefix_or_exact"] and not forbid["contains"]
    required_features_ok = not required_misses
    stage64k_allowed = k_summary.get("decision") == "FULL_SCOPE_LAG_SAFE_FEATURE_DATASET_PREFLIGHT_PASS_STAGE64L_DESIGN_ALLOWED_NO_VALIDATION"

    issues: List[str] = []
    if not dataset_meta.get("found"):
        issues.append("stage64k dataset file missing")
    if row_count < minimum_rows:
        issues.append(f"dataset row_count below minimum: {row_count} < {minimum_rows}")
    if not date_col:
        issues.append("no date/time column detected")
    if not splits_ready:
        issues.append("one or more validation splits below minimum rows")
    if not forbidden_ok:
        issues.append("target/signal/validation/outcome-like columns present")
    if not required_features_ok:
        issues.append("required feature groups missing")
    if not stage64k_allowed:
        issues.append("Stage64K summary does not explicitly allow Stage64L design")

    if issues:
        decision = "FULL_SCOPE_WALK_FORWARD_DESIGN_BLOCKED_FIX_DATASET_OR_STOP_NO_ORDER"
        next_allowed = "FIX_STAGE64K_DATASET_OR_PROGRAM_STOP_NO_ORDER"
    else:
        decision = "FULL_SCOPE_WALK_FORWARD_VALIDATION_DESIGN_COMPLETE_STAGE64M_ALLOWED_NO_SCAN_NO_ORDER"
        next_allowed = "Stage64M_FULL_SCOPE_WALK_FORWARD_VALIDATION_RUN_NO_ORDER"

    summary = {
        "stage": STAGE,
        "status": "FULL_SCOPE_WALK_FORWARD_VALIDATION_DESIGN_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_order": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": False,
        "generated_utc": utc_now_iso(),
        "root": str(root),
        "inputs": {
            "config": str(config_path),
            "stage64k_summary": str(stage64k_summary_path),
            "stage64k_dataset": str(dataset_path),
        },
        "dataset_checks": {
            "found": bool(dataset_meta.get("found")),
            "row_count": row_count,
            "minimum_dataset_rows": minimum_rows,
            "date_column": date_col,
            "first_feature_date_utc": dataset_meta.get("first_feature_date_utc"),
            "last_feature_date_utc": dataset_meta.get("last_feature_date_utc"),
            "column_count": len(columns),
            "target_signal_validation_like_columns": forbid,
            "forbidden_columns_ok": forbidden_ok,
            "dataset_ok": dataset_ok,
        },
        "split_coverage": split_rows,
        "feature_map": feature_map,
        "missing_required_feature_groups": required_misses,
        "required_features_ok": required_features_ok,
        "stage64k_decision": k_summary.get("decision"),
        "stage64k_allowed": stage64k_allowed,
        "validation_design": {
            "horizons_trading_days": horizons,
            "candidate_count": len(candidates),
            "benchmark_count": len(benchmarks),
            "primary_benchmark_id": "H64L_B1_GOLD_TREND_ONLY_REFERENCE",
            "effective_test_count": effective_test_count,
            "multiple_testing_rule": cfg["validation_design"]["multiple_testing_rule"],
            "pass_gates": cfg["validation_design"]["pass_gates"],
            "event_calendar_policy": cfg["validation_design"]["event_calendar_policy"],
            "broker_alignment_policy": cfg["validation_design"]["broker_alignment_policy"],
        },
        "benchmarks": benchmarks,
        "candidates": candidates,
        "issues": issues,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_VALIDATION_SCAN_IN_STAGE64L",
            "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
            "NO_POST_HOC_EVENT_EXCLUSION",
            "NO_REDUCED_SCOPE_RETEST",
            "NO_RESCUE_FILTERING",
            "NO_NEW_INTRADAY_SCAN",
            "NO_FULL_SCOPE_VALIDATION_CLAIM_FROM_STAGE64L",
        ],
        "next_allowed_step": next_allowed,
        "outputs": {
            "summary_json": str(out_dir / "stage64l_full_scope_walk_forward_validation_design_summary.json"),
            "report_md": str(out_dir / "stage64l_full_scope_walk_forward_validation_design_report.md"),
            "hypothesis_design_csv": str(out_dir / "stage64l_hypothesis_design.csv"),
            "split_coverage_csv": str(out_dir / "stage64l_split_coverage.csv"),
            "feature_map_json": str(out_dir / "stage64l_feature_map.json"),
        },
    }

    report_lines = [
        "# Stage64L - Full-Scope Walk-Forward Validation Design (No Scan)",
        "",
        f"Generated UTC: `{summary['generated_utc']}`",
        "",
        "## Status",
        "",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        "- validation_run_performed: `False`",
        "- validation_allowed_for_order_or_promotion: `False`",
        "- promotion/paper/live: `NO_GO`",
        "",
        "## Executive conclusion",
        "",
    ]
    if issues:
        report_lines.append("Stage64L design is blocked because the Stage64K dataset or required feature schema is incomplete. No validation run is allowed.")
    else:
        report_lines.append("Stage64L predeclares the full-scope walk-forward validation protocol using the Stage64K lag-safe dataset. It does not run validation, generate signals, connect to a broker, or authorize any order path.")
    report_lines += [
        "",
        "## Dataset checks",
        "",
        f"- row_count: `{row_count}`",
        f"- minimum_dataset_rows: `{minimum_rows}`",
        f"- date_column: `{date_col}`",
        f"- first_feature_date_utc: `{dataset_meta.get('first_feature_date_utc')}`",
        f"- last_feature_date_utc: `{dataset_meta.get('last_feature_date_utc')}`",
        f"- forbidden_columns_ok: `{forbidden_ok}`",
        f"- required_features_ok: `{required_features_ok}`",
        "",
        "## Split coverage",
        "",
        "| split_id | start | end | rows | min_rows | ready |",
        "|---|---|---|---:|---:|---:|",
    ]
    for sp in split_rows:
        report_lines.append(f"| `{sp['split_id']}` | {sp['start']} | {sp['end']} | {sp['row_count']} | {sp['min_rows']} | {sp['ready']} |")
    report_lines += [
        "",
        "## Feature map",
        "",
        "| feature_key | selected_column |",
        "|---|---|",
    ]
    for k, v in feature_map.items():
        report_lines.append(f"| `{k}` | `{v}` |")
    if required_misses:
        report_lines += [
            "",
            "## Missing required feature groups",
            "",
            "| group_id | required | present | min_present |",
            "|---|---|---|---:|",
        ]
        for miss in required_misses:
            report_lines.append(f"| `{miss['group_id']}` | `{miss['required']}` | `{miss['present']}` | {miss['min_present']} |")
    report_lines += [
        "",
        "## Predeclared validation design",
        "",
        f"- horizons_trading_days: `{horizons}`",
        f"- candidate_count: `{len(candidates)}`",
        f"- benchmark_count: `{len(benchmarks)}`",
        f"- primary_benchmark_id: `H64L_B1_GOLD_TREND_ONLY_REFERENCE`",
        f"- effective_test_count: `{effective_test_count}`",
        f"- multiple_testing_rule: `{cfg['validation_design']['multiple_testing_rule']}`",
        "",
        "## Hypotheses",
        "",
        "| hypothesis_id | role | rule_expression |",
        "|---|---|---|",
    ]
    for h in benchmarks + candidates:
        report_lines.append(f"| `{h['hypothesis_id']}` | `{h['role']}` | `{h['rule_expression']}` |")
    report_lines += [
        "",
        "## Pass gates for Stage64M",
        "",
    ]
    for gate in cfg["validation_design"]["pass_gates"]:
        report_lines.append(f"- `{gate}`")
    report_lines += [
        "",
        "## Event-calendar governance",
        "",
        cfg["validation_design"]["event_calendar_policy"],
        "",
        "## Broker/spot alignment",
        "",
        cfg["validation_design"]["broker_alignment_policy"],
        "",
        "## Issues",
        "",
    ]
    if issues:
        for issue in issues:
            report_lines.append(f"- `{issue}`")
    else:
        report_lines.append("- none")
    report_lines += [
        "",
        "## Hard blocks",
        "",
    ]
    for hb in summary["hard_blocks"]:
        report_lines.append(f"- `{hb}`")
    report_lines += [
        "",
        "## Next allowed step",
        "",
        f"`{next_allowed}`",
        "",
    ]

    write_json(out_dir / "stage64l_full_scope_walk_forward_validation_design_summary.json", summary)
    write_json(out_dir / "stage64l_feature_map.json", {"feature_map": feature_map})
    write_csv(out_dir / "stage64l_hypothesis_design.csv", design_rows)
    write_csv(out_dir / "stage64l_split_coverage.csv", split_rows)
    (out_dir / "stage64l_full_scope_walk_forward_validation_design_report.md").write_text("\n".join(report_lines), encoding="utf-8")

    print("status", summary["status"])
    print("decision", summary["decision"])
    print("dataset_rows", row_count)
    print("effective_test_count", effective_test_count)
    print("next_allowed_step", next_allowed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
