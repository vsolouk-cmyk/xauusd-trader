#!/usr/bin/env python3
"""Stage87 unified observer bridge.

Observer-only bridge for the Stage85 five-rule portfolio. It writes a key,value CSV
for MT5 display and never authorizes execution.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "K06_RESILIENT_GOLD_VS_DXY_H120",
        "short_id": "K06",
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
        "short_id": "K03",
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
        "short_id": "K07",
        "label": "K07_DXY_TREND_RELIEF_GOLD_TREND",
        "priority": 3,
        "horizon_trading_days": 120,
        "conditions": [
            ("gold_sma20_over_50", ">", 0.0),
            ("dxy_sma20_over_50", "<", 0.0),
        ],
    },
    {
        "rule_id": "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "short_id": "S83_14",
        "label": "REALYIELD_120D_DOWN_GOLD_NOT_TRENDING",
        "priority": 4,
        "horizon_trading_days": 120,
        "conditions": [
            ("real_yield_change_120d", "<", 0.0),
            ("gold_sma20_over_50", "<", 0.0),
        ],
    },
    {
        "rule_id": "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
        "short_id": "S83_13",
        "label": "DXY_120D_DOWN_GOLD_NOT_TRENDING",
        "priority": 5,
        "horizon_trading_days": 120,
        "conditions": [
            ("dxy_ret_120d", "<", 0.0),
            ("gold_sma20_over_50", "<", 0.0),
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
    "NO_ORDER_AUTHORIZATION_FROM_STAGE87",
    "NO_THRESHOLD_TUNING_FROM_UNIFIED_OBSERVER_BRIDGE",
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


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def read_macro_rows(path: Path, date_col: str) -> Tuple[List[str], List[Dict[str, str]], str, str]:
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        if not fields:
            raise RuntimeError(f"empty csv or missing header: {path}")
        if date_col not in fields:
            raise RuntimeError(f"date_col {date_col!r} not in macro columns")
        for row in reader:
            rows.append(dict(row))
    if not rows:
        raise RuntimeError(f"no rows in macro csv: {path}")
    min_date = str(rows[0].get(date_col, "")).strip()
    max_date = str(rows[-1].get(date_col, "")).strip()
    return fields, rows, min_date, max_date


def get_num(row: Dict[str, str], col: str) -> float | None:
    return to_float(row.get(col))


def put_num(row: Dict[str, str], col: str, value: float | None) -> None:
    row[col] = "" if value is None else repr(float(value))


def add_derived_features(rows: List[Dict[str, str]]) -> List[str]:
    added: List[str] = []
    n = len(rows)

    def ensure_return(col_out: str, base_col: str, lag: int) -> None:
        nonlocal added
        if any(str(r.get(col_out, "")).strip() for r in rows):
            return
        for i, r in enumerate(rows):
            if i < lag:
                put_num(r, col_out, None)
                continue
            now = get_num(r, base_col)
            prev = get_num(rows[i - lag], base_col)
            if now is None or prev is None or prev == 0:
                put_num(r, col_out, None)
            else:
                put_num(r, col_out, (now / prev) - 1.0)
        added.append(col_out)

    def ensure_change(col_out: str, base_col: str, lag: int) -> None:
        nonlocal added
        if any(str(r.get(col_out, "")).strip() for r in rows):
            return
        for i, r in enumerate(rows):
            if i < lag:
                put_num(r, col_out, None)
                continue
            now = get_num(r, base_col)
            prev = get_num(rows[i - lag], base_col)
            if now is None or prev is None:
                put_num(r, col_out, None)
            else:
                put_num(r, col_out, now - prev)
        added.append(col_out)

    # Do not assume all upstream datasets already contain long-lookback features.
    if n:
        ensure_return("dxy_ret_120d", "dxy", 120)
        ensure_return("dxy_ret_60d", "dxy", 60)
        ensure_change("real_yield_change_120d", "real_yield", 120)
        ensure_change("real_yield_change_60d", "real_yield", 60)
        ensure_return("gold_ret_120d", "gold_close", 120)
        ensure_return("gold_ret_60d", "gold_close", 60)
    return added


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
        "short_id": rule["short_id"],
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
    fields, rows, min_date, max_date = read_macro_rows(macro_path, date_col)
    derived_features_added = add_derived_features(rows)
    latest_row = rows[-1]
    latest_date = str(latest_row.get(date_col, "")).strip()

    rule_results = [eval_rule(latest_row, rule) for rule in RULES]
    active_rules = sorted([r for r in rule_results if r["signal_active"]], key=lambda r: r["priority"])
    selected = active_rules[0] if active_rules else None

    locks = [
        stage_lock(root, "Stage85", config["stage85_summary_path"], "PORTFOLIO_INCREMENT_SELECTED_FOR_STAGE86_OBSERVER_EXPANSION"),
    ]
    lock_pass_count = sum(1 for x in locks if x["matches_required"])

    bridge_csv = root / config.get("bridge_csv_path", "data/mt5_bridge/unified_observer_signal.csv")
    mode = "OBSERVER_ONLY_NO_TRADE"
    pairs: List[Tuple[str, Any]] = [
        ("schema_version", "stage87_unified_observer_v1"),
        ("stage", "Stage87_UNIFIED_OBSERVER_BRIDGE"),
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
        ("primary_rule_id", "K06_RESILIENT_GOLD_VS_DXY_H120"),
        ("primary_label", "K06_RESILIENT_GOLD_VS_DXY"),
    ]
    k06_result = next((r for r in rule_results if r["short_id"] == "K06"), None)
    if k06_result is not None:
        pairs.extend([
            ("primary_signal_active", k06_result["signal_active"]),
            ("primary_failures", "|".join(k06_result["rule_failures"])),
            ("k06_signal_active", k06_result["signal_active"]),
            ("k06_failures", "|".join(k06_result["rule_failures"])),
        ])

    for r in rule_results:
        prefix = r["rule_id"]
        short = r["short_id"]
        failures = "|".join(r["rule_failures"])
        pairs.extend([
            (f"{prefix}_label", r["label"]),
            (f"{prefix}_signal_active", r["signal_active"]),
            (f"{prefix}_failures", failures),
            (f"{short}_rule_id", r["rule_id"]),
            (f"{short}_label", r["label"]),
            (f"{short}_active", r["signal_active"]),
            (f"{short}_failures", failures),
        ])
    write_key_value_csv(bridge_csv, pairs)

    issues: List[str] = []
    if lock_pass_count != len(locks):
        issues.append("STAGE85_LOCK_NOT_READY")
    if price_col not in fields:
        issues.append(f"PRICE_COLUMN_MISSING:{price_col}")

    decision = "STAGE87_UNIFIED_OBSERVER_READY_ACTIVE_REVIEW_ONLY_NO_ORDER" if active_rules else "STAGE87_UNIFIED_OBSERVER_READY_WAIT_SIGNAL_NO_ORDER"
    if issues:
        decision = "STAGE87_UNIFIED_OBSERVER_BLOCKED_NO_ORDER"

    summary: Dict[str, Any] = {
        "stage": "Stage87_UNIFIED_OBSERVER_BRIDGE",
        "root": str(root),
        "config": str(config_path),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "STAGE87_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": "S87_UNIFIED_OBSERVER_READY" if not issues else "S87_UNIFIED_OBSERVER_BLOCKED",
        "disposition": "UNIFIED_OBSERVER_READY_NO_ORDER" if not issues else "UNIFIED_OBSERVER_BLOCKED_NO_ORDER",
        "bridge_role": "MT5 unified observer-only bridge. The EA may read/display signals but cannot trade.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": len(rows),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": min_date,
            "max_date": max_date,
            "sha256": sha256_path(macro_path),
            "derived_features_added": derived_features_added,
        },
        "lock_checks": locks,
        "lock_pass_count": lock_pass_count,
        "lock_total_count": len(locks),
        "latest_feature_date_utc": latest_date,
        "unified_portfolio_rule_ids": [r["rule_id"] for r in RULES],
        "new_stage85_increment_rule_ids": [
            "S83_14_REALYIELD_120D_DOWN_GOLD_NOT_TRENDING_H120",
            "S83_13_DXY_120D_DOWN_GOLD_NOT_TRENDING_H120",
        ],
        "rule_results": rule_results,
        "active_rule_ids": [r["rule_id"] for r in active_rules],
        "selected_rule_id": selected["rule_id"] if selected else None,
        "selected_label": selected["label"] if selected else None,
        "bridge_csv": {
            "path": str(bridge_csv),
            "written": bridge_csv.exists(),
            "schema_version": "stage87_unified_observer_v1",
            "mode": mode,
            "any_signal_active_exported": bool(active_rules),
            "order_authorized": False,
            "broker_connection_allowed": False,
        },
        "issues": issues,
        "cautions": [],
        "hard_blocks": HARD_BLOCKS,
        "outputs": {
            "summary_json": str(out_dir / "stage87_unified_observer_bridge_summary.json"),
            "report_md": str(out_dir / "stage87_unified_observer_bridge_report.md"),
            "bridge_csv": str(bridge_csv),
        },
    }

    summary_path = out_dir / "stage87_unified_observer_bridge_summary.json"
    report_path = out_dir / "stage87_unified_observer_bridge_report.md"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    lines = [
        "# Stage87 Unified Observer Bridge",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Latest unified observer signal",
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
