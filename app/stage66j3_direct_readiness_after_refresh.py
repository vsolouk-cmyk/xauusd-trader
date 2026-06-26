#!/usr/bin/env python3
"""Stage66J3 direct multi-readiness after Stage67D6 refresh.

No broker, no order, no paper-live/live. This runner intentionally avoids the
older Stage66J/Stage66K child scripts whose return codes currently treat
WAIT/BLOCKED no-ticket states as hard failures. It directly inspects the
lag-safe macro feature dataset and applies the locked Stage66 rule conditions
as read-only signal checks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage66J3_DIRECT_READINESS_AFTER_REFRESH"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE66J3",
    "NO_THRESHOLD_TUNING",
    "NO_PROMOTION_FROM_DIRECT_READINESS_ONLY",
]

RULES = {
    "h64l_v2": {
        "label": "H64L v2",
        "horizon_trading_days": 120,
        "type": "primary",
        "required_columns": [
            "gold_sma20_over_50",
            "dxy_ret_20d",
            "real_yield_change_20d",
            "etf_flow_tonnes_3m",
            "central_bank_demand_tonnes_3m",
            "gold_sma50_over_200",
        ],
        "conditions": [
            ["gold_sma20_over_50", ">", 0.0],
            ["dxy_ret_20d", "<", 0.0],
            ["real_yield_change_20d", "<", 0.0],
            ["etf_flow_tonnes_3m", ">", 0.0],
            ["central_bank_demand_tonnes_3m", ">", 0.0],
            ["gold_sma50_over_200", ">", 0.0],
        ],
        "active_decision": "H64L_V2_SIGNAL_ACTIVE_REQUIRES_EXISTING_NO_BROKER_DRY_RUN_REVIEW",
        "inactive_decision": "WAIT_FOR_FRESH_H64L_V2_SIGNAL_NO_DRY_RUN_TICKET",
        "data_wait_decision": "WAIT_FOR_FRESH_MACRO_DATA_NO_DRY_RUN_TICKET",
    },
    "d3_h60": {
        "label": "D3 H60",
        "horizon_trading_days": 60,
        "type": "complementary_primary",
        "required_columns": ["gold_sma20_over_50", "dxy_sma20_over_50", "dxy_ret_20d"],
        "conditions": [
            ["gold_sma20_over_50", ">", 0.0],
            ["dxy_sma20_over_50", "<", 0.0],
            ["dxy_ret_20d", "<", 0.0],
        ],
        "active_decision": "D3_H60_SIGNAL_ACTIVE_REQUIRES_EXISTING_NO_BROKER_DRY_RUN_REVIEW",
        "inactive_decision": "WAIT_FOR_FRESH_COMPLEMENTARY_D3_H60_SIGNAL_NO_DRY_RUN_TICKET",
        "data_wait_decision": "WAIT_FOR_FRESH_D3_MACRO_DATA_NO_DRY_RUN_TICKET",
    },
    "d1_backup": {
        "label": "D1_DXY_REALYIELD_GOLD_TREND_SHORT_HORIZON_LONG_H60",
        "horizon_trading_days": 60,
        "type": "backup",
        "required_columns": ["gold_sma20_over_50", "dxy_ret_20d", "real_yield_change_20d"],
        "conditions": [
            ["gold_sma20_over_50", ">", 0.0],
            ["dxy_ret_20d", "<", 0.0],
            ["real_yield_change_20d", "<", 0.0],
        ],
        "active_decision": "BACKUP_D1_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER",
        "inactive_decision": "WAIT_FOR_FRESH_BACKUP_D1_SIGNAL_NO_ORDER",
        "data_wait_decision": "WAIT_FOR_FRESH_BACKUP_D1_MACRO_DATA_NO_ORDER",
    },
    "d4_backup": {
        "label": "D4_VOL_RISK_OFF_REALYIELD_GOLD_LONG_H60",
        "horizon_trading_days": 60,
        "type": "backup",
        "required_columns": ["gold_sma20_over_50", "vix_change_20d", "real_yield_change_20d"],
        "conditions": [
            ["gold_sma20_over_50", ">", 0.0],
            ["vix_change_20d", ">", 0.0],
            ["real_yield_change_20d", "<", 0.0],
        ],
        "active_decision": "BACKUP_D4_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER",
        "inactive_decision": "WAIT_FOR_FRESH_BACKUP_D4_SIGNAL_NO_ORDER",
        "data_wait_decision": "WAIT_FOR_FRESH_BACKUP_D4_MACRO_DATA_NO_ORDER",
    },
}

BACKUP_PRIOR_METRICS = {
    "d1_backup": {"audit_pass": True, "trade_count": 36.0, "mean_net_return_bps": 176.4234614115411, "win_rate": 0.6111111111111112},
    "d4_backup": {"audit_pass": True, "trade_count": 37.0, "mean_net_return_bps": 165.06188961063145, "win_rate": 0.5945945945945946},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "na", "n/a"}:
        return None
    s = s.replace(",", "")
    try:
        f = float(s)
    except ValueError:
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def compare(value: Optional[float], op: str, threshold: float) -> Optional[bool]:
    if value is None:
        return None
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    raise ValueError(f"unsupported operator {op}")


def load_latest_macro_row(path: Path) -> Tuple[Dict[str, str], Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader]
        fieldnames = reader.fieldnames or []
    if not rows:
        raise ValueError(f"macro dataset is empty: {path}")
    date_col = "feature_date_utc" if "feature_date_utc" in fieldnames else "date_utc"
    rows.sort(key=lambda r: str(r.get(date_col, "")))
    latest = rows[-1]
    info = {
        "path": str(path),
        "rows": len(rows),
        "columns": fieldnames,
        "date_col": date_col,
        "latest_feature_date_utc": latest.get(date_col),
        "sha256": sha256_file(path),
    }
    return latest, info


def evaluate_rule(rule_key: str, rule: Dict[str, Any], row: Dict[str, str]) -> Dict[str, Any]:
    missing_columns = [c for c in rule["required_columns"] if c not in row]
    condition_results: List[Dict[str, Any]] = []
    failures: List[str] = []
    missing_values: List[str] = []
    active = True

    for col, op, threshold in rule["conditions"]:
        val = parse_float(row.get(col)) if col in row else None
        passed = compare(val, op, float(threshold)) if col in row else None
        condition_results.append({
            "column": col,
            "operator": op,
            "threshold": float(threshold),
            "value": val,
            "passed": passed,
        })
        if passed is None:
            active = False
            missing_values.append(col)
            failures.append(f"{col}:None{op}{float(threshold)}")
        elif not passed:
            active = False
            failures.append(f"{col}:{val}{op}{float(threshold)}")

    if missing_columns or missing_values:
        classification = f"{rule_key.upper()}_WAIT_DATA"
        decision = rule["data_wait_decision"]
    elif active:
        classification = f"{rule_key.upper()}_ACTIVE_REVIEW_ONLY"
        decision = rule["active_decision"]
    else:
        classification = f"{rule_key.upper()}_WAIT_SIGNAL_INACTIVE"
        decision = rule["inactive_decision"]

    return {
        "rule_key": rule_key,
        "label": rule["label"],
        "type": rule["type"],
        "horizon_trading_days": rule["horizon_trading_days"],
        "signal_active": active and not missing_columns and not missing_values,
        "decision": decision,
        "classification": classification,
        "missing_columns": missing_columns,
        "missing_values": missing_values,
        "rule_failures": failures,
        "condition_results": condition_results,
        "ticket_generation_allowed_here": False,
        **BACKUP_PRIOR_METRICS.get(rule_key, {}),
    }


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("# Stage66J3 Direct Readiness After Refresh")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append(f"- classification: `{summary['classification']}`")
    lines.append("")
    lines.append("## Macro dataset")
    lines.append("")
    mi = summary["macro_dataset"]
    lines.append(f"- rows: `{mi.get('rows')}`")
    lines.append(f"- latest_feature_date_utc: `{mi.get('latest_feature_date_utc')}`")
    lines.append(f"- path: `{mi.get('path')}`")
    lines.append("")
    lines.append("## Signal snapshot")
    for key in ["h64l_v2", "d3_h60", "d1_backup", "d4_backup"]:
        r = summary["rule_results"].get(key, {})
        lines.append("")
        lines.append(f"### {r.get('label', key)}")
        lines.append("")
        lines.append(f"- decision: `{r.get('decision')}`")
        lines.append(f"- classification: `{r.get('classification')}`")
        lines.append(f"- signal_active: `{r.get('signal_active')}`")
        if r.get("rule_failures"):
            lines.append(f"- rule_failures: `{' ; '.join(r['rule_failures'])}`")
        if r.get("missing_values"):
            lines.append(f"- missing_values: `{', '.join(r['missing_values'])}`")
    lines.append("")
    lines.append("## Issues")
    if summary.get("issues"):
        for issue in summary["issues"]:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    for hb in summary["hard_blocks"]:
        lines.append(f"- `{hb}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_ledger(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fields = [
        "generated_utc", "status", "decision", "classification", "feature_date_utc",
        "h64l_active", "d3_active", "d1_active", "d4_active", "active_backup_count",
    ]
    row = {
        "generated_utc": summary["generated_utc"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "feature_date_utc": summary["macro_dataset"].get("latest_feature_date_utc"),
        "h64l_active": summary["rule_results"]["h64l_v2"]["signal_active"],
        "d3_active": summary["rule_results"]["d3_h60"]["signal_active"],
        "d1_active": summary["rule_results"]["d1_backup"]["signal_active"],
        "d4_active": summary["rule_results"]["d4_backup"]["signal_active"],
        "active_backup_count": summary["backup_counts"]["active_backup_count"],
    }
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    macro_rel = config.get("macro_dataset", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    macro_path = root / macro_rel
    latest_row, macro_info = load_latest_macro_row(macro_path)
    rule_results = {key: evaluate_rule(key, rule, latest_row) for key, rule in RULES.items()}

    active_primary = [k for k in ["h64l_v2", "d3_h60"] if rule_results[k]["signal_active"]]
    active_backups = [k for k in ["d1_backup", "d4_backup"] if rule_results[k]["signal_active"]]
    data_wait = [k for k, v in rule_results.items() if v["missing_columns"] or v["missing_values"]]

    issues: List[str] = []
    # Missing central-bank demand is known/nonfatal after Stage67D6 because WGC file is cross-section only.
    if "h64l_v2" in data_wait and rule_results["h64l_v2"].get("missing_values") == ["central_bank_demand_tonnes_3m"]:
        issues.append("H64L_WAIT_CENTRAL_BANK_3M_DEMAND_SERIES_NOT_AVAILABLE")
    else:
        for k in data_wait:
            issues.append(f"{k.upper()}_WAIT_DATA")

    if active_backups:
        decision = "STAGE66J3_BACKUP_SIGNAL_ACTIVE_REQUIRES_STAGE66L_NO_ORDER"
        classification = "J3_BACKUP_ACTIVE_REVIEW_PATH_ONLY"
    elif active_primary:
        decision = "STAGE66J3_PRIMARY_OR_D3_SIGNAL_ACTIVE_REVIEW_ONLY_NO_ORDER"
        classification = "J3_PRIMARY_ACTIVE_REVIEW_PATH_ONLY"
    else:
        decision = "STAGE66J3_DIRECT_READINESS_WAIT_SIGNALS_NO_ORDER"
        classification = "J3_WAIT_ALL_INACTIVE_OR_DATA_WAIT"

    status = "STAGE66J3_COMPLETE_NO_PROMOTION"

    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config_path.relative_to(root)) if config_path.is_relative_to(root) else str(config_path),
        "generated_utc": utc_now(),
        "status": status,
        "decision": decision,
        "classification": classification,
        "macro_dataset": macro_info,
        "rule_results": rule_results,
        "signal_snapshot": {
            "h64l_v2": rule_results["h64l_v2"],
            "d3_h60": rule_results["d3_h60"],
        },
        "backup_readiness": [rule_results["d1_backup"], rule_results["d4_backup"]],
        "backup_counts": {
            "configured_backup_count": 2,
            "ready_backup_count": 2,
            "active_backup_count": len(active_backups),
        },
        "active_primary_rule_ids": active_primary,
        "active_backup_rule_ids": active_backups,
        "ticket_paths": [],
        "issues": issues,
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "No order may be placed from Stage66J3.",
            "Stage66J3 is a direct readiness collector after Stage67D6 and does not invoke older child scripts.",
            "If H64L or D3 becomes active, review only; use the explicit no-broker ticket generator path before any later authorization package.",
            "If a backup signal becomes active, build Stage66L no-broker backup dry-run ticket generator before any review.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage66j3_direct_readiness_after_refresh_summary.json"),
            "report_md": str(out_dir / "stage66j3_direct_readiness_after_refresh_report.md"),
            "ledger_csv": "data/forward_shadow/stage66j3_direct_readiness_after_refresh_ledger.csv",
        },
    }

    summary_path = out_dir / "stage66j3_direct_readiness_after_refresh_summary.json"
    report_path = out_dir / "stage66j3_direct_readiness_after_refresh_report.md"
    ledger_path = root / "data/forward_shadow/stage66j3_direct_readiness_after_refresh_ledger.csv"
    write_json(summary_path, summary)
    write_report(report_path, summary)
    append_ledger(ledger_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/stage66j3_direct_readiness_after_refresh.json")
    parser.add_argument("--out", default="reports/stage66j3_direct_readiness_after_refresh")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)

    try:
        summary = run(root, config_path, out_dir)
        print(json.dumps({
            "stage": STAGE,
            "status": summary["status"],
            "decision": summary["decision"],
            "classification": summary["classification"],
            "active_backup_count": summary["backup_counts"]["active_backup_count"],
            "summary_json": summary["outputs"]["summary_json"],
            "report_md": summary["outputs"]["report_md"],
        }, indent=2))
        return 0
    except Exception as exc:
        out_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "stage": STAGE,
            "root": str(root),
            "config": str(config_path),
            "generated_utc": utc_now(),
            "status": "STAGE66J3_STOPPED_NO_PROMOTION",
            "decision": "STAGE66J3_INPUT_OR_DATA_ISSUE_STOP_NO_ORDER",
            "classification": "J3_STOP_ISSUES",
            "issues": [f"EXCEPTION:{type(exc).__name__}:{exc}"],
            "hard_blocks": HARD_BLOCKS,
        }
        write_json(out_dir / "stage66j3_direct_readiness_after_refresh_summary.json", summary)
        write_report(out_dir / "stage66j3_direct_readiness_after_refresh_report.md", summary)
        print(json.dumps({
            "stage": STAGE,
            "status": summary["status"],
            "decision": summary["decision"],
            "classification": summary["classification"],
            "error": str(exc),
        }, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
