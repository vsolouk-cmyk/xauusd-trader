#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage144C_DEMO_EXECUTION_LEDGER_AUDIT"
STATUS = "STAGE144C_COMPLETE_ROBUST_DEAL_RECONCILIATION_READY"

DEFAULT_MT5_FILES = "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"
TRADE_LOG_NAME = "xauusd_stage134_demo_executor_trade_log.csv"
DEALS_HISTORY_NAME = "xauusd_stage140_demo_deals_history.csv"

RISK_BLOCKS = [
    "NO_ORDER_SEND_IN_STAGE144C",
    "NO_POSITION_MODIFICATION_IN_STAGE144C",
    "READ_ONLY_RECONCILIATION",
    "USE_SUCCESSFUL_DEMO_BUY_ATTEMPTS_ONLY",
    "TIME_EXIT_TRADE_LOG_ROWS_ARE_NOT_NEW_ATTEMPTS",
    "PAIR_BY_DEAL_POSITION_ID_AFTER_MATCHING_ENTRY_DEAL",
]


@dataclass
class Attempt:
    audit_order: int
    signal_key: str
    rule_id: str
    feature_date: str
    time_current: str
    symbol: str
    lot: str
    price: float
    sl: str
    tp: str
    retcode: str
    retcode_description: str
    account_mode: str
    raw: Dict[str, str]


@dataclass
class Deal:
    deal_ticket: str
    deal_time: str
    symbol: str
    position_id: str
    entry_code: str
    deal_type: str
    volume: float
    price: float
    profit: float
    swap: float
    commission: float
    magic: str
    reason_code: str
    comment: str
    generated_utc: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_bool(v: Any) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes", "y"}


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        s = str(v).strip()
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def clean_str(v: Any) -> str:
    return "" if v is None else str(v).strip()


def parse_dt(v: str) -> Optional[datetime]:
    s = clean_str(v)
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def seconds_between(a: str, b: str) -> Optional[float]:
    da, db = parse_dt(a), parse_dt(b)
    if da is None or db is None:
        return None
    return abs((da - db).total_seconds())


def read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        return [dict(r) for r in reader if any(clean_str(x) for x in r.values())]


def read_csv_rows(path: Path) -> Tuple[Optional[List[str]], List[List[str]]]:
    if not path.exists() or path.stat().st_size <= 0:
        return None, []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except Exception:
            dialect = csv.excel
        rows = [row for row in csv.reader(f, dialect=dialect) if any(clean_str(x) for x in row)]
    if not rows:
        return None, []
    first = [clean_str(x) for x in rows[0]]
    lower = {x.lower() for x in first}
    # Headerless Stage140 rows can legitimately contain comments such as "comment".
    # Treat as header only when structural column names are present, not just a free-text comment value.
    structural_header_hits = sum(1 for x in {"deal_ticket", "ticket", "deal_time", "position_id", "profit", "symbol", "price", "volume"} if x in lower)
    has_header = structural_header_hits >= 2
    if has_header:
        return first, rows[1:]
    return None, rows


def parse_attempts(path: Path) -> List[Attempt]:
    rows = read_csv_dicts(path)
    attempts: List[Attempt] = []
    seen: set[str] = set()
    for r in rows:
        event_type = clean_str(r.get("event_type"))
        if event_type != "DEMO_BUY_ATTEMPT":
            continue
        if not parse_bool(r.get("ok")):
            continue
        signal_key = clean_str(r.get("signal_key"))
        if not signal_key:
            continue
        # Deduplicate real entries by signal key. TIME_EXIT rows are already excluded.
        if signal_key in seen:
            continue
        seen.add(signal_key)
        attempts.append(
            Attempt(
                audit_order=len(attempts) + 1,
                signal_key=signal_key,
                rule_id=clean_str(r.get("rule_id")),
                feature_date=clean_str(r.get("feature_date")),
                time_current=clean_str(r.get("time_current")),
                symbol=clean_str(r.get("symbol")),
                lot=clean_str(r.get("lot")),
                price=to_float(r.get("price")),
                sl=clean_str(r.get("sl")),
                tp=clean_str(r.get("tp")),
                retcode=clean_str(r.get("retcode")),
                retcode_description=clean_str(r.get("retcode_description")),
                account_mode=clean_str(r.get("account_mode")),
                raw=r,
            )
        )
    return attempts


HEADER_INDEX_MAP = {
    "generated_utc": ["generated_utc", "snapshot_utc"],
    "deal_ticket": ["deal_ticket", "ticket", "deal_id"],
    "deal_time": ["deal_time", "time", "time_utc"],
    "symbol": ["symbol"],
    "position_id": ["position_id", "position"],
    "entry_code": ["entry", "deal_entry", "entry_code"],
    "deal_type": ["type", "deal_type"],
    "volume": ["volume", "deal_volume"],
    "price": ["price", "deal_price"],
    "profit": ["profit"],
    "swap": ["swap"],
    "commission": ["commission"],
    "magic": ["magic"],
    "reason_code": ["reason", "reason_code"],
    "comment": ["comment"],
}


