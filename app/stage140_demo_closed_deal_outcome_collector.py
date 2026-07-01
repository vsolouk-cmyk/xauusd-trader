#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

STAGE = "Stage140_DEMO_CLOSED_DEAL_OUTCOME_MONITOR"
STATUS = "STAGE140B_COMPLETE_MQL5_COMPAT_CLOSED_DEAL_OUTCOME_COLLECTOR_READY"

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_MT5_INDICATORS = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Indicators/XAUUSD"
)

INDICATOR_NAME = "Stage140_DemoClosedDealOutcomeMonitor.mq5"
DEALS_KV = "xauusd_stage140_demo_closed_deal_outcome_kv.csv"
DEALS_HISTORY = "xauusd_stage140_demo_deals_history.csv"
STAGE134_TRADE_LOG = "xauusd_stage134_demo_executor_trade_log.csv"

RISK_BLOCKS = [
    "NO_ORDER_SEND_IN_STAGE140",
    "NO_TRADE_MODIFICATION_IN_STAGE140",
    "READ_ONLY_DEAL_HISTORY_MONITOR",
    "DEMO_CLOSED_OUTCOME_EVALUATION_ONLY",
    "MQL5_COMPAT_ENUM_SAFE_INDICATOR",
    "DO_NOT_DUPLICATE_STAGE134_SIGNAL",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_kv(path: Path) -> Tuple[Dict[str, str], str]:
    if not path.exists() or path.stat().st_size <= 0:
        return {}, "MISSING_OR_EMPTY"
    kv: Dict[str, str] = {}
    fmt = "UNKNOWN"
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            k, v = line.split("|", 1)
            fmt = "PIPE"
        elif "," in line:
            k, v = line.split(",", 1)
            if fmt == "UNKNOWN":
                fmt = "COMMA"
        else:
            continue
        kv[k.strip().strip('"').strip("'")] = v.strip().strip('"').strip("'")
    return kv, fmt


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
    except Exception:
        return []


def age_sec(path: Path) -> float | None:
    if not path.exists() or path.stat().st_size <= 0:
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def fnum(v: Any) -> float | None:
    try:
        s = str(v).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def inum(v: Any) -> int:
    try:
        s = str(v).strip()
        if not s:
            return 0
        return int(float(s))
    except Exception:
        return 0


def reason_label(code: str) -> str:
    # Conservative mapping based on common MT5 enum values; preserve raw code either way.
    # Many builds expose names, but the indicator writes numeric codes to avoid compile issues.
    mp = {
        "0": "CLIENT",
        "1": "EXPERT",
        "2": "DEALER",
        "3": "SL",
        "4": "TP",
        "5": "SO",
        "6": "ROLLOVER",
        "7": "VMARGIN",
        "8": "SPLIT",
    }
    return mp.get(str(code).strip(), str(code).strip())


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as out:
        w = csv.DictWriter(out, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.replace(path)


def append_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as out:
        w = csv.DictWriter(out, fieldnames=fields)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as out:
        for k, v in kv.items():
            out.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)


def install_indicator(root: Path, mt5_indicators: Path) -> str:
    src = root / "mql5/Indicators/XAUUSD" / INDICATOR_NAME
    if not src.exists():
        raise FileNotFoundError(f"missing indicator source: {src}")
    ensure_dir(mt5_indicators)
    dst = mt5_indicators / INDICATOR_NAME
    import shutil
    try:
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
    except shutil.SameFileError:
        pass
    return str(dst)


FIELDS = [
    "snapshot_utc",
    "deals_monitor_exists",
    "deals_monitor_fresh",
    "deals_monitor_age_sec",
    "collector_decision",
    "account_mode",
    "symbol",
    "history_from",
    "history_to",
    "history_select_ok",
    "history_deals_total",
    "symbol_deals",
    "stage134_like_deals",
    "latest_position_id",
    "latest_entry_deal_ticket",
    "latest_entry_time",
    "latest_entry_price",
    "latest_entry_volume",
    "latest_entry_type_code",
    "latest_exit_deal_ticket",
    "latest_exit_time",
    "latest_exit_price",
    "latest_exit_volume",
    "latest_exit_type_code",
    "latest_exit_reason_code",
    "latest_exit_reason_label",
    "latest_exit_profit",
    "latest_exit_swap",
    "latest_exit_commission",
    "latest_net_profit",
    "latest_points_move",
    "latest_bps_move",
    "stage134_trade_attempts",
    "stage134_trade_accepted",
    "latest_stage134_rule_id",
    "latest_stage134_signal_key",
    "latest_stage134_entry_price",
    "latest_stage134_lot",
    "latest_stage134_retcode",
]


def collect(root: Path, mt5_files: Path, mt5_indicators: Path, install_indicator_flag: bool, stale_after_sec: float, write_mt5_status_kv: bool) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    mt5_indicators = mt5_indicators.expanduser()
    out = ensure_dir(root / "reports/stage140_demo_closed_deal_outcome_monitor")
    data = ensure_dir(root / "data/demo_execution")
    snapshot_utc = utc_now()

    installed_to = ""
    if install_indicator_flag:
        installed_to = install_indicator(root, mt5_indicators)

    deals_kv_path = mt5_files / DEALS_KV
    deals_kv, deals_fmt = read_kv(deals_kv_path)
    mon_age = age_sec(deals_kv_path)
    mon_exists = mon_age is not None
    mon_fresh = bool(mon_age is not None and mon_age <= stale_after_sec)

    trade_rows = read_csv_rows(mt5_files / STAGE134_TRADE_LOG)
    attempts = sum(1 for r in trade_rows if "ATTEMPT" in str(r.get("event_type", "")))
    accepted = sum(1 for r in trade_rows if str(r.get("ok", "")).lower() == "true")
    latest_trade = trade_rows[-1] if trade_rows else {}

    latest_net = fnum(deals_kv.get("latest_net_profit", "")) if deals_kv else None
    latest_exit_ticket = deals_kv.get("latest_exit_deal_ticket", "") if deals_kv else ""
    latest_entry_ticket = deals_kv.get("latest_entry_deal_ticket", "") if deals_kv else ""
    symbol_deals = inum(deals_kv.get("symbol_deals", "")) if deals_kv else 0

    if not mon_exists:
        decision = "STAGE140_DEAL_MONITOR_NOT_CONFIRMED_ATTACH_INDICATOR"
    elif not mon_fresh:
        decision = "STAGE140_DEAL_MONITOR_STALE_REATTACH_OR_WAIT"
    elif latest_exit_ticket and latest_exit_ticket != "0":
        if latest_net is None:
            decision = "STAGE140_CLOSED_DEMO_DEAL_FOUND_PNL_UNKNOWN"
        elif latest_net > 0:
            decision = "STAGE140_CLOSED_DEMO_DEAL_PROFIT"
        elif latest_net < 0:
            decision = "STAGE140_CLOSED_DEMO_DEAL_LOSS"
        else:
            decision = "STAGE140_CLOSED_DEMO_DEAL_FLAT"
    elif latest_entry_ticket and latest_entry_ticket != "0":
        decision = "STAGE140_ENTRY_DEAL_FOUND_BUT_NO_EXIT_DEAL"
    elif accepted > 0 and symbol_deals == 0:
        decision = "STAGE140_ACCEPTED_ORDER_BUT_NO_SYMBOL_DEAL_FOUND_CHECK_HISTORY_WINDOW"
    elif accepted > 0:
        decision = "STAGE140_ACCEPTED_ORDER_BUT_NO_CLOSED_OUTCOME_FOUND_YET"
    else:
        decision = "STAGE140_NO_STAGE134_ACCEPTED_ORDER"

    reason_code = deals_kv.get("latest_exit_reason_code", deals_kv.get("latest_exit_reason", ""))

    row = {
        "snapshot_utc": snapshot_utc,
        "deals_monitor_exists": mon_exists,
        "deals_monitor_fresh": mon_fresh,
        "deals_monitor_age_sec": round(mon_age, 2) if mon_age is not None else "",
        "collector_decision": decision,
        "account_mode": deals_kv.get("account_mode", ""),
        "symbol": deals_kv.get("symbol", ""),
        "history_from": deals_kv.get("history_from", ""),
        "history_to": deals_kv.get("history_to", ""),
        "history_select_ok": deals_kv.get("history_select_ok", ""),
        "history_deals_total": deals_kv.get("history_deals_total", ""),
        "symbol_deals": deals_kv.get("symbol_deals", ""),
        "stage134_like_deals": deals_kv.get("stage134_like_deals", ""),
        "latest_position_id": deals_kv.get("latest_position_id", ""),
        "latest_entry_deal_ticket": deals_kv.get("latest_entry_deal_ticket", ""),
        "latest_entry_time": deals_kv.get("latest_entry_time", ""),
        "latest_entry_price": deals_kv.get("latest_entry_price", ""),
        "latest_entry_volume": deals_kv.get("latest_entry_volume", ""),
        "latest_entry_type_code": deals_kv.get("latest_entry_type_code", deals_kv.get("latest_entry_type", "")),
        "latest_exit_deal_ticket": deals_kv.get("latest_exit_deal_ticket", ""),
        "latest_exit_time": deals_kv.get("latest_exit_time", ""),
        "latest_exit_price": deals_kv.get("latest_exit_price", ""),
        "latest_exit_volume": deals_kv.get("latest_exit_volume", ""),
        "latest_exit_type_code": deals_kv.get("latest_exit_type_code", deals_kv.get("latest_exit_type", "")),
        "latest_exit_reason_code": reason_code,
        "latest_exit_reason_label": reason_label(reason_code),
        "latest_exit_profit": deals_kv.get("latest_exit_profit", ""),
        "latest_exit_swap": deals_kv.get("latest_exit_swap", ""),
        "latest_exit_commission": deals_kv.get("latest_exit_commission", ""),
        "latest_net_profit": deals_kv.get("latest_net_profit", ""),
        "latest_points_move": deals_kv.get("latest_points_move", ""),
        "latest_bps_move": deals_kv.get("latest_bps_move", ""),
        "stage134_trade_attempts": attempts,
        "stage134_trade_accepted": accepted,
        "latest_stage134_rule_id": latest_trade.get("rule_id", ""),
        "latest_stage134_signal_key": latest_trade.get("signal_key", ""),
        "latest_stage134_entry_price": latest_trade.get("price", ""),
        "latest_stage134_lot": latest_trade.get("lot", ""),
        "latest_stage134_retcode": latest_trade.get("retcode", ""),
    }

    latest_csv = out / "stage140_latest_closed_deal_outcome_snapshot.csv"
    history_csv = data / "stage140_demo_closed_deal_outcome_snapshots.csv"
    risk_csv = out / "stage140_risk_manifest.csv"
    write_rows(latest_csv, [row], FIELDS)
    append_rows(history_csv, [row], FIELDS)
    write_rows(risk_csv, [{"risk_block": b, "status": "ACTIVE"} for b in RISK_BLOCKS], ["risk_block", "status"])

    status_kv = {
        "stage": STAGE,
        "status": STATUS,
        "collector_decision": decision,
        "generated_utc": snapshot_utc,
        "deals_monitor_exists": str(mon_exists).lower(),
        "deals_monitor_fresh": str(mon_fresh).lower(),
        "latest_net_profit": row["latest_net_profit"],
        "latest_exit_reason_code": row["latest_exit_reason_code"],
        "latest_exit_reason_label": row["latest_exit_reason_label"],
        "stage134_trade_accepted": accepted,
        "installed_to": installed_to,
    }
    status_repo = data / "stage140_closed_deal_outcome_collector_status_kv.csv"
    status_report = out / "stage140_closed_deal_outcome_collector_status_kv.csv"
    write_kv(status_repo, status_kv)
    write_kv(status_report, status_kv)

    mt5_status_kv = ""
    if write_mt5_status_kv:
        mt5_status_kv = str(mt5_files / "xauusd_stage140_closed_deal_outcome_collector_status_kv.csv")
        write_kv(Path(mt5_status_kv), status_kv)

    deals_rows = read_csv_rows(mt5_files / DEALS_HISTORY)
    recent_deals = deals_rows[-20:] if deals_rows else []

    summary = {
        "stage": STAGE,
        "generated_utc": snapshot_utc,
        "status": STATUS,
        "collector_decision": decision,
        "root": str(root),
        "mt5_files": str(mt5_files),
        "mt5_indicators": str(mt5_indicators),
        "indicator_name": INDICATOR_NAME,
        "installed_to": installed_to,
        "deals_kv": str(deals_kv_path),
        "deals_kv_format": deals_fmt,
        "deals_history": str(mt5_files / DEALS_HISTORY),
        "trade_log": str(mt5_files / STAGE134_TRADE_LOG),
        **row,
        "recent_deals": recent_deals,
        "latest_snapshot_csv": str(latest_csv),
        "history_csv": str(history_csv),
        "risk_manifest_csv": str(risk_csv),
        "status_kv_repo": str(status_repo),
        "status_kv_report": str(status_report),
        "mt5_collector_status_kv": mt5_status_kv,
        "summary_json": str(out / "stage140_demo_closed_deal_outcome_monitor_summary.json"),
        "next": [
            "If collector_decision is a closed profit/loss/flat outcome, archive the first demo-order outcome and continue demo loop with duplicate control.",
            "If entry is found but no exit deal, keep Stage139 position monitor active and wait for closure.",
            "If no symbol deal is found, widen the MT5 history window or verify the account/history tab.",
        ],
    }
    write_json(out / "stage140_demo_closed_deal_outcome_monitor_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--mt5-indicators", default=DEFAULT_MT5_INDICATORS)
    ap.add_argument("--install-indicator", action="store_true")
    ap.add_argument("--stale-after-sec", type=float, default=240.0)
    ap.add_argument("--write-mt5-status-kv", action="store_true")
    args = ap.parse_args()
    collect(
        root=Path(args.root),
        mt5_files=Path(args.mt5_files),
        mt5_indicators=Path(args.mt5_indicators),
        install_indicator_flag=args.install_indicator,
        stale_after_sec=args.stale_after_sec,
        write_mt5_status_kv=args.write_mt5_status_kv,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
