#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

STAGE = "Stage145_CLEAN_LEDGER_PERFORMANCE_GATE"
STATUS = "STAGE145_COMPLETE_CLEAN_LEDGER_PERFORMANCE_GATE_READY"

DEFAULT_CLEAN_LEDGER = "data/demo_execution/stage144_clean_demo_execution_ledger.csv"

RISK_BLOCKS = [
    "NO_ORDER_SEND_IN_STAGE145",
    "NO_POSITION_MODIFICATION_IN_STAGE145",
    "CLEAN_LEDGER_ONLY",
    "DEMO_PERFORMANCE_GATE",
    "NO_LIVE_REAL_PROMOTION_FROM_SMALL_N",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


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


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def f(v: Any, default: float = 0.0) -> float:
    try:
        s = str(v).strip()
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def normalize_outcome(v: Any) -> str:
    return str(v or "").strip().upper()


def max_consecutive_losses(rows: List[Dict[str, str]]) -> int:
    best = 0
    cur = 0
    for r in rows:
        if normalize_outcome(r.get("outcome")) == "LOSS":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def evaluate(rows: List[Dict[str, str]], min_eval_trades: int, min_continue_win_rate: float, min_continue_mean_bps: float, max_loss_streak: int) -> Dict[str, Any]:
    closed = [r for r in rows if normalize_outcome(r.get("outcome")) in {"PROFIT", "LOSS", "FLAT"}]
    n = len(closed)
    profits = [f(r.get("net_profit")) for r in closed]
    bps = [f(r.get("bps_move")) for r in closed]
    wins = [r for r in closed if normalize_outcome(r.get("outcome")) == "PROFIT"]
    losses = [r for r in closed if normalize_outcome(r.get("outcome")) == "LOSS"]
    flats = [r for r in closed if normalize_outcome(r.get("outcome")) == "FLAT"]
    loss_streak = max_consecutive_losses(closed)

    win_rate = round(len(wins) / n, 4) if n else 0.0
    total_net = round(sum(profits), 2)
    mean_net = round(total_net / n, 2) if n else 0.0
    total_bps = round(sum(bps), 2)
    mean_bps = round(total_bps / n, 2) if n else 0.0

    last = closed[-1] if closed else {}
    last_outcome = normalize_outcome(last.get("outcome"))

    if n == 0:
        gate_decision = "STAGE145_NO_CLOSED_DEMO_OUTCOMES"
        action = "COLLECT_DEMO_OUTCOMES"
        severity = "INFO"
    elif loss_streak >= max_loss_streak:
        gate_decision = "STAGE145_FREEZE_REPAIR_RULE_LOSS_STREAK"
        action = "FREEZE_CURRENT_RULE_AND_REPAIR_DISCOVERY"
        severity = "HIGH"
    elif n < min_eval_trades:
        gate_decision = "STAGE145_CONTINUE_DEMO_ACCUMULATION_SMALL_N"
        action = "CONTINUE_DEMO_LOOP_NO_LIVE_PROMOTION"
        severity = "INFO"
    elif win_rate >= min_continue_win_rate and mean_bps >= min_continue_mean_bps and total_net > 0:
        gate_decision = "STAGE145_DEMO_EDGE_STILL_POSITIVE_CONTINUE_ACCUMULATION"
        action = "CONTINUE_DEMO_LOOP_PREPARE_DEEPER_AUDIT"
        severity = "LOW"
    elif total_net <= 0 or mean_bps <= 0:
        gate_decision = "STAGE145_FREEZE_REPAIR_RULE_NEGATIVE_EXPECTANCY"
        action = "FREEZE_CURRENT_RULE_AND_REPAIR_DISCOVERY"
        severity = "HIGH"
    else:
        gate_decision = "STAGE145_DEMO_EDGE_MARGINAL_CONTINUE_WITH_CAUTION"
        action = "CONTINUE_DEMO_LOOP_WITH_CAUTION"
        severity = "MEDIUM"

    return {
        "closed_trade_count": n,
        "profit_count": len(wins),
        "loss_count": len(losses),
        "flat_count": len(flats),
        "win_rate": win_rate,
        "total_net_profit": total_net,
        "mean_net_profit": mean_net,
        "total_bps": total_bps,
        "mean_bps": mean_bps,
        "max_consecutive_losses": loss_streak,
        "last_outcome": last_outcome,
        "last_signal_key": last.get("signal_key", ""),
        "last_rule_id": last.get("rule_id", ""),
        "last_net_profit": last.get("net_profit", ""),
        "last_bps_move": last.get("bps_move", ""),
        "gate_decision": gate_decision,
        "recommended_action": action,
        "severity": severity,
    }


FIELDS = [
    "snapshot_utc",
    "gate_decision",
    "recommended_action",
    "severity",
    "closed_trade_count",
    "profit_count",
    "loss_count",
    "flat_count",
    "win_rate",
    "total_net_profit",
    "mean_net_profit",
    "total_bps",
    "mean_bps",
    "max_consecutive_losses",
    "last_outcome",
    "last_signal_key",
    "last_rule_id",
    "last_net_profit",
    "last_bps_move",
]


def run(root: Path, clean_ledger: Path, min_eval_trades: int, min_continue_win_rate: float, min_continue_mean_bps: float, max_loss_streak: int) -> Dict[str, Any]:
    root = root.expanduser()
    ledger_path = clean_ledger if clean_ledger.is_absolute() else root / clean_ledger
    out = ensure_dir(root / "reports/stage145_clean_ledger_performance_gate")
    data = ensure_dir(root / "data/demo_execution")
    generated = utc_now()

    rows = read_csv_rows(ledger_path)
    metrics = evaluate(rows, min_eval_trades, min_continue_win_rate, min_continue_mean_bps, max_loss_streak)

    row = {"snapshot_utc": generated, **metrics}
    latest_csv = out / "stage145_latest_performance_gate_snapshot.csv"
    history_csv = data / "stage145_clean_ledger_performance_gate_snapshots.csv"
    risk_csv = out / "stage145_risk_manifest.csv"
    write_csv(latest_csv, [row], FIELDS)

    exists = history_csv.exists() and history_csv.stat().st_size > 0
    with history_csv.open("a", encoding="utf-8", newline="") as fobj:
        w = csv.DictWriter(fobj, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)

    write_csv(risk_csv, [{"risk_block": x, "status": "ACTIVE"} for x in RISK_BLOCKS], ["risk_block", "status"])

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "root": str(root),
        "clean_ledger": str(ledger_path),
        "clean_ledger_exists": ledger_path.exists(),
        "min_eval_trades": min_eval_trades,
        "min_continue_win_rate": min_continue_win_rate,
        "min_continue_mean_bps": min_continue_mean_bps,
        "max_loss_streak": max_loss_streak,
        **metrics,
        "latest_csv": str(latest_csv),
        "history_csv": str(history_csv),
        "risk_manifest_csv": str(risk_csv),
        "summary_json": str(out / "stage145_clean_ledger_performance_gate_summary.json"),
        "next": [
            "Continue the demo loop while gate_decision is small-N continue or positive continue.",
            "Do not promote to real/live from this sample size.",
            "If gate_decision becomes freeze/repair, stop allowing the current rule family and return to discovery repair.",
        ],
    }
    write_json(out / "stage145_clean_ledger_performance_gate_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--clean-ledger", default=DEFAULT_CLEAN_LEDGER)
    ap.add_argument("--min-eval-trades", type=int, default=10)
    ap.add_argument("--min-continue-win-rate", type=float, default=0.55)
    ap.add_argument("--min-continue-mean-bps", type=float, default=2.0)
    ap.add_argument("--max-loss-streak", type=int, default=3)
    args = ap.parse_args()
    run(
        root=Path(args.root),
        clean_ledger=Path(args.clean_ledger),
        min_eval_trades=args.min_eval_trades,
        min_continue_win_rate=args.min_continue_win_rate,
        min_continue_mean_bps=args.min_continue_mean_bps,
        max_loss_streak=args.max_loss_streak,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