def col_by_header(header: List[str], row: List[str], key: str, default: str = "") -> str:
    lowered = [h.strip().lower() for h in header]
    for name in HEADER_INDEX_MAP[key]:
        if name in lowered:
            idx = lowered.index(name)
            return clean_str(row[idx]) if idx < len(row) else default
    return default


def parse_deal_from_header(header: List[str], row: List[str]) -> Optional[Deal]:
    ticket = col_by_header(header, row, "deal_ticket")
    if not ticket:
        return None
    return Deal(
        generated_utc=col_by_header(header, row, "generated_utc"),
        deal_ticket=ticket,
        deal_time=col_by_header(header, row, "deal_time"),
        symbol=col_by_header(header, row, "symbol"),
        position_id=col_by_header(header, row, "position_id"),
        entry_code=col_by_header(header, row, "entry_code"),
        deal_type=col_by_header(header, row, "deal_type"),
        volume=to_float(col_by_header(header, row, "volume")),
        price=to_float(col_by_header(header, row, "price")),
        profit=to_float(col_by_header(header, row, "profit")),
        swap=to_float(col_by_header(header, row, "swap")),
        commission=to_float(col_by_header(header, row, "commission")),
        magic=col_by_header(header, row, "magic"),
        reason_code=col_by_header(header, row, "reason_code"),
        comment=col_by_header(header, row, "comment"),
    )


def parse_deal_from_positional(row: List[str]) -> Optional[Deal]:
    # Stage140 observed headerless layout:
    # generated_utc,ticket,deal_time,symbol,position_id,entry_code,type,volume,price,profit,swap,commission,magic,reason,comment
    if len(row) < 14:
        return None
    ticket = clean_str(row[1])
    if not ticket or not ticket.isdigit():
        return None
    return Deal(
        generated_utc=clean_str(row[0]),
        deal_ticket=ticket,
        deal_time=clean_str(row[2]),
        symbol=clean_str(row[3]),
        position_id=clean_str(row[4]),
        entry_code=clean_str(row[5]),
        deal_type=clean_str(row[6]),
        volume=to_float(row[7]),
        price=to_float(row[8]),
        profit=to_float(row[9]),
        swap=to_float(row[10]),
        commission=to_float(row[11]),
        magic=clean_str(row[12]),
        reason_code=clean_str(row[13]),
        comment=clean_str(row[14]) if len(row) > 14 else "",
    )


def parse_deals(path: Path) -> List[Deal]:
    header, rows = read_csv_rows(path)
    by_ticket: Dict[str, Deal] = {}
    for row in rows:
        d = parse_deal_from_header(header, row) if header else parse_deal_from_positional(row)
        if not d:
            continue
        # Keep latest collector snapshot for duplicate ticket rows.
        by_ticket[d.deal_ticket] = d
    deals = list(by_ticket.values())
    deals.sort(key=lambda d: (parse_dt(d.deal_time) or datetime.min.replace(tzinfo=timezone.utc), d.deal_ticket))
    return deals


def is_entry(d: Deal) -> bool:
    return d.entry_code == "0"


def is_exit(d: Deal) -> bool:
    return d.entry_code == "1"


def match_attempt_to_entry(attempt: Attempt, entry_deals: List[Deal], used_tickets: set[str]) -> Optional[Deal]:
    candidates: List[Tuple[float, Deal]] = []
    for d in entry_deals:
        if d.deal_ticket in used_tickets:
            continue
        if attempt.symbol and d.symbol and attempt.symbol != d.symbol:
            continue
        if abs(d.volume - to_float(attempt.lot)) > 1e-9:
            continue
        price_diff = abs(d.price - attempt.price) if attempt.price else 0.0
        dt = seconds_between(attempt.time_current, d.deal_time)
        # Prefer exact/near MT5 fill time and price. Allow broad windows because MT5 local/server offsets can vary.
        if dt is None:
            dt_score = 3600.0
        else:
            dt_score = dt
        if price_diff <= 1.0 and dt_score <= 6 * 3600:
            score = dt_score + price_diff * 1000.0
            candidates.append((score, d))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def infer_exit_reason(exit_deals: List[Deal]) -> Tuple[str, str]:
    if not exit_deals:
        return "", ""
    comment = " ".join(d.comment.lower() for d in exit_deals)
    codes = ";".join(d.reason_code for d in exit_deals if d.reason_code)
    if "[tp" in comment or any(d.reason_code == "5" for d in exit_deals):
        return "TP", codes
    if "[sl" in comment or any(d.reason_code == "4" for d in exit_deals):
        return "SL", codes
    if any(d.reason_code == "3" for d in exit_deals):
        return "TIME_EXIT", codes
    return "CLOSE", codes


