#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage139_DEMO_POSITION_OUTCOME_MONITOR"
STATUS = "STAGE139_COMPLETE_DEMO_POSITION_OUTCOME_MONITOR_COLLECTOR_READY"

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_MT5_INDICATORS = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Indicators/XAUUSD"
)

MONITOR_KV = "xauusd_stage139_demo_position_monitor_kv.csv"
MONITOR_HISTORY = "xauusd_stage139_demo_position_monitor_history.csv"
STAGE134_TRADE_LOG = "xauusd_stage134_demo_executor_trade_log.csv"
INDICATOR_NAME = "Stage139_DemoPositionOutcomeMonitor.mq5"

RISK_BLOCKS = [
    "NO_ORDER_SEND_IN_STAGE139",
    "NO_TRADE_MODIFICATION_IN_STAGE139",
    "READ_ONLY_POSITION_MONITOR",
    "DEMO_OUTCOME_EVALUATION_ONLY",
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


def to_float(v: Any) -> float | None:
    try:
        s = str(v).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.replace(path)


def append_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)


def install_indicator(root: Path, mt5_indicators: Path) -> str:
    src = root / "mql5/Indicators/XAUUSD" / INDICATOR_NAME
    if not src.exists():
        raise FileNotFoundError(f"missing indicator source: {src}")
    ensure_dir(mt5_indicators)
    dest = mt5_indicators / INDICATOR_NAME
    import shutil
    try:
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
    except shutil.SameFileError:
        pass
    return str(dest)


