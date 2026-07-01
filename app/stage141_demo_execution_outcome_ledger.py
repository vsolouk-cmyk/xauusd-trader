#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage141_DEMO_EXECUTION_OUTCOME_LEDGER"
STATUS = "STAGE141_COMPLETE_DEMO_EXECUTION_OUTCOME_LEDGER_READY"

DEFAULT_STAGE134_SUMMARY = "reports/stage134_demo_executor_pilot/stage134_demo_executor_pilot_summary.json"
DEFAULT_STAGE138_SUMMARY = "reports/stage138_broker_technical_demo_discovery/stage138_broker_technical_demo_discovery_summary.json"
DEFAULT_STAGE140_SUMMARY = "reports/stage140_demo_closed_deal_outcome_monitor/stage140_demo_closed_deal_outcome_monitor_summary.json"

RISK_BLOCKS = [
    "NO_ORDER_SEND_IN_STAGE141",
    "NO_POSITION_MODIFICATION_IN_STAGE141",
    "LEDGER_ONLY",
    "DEMO_OUTCOME_CLASSIFICATION",
    "DUPLICATE_OUTCOME_GUARD_BY_SIGNAL_AND_EXIT_DEAL",
    "CONTINUE_LOOP_ONLY_ON_NEXT_DISTINCT_SIGNAL",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists() or path.stat().st_size <= 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def to_float(v: Any) -> float | None:
    try:
        s = str(v).strip()
        if not s:
            return None
        x = float(s)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def infer_exit_reason(stage140: Dict[str, Any]) -> str:
    # Prefer human-readable deal comment because Stage140B writes numeric reason codes for compile compatibility.
    for deal in reversed(stage140.get("recent_deals", []) or []):
        entry_code = str(deal.get("entry_code", "")).strip()
        comment = str(deal.get("comment", "")).lower()
        if entry_code in {"1", "2", "3"}:
            if "tp" in comment:
                return "TP"
            if "sl" in comment:
                return "SL"
            if "so" in comment or "stop out" in comment:
                return "STOP_OUT"
            if "close" in comment:
                return "CLOSE"
    label = str(stage140.get("latest_exit_reason_label", "")).strip()
    code = str(stage140.get("latest_exit_reason_code", "")).strip()
    # Preserve label only if it is not suspiciously inconsistent with TP/SL comments.
    if label:
        return label
    return code or ""


def infer_outcome(stage140: Dict[str, Any]) -> Tuple[str, str]:
    decision = str(stage140.get("collector_decision", ""))
    net = to_float(stage140.get("latest_net_profit"))
    reason = infer_exit_reason(stage140)

    if "PROFIT" in decision or (net is not None and net > 0):
        return "PROFIT", reason
    if "LOSS" in decision or (net is not None and net < 0):
        return "LOSS", reason
    if "FLAT" in decision or (net is not None and net == 0):
        return "FLAT", reason
    if "ENTRY_DEAL_FOUND_BUT_NO_EXIT" in decision:
        return "OPEN_OR_UNRESOLVED", reason
    return "UNKNOWN", reason


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.replace(path)


def append_unique_csv(path: Path, row: Dict[str, Any], fields: List[str], key_fields: List[str]) -> Tuple[int, bool]:
    ensure_dir(path.parent)
    existing = read_csv_rows(path)
    key = tuple(str(row.get(k, "")) for k in key_fields)
    for r in existing:
        if tuple(str(r.get(k, "")) for k in key_fields) == key:
            return len(existing), False
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fields})
    return len(existing) + 1, True


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


FIELDS = [
    "ledger_utc",
    "stage",
    "outcome_status",
    "next_action",
    "rule_id",
    "signal_key",
    "entry_time",
    "entry_price",
    "entry_volume",
    "entry_deal_ticket",
    "exit_time",
    "exit_price",
    "exit_volume",
    "exit_deal_ticket",
    "exit_reason",
    "exit_reason_code",
    "net_profit",
    "points_move",
    "bps_move",
    "retcode",
    "retcode_description",
    "account_mode",
    "stage134_trade_attempts",
    "stage134_trade_accepted",
    "stage138_selected_label",
    "stage138_validation_mean_bps",
    "stage138_tail_mean_bps",
    "stage138_bar_max_utc",
]


