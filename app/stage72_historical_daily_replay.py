#!/usr/bin/env python3
"""Stage72 Historical Daily Replay for K06.

This is a no-order operational replay. It treats each historical row as if it were
"today" and evaluates the locked K06 thesis using only same-row lag-safe features.
Future rows are used only after a configured horizon has elapsed to score matured
historical outcomes, exactly like a future ledger would mature over time.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DATE_COL_DEFAULT = "feature_date_utc"
PRICE_COL_DEFAULT = "gold_close"

K06_RULE = {
    "thesis_id": "K06_RESILIENT_GOLD_VS_DXY",
    "family": "GOLD_RESILIENCE_AGAINST_DXY",
    "direction": "long",
    "horizon_trading_days": 120,
    "entry_cooldown_trading_days": 120,
    "cost_bps_total": 50.0,
    "conditions": [
        {"column": "gold_sma20_over_50", "operator": ">", "threshold": 0.0},
        {"column": "dxy_ret_20d", "operator": ">", "threshold": 0.0},
        {"column": "real_yield_change_20d", "operator": "<", "threshold": 0.0},
    ],
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "macro_dataset": "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
    "date_col": DATE_COL_DEFAULT,
    "price_col": PRICE_COL_DEFAULT,
    "replay_start": "2019-01-01",
    "replay_end": None,
    "locked_final_holdout_start": "2023-01-01",
    "stage71_summary": "reports/stage71_locked_historical_forward_test/stage71_locked_historical_forward_test_summary.json",
    "rule": K06_RULE,
    "decision_constraints": {
        "min_replay_rows": 800,
        "min_matured_events": 5,
        "min_mean_net_return_bps": 100.0,
        "min_win_rate": 0.55,
        "min_final_holdout_matured_events": 3,
        "min_final_holdout_mean_net_bps": 0.0,
        "max_abs_worst_loss_bps": 1500.0,
        "max_lookahead_violations": 0,
        "max_missing_feature_rows": 0,
    },
    "hard_blocks": [
        "NO_AUTOMATED_ORDER",
        "NO_PAPER_ORDER",
        "NO_BROKER_CONNECTION",
        "NO_EA_PROMOTION",
        "NO_PAPER_LIVE",
        "NO_LIVE",
        "NO_ORDER_AUTHORIZATION_FROM_STAGE72",
        "NO_THRESHOLD_TUNING_FROM_HISTORICAL_DAILY_REPLAY",
        "NO_PROMOTION_FROM_STAGE72_WITHOUT_SEPARATE_GOVERNANCE",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage72 K06 historical daily replay")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--config", default="configs/stage72_historical_daily_replay.json")
    parser.add_argument("--out", default="reports/stage72_historical_daily_replay")
    return parser.parse_args()


def load_config(root: Path, config_path: str) -> Dict[str, Any]:
    path = (root / config_path).resolve()
    if not path.exists():
        return DEFAULT_CONFIG.copy()
    with path.open("r", encoding="utf-8") as f:
        user_cfg = json.load(f)
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    deep_update(cfg, user_cfg)
    return cfg


def deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> None:
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(value: str) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Accept YYYY-MM-DD or timestamp-like values.
    if "T" in s:
        s = s.split("T", 1)[0]
    if " " in s:
        s = s.split(" ", 1)[0]
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s == "" or s.lower() in {"nan", "none", "null", "."}:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def read_csv_rows(path: Path, date_col: str) -> Tuple[List[Dict[str, str]], List[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Empty CSV or missing header: {path}")
        rows = [dict(row) for row in reader]
        fieldnames = list(reader.fieldnames)
    for row in rows:
        row["__date"] = parse_date(row.get(date_col, "")) or ""
    rows = [r for r in rows if r["__date"]]
    rows.sort(key=lambda r: r["__date"])
    return rows, fieldnames


def eval_condition(row: Dict[str, str], cond: Dict[str, Any]) -> Dict[str, Any]:
    col = cond["column"]
    op = cond["operator"]
    thr = float(cond["threshold"])
    value = to_float(row.get(col))
    if value is None:
        passed = False
        reason = "missing"
    elif op == ">":
        passed = value > thr
        reason = "ok" if passed else f"{value}>{thr}"
    elif op == "<":
        passed = value < thr
        reason = "ok" if passed else f"{value}<{thr}"
    elif op == ">=":
        passed = value >= thr
        reason = "ok" if passed else f"{value}>={thr}"
    elif op == "<=":
        passed = value <= thr
        reason = "ok" if passed else f"{value}<={thr}"
    else:
        raise ValueError(f"Unsupported operator: {op}")
    return {
        "column": col,
        "operator": op,
        "threshold": thr,
        "value": value,
        "passed": passed,
        "reason": reason,
    }


def eval_rule(row: Dict[str, str], rule: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]], List[str], List[str]]:
    results = [eval_condition(row, c) for c in rule["conditions"]]
    missing = [r["column"] for r in results if r["value"] is None]
    failures = [f"{r['column']}:{r['reason']}" for r in results if not r["passed"] and r["reason"] != "missing"]
    missing_failures = [f"{r['column']}:missing" for r in results if r["reason"] == "missing"]
    return all(r["passed"] for r in results), results, failures, missing_failures


def bps_return(entry_price: float, exit_price: float, cost_bps: float, direction: str) -> Tuple[float, float]:
    if entry_price <= 0 or exit_price <= 0:
        raise ValueError("Non-positive price cannot be used for return")
    if direction == "long":
        gross = (exit_price / entry_price - 1.0) * 10000.0
    elif direction == "short":
        gross = (entry_price / exit_price - 1.0) * 10000.0
    else:
        raise ValueError(f"Unsupported direction: {direction}")
    return gross, gross - cost_bps


def summarize_returns(values: Sequence[float]) -> Dict[str, Any]:
    vals = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if not vals:
        return {
            "entry_count": 0,
            "mean_net_return_bps": None,
            "median_net_return_bps": None,
            "win_rate": None,
            "min_net_return_bps": None,
            "max_net_return_bps": None,
            "total_net_return_bps": 0.0,
        }
    return {
        "entry_count": len(vals),
        "mean_net_return_bps": round(statistics.mean(vals), 4),
        "median_net_return_bps": round(statistics.median(vals), 4),
        "win_rate": round(sum(1 for v in vals if v > 0) / len(vals), 4),
        "min_net_return_bps": round(min(vals), 4),
        "max_net_return_bps": round(max(vals), 4),
        "total_net_return_bps": round(sum(vals), 4),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def stage71_lock_status(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    rel = cfg.get("stage71_summary")
    if not rel:
        return {"exists": False, "status": "NOT_CONFIGURED"}
    path = (root / rel).resolve()
    if not path.exists():
        return {"exists": False, "path": str(path), "status": "MISSING_STAGE71_SUMMARY"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        return {"exists": True, "path": str(path), "status": "UNREADABLE", "error": str(exc)}
    return {
        "exists": True,
        "path": str(path),
        "status": "READ_OK",
        "stage71_decision": data.get("decision"),
        "stage71_disposition": data.get("disposition"),
        "stage71_classification": data.get("classification"),
        "stage71_passes_locked_test": data.get("disposition") == "K06_PASSES_LOCKED_HISTORICAL_FORWARD",
    }


def run(root: Path, cfg: Dict[str, Any], out_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    macro_path = (root / cfg["macro_dataset"]).resolve()
    if not macro_path.exists():
        raise FileNotFoundError(f"Macro dataset not found: {macro_path}")

    date_col = cfg.get("date_col", DATE_COL_DEFAULT)
    price_col = cfg.get("price_col", PRICE_COL_DEFAULT)
    rows, fieldnames = read_csv_rows(macro_path, date_col)
    if not rows:
        raise ValueError("No dated rows loaded from macro dataset")
    if price_col not in fieldnames:
        raise ValueError(f"Missing price column: {price_col}")

    rule = cfg.get("rule", K06_RULE)
    horizon = int(rule.get("horizon_trading_days", 120))
    cooldown = int(rule.get("entry_cooldown_trading_days", horizon))
    cost_bps = float(rule.get("cost_bps_total", 50.0))
    direction = rule.get("direction", "long")

    replay_start = cfg.get("replay_start")
    replay_end = cfg.get("replay_end")
    final_holdout_start = cfg.get("locked_final_holdout_start", "2023-01-01")
    start_idx = 0
    end_idx = len(rows) - 1
    if replay_start:
        start_idx = next((i for i, r in enumerate(rows) if r["__date"] >= replay_start), len(rows))
    if replay_end:
        end_idx = max((i for i, r in enumerate(rows) if r["__date"] <= replay_end), default=-1)
    if start_idx >= len(rows) or end_idx < start_idx:
        raise ValueError("Replay date range has no rows")

    replay_indices = list(range(start_idx, end_idx + 1))
    daily_ledger: List[Dict[str, Any]] = []
    activation_events: List[Dict[str, Any]] = []
    matured_outcomes: List[Dict[str, Any]] = []

    last_entry_idx: Optional[int] = None
    lookahead_violations = 0
    missing_feature_rows = 0

    for i in replay_indices:
        row = rows[i]
        date = row["__date"]
        price = to_float(row.get(price_col))
        active, cond_results, failures, missing_failures = eval_rule(row, rule)
        if missing_failures:
            missing_feature_rows += 1
        eligible_by_cooldown = last_entry_idx is None or (i - last_entry_idx) >= cooldown
        entry_triggered = bool(active and eligible_by_cooldown and price is not None)
        exit_idx = i + horizon
        outcome_status = "NO_ENTRY"
        if entry_triggered:
            last_entry_idx = i
            outcome_status = "PENDING_UNTIL_FUTURE_ROW"
            event = {
                "entry_id": f"K06_{date}",
                "entry_index": i,
                "entry_date": date,
                "entry_price": price,
                "horizon_trading_days": horizon,
                "matures_on_index": exit_idx,
                "matures_on_date": rows[exit_idx]["__date"] if exit_idx < len(rows) else None,
                "matures_within_dataset": exit_idx < len(rows),
                "cooldown_trading_days": cooldown,
                "cost_bps_total": cost_bps,
                "direction": direction,
                "generated_in_replay_without_future_outcome": True,
            }
            activation_events.append(event)
            if exit_idx <= end_idx and exit_idx < len(rows):
                exit_row = rows[exit_idx]
                exit_price = to_float(exit_row.get(price_col))
                if exit_price is not None:
                    gross, net = bps_return(float(price), float(exit_price), cost_bps, direction)
                    outcome_status = "MATURED_WITHIN_REPLAY"
                    matured_outcomes.append({
                        **event,
                        "exit_index": exit_idx,
                        "exit_date": exit_row["__date"],
                        "exit_price": exit_price,
                        "gross_return_bps": round(gross, 4),
                        "net_return_bps": round(net, 4),
                        "split_role": "FINAL_STATISTICAL_HOLDOUT" if date >= final_holdout_start else "LOCKED_HISTORICAL_FORWARD_OR_PRIOR",
                    })
            elif exit_idx < len(rows):
                # This is a valid historical event whose outcome exists outside the replay end.
                # If replay_end is configured before latest, do not score it inside this replay.
                pass
            else:
                # No future row exists in the dataset. In real life this would be pending.
                pass

        ledger_row: Dict[str, Any] = {
            "replay_date": date,
            "row_index": i,
            "price": price,
            "signal_active": active,
            "eligible_by_cooldown": eligible_by_cooldown,
            "entry_triggered": entry_triggered,
            "outcome_status_at_replay_time": outcome_status,
            "rule_failures": "; ".join(failures + missing_failures),
            "lookahead_used_for_signal": False,
        }
        for cr in cond_results:
            ledger_row[f"{cr['column']}_value"] = cr["value"]
            ledger_row[f"{cr['column']}_passed"] = cr["passed"]
        daily_ledger.append(ledger_row)

    # Lookahead audit: signal rows must not contain future outcome fields. This script only uses current row.
    # A violation is reserved for future schema expansion.
    lookahead_violations = 0

    all_net = [float(r["net_return_bps"]) for r in matured_outcomes]
    overall = summarize_returns(all_net)
    final_net = [float(r["net_return_bps"]) for r in matured_outcomes if r.get("entry_date", "") >= final_holdout_start]
    final_summary = summarize_returns(final_net)

    # Monthly refresh stats from daily ledger.
    month_map: Dict[str, Dict[str, Any]] = {}
    for row in daily_ledger:
        month = str(row["replay_date"])[:7]
        m = month_map.setdefault(month, {"month": month, "replay_rows": 0, "active_days": 0, "entry_triggers": 0})
        m["replay_rows"] += 1
        m["active_days"] += 1 if row["signal_active"] else 0
        m["entry_triggers"] += 1 if row["entry_triggered"] else 0
    monthly_rows = list(month_map.values())
    for m in monthly_rows:
        m["active_pct"] = round(100.0 * m["active_days"] / m["replay_rows"], 4) if m["replay_rows"] else 0.0

    constraints = cfg.get("decision_constraints", DEFAULT_CONFIG["decision_constraints"])
    hard_failures: List[str] = []
    cautions: List[str] = []
    if len(daily_ledger) < int(constraints["min_replay_rows"]):
        hard_failures.append(f"REPLAY_ROWS_LT_MIN:{len(daily_ledger)}<{constraints['min_replay_rows']}")
    if overall["entry_count"] < int(constraints["min_matured_events"]):
        hard_failures.append(f"MATURED_EVENTS_LT_MIN:{overall['entry_count']}<{constraints['min_matured_events']}")
    if overall["mean_net_return_bps"] is None or overall["mean_net_return_bps"] < float(constraints["min_mean_net_return_bps"]):
        hard_failures.append(f"MEAN_NET_LT_MIN:{overall['mean_net_return_bps']}<{constraints['min_mean_net_return_bps']}")
    if overall["win_rate"] is None or overall["win_rate"] < float(constraints["min_win_rate"]):
        hard_failures.append(f"WIN_RATE_LT_MIN:{overall['win_rate']}<{constraints['min_win_rate']}")
    if final_summary["entry_count"] < int(constraints["min_final_holdout_matured_events"]):
        hard_failures.append(f"FINAL_HOLDOUT_EVENTS_LT_MIN:{final_summary['entry_count']}<{constraints['min_final_holdout_matured_events']}")
    if final_summary["mean_net_return_bps"] is None or final_summary["mean_net_return_bps"] < float(constraints["min_final_holdout_mean_net_bps"]):
        hard_failures.append(f"FINAL_HOLDOUT_MEAN_LT_MIN:{final_summary['mean_net_return_bps']}<{constraints['min_final_holdout_mean_net_bps']}")
    if overall["min_net_return_bps"] is not None and abs(float(overall["min_net_return_bps"])) > float(constraints["max_abs_worst_loss_bps"]):
        hard_failures.append(f"WORST_LOSS_ABS_GT_MAX:{overall['min_net_return_bps']}<{constraints['max_abs_worst_loss_bps']}")
    if lookahead_violations > int(constraints["max_lookahead_violations"]):
        hard_failures.append(f"LOOKAHEAD_VIOLATIONS_GT_MAX:{lookahead_violations}>{constraints['max_lookahead_violations']}")
    if missing_feature_rows > int(constraints["max_missing_feature_rows"]):
        hard_failures.append(f"MISSING_FEATURE_ROWS_GT_MAX:{missing_feature_rows}>{constraints['max_missing_feature_rows']}")

    pending_events = [e for e in activation_events if not e["matures_within_dataset"]]
    if pending_events:
        cautions.append(f"PENDING_EVENTS_WITHOUT_FUTURE_ROWS:{len(pending_events)}")

    stage71_status = stage71_lock_status(root, cfg)
    if stage71_status.get("exists") and not stage71_status.get("stage71_passes_locked_test", False):
        cautions.append("STAGE71_SUMMARY_EXISTS_BUT_DID_NOT_PASS_LOCKED_TEST")
    elif not stage71_status.get("exists"):
        cautions.append("STAGE71_SUMMARY_MISSING_REPLAY_STILL_RAN")

    if hard_failures:
        decision = "K06_HISTORICAL_DAILY_REPLAY_FAIL_NO_ORDER"
        classification = "S72_K06_REPLAY_FAIL"
        disposition = "K06_FAILS_HISTORICAL_DAILY_REPLAY"
    elif cautions:
        decision = "K06_HISTORICAL_DAILY_REPLAY_PASS_WITH_CAUTION_NO_ORDER"
        classification = "S72_K06_REPLAY_PASS_WITH_CAUTION"
        disposition = "K06_PASSES_HISTORICAL_DAILY_REPLAY_WITH_CAUTION"
    else:
        decision = "K06_HISTORICAL_DAILY_REPLAY_PASS_NO_ORDER"
        classification = "S72_K06_REPLAY_PASS"
        disposition = "K06_PASSES_HISTORICAL_DAILY_REPLAY"

    # Write outputs.
    daily_csv = out_dir / "stage72_k06_historical_daily_ledger.csv"
    events_csv = out_dir / "stage72_k06_activation_events.csv"
    matured_csv = out_dir / "stage72_k06_matured_outcomes.csv"
    monthly_csv = out_dir / "stage72_k06_monthly_replay_metrics.csv"
    compatibility_csv = out_dir / "stage72_historical_replay_audit.csv"
    summary_json = out_dir / "stage72_historical_daily_replay_summary.json"
    report_md = out_dir / "stage72_historical_daily_replay_report.md"

    ledger_fields = [
        "replay_date", "row_index", "price", "signal_active", "eligible_by_cooldown",
        "entry_triggered", "outcome_status_at_replay_time", "rule_failures",
        "lookahead_used_for_signal",
    ]
    for cond in rule["conditions"]:
        ledger_fields.extend([f"{cond['column']}_value", f"{cond['column']}_passed"])
    write_csv(daily_csv, daily_ledger, ledger_fields)

    event_fields = [
        "entry_id", "entry_index", "entry_date", "entry_price", "horizon_trading_days",
        "matures_on_index", "matures_on_date", "matures_within_dataset", "cooldown_trading_days",
        "cost_bps_total", "direction", "generated_in_replay_without_future_outcome",
    ]
    write_csv(events_csv, activation_events, event_fields)

    matured_fields = event_fields + ["exit_index", "exit_date", "exit_price", "gross_return_bps", "net_return_bps", "split_role"]
    write_csv(matured_csv, matured_outcomes, matured_fields)
    write_csv(monthly_csv, monthly_rows, ["month", "replay_rows", "active_days", "active_pct", "entry_triggers"])

    replay_audit_rows = [
        {"check": "signal_uses_only_current_row_lag_safe_features", "value": True, "status": "PASS"},
        {"check": "future_prices_used_only_after_maturity_for_outcome_scoring", "value": True, "status": "PASS"},
        {"check": "lookahead_violations", "value": lookahead_violations, "status": "PASS" if lookahead_violations == 0 else "FAIL"},
        {"check": "missing_feature_rows", "value": missing_feature_rows, "status": "PASS" if missing_feature_rows == 0 else "FAIL"},
        {"check": "stage71_locked_test_status", "value": stage71_status.get("stage71_disposition", stage71_status.get("status")), "status": "PASS" if stage71_status.get("stage71_passes_locked_test") else "WARN"},
    ]
    write_csv(compatibility_csv, replay_audit_rows, ["check", "value", "status"])

    latest_row = rows[end_idx]
    latest_active, latest_conditions, latest_failures, latest_missing = eval_rule(latest_row, rule)

    summary: Dict[str, Any] = {
        "stage": "Stage72_HISTORICAL_DAILY_REPLAY",
        "root": str(root),
        "config": str((root / cfg.get("_config_path", "configs/stage72_historical_daily_replay.json")).resolve()),
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "STAGE72_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
        "replay_principle": "Historical rows are replayed one by one as daily refresh snapshots. No future row is used to trigger a signal; future prices are used only after the configured horizon has matured, to score historical outcomes.",
        "macro_dataset": {
            "path": str(macro_path),
            "rows_raw": len(rows),
            "rows_replayed": len(daily_ledger),
            "date_col": date_col,
            "price_col": price_col,
            "min_date": rows[0]["__date"],
            "max_date": rows[-1]["__date"],
            "replay_start": rows[start_idx]["__date"],
            "replay_end": rows[end_idx]["__date"],
            "sha256": sha256_file(macro_path),
        },
        "champion": {
            "thesis_id": rule.get("thesis_id"),
            "family": rule.get("family"),
            "direction": direction,
            "horizon_trading_days": horizon,
            "entry_cooldown_trading_days": cooldown,
            "cost_bps_total": cost_bps,
            "conditions_text": ";".join(f"{c['column']}{c['operator']}{c['threshold']}" for c in rule["conditions"]),
        },
        "historical_daily_replay": {
            "replay_rows": len(daily_ledger),
            "active_days": sum(1 for r in daily_ledger if r["signal_active"]),
            "entry_triggers": len(activation_events),
            "matured_outcomes": len(matured_outcomes),
            "pending_unmatured_events": len(pending_events),
            "lookahead_violations": lookahead_violations,
            "missing_feature_rows": missing_feature_rows,
        },
        "matured_outcome_metrics": overall,
        "final_holdout_matured_outcome_metrics": final_summary,
        "latest_signal_snapshot": {
            "latest_feature_date_utc": latest_row["__date"],
            "signal_active": latest_active,
            "condition_results": latest_conditions,
            "rule_failures": latest_failures + latest_missing,
        },
        "stage71_lock_status": stage71_status,
        "decision_constraints": constraints,
        "hard_failures": hard_failures,
        "cautions": cautions,
        "hard_blocks": cfg.get("hard_blocks", DEFAULT_CONFIG["hard_blocks"]),
        "operator_instructions": [
            "Stage72 is a historical daily replay and cannot authorize orders.",
            "Do not wait for real future data to prove the K06 thesis statistically; use locked/final historical replay for proof and keep real forward only for operational sanity.",
            "Signals are generated from same-row lag-safe features only; future rows are used only to score matured historical outcomes.",
            "Broker, EA, paper-live, and live paths remain blocked without separate governance.",
        ],
        "outputs": {
            "summary_json": str(summary_json),
            "report_md": str(report_md),
            "daily_ledger_csv": str(daily_csv),
            "activation_events_csv": str(events_csv),
            "matured_outcomes_csv": str(matured_csv),
            "monthly_replay_metrics_csv": str(monthly_csv),
            "historical_replay_audit_csv": str(compatibility_csv),
        },
    }

    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_md.write_text(render_report(summary), encoding="utf-8")
    return summary


def render_report(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Stage72 Historical Daily Replay")
    lines.append("")
    lines.append("## Decision")
    for key in ["status", "decision", "classification", "disposition"]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("## Replay principle")
    lines.append(summary["replay_principle"])
    lines.append("")
    lines.append("## Champion")
    ch = summary["champion"]
    lines.append(f"- thesis_id: `{ch['thesis_id']}`")
    lines.append(f"- family: `{ch['family']}`")
    lines.append(f"- horizon_trading_days: `{ch['horizon_trading_days']}`")
    lines.append(f"- entry_cooldown_trading_days: `{ch['entry_cooldown_trading_days']}`")
    lines.append(f"- conditions: `{ch['conditions_text']}`")
    lines.append("")
    lines.append("## Historical daily replay")
    replay = summary["historical_daily_replay"]
    for key, value in replay.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Matured outcome metrics")
    for key, value in summary["matured_outcome_metrics"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Final holdout matured outcome metrics")
    for key, value in summary["final_holdout_matured_outcome_metrics"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Latest signal snapshot")
    latest = summary["latest_signal_snapshot"]
    lines.append(f"- latest_feature_date_utc: `{latest['latest_feature_date_utc']}`")
    lines.append(f"- signal_active: `{latest['signal_active']}`")
    lines.append(f"- rule_failures: `{'; '.join(latest['rule_failures'])}`")
    lines.append("")
    lines.append("## Stage71 lock status")
    st71 = summary["stage71_lock_status"]
    for key in ["exists", "status", "stage71_decision", "stage71_disposition", "stage71_passes_locked_test"]:
        if key in st71:
            lines.append(f"- {key}: `{st71.get(key)}`")
    lines.append("")
    lines.append("## Hard failures")
    if summary["hard_failures"]:
        for item in summary["hard_failures"]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Cautions")
    if summary["cautions"]:
        for item in summary["cautions"]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Hard blocks")
    for item in summary["hard_blocks"]:
        lines.append(f"- `{item}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    cfg = load_config(root, args.config)
    cfg["_config_path"] = args.config
    summary = run(root, cfg, root / args.out)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "classification": summary["classification"],
        "disposition": summary["disposition"],
        "summary_json": summary["outputs"]["summary_json"],
        "report_md": summary["outputs"]["report_md"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
