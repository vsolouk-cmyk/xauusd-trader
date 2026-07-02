#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

STAGE = "Stage144_DEMO_EXECUTION_LEDGER_AUDIT"
STATUS = "STAGE144_COMPLETE_DEMO_EXECUTION_LEDGER_AUDIT_READY"

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)

TRADE_LOG = "xauusd_stage134_demo_executor_trade_log.csv"
DEALS_HISTORY = "xauusd_stage140_demo_deals_history.csv"

RISK_BLOCKS = [
    "NO_ORDER_SEND_IN_STAGE144",
    "NO_POSITION_MODIFICATION_IN_STAGE144",
    "READ_ONLY_LEDGER_AUDIT",
    "RECONCILE_TRADE_LOG_AND_DEAL_HISTORY",
    "DO_NOT_PROMOTE_FROM_DIRTY_LEDGER",
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


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        s = str(v).strip()
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def norm(v: Any) -> str:
    return str(v or "").strip()


def is_attempt_row(r: Dict[str, str]) -> bool:
    return "ATTEMPT" in str(r.get("event_type", "")) or str(r.get("ok", "")).lower() == "true"


def infer_exit_reason(comment: str, reason_code: str) -> str:
    c = str(comment or "").lower()
    if "tp" in c:
        return "TP"
    if "sl" in c:
        return "SL"
    if "so" in c or "stop out" in c:
        return "STOP_OUT"
    return str(reason_code or "").strip()


def unique_attempts(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out = []
    seen = set()
    for r in rows:
        if not is_attempt_row(r):
            continue
        key = (norm(r.get("signal_key")), norm(r.get("rule_id")), norm(r.get("price")), norm(r.get("retcode")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def unique_deals(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out = []
    seen = set()
    for r in rows:
        ticket = norm(r.get("ticket"))
        if not ticket or ticket in seen:
            continue
        seen.add(ticket)
        out.append(r)
    return out


def build_position_pairs(deals: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    by_pos: Dict[str, Dict[str, Any]] = {}
    for d in deals:
        pos = norm(d.get("position_id"))
        if not pos:
            continue
        entry_code = norm(d.get("entry_code"))
        item = by_pos.setdefault(pos, {"position_id": pos, "entries": [], "exits": []})
        if entry_code in {"0", "2"}:
            item["entries"].append(d)
        if entry_code in {"1", "2", "3"}:
            item["exits"].append(d)

    pairs = []
    for pos, item in by_pos.items():
        entries = sorted(item["entries"], key=lambda x: norm(x.get("time")))
        exits = sorted(item["exits"], key=lambda x: norm(x.get("time")))
        if not entries:
            continue
        entry = entries[-1]
        exit_ = exits[-1] if exits else {}
        profit = to_float(exit_.get("profit", 0)) + to_float(exit_.get("swap", 0)) + to_float(exit_.get("commission", 0))
        entry_price = to_float(entry.get("price", 0))
        exit_price = to_float(exit_.get("price", 0))
        entry_type = norm(entry.get("type_code"))
        if entry_price and exit_price:
            points = (entry_price - exit_price) if entry_type == "1" else (exit_price - entry_price)
            bps = points / entry_price * 10000.0
        else:
            points = 0.0
            bps = 0.0
        pairs.append({
            "position_id": pos,
            "entry_deal_ticket": entry.get("ticket", ""),
            "entry_time": entry.get("time", ""),
            "entry_price": entry.get("price", ""),
            "entry_volume": entry.get("volume", ""),
            "entry_comment": entry.get("comment", ""),
            "exit_deal_ticket": exit_.get("ticket", ""),
            "exit_time": exit_.get("time", ""),
            "exit_price": exit_.get("price", ""),
            "exit_volume": exit_.get("volume", ""),
            "exit_comment": exit_.get("comment", ""),
            "exit_reason_code": exit_.get("reason_code", ""),
            "exit_reason": infer_exit_reason(exit_.get("comment", ""), exit_.get("reason_code", "")),
            "net_profit": round(profit, 2),
            "points_move": round(points, 2),
            "bps_move": round(bps, 2),
            "closed": bool(exit_),
        })
    return sorted(pairs, key=lambda x: norm(x.get("entry_time")))


def match_attempts_to_pairs(attempts: List[Dict[str, str]], pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    used_pairs = set()
    for idx, a in enumerate(attempts):
        a_price = to_float(a.get("price", 0))
        a_rule = norm(a.get("rule_id"))
        best_i = None
        best_score = 10**9
        for i, p in enumerate(pairs):
            if i in used_pairs:
                continue
            p_price = to_float(p.get("entry_price", 0))
            score = abs(a_price - p_price) if a_price and p_price else 999999
            entry_comment = norm(p.get("entry_comment"))
            if a_rule and a_rule[:24] in entry_comment:
                score -= 100
            if score < best_score:
                best_score = score
                best_i = i
        pair = pairs[best_i] if best_i is not None else {}
        if best_i is not None:
            used_pairs.add(best_i)

        outcome = "OPEN_OR_UNMATCHED"
        if pair and pair.get("closed"):
            net = to_float(pair.get("net_profit", 0))
            outcome = "PROFIT" if net > 0 else ("LOSS" if net < 0 else "FLAT")

        rows.append({
            "audit_order": idx + 1,
            "signal_key": norm(a.get("signal_key")),
            "rule_id": a_rule,
            "feature_date": a.get("feature_date", ""),
            "retcode": a.get("retcode", ""),
            "retcode_description": a.get("retcode_description", ""),
            "account_mode": a.get("account_mode", ""),
            "entry_price_from_trade_log": a.get("price", ""),
            "lot_from_trade_log": a.get("lot", ""),
            "position_id": pair.get("position_id", ""),
            "entry_deal_ticket": pair.get("entry_deal_ticket", ""),
            "entry_time": pair.get("entry_time", ""),
            "entry_price": pair.get("entry_price", ""),
            "entry_volume": pair.get("entry_volume", ""),
            "exit_deal_ticket": pair.get("exit_deal_ticket", ""),
            "exit_time": pair.get("exit_time", ""),
            "exit_price": pair.get("exit_price", ""),
            "exit_volume": pair.get("exit_volume", ""),
            "exit_reason": pair.get("exit_reason", ""),
            "exit_reason_code": pair.get("exit_reason_code", ""),
            "net_profit": pair.get("net_profit", ""),
            "points_move": pair.get("points_move", ""),
            "bps_move": pair.get("bps_move", ""),
            "outcome": outcome,
        })
    return rows


FIELDS = [
    "audit_order", "signal_key", "rule_id", "feature_date", "retcode", "retcode_description",
    "account_mode", "entry_price_from_trade_log", "lot_from_trade_log", "position_id",
    "entry_deal_ticket", "entry_time", "entry_price", "entry_volume", "exit_deal_ticket",
    "exit_time", "exit_price", "exit_volume", "exit_reason", "exit_reason_code",
    "net_profit", "points_move", "bps_move", "outcome",
]


def run(root: Path, mt5_files: Path) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    out = ensure_dir(root / "reports/stage144_demo_execution_ledger_audit")
    data = ensure_dir(root / "data/demo_execution")
    generated = utc_now()

    trade_log_path = mt5_files / TRADE_LOG
    deals_history_path = mt5_files / DEALS_HISTORY
    raw_attempts = read_csv_rows(trade_log_path)
    raw_deals = read_csv_rows(deals_history_path)
    attempts = unique_attempts(raw_attempts)
    deals = unique_deals(raw_deals)
    pairs = build_position_pairs(deals)
    clean_rows = match_attempts_to_pairs(attempts, pairs)

    closed = [r for r in clean_rows if r.get("outcome") in {"PROFIT", "LOSS", "FLAT"}]
    profits = [to_float(r.get("net_profit", 0)) for r in closed]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    bps_values = [to_float(r.get("bps_move", 0)) for r in closed]

    report_clean_csv = out / "stage144_clean_demo_execution_ledger.csv"
    canonical_csv = data / "stage144_clean_demo_execution_ledger.csv"
    risk_csv = out / "stage144_risk_manifest.csv"
    write_csv(report_clean_csv, clean_rows, FIELDS)
    write_csv(canonical_csv, clean_rows, FIELDS)
    write_csv(risk_csv, [{"risk_block": b, "status": "ACTIVE"} for b in RISK_BLOCKS], ["risk_block", "status"])

    raw_stage141 = root / "data/demo_execution/stage141_demo_execution_outcome_ledger.csv"
    raw_stage141_rows = read_csv_rows(raw_stage141)
    stage141_row_count = len(raw_stage141_rows)
    clean_count = len(clean_rows)
    closed_count = len(closed)
    mismatch = stage141_row_count != clean_count

    if mismatch:
        decision = "STAGE144_LEDGER_COUNT_MISMATCH_USE_CLEAN_RECONCILED_LEDGER"
    elif closed_count == clean_count and clean_count > 0:
        decision = "STAGE144_LEDGER_RECONCILED_ALL_TRADES_CLOSED"
    elif clean_count == 0:
        decision = "STAGE144_NO_DEMO_TRADES_FOUND"
    else:
        decision = "STAGE144_LEDGER_RECONCILED_SOME_TRADES_OPEN_OR_UNMATCHED"

    summary = {
        "stage": STAGE,
        "generated_utc": generated,
        "status": STATUS,
        "decision": decision,
        "root": str(root),
        "mt5_files": str(mt5_files),
        "trade_log": str(trade_log_path),
        "deals_history": str(deals_history_path),
        "raw_trade_log_rows": len(raw_attempts),
        "unique_trade_attempts": len(attempts),
        "raw_deal_history_rows": len(raw_deals),
        "unique_deals": len(deals),
        "position_pairs": len(pairs),
        "stage141_raw_ledger_csv": str(raw_stage141),
        "stage141_raw_ledger_row_count": stage141_row_count,
        "clean_ledger_row_count": clean_count,
        "closed_trade_count": closed_count,
        "ledger_count_mismatch": mismatch,
        "profit_count": len(wins),
        "loss_count": len(losses),
        "flat_count": len([p for p in profits if p == 0]),
        "total_net_profit": round(sum(profits), 2),
        "mean_net_profit": round(sum(profits) / len(profits), 2) if profits else 0.0,
        "total_bps": round(sum(bps_values), 2),
        "mean_bps": round(sum(bps_values) / len(bps_values), 2) if bps_values else 0.0,
        "win_rate": round(len(wins) / len(profits), 4) if profits else 0.0,
        "latest_outcome": clean_rows[-1] if clean_rows else {},
        "clean_ledger_csv": str(canonical_csv),
        "report_clean_ledger_csv": str(report_clean_csv),
        "risk_manifest_csv": str(risk_csv),
        "summary_json": str(out / "stage144_demo_execution_ledger_audit_summary.json"),
        "next": [
            "Use the clean Stage144 ledger for operational evaluation when Stage141 row count is inconsistent.",
            "Continue demo execution loop, but do not promote from fewer than several reconciled closed outcomes.",
            "If ledger_count_mismatch persists, patch Stage141 to read/write from Stage144 clean ledger baseline.",
        ],
    }
    write_json(out / "stage144_demo_execution_ledger_audit_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    args = ap.parse_args()
    run(Path(args.root), Path(args.mt5_files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
