#!/usr/bin/env python3
"""Stage70C K06 no-order shadow candidate monitor.

This module evaluates the locked K06 champion on the latest macro row and
records a no-order forward-shadow ledger row. It deliberately does not connect
to a broker, place paper orders, generate EA instructions, or tune thresholds.
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

STAGE = "Stage70C_K06_NO_ORDER_SHADOW_CANDIDATE"
DEFAULT_CONFIG = "configs/stage70c_k06_no_order_shadow_candidate.json"


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


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def as_float(value: Any) -> Optional[float]:
    if is_missing(value):
        return None
    try:
        x = float(value)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def eval_condition(value: Optional[float], operator: str, threshold: float) -> bool:
    if value is None:
        return False
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


def parse_date(value: Any) -> Optional[pd.Timestamp]:
    if is_missing(value):
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def load_macro(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"macro dataset not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("macro dataset is empty")
    if "feature_date_utc" not in df.columns:
        raise ValueError("macro dataset missing feature_date_utc")
    df["__feature_ts"] = pd.to_datetime(df["feature_date_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["__feature_ts"]).sort_values("__feature_ts").reset_index(drop=True)
    if df.empty:
        raise ValueError("macro dataset has no parseable feature dates")
    return df


def evaluate_latest(df: pd.DataFrame, conditions: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str], List[str], List[Dict[str, Any]]]:
    latest = df.iloc[-1]
    missing_columns: List[str] = []
    missing_values: List[str] = []
    failures: List[str] = []
    results: List[Dict[str, Any]] = []
    for cond in conditions:
        col = cond["column"]
        op = cond["operator"]
        thr = float(cond["threshold"])
        if col not in df.columns:
            missing_columns.append(col)
            val = None
            passed = False
            failures.append(f"{col}:MISSING_COLUMN{op}{thr}")
        else:
            val = as_float(latest[col])
            if val is None:
                missing_values.append(col)
                passed = False
                failures.append(f"{col}:MISSING_VALUE{op}{thr}")
            else:
                passed = eval_condition(val, op, thr)
                if not passed:
                    failures.append(f"{col}:{val}{op}{thr}")
        results.append({"column": col, "operator": op, "threshold": thr, "value": val, "passed": passed})
    latest_snapshot = {
        "latest_feature_date_utc": str(latest["feature_date_utc"]),
        "signal_active": bool(results and all(r["passed"] for r in results)),
        "condition_results": results,
        "rule_failures": failures,
        "missing_columns": missing_columns,
        "missing_values": missing_values,
    }
    return latest_snapshot, missing_columns, missing_values, results


def check_stage70b_lock(root: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    stage70b_path = root / config["inputs"].get("stage70b_summary", "")
    required = config["champion"].get("stage70b_required_disposition")
    lock = {
        "path": str(stage70b_path),
        "exists": stage70b_path.exists(),
        "required_disposition": required,
        "actual_disposition": None,
        "matches_required": False,
    }
    if stage70b_path.exists():
        try:
            payload = read_json(stage70b_path)
            actual = payload.get("disposition") or payload.get("decision")
            lock["actual_disposition"] = actual
            lock["matches_required"] = (actual == required)
        except Exception as exc:
            lock["read_error"] = str(exc)
    return lock


def append_ledger(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "generated_utc",
        "latest_feature_date_utc",
        "decision",
        "classification",
        "policy_signal_active",
        "selected_thesis_id",
        "selected_rule_label",
        "horizon_trading_days",
        "rule_failures",
        "macro_sha256",
        "summary_json",
        "report_md",
    ]
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fieldnames})


def make_report(summary: Dict[str, Any]) -> str:
    snap = summary.get("latest_signal_snapshot", {})
    cond_lines = []
    for r in snap.get("condition_results", []):
        cond_lines.append(
            f"- `{r['column']}` {r['operator']} `{r['threshold']}`: value=`{r['value']}`, passed=`{r['passed']}`"
        )
    if not cond_lines:
        cond_lines = ["- none"]
    hard_blocks = "\n".join([f"- `{x}`" for x in summary.get("hard_blocks", [])]) or "- none"
    failures = snap.get("rule_failures", [])
    failures_line = "; ".join(failures) if failures else "none"
    return f"""# Stage70C K06 No-Order Shadow Candidate

