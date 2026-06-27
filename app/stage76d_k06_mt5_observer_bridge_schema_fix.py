#!/usr/bin/env python3
"""
Stage76D K06 MT5 Observer Bridge Schema Fix.

Writes the MT5 bridge CSV in key,value format required by K06_ObserverOnly_EA.mq5.
This stage is observer-only. It never authorizes orders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, List, Tuple, Any

import pandas as pd


K06_CONDITIONS = [
    ("gold_sma20_over_50", ">", 0.0),
    ("dxy_ret_20d", ">", 0.0),
    ("real_yield_change_20d", "<", 0.0),
]

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_SEND_IN_EA",
    "OBSERVER_ONLY_EA",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE76D",
    "NO_THRESHOLD_TUNING_FROM_MT5_BRIDGE",
]

LOCKS = [
    ("Stage70B", "reports/stage70b_champion_hard_audit/stage70b_champion_hard_audit_summary.json",
     "PROMOTE_TO_NO_ORDER_SHADOW_CANDIDATE"),
    ("Stage71", "reports/stage71_locked_historical_forward_test/stage71_locked_historical_forward_test_summary.json",
     "K06_PASSES_LOCKED_HISTORICAL_FORWARD"),
    ("Stage72", "reports/stage72_historical_daily_replay/stage72_historical_daily_replay_summary.json",
     "K06_PASSES_HISTORICAL_DAILY_REPLAY"),
    ("Stage73B", "reports/stage73b_corrected_asof_validation_bridge/stage73b_corrected_asof_validation_bridge_summary.json",
     "K06_PASSES_CORRECTED_ASOF_VALIDATION"),
    ("Stage75", "reports/stage75_historical_activation_drill/stage75_historical_activation_drill_summary.json",
     "K06_PASSES_HISTORICAL_ACTIVATION_DRILL"),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_disposition(payload: Dict[str, Any]) -> str:
    return str(payload.get("disposition") or payload.get("decision") or "")


def check_locks(root: Path) -> List[Dict[str, Any]]:
    rows = []
    for stage, rel_path, required in LOCKS:
        p = root / rel_path
        item = {
            "stage": stage,
            "path": str(p),
            "exists": p.exists(),
            "read_ok": False,
            "required_disposition": required,
            "actual_disposition": None,
            "matches_required": False,
            "issue": None,
        }
        if not p.exists():
            item["issue"] = "LOCK_FILE_MISSING"
        else:
            try:
                payload = read_json(p)
                actual = get_disposition(payload)
                item["read_ok"] = True
                item["actual_disposition"] = actual
                item["matches_required"] = (actual == required)
                if not item["matches_required"]:
                    item["issue"] = "LOCK_DISPOSITION_MISMATCH"
            except Exception as exc:
                item["issue"] = f"LOCK_READ_ERROR:{type(exc).__name__}:{exc}"
        rows.append(item)
    return rows


def as_date_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(pd.to_datetime(value).date())


def eval_condition(value: Any, op: str, threshold: float) -> Tuple[bool, str, float | None]:
    if pd.isna(value):
        return False, "missing", None
    try:
        v = float(value)
    except Exception:
        return False, "non_numeric", None
    if op == ">":
        ok = v > threshold
    elif op == "<":
        ok = v < threshold
    else:
        raise ValueError(f"unsupported operator {op}")
    return ok, "ok" if ok else f"{v}{op}{threshold}", v


def evaluate_latest(df: pd.DataFrame, date_col: str, price_col: str) -> Dict[str, Any]:
    df2 = df.copy()
    df2[date_col] = pd.to_datetime(df2[date_col], errors="coerce")
    df2 = df2.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    if df2.empty:
        raise ValueError("macro dataset has no parseable dates")
    row = df2.iloc[-1]
    condition_results = []
    failures = []
    missing_columns = []
    missing_values = []

    for col, op, thr in K06_CONDITIONS:
        if col not in df2.columns:
            missing_columns.append(col)
            condition_results.append({
                "column": col, "operator": op, "threshold": thr,
                "value": None, "passed": False, "reason": "missing_column"
            })
            failures.append(f"{col}:missing_column")
            continue
        ok, reason, v = eval_condition(row[col], op, thr)
        if reason == "missing":
            missing_values.append(col)
        condition_results.append({
            "column": col, "operator": op, "threshold": thr,
            "value": v, "passed": ok, "reason": reason,
        })
        if not ok:
            failures.append(f"{col}:{reason}")

    price_ref = None
    if price_col in df2.columns and not pd.isna(row[price_col]):
        price_ref = float(row[price_col])

    return {
        "latest_feature_date_utc": as_date_text(row[date_col]),
        "signal_active": bool(condition_results and all(x["passed"] for x in condition_results)),
        "condition_results": condition_results,
        "rule_failures": failures,
        "missing_columns": missing_columns,
        "missing_values": missing_values,
        "price_reference": price_ref,
        "row_count": int(len(df2)),
        "min_date": as_date_text(df2[date_col].iloc[0]),
        "max_date": as_date_text(df2[date_col].iloc[-1]),
    }


def write_key_value_csv(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        ("schema_version", "stage76d_key_value_v2"),
        ("generated_utc", data["generated_utc"]),
        ("stage", "Stage76D_K06_MT5_OBSERVER_BRIDGE_SCHEMA_FIX"),
        ("thesis_id", "K06_RESILIENT_GOLD_VS_DXY"),
        ("family", "GOLD_RESILIENCE_AGAINST_DXY"),
        ("direction", "long"),
        ("latest_feature_date_utc", data["latest_feature_date_utc"]),
        ("signal_active", str(data["signal_active"]).lower()),
        ("price_reference", "" if data["price_reference"] is None else f"{data['price_reference']:.8g}"),
        ("horizon_trading_days", "120"),
        ("entry_cooldown_trading_days", "120"),
        ("gold_sma20_over_50", data["condition_value_map"].get("gold_sma20_over_50", "")),
        ("dxy_ret_20d", data["condition_value_map"].get("dxy_ret_20d", "")),
        ("real_yield_change_20d", data["condition_value_map"].get("real_yield_change_20d", "")),
        ("condition_results_json", json.dumps(data["condition_results"], ensure_ascii=False, separators=(",", ":"))),
        ("rule_failures", "; ".join(data["rule_failures"])),
        ("missing_columns", "; ".join(data["missing_columns"])),
        ("missing_values", "; ".join(data["missing_values"])),
        ("order_authorized", "false"),
        ("broker_connection_allowed", "false"),
        ("ea_mode", "OBSERVER_ONLY_NO_TRADE"),
        ("macro_sha256", data["macro_sha256"]),
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for k, v in rows:
            w.writerow([k, v])


def write_wide_csv(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schema_version": "stage76d_wide_reference_v2",
        "generated_utc": data["generated_utc"],
        "stage": "Stage76D_K06_MT5_OBSERVER_BRIDGE_SCHEMA_FIX",
        "thesis_id": "K06_RESILIENT_GOLD_VS_DXY",
        "family": "GOLD_RESILIENCE_AGAINST_DXY",
        "direction": "long",
        "latest_feature_date_utc": data["latest_feature_date_utc"],
        "signal_active": str(data["signal_active"]).lower(),
        "price_reference": data["price_reference"],
        "horizon_trading_days": 120,
        "entry_cooldown_trading_days": 120,
        "gold_sma20_over_50": data["condition_value_map"].get("gold_sma20_over_50", ""),
        "dxy_ret_20d": data["condition_value_map"].get("dxy_ret_20d", ""),
        "real_yield_change_20d": data["condition_value_map"].get("real_yield_change_20d", ""),
        "rule_failures": "; ".join(data["rule_failures"]),
        "missing_columns": "; ".join(data["missing_columns"]),
        "missing_values": "; ".join(data["missing_values"]),
        "order_authorized": "false",
        "broker_connection_allowed": "false",
        "ea_mode": "OBSERVER_ONLY_NO_TRADE",
        "macro_sha256": data["macro_sha256"],
    }
    pd.DataFrame([row]).to_csv(path, index=False)


def make_report(summary: Dict[str, Any]) -> str:
    ls = summary["latest_signal_snapshot"]
    bridge = summary["bridge_csv"]
    lines = [
        "# Stage76D K06 MT5 Observer Bridge Schema Fix",
        "",
        "## Decision",
        f"- status: `{summary['status']}`",
        f"- decision: `{summary['decision']}`",
        f"- classification: `{summary['classification']}`",
        f"- disposition: `{summary['disposition']}`",
        "",
        "## Bridge CSV",
        f"- key_value_path: `{bridge['key_value_path']}`",
        f"- written: `{bridge['written']}`",
        "- schema: `key,value`",
        "",
        "## Latest K06 signal",
        f"- latest_feature_date_utc: `{ls['latest_feature_date_utc']}`",
        f"- signal_active: `{ls['signal_active']}`",
        f"- rule_failures: `{'; '.join(ls['rule_failures'])}`",
        "",
        "## Lock checks",
    ]
    for item in summary["lock_checks"]:
        lines.append(
            f"- `{item['stage']}`: exists=`{item['exists']}`, read_ok=`{item['read_ok']}`, "
            f"matches_required=`{item['matches_required']}`, actual=`{item['actual_disposition']}`"
        )
    lines += [
        "",
        "## Issues",
        "- " + ("; ".join(summary["issues"]) if summary["issues"] else "none"),
        "",
        "## Hard blocks",
    ]
    lines += [f"- `{x}`" for x in summary["hard_blocks"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", default="configs/stage76d_k06_mt5_observer_bridge_schema_fix.json")
    ap.add_argument("--out", default="reports/stage76d_k06_mt5_observer_bridge_schema_fix")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg_path = root / args.config
    cfg = read_json(cfg_path) if cfg_path.exists() else {}
    macro_path = root / cfg.get("macro_path", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    date_col = cfg.get("date_col", "feature_date_utc")
    price_col = cfg.get("price_col", "gold_close")
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    issues = []

    if not macro_path.exists():
        raise FileNotFoundError(f"macro dataset not found: {macro_path}")
    df = pd.read_csv(macro_path)
    latest = evaluate_latest(df, date_col, price_col)
    macro_sha = sha256_file(macro_path)
    lock_checks = check_locks(root)
    for item in lock_checks:
        if not item["matches_required"]:
            issues.append(f"LOCK_NOT_READY:{item['stage']}:{item['issue']}")

    value_map = {}
    for cr in latest["condition_results"]:
        val = cr.get("value")
        value_map[cr["column"]] = "" if val is None else str(val)

    kv_path = root / cfg.get("bridge_csv_path", "data/mt5_bridge/k06_observer_signal.csv")
    wide_path = root / cfg.get("wide_reference_csv_path", "data/mt5_bridge/k06_observer_signal_wide_reference.csv")
    payload = {
        **latest,
        "generated_utc": generated_utc,
        "condition_value_map": value_map,
        "macro_sha256": macro_sha,
    }
    write_key_value_csv(kv_path, payload)
    write_wide_csv(wide_path, payload)

    decision = "STAGE76D_MT5_OBSERVER_READY_WAIT_SIGNAL_NO_ORDER"
    classification = "S76D_OBSERVER_READY_WAIT_SIGNAL"
    disposition = "OBSERVER_READY_WAIT_SIGNAL_NO_ORDER"
    if issues:
        decision = "STAGE76D_MT5_OBSERVER_BLOCKED_NO_ORDER"
        classification = "S76D_BLOCKED"
        disposition = "OBSERVER_BLOCKED_NO_ORDER"
    elif latest["signal_active"]:
        decision = "STAGE76D_MT5_OBSERVER_READY_ACTIVE_REVIEW_ONLY_NO_ORDER"
        classification = "S76D_OBSERVER_ACTIVE_REVIEW_ONLY"
        disposition = "OBSERVER_READY_ACTIVE_REVIEW_ONLY_NO_ORDER"

    summary = {
        "stage": "Stage76D_K06_MT5_OBSERVER_BRIDGE_SCHEMA_FIX",
        "root": str(root),
        "config": str(cfg_path),
        "generated_utc": generated_utc,
        "status": "STAGE76D_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "bridge_role": "Writes key,value CSV consumed by K06_ObserverOnly_EA.mq5. Observer-only.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows": latest["row_count"],
            "date_col": date_col,
            "price_col": price_col,
            "min_date": latest["min_date"],
            "max_date": latest["max_date"],
            "sha256": macro_sha,
        },
        "lock_checks": lock_checks,
        "lock_pass_count": sum(1 for x in lock_checks if x["matches_required"]),
        "lock_total_count": len(lock_checks),
        "latest_signal_snapshot": {
            "latest_feature_date_utc": latest["latest_feature_date_utc"],
            "signal_active": latest["signal_active"],
            "condition_results": latest["condition_results"],
            "rule_failures": latest["rule_failures"],
            "missing_columns": latest["missing_columns"],
            "missing_values": latest["missing_values"],
        },
        "bridge_csv": {
            "key_value_path": str(kv_path),
            "wide_reference_path": str(wide_path),
            "written": kv_path.exists(),
            "schema": "key,value",
            "signal_active_exported": latest["signal_active"],
            "order_authorized": False,
            "broker_connection_allowed": False,
            "ea_mode": "OBSERVER_ONLY_NO_TRADE",
        },
        "mql5_ea": {
            "source_file_in_package": "mt5/K06_ObserverOnly_EA.mq5",
            "mode": "OBSERVER_ONLY_NO_TRADE",
            "expected_csv_schema": "key,value",
        },
        "issues": issues,
        "cautions": [],
        "hard_blocks": HARD_BLOCKS,
        "operator_instructions": [
            "Run Stage76D after macro refresh to rewrite MQL5/Files-compatible key,value CSV.",
            "The EA is fixed unless its display/reader logic changes. Daily updates should replace only the CSV.",
            "No order path is present in this stage.",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage76d_k06_mt5_observer_bridge_schema_fix_summary.json"),
            "report_md": str(out_dir / "stage76d_k06_mt5_observer_bridge_schema_fix_report.md"),
            "bridge_csv": str(kv_path),
            "wide_reference_csv": str(wide_path),
        },
    }

    (out_dir / "stage76d_k06_mt5_observer_bridge_schema_fix_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "stage76d_k06_mt5_observer_bridge_schema_fix_report.md").write_text(
        make_report(summary), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