def run(root: Path, stage134_summary_path: Path, stage138_summary_path: Path, stage140_summary_path: Path) -> Dict[str, Any]:
    root = root.expanduser()
    s134p = stage134_summary_path if stage134_summary_path.is_absolute() else root / stage134_summary_path
    s138p = stage138_summary_path if stage138_summary_path.is_absolute() else root / stage138_summary_path
    s140p = stage140_summary_path if stage140_summary_path.is_absolute() else root / stage140_summary_path

    s134 = read_json(s134p)
    s138 = read_json(s138p)
    s140 = read_json(s140p)

    out = ensure_dir(root / "reports/stage141_demo_execution_outcome_ledger")
    data = ensure_dir(root / "data/demo_execution")
    ledger_path = data / "stage141_demo_execution_outcome_ledger.csv"
    latest_path = out / "stage141_latest_demo_execution_outcome.csv"
    risk_path = out / "stage141_risk_manifest.csv"
    generated = utc_now()

    outcome, exit_reason = infer_outcome(s140)
    net = to_float(s140.get("latest_net_profit"))

    if outcome == "PROFIT":
        next_action = "CONTINUE_DEMO_LOOP_ALLOW_NEXT_DISTINCT_SIGNAL"
        decision = "STAGE141_DEMO_OUTCOME_PROFIT_CONFIRMED_CONTINUE_LOOP"
    elif outcome == "LOSS":
        next_action = "FREEZE_OR_REPAIR_RULE_IF_LOSS_CLUSTER_CONTINUES"
        decision = "STAGE141_DEMO_OUTCOME_LOSS_CONFIRMED_REVIEW_RULE"
    elif outcome == "FLAT":
        next_action = "CONTINUE_DEMO_LOOP_WITH_COST_REVIEW"
        decision = "STAGE141_DEMO_OUTCOME_FLAT_CONFIRMED_REVIEW_COST"
    elif outcome == "OPEN_OR_UNRESOLVED":
        next_action = "KEEP_MONITORING_STAGE139_STAGE140"
        decision = "STAGE141_DEMO_OUTCOME_UNRESOLVED_KEEP_MONITORING"
    else:
        next_action = "REVIEW_STAGE140_HISTORY_OUTPUT"
        decision = "STAGE141_DEMO_OUTCOME_UNKNOWN_REVIEW_HISTORY"

    selected_score = s138.get("selected_score") or {}

    row = {
        "ledger_utc": generated,
        "stage": STAGE,
        "outcome_status": outcome,
        "next_action": next_action,
        "rule_id": s140.get("latest_stage134_rule_id") or s134.get("latest_trade_rule_id") or s138.get("selected_rule_id"),
        "signal_key": s140.get("latest_stage134_signal_key") or s134.get("latest_trade_signal_key"),
        "entry_time": s140.get("latest_entry_time"),
        "entry_price": s140.get("latest_entry_price") or s140.get("latest_stage134_entry_price") or s134.get("latest_trade_price"),
        "entry_volume": s140.get("latest_entry_volume") or s140.get("latest_stage134_lot") or s134.get("latest_trade_lot"),
        "entry_deal_ticket": s140.get("latest_entry_deal_ticket"),
        "exit_time": s140.get("latest_exit_time"),
        "exit_price": s140.get("latest_exit_price"),
        "exit_volume": s140.get("latest_exit_volume"),
        "exit_deal_ticket": s140.get("latest_exit_deal_ticket"),
        "exit_reason": exit_reason,
        "exit_reason_code": s140.get("latest_exit_reason_code"),
        "net_profit": s140.get("latest_net_profit"),
        "points_move": s140.get("latest_points_move"),
        "bps_move": s140.get("latest_bps_move"),
        "retcode": s140.get("latest_stage134_retcode") or s134.get("latest_trade_retcode"),
        "retcode_description": s134.get("latest_trade_retcode_description") or s134.get("last_retcode_description"),
        "account_mode": s140.get("account_mode") or s134.get("account_mode"),
        "stage134_trade_attempts": s140.get("stage134_trade_attempts") or s134.get("trade_attempts"),
        "stage134_trade_accepted": s140.get("stage134_trade_accepted") or s134.get("trade_accepted"),
        "stage138_selected_label": s138.get("selected_label"),
        "stage138_validation_mean_bps": selected_score.get("validation_mean_bps", ""),
        "stage138_tail_mean_bps": selected_score.get("tail_mean_bps", ""),
        "stage138_bar_max_utc": s138.get("bar_max_utc", ""),
    }

    ledger_count, appended = append_unique_csv(
        ledger_path,
        row,
        FIELDS,
        key_fields=["signal_key", "entry_deal_ticket", "exit_deal_ticket"],
    )
    write_csv(latest_path, [row], FIELDS)
    write_csv(risk_path, [{"risk_block": b, "status": "ACTIVE"} for b in RISK_BLOCKS], ["risk_block", "status"])

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "decision": decision,
        "root": str(root),
        "stage134_summary": str(s134p),
        "stage138_summary": str(s138p),
        "stage140_summary": str(s140p),
        "outcome_status": outcome,
        "exit_reason_inferred": exit_reason,
        "net_profit": row["net_profit"],
        "points_move": row["points_move"],
        "bps_move": row["bps_move"],
        "rule_id": row["rule_id"],
        "signal_key": row["signal_key"],
        "entry_price": row["entry_price"],
        "exit_price": row["exit_price"],
        "entry_deal_ticket": row["entry_deal_ticket"],
        "exit_deal_ticket": row["exit_deal_ticket"],
        "ledger_csv": str(ledger_path),
        "latest_csv": str(latest_path),
        "ledger_row_appended": appended,
        "ledger_row_count": ledger_count,
        "next_action": next_action,
        "next": [
            "Keep Stage138 refresh running and keep Stage134 duplicate guard enabled.",
            "Allow the next demo order only on a distinct new signal key, not the already closed signal.",
            "After several outcomes, evaluate rule expectancy from the Stage141 ledger before live-real consideration.",
        ],
    }
    write_json(out / "stage141_demo_execution_outcome_ledger_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--stage134-summary", default=DEFAULT_STAGE134_SUMMARY)
    ap.add_argument("--stage138-summary", default=DEFAULT_STAGE138_SUMMARY)
    ap.add_argument("--stage140-summary", default=DEFAULT_STAGE140_SUMMARY)
    args = ap.parse_args()
    run(
        root=Path(args.root),
        stage134_summary_path=Path(args.stage134_summary),
        stage138_summary_path=Path(args.stage138_summary),
        stage140_summary_path=Path(args.stage140_summary),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