FIELDS = [
    "snapshot_utc",
    "monitor_exists",
    "monitor_fresh",
    "monitor_age_sec",
    "collector_decision",
    "account_mode",
    "symbol",
    "positions_total",
    "matching_positions",
    "stage134_matching_positions",
    "has_open_position",
    "position_ticket",
    "position_type",
    "position_volume",
    "position_open_price",
    "position_current_price",
    "position_sl",
    "position_tp",
    "position_profit",
    "position_swap",
    "position_commission",
    "position_magic",
    "position_comment",
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
    out = ensure_dir(root / "reports/stage139_demo_position_outcome_monitor")
    data = ensure_dir(root / "data/demo_execution")
    snapshot_utc = utc_now()

    installed_to = ""
    if install_indicator_flag:
        installed_to = install_indicator(root, mt5_indicators)

    monitor_path = mt5_files / MONITOR_KV
    monitor_kv, monitor_fmt = read_kv(monitor_path)
    mon_age = age_sec(monitor_path)
    monitor_exists = mon_age is not None
    monitor_fresh = bool(mon_age is not None and mon_age <= stale_after_sec)

    trade_log_path = mt5_files / STAGE134_TRADE_LOG
    trade_rows = read_csv_rows(trade_log_path)
    attempts = sum(1 for r in trade_rows if "ATTEMPT" in str(r.get("event_type", "")))
    accepted = sum(1 for r in trade_rows if str(r.get("ok", "")).lower() == "true")
    latest_trade = trade_rows[-1] if trade_rows else {}

    matching_positions = int(float(monitor_kv.get("matching_positions", "0") or "0")) if monitor_kv else 0
    stage134_matching_positions = int(float(monitor_kv.get("stage134_matching_positions", "0") or "0")) if monitor_kv else 0
    has_open = matching_positions > 0 or stage134_matching_positions > 0
    profit = to_float(monitor_kv.get("position_profit", "")) if monitor_kv else None

    if not monitor_exists:
        decision = "STAGE139_MONITOR_NOT_CONFIRMED_ATTACH_INDICATOR"
    elif not monitor_fresh:
        decision = "STAGE139_MONITOR_STALE_REATTACH_OR_WAIT_FOR_TICK"
    elif has_open:
        if profit is None:
            decision = "STAGE139_OPEN_DEMO_POSITION_PNL_UNKNOWN"
        elif profit > 0:
            decision = "STAGE139_OPEN_DEMO_POSITION_FLOATING_PROFIT"
        elif profit < 0:
            decision = "STAGE139_OPEN_DEMO_POSITION_FLOATING_LOSS"
        else:
            decision = "STAGE139_OPEN_DEMO_POSITION_FLAT"
    elif accepted > 0:
        decision = "STAGE139_NO_OPEN_POSITION_AFTER_ACCEPTED_ORDER_CHECK_HISTORY_OR_CLOSED"
    else:
        decision = "STAGE139_NO_OPEN_POSITION_NO_ACCEPTED_STAGE134_ORDER"

    row = {
        "snapshot_utc": snapshot_utc,
        "monitor_exists": monitor_exists,
        "monitor_fresh": monitor_fresh,
        "monitor_age_sec": round(mon_age, 2) if mon_age is not None else "",
        "collector_decision": decision,
        "account_mode": monitor_kv.get("account_mode", ""),
        "symbol": monitor_kv.get("symbol", ""),
        "positions_total": monitor_kv.get("positions_total", ""),
        "matching_positions": monitor_kv.get("matching_positions", ""),
        "stage134_matching_positions": monitor_kv.get("stage134_matching_positions", ""),
        "has_open_position": str(has_open).lower(),
        "position_ticket": monitor_kv.get("position_ticket", ""),
        "position_type": monitor_kv.get("position_type", ""),
        "position_volume": monitor_kv.get("position_volume", ""),
        "position_open_price": monitor_kv.get("position_open_price", ""),
        "position_current_price": monitor_kv.get("position_current_price", ""),
        "position_sl": monitor_kv.get("position_sl", ""),
        "position_tp": monitor_kv.get("position_tp", ""),
        "position_profit": monitor_kv.get("position_profit", ""),
        "position_swap": monitor_kv.get("position_swap", ""),
        "position_commission": monitor_kv.get("position_commission", ""),
        "position_magic": monitor_kv.get("position_magic", ""),
        "position_comment": monitor_kv.get("position_comment", ""),
        "stage134_trade_attempts": attempts,
        "stage134_trade_accepted": accepted,
        "latest_stage134_rule_id": latest_trade.get("rule_id", ""),
        "latest_stage134_signal_key": latest_trade.get("signal_key", ""),
        "latest_stage134_entry_price": latest_trade.get("price", ""),
        "latest_stage134_lot": latest_trade.get("lot", ""),
        "latest_stage134_retcode": latest_trade.get("retcode", ""),
    }

    latest_csv = out / "stage139_latest_position_outcome_snapshot.csv"
    history_csv = data / "stage139_demo_position_outcome_snapshots.csv"
    risk_csv = out / "stage139_risk_manifest.csv"
    write_rows(latest_csv, [row], FIELDS)
    append_rows(history_csv, [row], FIELDS)
    write_rows(risk_csv, [{"risk_block": b, "status": "ACTIVE"} for b in RISK_BLOCKS], ["risk_block", "status"])

    collector_status = {
        "stage": STAGE,
        "status": STATUS,
        "collector_decision": decision,
        "generated_utc": snapshot_utc,
        "monitor_exists": str(monitor_exists).lower(),
        "monitor_fresh": str(monitor_fresh).lower(),
        "has_open_position": str(has_open).lower(),
        "position_profit": row["position_profit"],
        "stage134_trade_accepted": accepted,
        "installed_to": installed_to,
    }
    status_repo = data / "stage139_position_outcome_collector_status_kv.csv"
    status_report = out / "stage139_position_outcome_collector_status_kv.csv"
    write_kv(status_repo, collector_status)
    write_kv(status_report, collector_status)

    mt5_status_kv = ""
    if write_mt5_status_kv:
        mt5_status_kv = str(mt5_files / "xauusd_stage139_position_outcome_collector_status_kv.csv")
        write_kv(Path(mt5_status_kv), collector_status)

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
        "monitor_kv": str(monitor_path),
        "monitor_format": monitor_fmt,
        "trade_log": str(trade_log_path),
        **row,
        "latest_snapshot_csv": str(latest_csv),
        "history_csv": str(history_csv),
        "risk_manifest_csv": str(risk_csv),
        "status_kv_repo": str(status_repo),
        "status_kv_report": str(status_report),
        "mt5_collector_status_kv": mt5_status_kv,
        "summary_json": str(out / "stage139_demo_position_outcome_monitor_summary.json"),
        "next": [
            "If monitor is not confirmed, compile and attach Stage139_DemoPositionOutcomeMonitor indicator to the XAUUSD chart.",
            "If an open demo position exists, keep monitoring floating PnL until SL/TP/time-exit/closure.",
            "Do not duplicate the Stage134 order for the same signal while this position/outcome is unresolved.",
        ],
    }
    write_json(out / "stage139_demo_position_outcome_monitor_summary.json", summary)
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
