#!/usr/bin/env python3
"""Stage68F robust policy shadow selector.

No-order, no-broker, no-paper selector for the Stage68E robustness-selected
cluster policy candidate. It evaluates the latest macro row, applies the locked
priority order, and appends a local forward-shadow ledger row.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

STAGE = "Stage68F_ROBUST_POLICY_SHADOW_SELECTOR"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def compare(value: Optional[float], operator: str, threshold: float) -> Optional[bool]:
    if value is None:
        return None
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    raise ValueError(f"Unsupported operator: {operator}")


def evaluate_rule(row: pd.Series, rule_key: str, rule_cfg: Dict[str, Any]) -> Dict[str, Any]:
    condition_results: List[Dict[str, Any]] = []
    missing_columns: List[str] = []
    missing_values: List[str] = []
    failures: List[str] = []

    for cond in rule_cfg.get("conditions", []):
        col = cond["column"]
        op = cond["operator"]
        threshold = float(cond["threshold"])
        if col not in row.index:
            missing_columns.append(col)
            passed = None
            value = None
        else:
            value = to_float(row[col])
            if value is None:
                missing_values.append(col)
            passed = compare(value, op, threshold)
        condition_results.append({
            "column": col,
            "operator": op,
            "threshold": threshold,
            "value": value,
            "passed": passed,
        })
        if passed is not True:
            failures.append(f"{col}:{value}{op}{threshold}")

    signal_active = bool(condition_results) and all(c["passed"] is True for c in condition_results)
    return {
        "rule_key": rule_key,
        "label": rule_cfg.get("label", rule_key),
        "type": rule_cfg.get("type", "unknown"),
        "horizon_trading_days": rule_cfg.get("horizon_trading_days"),
        "signal_active": signal_active,
        "missing_columns": missing_columns,
        "missing_values": missing_values,
        "rule_failures": failures,
        "condition_results": condition_results,
    }


def latest_row(df: pd.DataFrame, date_col: str = "feature_date_utc") -> pd.Series:
    if date_col not in df.columns:
        raise ValueError(f"Macro dataset missing date column: {date_col}")
    tmp = df.copy()
    tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce", utc=True)
    tmp = tmp.dropna(subset=[date_col]).sort_values(date_col)
    if tmp.empty:
        raise ValueError("Macro dataset has no valid dated rows")
    return tmp.iloc[-1]


def iso_date(value: Any) -> Optional[str]:
    dt = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(dt):
        return None
    return dt.date().isoformat()


def append_ledger(root: Path, row: Dict[str, Any]) -> str:
    ledger = root / "data" / "forward_shadow" / "stage68f_robust_policy_shadow_selector_ledger.csv"
    ensure_dir(ledger.parent)
    fieldnames = [
        "generated_utc",
        "feature_date_utc",
        "policy_id",
        "policy_signal_active",
        "selected_rule_key",
        "selected_rule_label",
        "selected_rule_horizon_trading_days",
        "active_allowed_rule_ids",
        "active_reference_only_rule_ids",
        "decision",
        "classification",
    ]
    write_header = not ledger.exists()
    with ledger.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fieldnames})
    return str(ledger)


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Stage68F Robust Policy Shadow Selector")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append(f"- classification: `{summary['classification']}`")
    lines.append(f"- policy_id: `{summary['policy']['policy_id']}`")
    lines.append("")
    lines.append("## Latest macro row")
    lines.append("")
    md = summary["macro_dataset"]
    lines.append(f"- rows: `{md['rows']}`")
    lines.append(f"- latest_feature_date_utc: `{md['latest_feature_date_utc']}`")
    lines.append(f"- path: `{md['path']}`")
    lines.append("")
    lines.append("## Policy selection")
    lines.append("")
    sel = summary["policy_selection"]
    lines.append(f"- policy_signal_active: `{sel['policy_signal_active']}`")
    lines.append(f"- selected_rule_key: `{sel.get('selected_rule_key')}`")
    lines.append(f"- selected_rule_label: `{sel.get('selected_rule_label')}`")
    lines.append(f"- active_allowed_rule_ids: `{', '.join(sel.get('active_allowed_rule_ids', []))}`")
    lines.append(f"- active_reference_only_rule_ids: `{', '.join(sel.get('active_reference_only_rule_ids', []))}`")
    lines.append("")
    lines.append("## Rule snapshot")
    lines.append("")
    for key, rr in summary["rule_results"].items():
        lines.append(f"### `{key}`")
        lines.append("")
        lines.append(f"- signal_active: `{rr['signal_active']}`")
        if rr.get("rule_failures"):
            lines.append(f"- rule_failures: `{' ; '.join(rr['rule_failures'])}`")
        lines.append("")
    lines.append("## Issues")
    lines.append("")
    issues = summary.get("issues", [])
    if issues:
        for issue in issues:
            lines.append(f"- `{issue}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for hb in summary.get("hard_blocks", []):
        lines.append(f"- `{hb}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    cfg = load_json(config_path)
    macro_path = root / cfg["macro_dataset"]
    issues: List[str] = []
    if not macro_path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {macro_path}")
    df = pd.read_csv(macro_path)
    row = latest_row(df)
    feature_date = iso_date(row.get("feature_date_utc"))

    rules: Dict[str, Dict[str, Any]] = cfg["rules"]
    rule_results: Dict[str, Dict[str, Any]] = {}
    for rule_key, rule_cfg in rules.items():
        rule_results[rule_key] = evaluate_rule(row, rule_key, rule_cfg)

    priority = list(cfg.get("priority", []))
    allow_rules = set(cfg.get("allow_rules", []))
    ref_rules = set(cfg.get("reference_only_rules", []))
    active_allowed = [rk for rk in priority if rk in allow_rules and rule_results.get(rk, {}).get("signal_active")]
    active_reference = [rk for rk in cfg.get("reference_only_rules", []) if rule_results.get(rk, {}).get("signal_active")]

    selected_key: Optional[str] = active_allowed[0] if active_allowed else None
    selected_rule = rule_results[selected_key] if selected_key else None
    policy_signal_active = selected_key is not None

    if policy_signal_active:
        decision = "STAGE68F_POLICY_SIGNAL_ACTIVE_REVIEW_ONLY_NO_ORDER"
        classification = "S68F_POLICY_SIGNAL_ACTIVE_REVIEW_ONLY"
    else:
        decision = "STAGE68F_POLICY_WAIT_SIGNAL_NO_ORDER"
        classification = "S68F_POLICY_WAIT_SIGNAL_INACTIVE"

    generated = utc_now()
    ledger_row = {
        "generated_utc": generated,
        "feature_date_utc": feature_date,
        "policy_id": cfg.get("policy_id"),
        "policy_signal_active": policy_signal_active,
        "selected_rule_key": selected_key or "",
        "selected_rule_label": selected_rule.get("label") if selected_rule else "",
        "selected_rule_horizon_trading_days": selected_rule.get("horizon_trading_days") if selected_rule else "",
        "active_allowed_rule_ids": ";".join(active_allowed),
        "active_reference_only_rule_ids": ";".join(active_reference),
        "decision": decision,
        "classification": classification,
    }
    ledger_path = append_ledger(root, ledger_row)

    ensure_dir(out_dir)
    summary = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config_path),
        "generated_utc": generated,
        "status": "STAGE68F_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "policy": {
            "policy_id": cfg.get("policy_id"),
            "policy_source": cfg.get("policy_source"),
            "priority": priority,
            "allow_rules": list(cfg.get("allow_rules", [])),
            "reference_only_rules": list(cfg.get("reference_only_rules", [])),
            "cluster_window_calendar_days": cfg.get("cluster_window_calendar_days"),
        },
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "columns": list(df.columns),
            "date_col": "feature_date_utc",
            "latest_feature_date_utc": feature_date,
            "sha256": sha256_file(macro_path),
        },
        "policy_selection": {
            "policy_signal_active": policy_signal_active,
            "selected_rule_key": selected_key,
            "selected_rule_label": selected_rule.get("label") if selected_rule else None,
            "selected_rule_horizon_trading_days": selected_rule.get("horizon_trading_days") if selected_rule else None,
            "active_allowed_rule_ids": active_allowed,
            "active_reference_only_rule_ids": active_reference,
            "ticket_generation_allowed_here": False,
        },
        "rule_results": rule_results,
        "issues": issues,
        "hard_blocks": cfg.get("hard_blocks", []),
        "operator_instructions": [
            "Stage68F is a no-order shadow selector and cannot authorize orders.",
            "If the policy signal becomes active, perform manual review only.",
            "D1 is reference-only and is excluded from the selected robustness policy.",
            "Broker, EA, paper-live, and live paths remain blocked.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage68f_robust_policy_shadow_selector_summary.json"),
            "report_md": str(out_dir / "stage68f_robust_policy_shadow_selector_report.md"),
            "ledger_csv": ledger_path,
        },
    }

    (out_dir / "stage68f_robust_policy_shadow_selector_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(out_dir / "stage68f_robust_policy_shadow_selector_report.md", summary)
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--root", default=".")
    p.add_argument("--config", default="configs/stage68f_robust_policy_shadow_selector.json")
    p.add_argument("--out", default="reports/stage68f_robust_policy_shadow_selector")
    args = p.parse_args()
    root = Path(args.root).resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    summary = run(root, config_path, out_dir)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "policy_signal_active": summary["policy_selection"]["policy_signal_active"],
        "selected_rule_key": summary["policy_selection"]["selected_rule_key"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