## Decision

- status: `{summary['status']}`
- decision: `{summary['decision']}`
- classification: `{summary['classification']}`
- disposition: `{summary['disposition']}`

## Champion

- thesis_id: `{summary['champion']['thesis_id']}`
- family: `{summary['champion']['family']}`
- horizon_trading_days: `{summary['champion']['horizon_trading_days']}`
- conditions: `{summary['champion']['conditions_text']}`

## Latest macro row

- rows: `{summary['macro_dataset']['rows']}`
- latest_feature_date_utc: `{snap.get('latest_feature_date_utc')}`
- macro_sha256: `{summary['macro_dataset']['sha256']}`

## Signal snapshot

- policy_signal_active: `{summary['policy_selection']['policy_signal_active']}`
- selected_thesis_id: `{summary['policy_selection']['selected_thesis_id']}`
- selected_rule_label: `{summary['policy_selection']['selected_rule_label']}`
- ticket_generation_allowed_here: `{summary['policy_selection']['ticket_generation_allowed_here']}`
- rule_failures: `{failures_line}`

## Condition results

{chr(10).join(cond_lines)}

## Stage70B lock

- exists: `{summary['stage70b_lock']['exists']}`
- required_disposition: `{summary['stage70b_lock']['required_disposition']}`
- actual_disposition: `{summary['stage70b_lock']['actual_disposition']}`
- matches_required: `{summary['stage70b_lock']['matches_required']}`

## Issues

{chr(10).join([f'- `{x}`' for x in summary.get('issues', [])]) if summary.get('issues') else '- none'}

## Hard blocks