def build_ledger(attempts: List[Attempt], deals: List[Deal]) -> List[Dict[str, Any]]:
    entry_deals = [d for d in deals if is_entry(d)]
    deals_by_pos: Dict[str, List[Deal]] = {}
    for d in deals:
        deals_by_pos.setdefault(d.position_id, []).append(d)
    used_entries: set[str] = set()
    rows: List[Dict[str, Any]] = []
    for a in attempts:
        entry = match_attempt_to_entry(a, entry_deals, used_entries)
        if entry:
            used_entries.add(entry.deal_ticket)
        exit_deals: List[Deal] = []
        if entry and entry.position_id:
            exit_deals = [d for d in deals_by_pos.get(entry.position_id, []) if is_exit(d)]
            exit_deals.sort(key=lambda d: parse_dt(d.deal_time) or datetime.max.replace(tzinfo=timezone.utc))
        if entry and exit_deals:
            net = round(sum(d.profit + d.swap + d.commission for d in exit_deals), 2)
            exit_price = exit_deals[-1].price
            points = round(exit_price - entry.price, 2)
            bps = round((points / entry.price) * 10000.0, 2) if entry.price else 0.0
            outcome = "PROFIT" if net > 0 else "LOSS" if net < 0 else "FLAT"
            reason, reason_code = infer_exit_reason(exit_deals)
            rows.append({
                "audit_order": a.audit_order,
                "signal_key": a.signal_key,
                "rule_id": a.rule_id,
                "feature_date": a.feature_date,
                "retcode": a.retcode,
                "retcode_description": a.retcode_description,
                "account_mode": a.account_mode,
                "entry_price_from_trade_log": f"{a.price:.2f}",
                "lot_from_trade_log": a.lot,
                "position_id": entry.position_id,
                "entry_deal_ticket": entry.deal_ticket,
                "entry_time": entry.deal_time,
                "entry_price": f"{entry.price:.2f}",
                "entry_volume": f"{entry.volume:.2f}",
                "exit_deal_ticket": ";".join(d.deal_ticket for d in exit_deals),
                "exit_time": exit_deals[-1].deal_time,
                "exit_price": f"{exit_price:.2f}",
                "exit_volume": f"{sum(d.volume for d in exit_deals):.2f}",
                "exit_reason": reason,
                "exit_reason_code": reason_code,
                "net_profit": net,
                "points_move": points,
                "bps_move": bps,
                "outcome": outcome,
            })
        else:
            rows.append({
                "audit_order": a.audit_order,
                "signal_key": a.signal_key,
                "rule_id": a.rule_id,
                "feature_date": a.feature_date,
                "retcode": a.retcode,
                "retcode_description": a.retcode_description,
                "account_mode": a.account_mode,
                "entry_price_from_trade_log": f"{a.price:.2f}" if a.price else "",
                "lot_from_trade_log": a.lot,
                "position_id": entry.position_id if entry else "",
                "entry_deal_ticket": entry.deal_ticket if entry else "",
                "entry_time": entry.deal_time if entry else "",
                "entry_price": f"{entry.price:.2f}" if entry else "",
                "entry_volume": f"{entry.volume:.2f}" if entry else "",
                "exit_deal_ticket": "",
                "exit_time": "",
                "exit_price": "",
                "exit_volume": "",
                "exit_reason": "",
                "exit_reason_code": "",
                "net_profit": "",
                "points_move": "",
                "bps_move": "",
                "outcome": "OPEN_OR_UNMATCHED",
            })
    return rows


LEDGER_FIELDS = [
    "audit_order", "signal_key", "rule_id", "feature_date", "retcode", "retcode_description", "account_mode",
    "entry_price_from_trade_log", "lot_from_trade_log", "position_id", "entry_deal_ticket", "entry_time",
    "entry_price", "entry_volume", "exit_deal_ticket", "exit_time", "exit_price", "exit_volume",
    "exit_reason", "exit_reason_code", "net_profit", "points_move", "bps_move", "outcome",
]


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


