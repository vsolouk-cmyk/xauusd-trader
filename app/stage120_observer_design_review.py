#!/usr/bin/env python3
"""Stage120 observer-design review for XAUUSD macro/COT/SPDR candidates.

This script is review-only. It does not write active observer files, MT5 bridge
files, EA files, or order surfaces. It converts Stage119 readiness outputs into
an observer-design draft and Stage121 preflight queue.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

STAGE = "Stage120_OBSERVER_DESIGN_REVIEW"
OUT_DIR = "stage120_observer_design_review"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE120",
    "NO_EA_CHANGE",
    "NO_OBSERVER_UPDATE_FROM_STAGE120",
    "NO_OBSERVER_BRIDGE_WRITE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

RULE_DESIGN_MAP = {
    "S117_06_SPDR_FLOW_SUPPORT_MACRO_RELIEF": {
        "design_rule_id": "S120_01_SPDR_FLOW_SUPPORT_MACRO_RELIEF_OBSERVER_DESIGN",
        "observer_family": "MACRO_SPDR_DOLLAR_RELIEF",
        "signal_side": "LONG_ONLY_OBSERVER",
        "timeframe": "H1",
        "horizon_hours": 120,
        "event_spacing_hours": 120,
        "required_features": [
            "spdr_value_chg_20d",
            "dollar_pressure_chg_20d",
            "real_yield_10y_chg_20d",
        ],
        "feature_sources": [
            "Stage116 validated SPDR GLD long candidate",
            "Stage116 validated dollar-pressure fallback from DTWEXBGS",
            "Stage115 daily macro panel",
        ],
        "condition_template": (
            "spdr_value_chg_20d >= {spdr_value_chg_20d_q75}; "
            "dollar_pressure_chg_20d <= {dollar_pressure_chg_20d_q50}; "
            "real_yield_10y_chg_20d <= {real_yield_10y_chg_20d_q50}"
        ),
        "source_risk": "SPDR_VALIDATED_CANDIDATE_SOURCE;WGC_NOT_USED_AS_HARD_FEATURE;DXY_DIRECT_INVALID_USING_DTWEXBGS_FALLBACK",
        "observer_mode": "DESIGN_ONLY_NOT_ACTIVE",
    },
    "S117_01_RY_DOWN_DOLLAR_DOWN_COT_NOT_CROWDED": {
        "design_rule_id": "S120_WATCH_RY_DOLLAR_COT_NOT_CROWDED_CONFIRMATION_DESIGN",
        "observer_family": "MACRO_COT_DOLLAR_RELIEF_WATCH",
        "signal_side": "LONG_ONLY_WATCH_OBSERVER",
        "timeframe": "H1",
        "horizon_hours": 120,
        "event_spacing_hours": 120,
        "required_features": [
            "real_yield_10y_chg_20d",
            "dollar_pressure_chg_20d",
            "cot_mm_net_z",
        ],
        "feature_sources": [
            "Stage115 daily macro panel",
            "Stage115 COT gold weekly features",
            "Stage116 validated dollar-pressure fallback from DTWEXBGS",
        ],
        "condition_template": (
            "real_yield_10y_chg_20d <= {real_yield_10y_chg_20d_q25}; "
            "dollar_pressure_chg_20d <= {dollar_pressure_chg_20d_q25}; "
            "cot_mm_net_z <= 1.0"
        ),
        "source_risk": "TAIL_EDGE_WEAK;DXY_DIRECT_INVALID_USING_DTWEXBGS_FALLBACK",
        "observer_mode": "WATCH_ONLY_EXTRA_CONFIRMATION_NOT_ACTIVE",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_csv_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def read_json_optional(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    rows = list(rows)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        fieldnames = keys or ["empty"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def scalar(row: pd.Series, key: str, default: Any = "") -> Any:
    if key not in row:
        return default
    val = row[key]
    if pd.isna(val):
        return default
    return val


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def load_thresholds(stage117_dir: Path) -> Dict[str, float]:
    path = stage117_dir / "stage117_selection_thresholds.csv"
    df = read_csv_optional(path)
    if df.empty:
        return {}
    first = df.iloc[0].to_dict()
    return {str(k): to_float(v) for k, v in first.items()}


def format_threshold(value: Any) -> str:
    if value is None or value == "":
        return "MISSING_THRESHOLD"
    try:
        f = float(value)
        if abs(f) >= 100:
            return f"{f:.6f}"
        return f"{f:.4f}"
    except Exception:
        return str(value)


def build_condition_text(template: str, thresholds: Dict[str, float]) -> str:
    vals = {k: format_threshold(v) for k, v in thresholds.items()}
    placeholders = {
        "spdr_value_chg_20d_q75": vals.get("spdr_value_chg_20d_q75", "MISSING_THRESHOLD"),
        "dollar_pressure_chg_20d_q50": vals.get("dollar_pressure_chg_20d_q50", "MISSING_THRESHOLD"),
        "real_yield_10y_chg_20d_q50": vals.get("real_yield_10y_chg_20d_q50", "MISSING_THRESHOLD"),
        "real_yield_10y_chg_20d_q25": vals.get("real_yield_10y_chg_20d_q25", "MISSING_THRESHOLD"),
        "dollar_pressure_chg_20d_q25": vals.get("dollar_pressure_chg_20d_q25", "MISSING_THRESHOLD"),
    }
    return template.format(**placeholders)


def readiness_bucket(readiness: str) -> str:
    if readiness.startswith("PRIMARY"):
        return "PRIMARY_DESIGN"
    if readiness.startswith("SECONDARY"):
        return "SECONDARY_DESIGN"
    if readiness.startswith("WATCH"):
        return "WATCH_ONLY"
    return "DO_NOT_CARRY_FORWARD"


def required_preflight_steps(bucket: str, candidate_only: bool) -> List[str]:
    base = [
        "replay Stage120 design on historical-as-of rows without changing observer files",
        "confirm feature availability at signal timestamp with no lookahead",
        "generate dry-run signal file under reports only, not MT5/MQL5/Files",
        "compare dry-run event counts with Stage117/Stage118 expected counts",
        "confirm no duplicate signal within 120h event-spacing window",
        "manual governance signoff before any active observer patch",
    ]
    if candidate_only:
        base.append("extra source check for SPDR candidate-only feature before active observer consideration")
    if bucket == "WATCH_ONLY":
        base.append("require a fresh confirmation scan or stronger tail-forward result before observer design activation")
    return base


def make_designs(queue: pd.DataFrame, thresholds: Dict[str, float]) -> List[Dict[str, Any]]:
    designs: List[Dict[str, Any]] = []
    for _, row in queue.iterrows():
        source_rule_id = str(scalar(row, "rule_id"))
        spec = RULE_DESIGN_MAP.get(source_rule_id)
        if not spec:
            continue
        observer_readiness = str(scalar(row, "observer_readiness"))
        bucket = readiness_bucket(observer_readiness)
        candidate_only = to_bool(scalar(row, "candidate_only", False))
        is_design_candidate = bucket in {"PRIMARY_DESIGN", "SECONDARY_DESIGN"}
        condition_text = build_condition_text(spec["condition_template"], thresholds)
        designs.append({
            "observer_design_rule_id": spec["design_rule_id"],
            "source_rule_id": source_rule_id,
            "description": scalar(row, "description"),
            "bucket": bucket,
            "is_stage121_preflight_candidate": bool(is_design_candidate),
            "observer_mode": spec["observer_mode"],
            "observer_family": spec["observer_family"],
            "timeframe": spec["timeframe"],
            "signal_side": spec["signal_side"],
            "horizon_hours": spec["horizon_hours"],
            "event_spacing_hours": spec["event_spacing_hours"],
            "condition_text": condition_text,
            "required_features": ";".join(spec["required_features"]),
            "feature_sources": ";".join(spec["feature_sources"]),
            "source_risk": spec["source_risk"],
            "candidate_only": candidate_only,
            "readiness_score": to_float(scalar(row, "readiness_score")),
            "stage118_audit_decision": scalar(row, "stage118_audit_decision"),
            "validation_cost10_mean_bps": to_float(scalar(row, "validation_cost10_mean_bps")),
            "validation_cost10_hit_rate": to_float(scalar(row, "validation_cost10_hit_rate")),
            "tail_cost10_mean_bps": to_float(scalar(row, "tail_cost10_mean_bps")),
            "tail_cost10_hit_rate": to_float(scalar(row, "tail_cost10_hit_rate")),
            "raw_all_events": to_float(scalar(row, "raw_all_events")),
            "stage116_dxy_fallback_active": to_bool(scalar(row, "stage116_dxy_fallback_active", False)),
            "stage116_direct_dxy_valid": to_bool(scalar(row, "stage116_direct_dxy_valid", False)),
            "stage116_spdr_status": scalar(row, "stage116_spdr_status"),
            "required_preflight_steps": " | ".join(required_preflight_steps(bucket, candidate_only)),
            "hard_block_statement": "DESIGN_ONLY_NO_OBSERVER_UPDATE_NO_MT5_NO_EA_NO_ORDER",
        })
    return designs


def make_rule_specs(designs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for d in designs:
        specs.append({
            "observer_design_rule_id": d["observer_design_rule_id"],
            "source_rule_id": d["source_rule_id"],
            "status": "DRAFT_ONLY_NOT_ACTIVE",
            "bucket": d["bucket"],
            "timeframe": d["timeframe"],
            "signal_side": d["signal_side"],
            "horizon_hours": int(d["horizon_hours"]),
            "event_spacing_hours": int(d["event_spacing_hours"]),
            "condition_text": d["condition_text"],
            "required_features": str(d["required_features"]).split(";"),
            "feature_sources": str(d["feature_sources"]).split(";"),
            "stage118_metrics": {
                "validation_cost10_mean_bps": d["validation_cost10_mean_bps"],
                "validation_cost10_hit_rate": d["validation_cost10_hit_rate"],
                "tail_cost10_mean_bps": d["tail_cost10_mean_bps"],
                "tail_cost10_hit_rate": d["tail_cost10_hit_rate"],
                "raw_all_events": d["raw_all_events"],
            },
            "governance": {
                "no_order": True,
                "no_observer_update": True,
                "no_mt5_or_ea_change": True,
                "requires_stage121_dry_run_preflight": bool(d["is_stage121_preflight_candidate"]),
            },
        })
    return specs


def make_feature_contract(designs: List[Dict[str, Any]], coverage: pd.DataFrame) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    cov_map: Dict[tuple, Dict[str, Any]] = {}
    if not coverage.empty and {"rule_id", "feature"}.issubset(coverage.columns):
        for _, r in coverage.iterrows():
            cov_map[(str(r["rule_id"]), str(r["feature"]))] = r.to_dict()
    for d in designs:
        for feature in str(d["required_features"]).split(";"):
            cov = cov_map.get((d["source_rule_id"], feature), {})
            rows.append({
                "observer_design_rule_id": d["observer_design_rule_id"],
                "source_rule_id": d["source_rule_id"],
                "feature": feature,
                "required_for_preflight": True,
                "full_coverage_pct": cov.get("full_coverage_pct", ""),
                "event_coverage_pct": cov.get("event_coverage_pct", ""),
                "min_required_event_coverage_pct": 99.0,
                "source_contract": feature_source_contract(feature),
            })
    return rows


def feature_source_contract(feature: str) -> str:
    if feature.startswith("spdr"):
        return "Stage116 validated_spdr_gld_long; candidate-only source; no WGC dependency"
    if feature.startswith("cot"):
        return "Stage115 COT gold weekly features; as-of weekly join; no lookahead"
    if "dollar_pressure" in feature:
        return "Stage116 validated dollar-pressure; DTWEXBGS fallback allowed; direct DXY not required"
    if "real_yield" in feature:
        return "Stage115 daily macro feature panel from FRED DFII10"
    return "Stage115/Stage116 feature panel"


def make_governance(summary119: Dict[str, Any], designs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    primary = sum(1 for d in designs if d["bucket"] == "PRIMARY_DESIGN")
    secondary = sum(1 for d in designs if d["bucket"] == "SECONDARY_DESIGN")
    watch = sum(1 for d in designs if d["bucket"] == "WATCH_ONLY")
    dxy_ctx = summary119.get("stage116_context", {}) if isinstance(summary119, dict) else {}
    return [
        {"gate": "ORDER_PERMISSION", "status": "BLOCKED", "reason": "Stage120 is design-review only; no automated/paper/demo/live order."},
        {"gate": "OBSERVER_UPDATE", "status": "BLOCKED", "reason": "Stage120 must not write active observer bridge/config/signal files."},
        {"gate": "MT5_OR_EA_CHANGE", "status": "BLOCKED", "reason": "No MT5, MQL5/Files, EA, or broker surface change allowed."},
        {"gate": "DIRECT_DXY", "status": "SOFT_FAIL_FALLBACK_OK", "reason": f"direct_dxy_valid={dxy_ctx.get('direct_dxy_valid')} fallback={dxy_ctx.get('dxy_fallback_active')}"},
        {"gate": "WGC_CENTRAL_BANK", "status": "EXCLUDED_FROM_HARD_FEATURES", "reason": "Stage120 designs do not require WGC ETF or central-bank rows."},
        {"gate": "STAGE121_PREFLIGHT_QUEUE", "status": "READY" if primary + secondary > 0 else "NOT_READY", "reason": f"primary={primary} secondary={secondary} watch={watch}"},
    ]


def make_report(summary: Dict[str, Any], designs: List[Dict[str, Any]], governance: List[Dict[str, Any]]) -> str:
    lines = [
        f"# {STAGE}",
        "",
        f"Generated UTC: {summary['generated_utc']}",
        "",
        f"Status: `{summary['status']}`",
        f"Decision: `{summary['decision']}`",
        "",
        "## Interpretation",
        "",
        "Stage120 converts Stage119 readiness into observer-design drafts only. It does not update the active observer, MT5, EA, broker, paper-order, or live-order surfaces.",
        "",
        "## Design queue",
        "",
    ]
    for d in designs:
        lines.extend([
            f"- `{d['observer_design_rule_id']}` from `{d['source_rule_id']}`: {d['bucket']}, score={d['readiness_score']:.1f}, mode=`{d['observer_mode']}`",
            f"  - Condition: `{d['condition_text']}`",
        ])
    lines.extend(["", "## Governance", ""])
    for g in governance:
        lines.append(f"- {g['gate']}: `{g['status']}` — {g['reason']}")
    lines.extend(["", "## Next use", "", "If Stage121 is created, it must be a dry-run preflight that writes only reports, not active observer or MT5 files."])
    return "\n".join(lines) + "\n"


def run(root: Path) -> Dict[str, Any]:
    reports = root / "reports"
    stage119_dir = reports / "stage119_portfolio_observer_readiness_review"
    stage118_dir = reports / "stage118_macro_cot_spdr_hard_audit"
    stage117_dir = reports / "stage117_segmented_macro_cot_dollar_discovery"
    out_dir = reports / OUT_DIR
    ensure_dir(out_dir)

    queue = read_csv_optional(stage119_dir / "stage119_observer_readiness_queue.csv")
    coverage = read_csv_optional(stage119_dir / "stage119_feature_coverage_review.csv")
    overlap = read_csv_optional(stage119_dir / "stage119_portfolio_overlap_review.csv")
    governance119 = read_csv_optional(stage119_dir / "stage119_governance_gate.csv")
    summary119 = read_json_optional(stage119_dir / "stage119_portfolio_observer_readiness_review_summary.json")
    thresholds = load_thresholds(stage117_dir)

    designs = make_designs(queue, thresholds) if not queue.empty else []
    specs = make_rule_specs(designs)
    feature_contract = make_feature_contract(designs, coverage)
    governance = make_governance(summary119, designs)

    observer_design_queue = out_dir / "stage120_observer_design_queue.csv"
    rule_specs_draft = out_dir / "stage120_observer_rule_specs_draft.json"
    feature_contract_path = out_dir / "stage120_observer_feature_contract.csv"
    governance_path = out_dir / "stage120_governance_gate.csv"
    preflight_path = out_dir / "stage120_stage121_preflight_queue.csv"
    watch_path = out_dir / "stage120_watchlist_only_rules.csv"
    overlap_path = out_dir / "stage120_portfolio_overlap_carry_forward.csv"
    report_md = out_dir / "stage120_observer_design_review_report.md"
    summary_json = out_dir / "stage120_observer_design_review_summary.json"

    write_csv(observer_design_queue, designs)
    write_json(rule_specs_draft, specs)
    write_csv(feature_contract_path, feature_contract)
    write_csv(governance_path, governance)
    preflight = [d for d in designs if d.get("is_stage121_preflight_candidate")]
    watch = [d for d in designs if d.get("bucket") == "WATCH_ONLY"]
    write_csv(preflight_path, preflight)
    write_csv(watch_path, watch)
    if not overlap.empty:
        overlap.to_csv(overlap_path, index=False)
    else:
        write_csv(overlap_path, [])

    primary_count = sum(1 for d in designs if d["bucket"] == "PRIMARY_DESIGN")
    secondary_count = sum(1 for d in designs if d["bucket"] == "SECONDARY_DESIGN")
    watch_count = sum(1 for d in designs if d["bucket"] == "WATCH_ONLY")
    preflight_count = len(preflight)
    if preflight_count > 0:
        decision = "STAGE120_STAGE121_DRY_RUN_PREFLIGHT_QUEUE_READY_NO_UPDATE"
    elif watch_count > 0:
        decision = "STAGE120_WATCH_ONLY_NO_PREFLIGHT_NO_UPDATE"
    else:
        decision = "STAGE120_NO_OBSERVER_DESIGN_CARRY_FORWARD_NO_UPDATE"

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": "STAGE120_COMPLETE_OBSERVER_DESIGN_REVIEW_READY_NO_UPDATE",
        "decision": decision,
        "classification": "OBSERVER_DESIGN_REVIEW_ONLY_NO_UPDATE",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "stage119_dir": str(stage119_dir),
        "stage118_dir": str(stage118_dir),
        "stage117_dir": str(stage117_dir),
        "queue_rows_seen": int(len(queue)) if not queue.empty else 0,
        "design_count": len(designs),
        "primary_design_count": primary_count,
        "secondary_design_count": secondary_count,
        "watch_only_count": watch_count,
        "stage121_preflight_candidate_count": preflight_count,
        "thresholds_loaded": bool(thresholds),
        "direct_dxy_valid": summary119.get("stage116_context", {}).get("direct_dxy_valid") if summary119 else None,
        "dxy_fallback_active": summary119.get("stage116_context", {}).get("dxy_fallback_active") if summary119 else None,
        "spdr_status": summary119.get("stage116_context", {}).get("spdr_gld_status") if summary119 else None,
        "observer_design_queue": str(observer_design_queue),
        "observer_rule_specs_draft": str(rule_specs_draft),
        "observer_feature_contract": str(feature_contract_path),
        "governance_gate": str(governance_path),
        "stage121_preflight_queue": str(preflight_path),
        "watchlist_only_rules": str(watch_path),
        "portfolio_overlap_carry_forward": str(overlap_path),
        "summary_json": str(summary_json),
        "report_md": str(report_md),
        "next": [
            "If stage121_preflight_candidate_count > 0, create Stage121 dry-run observer preflight only.",
            "Stage121 must write reports only; no active observer bridge, MT5, EA, paper-order, or live-order files.",
            "Watch-only rules require extra confirmation before any observer design activation path.",
        ],
    }
    write_json(summary_json, summary)
    report_md.write_text(make_report(summary, designs, governance))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage120 observer-design review only")
    parser.add_argument("--root", default=".", help="Repo root")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    summary = run(root)
    print(f"{STAGE} | status={summary['status']} | decision={summary['decision']} | preflight={summary['stage121_preflight_candidate_count']}")
    print(json.dumps({
        "summary_json": summary["summary_json"],
        "observer_design_queue": summary["observer_design_queue"],
        "stage121_preflight_queue": summary["stage121_preflight_queue"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