{hard_blocks}
"""


def run(root: Path, config_path: Path, out_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    config_path = (root / config_path).resolve() if not config_path.is_absolute() else config_path
    config = read_json(config_path)
    generated = utc_now_iso()
    issues: List[str] = []

    macro_path = root / config["inputs"]["macro_dataset"]
    stage70b_lock = check_stage70b_lock(root, config)
    if stage70b_lock.get("exists") and not stage70b_lock.get("matches_required"):
        issues.append("STAGE70B_LOCK_DISPOSITION_MISMATCH")
    if not stage70b_lock.get("exists"):
        issues.append("STAGE70B_SUMMARY_NOT_FOUND_LOCK_NOT_VERIFIED")

    try:
        df = load_macro(macro_path)
        macro_sha = sha256_file(macro_path)
        latest_signal_snapshot, missing_columns, missing_values, _ = evaluate_latest(df, config["champion"]["conditions"])
        macro_dataset = {
            "path": str(macro_path),
            "rows": int(len(df)),
            "columns": [c for c in df.columns if c != "__feature_ts"],
            "date_col": "feature_date_utc",
            "latest_feature_date_utc": latest_signal_snapshot["latest_feature_date_utc"],
            "sha256": macro_sha,
        }
        if missing_columns:
            issues.append("MISSING_COLUMNS:" + ",".join(missing_columns))
        if missing_values:
            issues.append("MISSING_VALUES:" + ",".join(missing_values))
    except Exception as exc:
        issues.append("MACRO_LOAD_OR_EVAL_ERROR:" + str(exc))
        df = pd.DataFrame()
        macro_sha = None
        latest_signal_snapshot = {
            "latest_feature_date_utc": None,
            "signal_active": False,
            "condition_results": [],
            "rule_failures": [str(exc)],
            "missing_columns": [],
            "missing_values": [],
        }
        macro_dataset = {
            "path": str(macro_path),
            "rows": 0,
            "columns": [],
            "date_col": "feature_date_utc",
            "latest_feature_date_utc": None,
            "sha256": None,
        }

    signal_active = bool(latest_signal_snapshot.get("signal_active")) and not any(i.startswith("MACRO_LOAD") for i in issues)
    if any(i.startswith("MACRO_LOAD") for i in issues) or latest_signal_snapshot.get("missing_columns"):
        decision = config["decision_policy"]["data_issue_decision"]
        classification = "S70C_INPUT_OR_DATA_ISSUE"
        disposition = "DATA_ISSUE_STOP_NO_ORDER"
    elif signal_active:
        decision = config["decision_policy"]["active_decision"]
        classification = "S70C_K06_SIGNAL_ACTIVE_REVIEW_ONLY"
        disposition = "ACTIVE_REVIEW_ONLY_NO_ORDER"
    else:
        decision = config["decision_policy"]["inactive_decision"]
        classification = "S70C_K06_WAIT_SIGNAL_INACTIVE"
        disposition = "WAIT_SIGNAL_NO_ORDER"

    conditions_text = ";".join(
        f"{c['column']}{c['operator']}{float(c['threshold'])}" for c in config["champion"]["conditions"]
    )
    selected_thesis_id = config["champion"]["thesis_id"] if signal_active else None
    selected_rule_label = f"{config['champion']['thesis_id']} {config['champion']['family']}" if signal_active else None

    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "stage70c_k06_no_order_shadow_candidate_summary.json"
    report_path = out_dir / "stage70c_k06_no_order_shadow_candidate_report.md"
    ledger_path = root / config["outputs"]["ledger_csv"]

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "root": str(root),
        "config": str(config_path),
        "generated_utc": generated,
        "status": "STAGE70C_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "champion": {
            "thesis_id": config["champion"]["thesis_id"],
            "family": config["champion"]["family"],
            "direction": config["champion"].get("direction", "long"),
            "horizon_trading_days": config["champion"]["horizon_trading_days"],
            "conditions_text": conditions_text,
            "cost_bps_total_reference": config["champion"].get("cost_bps_total_reference"),
            "entry_cooldown_trading_days_reference": config["champion"].get("entry_cooldown_trading_days_reference"),
        },
        "macro_dataset": macro_dataset,
        "stage70b_lock": stage70b_lock,
        "latest_signal_snapshot": latest_signal_snapshot,
        "policy_selection": {
            "policy_signal_active": signal_active,
            "selected_thesis_id": selected_thesis_id,
            "selected_rule_label": selected_rule_label,
            "selected_rule_horizon_trading_days": config["champion"]["horizon_trading_days"] if signal_active else None,
            "ticket_generation_allowed_here": False,
            "review_only_if_active": True,
        },
        "issues": issues,
        "backlog_policy": config.get("backlog_policy", {}),
        "hard_blocks": config.get("hard_blocks", []),
        "operator_instructions": config.get("operator_instructions", []),
        "outputs": {
            "summary_json": str(summary_path),
            "report_md": str(report_path),
            "ledger_csv": str(ledger_path),
        },
    }
    write_json(summary_path, summary)
    report_path.write_text(make_report(summary), encoding="utf-8")
    append_ledger(ledger_path, {
        "generated_utc": generated,
        "latest_feature_date_utc": latest_signal_snapshot.get("latest_feature_date_utc"),
        "decision": decision,
        "classification": classification,
        "policy_signal_active": signal_active,
        "selected_thesis_id": selected_thesis_id or "",
        "selected_rule_label": selected_rule_label or "",
        "horizon_trading_days": config["champion"]["horizon_trading_days"],
        "rule_failures": ";".join(latest_signal_snapshot.get("rule_failures", [])),
        "macro_sha256": macro_sha or "",
        "summary_json": str(summary_path),
        "report_md": str(report_path),
    })
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--out", default="reports/stage70c_k06_no_order_shadow_candidate")
    args = parser.parse_args(argv)
    summary = run(Path(args.root), Path(args.config), Path(args.out))
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "policy_signal_active": summary["policy_selection"]["policy_signal_active"],
        "selected_thesis_id": summary["policy_selection"]["selected_thesis_id"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