def read_stage141_count(root: Path) -> int:
    path = root / "data/demo_execution/stage141_demo_execution_outcome_ledger.csv"
    if not path.exists() or path.stat().st_size <= 0:
        return 0
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            return max(0, sum(1 for _ in csv.DictReader(f)))
    except Exception:
        return 0


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = [r for r in rows if r.get("outcome") in {"PROFIT", "LOSS", "FLAT"}]
    open_rows = [r for r in rows if r.get("outcome") == "OPEN_OR_UNMATCHED"]
    profits = [to_float(r.get("net_profit")) for r in closed]
    bps = [to_float(r.get("bps_move")) for r in closed]
    profit_count = sum(1 for r in closed if r.get("outcome") == "PROFIT")
    loss_count = sum(1 for r in closed if r.get("outcome") == "LOSS")
    flat_count = sum(1 for r in closed if r.get("outcome") == "FLAT")
    n = len(closed)
    return {
        "clean_ledger_row_count": len(rows),
        "closed_trade_count": n,
        "open_or_unmatched_count": len(open_rows),
        "profit_count": profit_count,
        "loss_count": loss_count,
        "flat_count": flat_count,
        "total_net_profit": round(sum(profits), 2),
        "mean_net_profit": round(sum(profits) / n, 2) if n else 0.0,
        "total_bps": round(sum(bps), 2),
        "mean_bps": round(sum(bps) / n, 2) if n else 0.0,
        "win_rate": round(profit_count / n, 4) if n else 0.0,
        "latest_outcome": rows[-1] if rows else {},
    }


def run(root: Path, mt5_files: Optional[Path] = None) -> Dict[str, Any]:
    root = root.expanduser()
    mt5 = mt5_files.expanduser() if mt5_files else Path(DEFAULT_MT5_FILES)
    trade_log = mt5 / TRADE_LOG_NAME
    deals_history = mt5 / DEALS_HISTORY_NAME
    report_dir = ensure_dir(root / "reports/stage144_demo_execution_ledger_audit")
    data_dir = ensure_dir(root / "data/demo_execution")

    attempts = parse_attempts(trade_log)
    deals = parse_deals(deals_history)
    ledger = build_ledger(attempts, deals)
    stats = summarize(ledger)

    clean_ledger_csv = data_dir / "stage144_clean_demo_execution_ledger.csv"
    report_clean_ledger_csv = report_dir / "stage144_clean_demo_execution_ledger.csv"
    risk_manifest_csv = report_dir / "stage144_risk_manifest.csv"
    summary_json = report_dir / "stage144_demo_execution_ledger_audit_summary.json"

    write_csv(clean_ledger_csv, ledger, LEDGER_FIELDS)
    write_csv(report_clean_ledger_csv, ledger, LEDGER_FIELDS)
    write_csv(risk_manifest_csv, [{"risk_block": x, "status": "ACTIVE"} for x in RISK_BLOCKS], ["risk_block", "status"])

    stage141_count = read_stage141_count(root)
    ledger_count_mismatch = stage141_count != stats["clean_ledger_row_count"]
    if stats["open_or_unmatched_count"] > 0:
        decision = "STAGE144C_LEDGER_RECONCILED_SOME_TRADES_OPEN_OR_UNMATCHED"
    elif stats["closed_trade_count"] == 0:
        decision = "STAGE144C_NO_CLOSED_TRADES"
    elif ledger_count_mismatch:
        decision = "STAGE144C_LEDGER_COUNT_MISMATCH_USE_CLEAN_RECONCILED_LEDGER"
    else:
        decision = "STAGE144C_LEDGER_FULLY_RECONCILED"

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": STATUS,
        "decision": decision,
        "root": str(root),
        "mt5_files": str(mt5),
        "trade_log": str(trade_log),
        "deals_history": str(deals_history),
        "raw_trade_log_rows": len(read_csv_dicts(trade_log)),
        "successful_buy_attempts": len(attempts),
        "unique_trade_attempts": len(attempts),
        "raw_deal_history_rows": len(read_csv_rows(deals_history)[1]),
        "unique_deals": len(deals),
        "position_pairs": len({d.position_id for d in deals if d.position_id}),
        "stage141_raw_ledger_csv": str(root / "data/demo_execution/stage141_demo_execution_outcome_ledger.csv"),
        "stage141_raw_ledger_row_count": stage141_count,
        "ledger_count_mismatch": ledger_count_mismatch,
        **stats,
        "clean_ledger_csv": str(clean_ledger_csv),
        "report_clean_ledger_csv": str(report_clean_ledger_csv),
        "risk_manifest_csv": str(risk_manifest_csv),
        "summary_json": str(summary_json),
        "next": [
            "Trust Stage144C clean ledger over Stage141 when counts differ.",
            "Keep current rule family frozen until replacement candidate is explicitly selected.",
            "Run Stage145 after Stage144C to refresh gate metrics.",
        ],
    }
    write_json(summary_json, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=None)
    args = ap.parse_args()
    run(Path(args.root), Path(args.mt5_files) if args.mt5_files else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
