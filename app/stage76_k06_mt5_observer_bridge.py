#!/usr/bin/env python3
"""Stage76 K06 MT5 observer-only bridge.

Builds a no-order CSV bridge row for an MT5 observer EA. This stage is deliberately
not an order generator and never authorizes broker, EA, paper-live, or live orders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd


@dataclass
class ConditionResult:
    column: str
    operator: str
    threshold: float
    value: Any
    passed: bool
    reason: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_macro(path: Path, date_col: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path)
    if date_col not in df.columns:
        raise ValueError(f"date column missing: {date_col}")
    df[date_col] = pd.to_datetime(df[date_col], utc=True, errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    if df.empty:
        raise ValueError("macro dataset has no valid dated rows")
    return df


def eval_condition(value: Any, operator: str, threshold: float) -> Tuple[bool, str]:
    try:
        v = float(value)
    except Exception:
        return False, "missing_or_non_numeric"
    if operator == ">":
        ok = v > threshold
    elif operator == "<":
        ok = v < threshold
    elif operator == ">=":
        ok = v >= threshold
    elif operator == "<=":
        ok = v <= threshold
    elif operator == "==":
        ok = v == threshold
    else:
        raise ValueError(f"unsupported operator: {operator}")
    return ok, "ok" if ok else f"{v}{operator}{threshold}"


def evaluate_latest(row: pd.Series, conditions: Iterable[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, Any]], List[str], List[str], List[str]]:
    results: List[Dict[str, Any]] = []
    failures: List[str] = []
    missing_columns: List[str] = []
    missing_values: List[str] = []
    for cond in conditions:
        col = str(cond["column"])
        op = str(cond["operator"])
        thr = float(cond["threshold"])
        if col not in row.index:
            missing_columns.append(col)
            result = ConditionResult(col, op, thr, None, False, "missing_column")
        else:
            val = row[col]
            if pd.isna(val):
                missing_values.append(col)
                result = ConditionResult(col, op, thr, None, False, "missing_value")
            else:
                ok, reason = eval_condition(val, op, thr)
                result = ConditionResult(col, op, thr, float(val), ok, reason)
        d = {
            "column": result.column,
            "operator": result.operator,
            "threshold": result.threshold,
            "value": result.value,
            "passed": result.passed,
            "reason": result.reason,
        }
        results.append(d)
        if not result.passed:
            failures.append(f"{result.column}:{result.value}{result.operator}{result.threshold}")
    active = (not missing_columns) and (not missing_values) and all(bool(x["passed"]) for x in results)
    return active, results, failures, missing_columns, missing_values


def check_locks(root: Path, locks: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    out: List[Dict[str, Any]] = []
    all_ok = True
    for lock in locks:
        rel = Path(str(lock["summary_path"]))
        path = root / rel
        item: Dict[str, Any] = {
            "stage": lock.get("stage"),
            "path": str(path),
            "exists": path.exists(),
            "read_ok": False,
            "required_disposition": lock.get("required_disposition"),
            "actual_disposition": None,
            "matches_required": False,
            "issue": None,
        }
        if not path.exists():
            item["issue"] = "LOCK_FILE_MISSING"
            all_ok = False
        else:
            try:
                data = read_json(path)
                item["read_ok"] = True
                item["actual_disposition"] = data.get("disposition")
                item["matches_required"] = item["actual_disposition"] == item["required_disposition"]
                if not item["matches_required"]:
                    item["issue"] = "LOCK_DISPOSITION_MISMATCH"
                    all_ok = False
            except Exception as exc:  # pragma: no cover
                item["issue"] = f"LOCK_READ_ERROR:{exc}"
                all_ok = False
        out.append(item)
    return out, all_ok


def csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def write_bridge_csv(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "schema_version",
        "generated_utc",
        "stage",
        "thesis_id",
        "family",
        "direction",
        "signal_date_utc",
        "signal_active",
        "price_reference",
        "horizon_trading_days",
        "entry_cooldown_trading_days",
        "condition_results_json",
        "rule_failures",
        "missing_columns",
        "missing_values",
        "order_authorized",
        "broker_connection_allowed",
        "ea_mode",
        "macro_sha256",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow({k: csv_safe(row.get(k)) for k in fields})


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    latest = summary.get("latest_signal_snapshot", {})
    bridge = summary.get("bridge_csv", {})
    lines = [
        "# Stage76 K06 MT5 Observer Bridge",
        "",
        "## Decision",
        f"- status: `{summary.get('status')}`",
        f"- decision: `{summary.get('decision')}`",
        f"- classification: `{summary.get('classification')}`",
        f"- disposition: `{summary.get('disposition')}`",
        "",
        "## Bridge role",
        "Creates a CSV bridge and observer-only MT5 EA handoff. It does not authorize orders.",
        "",
        "## Latest K06 signal",
        f"- latest_feature_date_utc: `{latest.get('latest_feature_date_utc')}`",
        f"- signal_active: `{latest.get('signal_active')}`",
        f"- rule_failures: `{'; '.join(latest.get('rule_failures', []))}`",
        "",
        "## Bridge CSV",
        f"- path: `{bridge.get('path')}`",
        f"- written: `{bridge.get('written')}`",
        "",
        "## Lock checks",
    ]
    for lock in summary.get("lock_checks", []):
        lines.append(f"- `{lock.get('stage')}`: exists=`{lock.get('exists')}`, read_ok=`{lock.get('read_ok')}`, matches_required=`{lock.get('matches_required')}`, actual=`{lock.get('actual_disposition')}`")
    lines += [
        "",
        "## Issues",
    ]
    issues = summary.get("issues", [])
    lines += [f"- {x}" for x in issues] if issues else ["- none"]
    lines += [
        "",
        "## Hard blocks",
    ]
    lines += [f"- `{x}`" for x in summary.get("hard_blocks", [])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(root: Path, config: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    stage = "Stage76_K06_MT5_OBSERVER_BRIDGE"
    macro_path = root / config["macro_path"]
    df = load_macro(macro_path, config.get("date_col", "feature_date_utc"))
    latest = df.iloc[-1]
    date_col = config.get("date_col", "feature_date_utc")
    price_col = config.get("price_col", "gold_close")
    latest_date = latest[date_col].date().isoformat()
    current_date = datetime.now(timezone.utc).date()
    age_days = (current_date - latest[date_col].date()).days
    fresh = age_days <= int(config.get("max_stale_calendar_days", 7))
    price_ref = None if price_col not in latest.index or pd.isna(latest[price_col]) else float(latest[price_col])
    signal_active, cond_results, failures, missing_cols, missing_vals = evaluate_latest(latest, config["conditions"])
    lock_checks, locks_ok = check_locks(root, config.get("stage_locks", []))
    issues: List[str] = []
    if not locks_ok:
        issues.append("REQUIRED_LOCK_CHECK_FAILED")
    if not fresh:
        issues.append("MACRO_DATA_STALE")
    if price_ref is None:
        issues.append("PRICE_REFERENCE_MISSING")
    if missing_cols:
        issues.append("MISSING_SIGNAL_COLUMNS")
    if missing_vals:
        issues.append("MISSING_SIGNAL_VALUES")
    bridge_row = {
        "schema_version": "stage76_v1",
        "generated_utc": utc_now_iso(),
        "stage": stage,
        "thesis_id": config["thesis_id"],
        "family": config["family"],
        "direction": config["direction"],
        "signal_date_utc": latest_date,
        "signal_active": signal_active and locks_ok and fresh and not issues,
        "price_reference": price_ref,
        "horizon_trading_days": config["horizon_trading_days"],
        "entry_cooldown_trading_days": config["entry_cooldown_trading_days"],
        "condition_results_json": cond_results,
        "rule_failures": "; ".join(failures),
        "missing_columns": "; ".join(missing_cols),
        "missing_values": "; ".join(missing_vals),
        "order_authorized": False,
        "broker_connection_allowed": False,
        "ea_mode": "OBSERVER_ONLY_NO_TRADE",
        "macro_sha256": sha256_file(macro_path),
    }
    bridge_path = root / config.get("bridge_csv_path", "data/mt5_bridge/k06_observer_signal.csv")
    write_bridge_csv(bridge_path, bridge_row)

    if issues:
        decision = "STAGE76_MT5_OBSERVER_BRIDGE_BLOCKED_NO_ORDER"
        classification = "S76_BRIDGE_BLOCKED"
        disposition = "OBSERVER_BRIDGE_BLOCKED_NO_ORDER"
    elif bridge_row["signal_active"]:
        decision = "STAGE76_MT5_OBSERVER_ACTIVE_SIGNAL_READY_NO_ORDER"
        classification = "S76_OBSERVER_ACTIVE_SIGNAL_READY"
        disposition = "OBSERVER_ACTIVE_SIGNAL_READY_NO_ORDER"
    else:
        decision = "STAGE76_MT5_OBSERVER_READY_WAIT_SIGNAL_NO_ORDER"
        classification = "S76_OBSERVER_READY_WAIT_SIGNAL"
        disposition = "OBSERVER_READY_WAIT_SIGNAL_NO_ORDER"

    summary: Dict[str, Any] = {
        "stage": stage,
        "root": str(root),
        "config": str(root / "configs/stage76_k06_mt5_observer_bridge.json"),
        "generated_utc": bridge_row["generated_utc"],
        "status": "STAGE76_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "bridge_role": "MT5 observer-only bridge. The EA may read/display signals but cannot trade.",
        "champion": {
            "thesis_id": config["thesis_id"],
            "family": config["family"],
            "direction": config["direction"],
            "horizon_trading_days": config["horizon_trading_days"],
            "entry_cooldown_trading_days": config["entry_cooldown_trading_days"],
            "conditions_text": ";".join(f"{c['column']}{c['operator']}{c['threshold']}" for c in config["conditions"]),
        },
        "macro_dataset": {
            "path": str(macro_path),
            "rows": int(len(df)),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": df[date_col].min().date().isoformat(),
            "max_date": df[date_col].max().date().isoformat(),
            "sha256": bridge_row["macro_sha256"],
        },
        "lock_checks": lock_checks,
        "lock_pass_count": sum(1 for x in lock_checks if x.get("matches_required")),
        "lock_total_count": len(lock_checks),
        "freshness": {
            "current_date_utc": current_date.isoformat(),
            "latest_feature_date_utc": latest_date,
            "age_calendar_days": int(age_days),
            "max_stale_calendar_days": int(config.get("max_stale_calendar_days", 7)),
            "fresh": fresh,
        },
        "latest_signal_snapshot": {
            "latest_feature_date_utc": latest_date,
            "signal_active": bool(signal_active),
            "condition_results": cond_results,
            "rule_failures": failures,
            "missing_columns": missing_cols,
            "missing_values": missing_vals,
        },
        "bridge_csv": {
            "path": str(bridge_path),
            "written": True,
            "signal_active_exported": bool(bridge_row["signal_active"]),
            "order_authorized": False,
            "broker_connection_allowed": False,
            "ea_mode": "OBSERVER_ONLY_NO_TRADE",
        },
        "mql5_ea": {
            "source_file_in_package": "mt5/K06_ObserverOnly_EA.mq5",
            "mode": "OBSERVER_ONLY_NO_TRADE",
            "order_functions_expected": "ABSENT",
        },
        "issues": issues,
        "cautions": [],
        "hard_blocks": config.get("hard_blocks", []),
        "operator_instructions": [
            "Stage76 does not authorize orders.",
            "K06_ObserverOnly_EA.mq5 must remain observer-only and must not include OrderSend, CTrade, Buy, Sell, or PositionOpen calls.",
            "The bridge CSV may be copied to MQL5/Files for display/logging only.",
            "Separate manual authorization and a new gated package are required before any demo order harness is created.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage76_k06_mt5_observer_bridge_summary.json"),
            "report_md": str(out_dir / "stage76_k06_mt5_observer_bridge_report.md"),
            "bridge_csv": str(bridge_path),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "stage76_k06_mt5_observer_bridge_summary.json", summary)
    write_report(out_dir / "stage76_k06_mt5_observer_bridge_report.md", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = read_json(config_path)
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    summary = run(root, config, out_dir)
    print(json.dumps({
        "status": summary["status"],
        "decision": summary["decision"],
        "disposition": summary["disposition"],
        "bridge_csv": summary["bridge_csv"]["path"],
        "issues": summary["issues"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
