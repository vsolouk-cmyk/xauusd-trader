#!/usr/bin/env python3
"""Stage78 portfolio observer bridge for XAUUSD K06/K03/K07.

No order, no broker, no EA promotion. Produces key,value CSV for observer-only MT5 EA.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

RULES = [
    {
        "rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120",
        "label": "K06_RESILIENT_GOLD_VS_DXY",
        "priority": 1,
        "horizon_trading_days": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_ret_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K03_SAFE_HAVEN_REALYIELD_H120",
        "label": "K03_WGC_RISK_UNCERTAINTY_SAFE_HAVEN",
        "priority": 2,
        "horizon_trading_days": 120,
        "conditions": [
            ("vix_change_20d", ">", 0.0),
            ("real_yield_change_20d", "<", 0.0),
        ],
    },
    {
        "rule_id": "K07_DXY_TREND_RELIEF_GOLD_TREND_H120",
        "label": "K07_DXY_TREND_RELIEF_GOLD_TREND",
        "priority": 3,
        "horizon_trading_days": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_sma20_over_50", "<", 0.0),
        ],
    },
]

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_SEND_IN_EA",
    "OBSERVER_ONLY_EA",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE78",
    "NO_THRESHOLD_TUNING_FROM_PORTFOLIO_BRIDGE",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    return p.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_last_csv_row(path: Path, date_col: str) -> Tuple[List[str], Dict[str, str], int, str, str]:
    rows = 0
    last: Dict[str, str] | None = None
    min_date = ""
    max_date = ""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        if not fields:
            raise RuntimeError(f"empty csv or missing header: {path}")
        if date_col not in fields:
            raise RuntimeError(f"date_col {date_col!r} not in macro columns")
        for row in reader:
            rows += 1
            d = (row.get(date_col) or "").strip()
            if d:
                min_date = min_date or d
                max_date = d
            last = row
    if last is None:
        raise RuntimeError(f"no rows in macro csv: {path}")
    return fields, last, rows, min_date, max_date


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def eval_condition(row: Dict[str, str], col: str, op: str, threshold: float) -> Dict[str, Any]:
    val = to_float(row.get(col))
    if val is None:
        return {
            "column": col,
            "operator": op,
            "threshold": threshold,
            "value": None,
            "passed": False,
            "reason": "missing_or_non_numeric",
        }
    if op == ">":
        passed = val > threshold
    elif op == "<":
        passed = val < threshold
    elif op == ">=":
        passed = val >= threshold
    elif op == "<=":
        passed = val <= threshold
    else:
        raise ValueError(f"unsupported operator: {op}")
    return {
        "column": col,
        "operator": op,
        "threshold": threshold,
        "value": val,
        "passed": passed,
        "reason": "ok" if passed else f"{val}{op}{threshold}",
    }


def eval_rule(row: Dict[str, str], rule: Dict[str, Any]) -> Dict[str, Any]:
    checks = [eval_condition(row, *cond) for cond in rule["conditions"]]
    failures = [f"{c['column']}:{c['reason']}" for c in checks if not c["passed"]]
    missing_columns = [c["column"] for c in checks if c["reason"] == "missing_or_non_numeric"]
    return {
        "rule_id": rule["rule_id"],
        "label": rule["label"],
        "priority": rule["priority"],
        "horizon_trading_days": rule["horizon_trading_days"],
        "signal_active": not failures,
        "condition_results": checks,
        "rule_failures": failures,
        "missing_columns": missing_columns,
    }


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    s = str(value)
    return s.replace("\n", " ").replace("\r", " ").replace(",", ";")


def write_key_value_csv(path: Path, pairs: Iterable[Tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("key,value\n")
        for k, v in pairs:
            f.write(f"{clean_value(k)},{clean_value(v)}\n")


def stage_lock(root: Path, stage: str, rel_path: str, required_disposition: str) -> Dict[str, Any]:
    path = root / rel_path
    result: Dict[str, Any] = {
        "stage": stage,
        "path": str(path),
        "exists": path.exists(),
        "read_ok": False,
        "required_disposition": required_disposition,
        "actual_disposition": None,
        "matches_required": False,
        "issue": None,
    }
    if not path.exists():
        result["issue"] = "MISSING_LOCK_FILE"
        return result
    try:
        data = load_json(path)
        result["read_ok"] = True
        result["actual_disposition"] = data.get("disposition")
        result["matches_required"] = data.get("disposition") == required_disposition
    except Exception as exc:  # pragma: no cover
        result["issue"] = f"READ_ERROR:{exc}"
    return result


def main() -> None:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    config = load_json(config_path)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    macro_path = root / config["macro_path"]
    date_col = config.get("date_col", "feature_date_utc")
    price_col = config.get("price_col", "gold_close")
    fields, latest_row, row_count, min_date, max_date = read_last_csv_row(macro_path, date_col)
    latest_date = (latest_row.get(date_col) or "").strip()

    rule_results = [eval_rule(latest_row, rule) for rule in RULES]
    active_rules = [r for r in rule_results if r["signal_active"]]
    active_rules.sort(key=lambda r: r["priority"])
    selected = active_rules[0] if active_rules else None

    locks = [
        stage_lock(root, "Stage77B", config["stage77b_summary_path"], "PORTFOLIO_READY_WITH_K06_PLUS_COMPLEMENTS"),
    ]
    lock_pass_count = sum(1 for x in locks if x["matches_required"])

    bridge_csv = root / config.get("bridge_csv_path", "data/mt5_bridge/portfolio_observer_signal.csv")
    mode = "OBSERVER_ONLY_NO_TRADE"
    pairs: List[Tuple[str, Any]] = [
        ("schema_version", "stage78_portfolio_observer_v1"),
        ("stage", "Stage78_PORTFOLIO_OBSERVER_BRIDGE"),
        ("generated_utc", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("feature_date", latest_date),
        ("portfolio_mode", mode),
        ("mode", mode),
        ("execution_allowed", False),
        ("order_authorized", False),
        ("broker_connection_allowed", False),
        ("rule_count", len(rule_results)),
        ("active_rule_count", len(active_rules)),
        ("any_signal_active", bool(active_rules)),
        ("selected_rule_id", selected["rule_id"] if selected else ""),
        ("selected_label", selected["label"] if selected else ""),
        ("selected_horizon_trading_days", selected["horizon_trading_days"] if selected else ""),
    ]
    for r in rule_results:
        prefix = r["rule_id"]
        pairs.extend([
            (f"{prefix}_label", r["label"]),
            (f"{prefix}_signal_active", r["signal_active"]),
            (f"{prefix}_failures", "|".join(r["rule_failures"])),
        ])
    write_key_value_csv(bridge_csv, pairs)

    issues = []
    if lock_pass_count != len(locks):
        issues.append("PORTFOLIO_LOCK_NOT_READY")
    if price_col not in fields:
        issues.append(f"PRICE_COLUMN_MISSING:{price_col}")

    decision = "STAGE78_PORTFOLIO_OBSERVER_READY_ACTIVE_REVIEW_ONLY_NO_ORDER" if active_rules else "STAGE78_PORTFOLIO_OBSERVER_READY_WAIT_SIGNAL_NO_ORDER"
    if issues:
        decision = "STAGE78_PORTFOLIO_OBSERVER_BLOCKED_NO_ORDER"

    summary: Dict[str, Any] = {
        "stage": "Stage78_PORTFOLIO_OBSERVER_BRIDGE",
        "root": str(root),
        "config": str(config_path),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "STAGE78_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": "S78_PORTFOLIO_OBSERVER_READY" if not issues else "S78_PORTFOLIO_OBSERVER_BLOCKED",
        "disposition": "PORTFOLIO_OBSERVER_READY_NO_ORDER" if not issues else "PORTFOLIO_OBSERVER_BLOCKED_NO_ORDER",
        "bridge_role": "MT5 portfolio observer-only bridge. The EA may read/display signals but cannot trade.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": row_count,
            "date_col": date_col,
            "price_col": price_col,
            "min_date": min_date,
            "max_date": max_date,
            "sha256": sha256_path(macro_path),
        },
        "lock_checks": locks,
        "lock_pass_count": lock_pass_count,
        "lock_total_count": len(locks),
        "latest_feature_date_utc": latest_date,
        "rule_results": rule_results,
        "active_rule_ids": [r["rule_id"] for r in active_rules],
        "selected_rule_id": selected["rule_id"] if selected else None,
        "selected_label": selected["label"] if selected else None,
        "bridge_csv": {
            "path": str(bridge_csv),
            "written": bridge_csv.exists(),
            "mode": mode,
            "any_signal_active_exported": bool(active_rules),
            "order_authorized": False,
            "broker_connection_allowed": False,
        },
        "issues": issues,
        "cautions": [],
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage78_portfolio_observer_bridge_summary.json"),
            "report_md": str(out_dir / "stage78_portfolio_observer_bridge_report.md"),
            "bridge_csv": str(bridge_csv),
        },
    }

    summary_path = out_dir / "stage78_portfolio_observer_bridge_summary.json"
    report_path = out_dir / "stage78_portfolio_observer_bridge_report.md"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    lines = [
        "# Stage78 Portfolio Observer Bridge",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Latest portfolio signal",
        f"- latest_feature_date_utc: `{latest_date}`",
        f"- active_rule_ids: `{','.join(summary['active_rule_ids'])}`",
        f"- selected_rule_id: `{summary['selected_rule_id']}`",
        "",
        "## Rule snapshot",
    ]
    for r in rule_results:
        lines.append(f"- `{r['rule_id']}` active=`{r['signal_active']}` failures=`{'|'.join(r['rule_failures'])}`")
    lines.extend([
        "",
        "## Bridge CSV",
        f"- path: `{bridge_csv}`",
        f"- written: `{bridge_csv.exists()}`",
        "",
        "## Issues",
        f"- {', '.join(issues) if issues else 'none'}",
        "",
        "## Hard blocks",
    ])
    for hb in HARD_BLOCKS:
        lines.append(f"- `{hb}`")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
