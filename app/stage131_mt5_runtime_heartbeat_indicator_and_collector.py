#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage131_MT5_RUNTIME_HEARTBEAT_INDICATOR_AND_COLLECTOR"
STATUS = "STAGE131_COMPLETE_RUNTIME_HEARTBEAT_COLLECTOR_READY_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE131",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_EA_CHANGE_FROM_STAGE131",
    "NO_INDICATOR_UI_OVERLAY_CHANGE_FROM_STAGE131",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_MT5_INDICATORS = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Indicators"
)
INDICATOR_NAME = "XAUUSD_Stage131_RuntimeHeartbeatIndicator.mq5"
HEARTBEAT_KV = "xauusd_stage131_runtime_heartbeat_kv.csv"
HEARTBEAT_HISTORY = "xauusd_stage131_runtime_heartbeat_history.csv"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_kv(path: Path) -> Tuple[Dict[str, str], str]:
    if not path.exists() or path.stat().st_size <= 0:
        return {}, "MISSING_OR_EMPTY"
    kv: Dict[str, str] = {}
    fmt = "UNKNOWN"
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
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
        k = k.strip().strip('"').strip("'")
        v = v.strip().strip('"').strip("'")
        if k:
            kv[k] = v
    return kv, fmt


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    tmp.replace(path)


def append_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)


def install_indicator(root: Path, mt5_indicators: Path) -> List[str]:
    src = root / "mql5/Indicators" / INDICATOR_NAME
    if not src.exists():
        raise FileNotFoundError(f"Missing indicator source in repo: {src}")
    dests = [
        mt5_indicators / INDICATOR_NAME,
        mt5_indicators / "Advisors/XAUUSD" / INDICATOR_NAME,
    ]
    written = []
    for d in dests:
        ensure_dir(d.parent)
        try:
            if src.resolve() == d.resolve():
                written.append(str(d))
                continue
        except FileNotFoundError:
            pass
        except OSError:
            pass
        try:
            shutil.copy2(src, d)
        except shutil.SameFileError:
            written.append(str(d))
            continue
        written.append(str(d))
    return written


FIELDS = [
    "snapshot_utc",
    "heartbeat_exists",
    "heartbeat_fresh",
    "heartbeat_age_sec",
    "heartbeat_mtime_utc",
    "kv_count",
    "kv_format",
    "status",
    "symbol",
    "period",
    "time_local",
    "time_current",
    "time_trade_server",
    "terminal_trade_allowed",
    "mql_trade_allowed",
    "account_trade_allowed",
    "allow_trading",
    "order_send",
    "stage130_latest_seen",
    "stage130b_latest_seen",
    "decision",
]


def read_json_safe(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def collect(root: Path, mt5_files: Path, stale_after_sec: float, write_mt5_status_kv: bool, write_mql5_indicator: bool, mt5_indicators: Path) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    mt5_indicators = mt5_indicators.expanduser()

    out = ensure_dir(root / "reports/stage131_mt5_runtime_heartbeat_indicator_and_collector")
    data = ensure_dir(root / "data/forward_shadow_telemetry")
    snapshot_utc = utc_now()

    indicator_written: List[str] = []
    if write_mql5_indicator:
        indicator_written = install_indicator(root, mt5_indicators)

    hb_path = mt5_files / HEARTBEAT_KV
    hist_path = mt5_files / HEARTBEAT_HISTORY
    kv, fmt = read_kv(hb_path)
    exists = hb_path.exists() and hb_path.stat().st_size > 0
    age = max(0.0, time.time() - hb_path.stat().st_mtime) if exists else None
    fresh = bool(exists and age is not None and age <= stale_after_sec)

    s130 = read_json_safe(root / "reports/stage130_forward_shadow_telemetry_collector/stage130_forward_shadow_telemetry_collector_summary.json")
    s130b = read_json_safe(root / "reports/stage130b_mt5_journal_and_files_telemetry_audit/stage130b_mt5_journal_and_files_telemetry_audit_summary.json")

    allow = kv.get("allow_trading", "")
    order_send = kv.get("order_send", "")
    no_order_ok = str(allow).lower() not in {"true", "1", "yes"} and str(order_send).lower() not in {"true", "1", "yes"}

    if not exists:
        decision = "STAGE131_HEARTBEAT_NOT_FOUND_ATTACH_INDICATOR_NO_ORDER"
    elif not fresh:
        decision = "STAGE131_HEARTBEAT_STALE_RUNTIME_NOT_CONFIRMED_NO_ORDER"
    elif not no_order_ok:
        decision = "STAGE131_HEARTBEAT_ORDER_FLAG_REVIEW_REQUIRED_NO_ORDER"
    elif s130 and int(s130.get("fresh_file_count", 0) or 0) <= 1:
        decision = "STAGE131_MT5_RUNTIME_CONFIRMED_OBSERVER_FILES_STALE_TELEMETRY_WRITER_NEEDED_NO_ORDER"
    else:
        decision = "STAGE131_MT5_RUNTIME_HEARTBEAT_CONFIRMED_NO_ORDER"

    row = {
        "snapshot_utc": snapshot_utc,
        "heartbeat_exists": exists,
        "heartbeat_fresh": fresh,
        "heartbeat_age_sec": round(age, 2) if age is not None else "",
        "heartbeat_mtime_utc": iso_from_epoch(hb_path.stat().st_mtime) if exists else "",
        "kv_count": len(kv),
        "kv_format": fmt,
        "status": kv.get("status", ""),
        "symbol": kv.get("symbol", ""),
        "period": kv.get("period", ""),
        "time_local": kv.get("time_local", ""),
        "time_current": kv.get("time_current", ""),
        "time_trade_server": kv.get("time_trade_server", ""),
        "terminal_trade_allowed": kv.get("terminal_trade_allowed", ""),
        "mql_trade_allowed": kv.get("mql_trade_allowed", ""),
        "account_trade_allowed": kv.get("account_trade_allowed", ""),
        "allow_trading": allow,
        "order_send": order_send,
        "stage130_latest_seen": bool(s130),
        "stage130b_latest_seen": bool(s130b),
        "decision": decision,
    }

    latest_path = out / "stage131_latest_runtime_heartbeat_snapshot.csv"
    history_path = data / "stage131_runtime_heartbeat_snapshots.csv"
    governance_path = out / "stage131_governance_no_order_manifest.csv"
    status_kv_repo = data / "stage131_runtime_heartbeat_status_kv.csv"
    status_kv_report = out / "stage131_runtime_heartbeat_status_kv.csv"
    write_rows(latest_path, [row], FIELDS)
    append_rows(history_path, [row], FIELDS)
    write_rows(governance_path, [{"block": b, "status": "ACTIVE"} for b in HARD_BLOCKS], ["block", "status"])

    status_kv = {
        "stage": STAGE,
        "status": STATUS,
        "decision": decision,
        "generated_utc": snapshot_utc,
        "allow_trading": "false",
        "order_send": "false",
        "heartbeat_exists": str(exists).lower(),
        "heartbeat_fresh": str(fresh).lower(),
        "heartbeat_age_sec": row["heartbeat_age_sec"],
        "symbol": row["symbol"],
        "period": row["period"],
    }
    write_kv(status_kv_repo, status_kv)
    write_kv(status_kv_report, status_kv)
    mt5_status_kv = ""
    if write_mt5_status_kv:
        p = mt5_files / "xauusd_stage131_runtime_heartbeat_collector_status_kv.csv"
        write_kv(p, status_kv)
        mt5_status_kv = str(p)

    summary = {
        "stage": STAGE,
        "generated_utc": snapshot_utc,
        "status": STATUS,
        "decision": decision,
        "classification": "MT5_RUNTIME_HEARTBEAT_TELEMETRY_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "mt5_files": str(mt5_files),
        "mt5_indicators": str(mt5_indicators),
        "heartbeat_kv": str(hb_path),
        "heartbeat_history": str(hist_path),
        "heartbeat_exists": exists,
        "heartbeat_fresh": fresh,
        "heartbeat_age_sec": row["heartbeat_age_sec"],
        "kv_count": len(kv),
        "indicator_written": indicator_written,
        "stage130_context_decision": s130.get("decision", ""),
        "stage130_fresh_file_count": s130.get("fresh_file_count", ""),
        "stage130_stale_file_count": s130.get("stale_file_count", ""),
        "stage130b_context_decision": s130b.get("decision", ""),
        "stage130b_runtime_log_events": s130b.get("runtime_log_events", ""),
        "latest_snapshot_csv": str(latest_path),
        "history_csv": str(history_path),
        "status_kv_repo": str(status_kv_repo),
        "status_kv_report": str(status_kv_report),
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": mt5_status_kv,
        "governance_no_order_manifest": str(governance_path),
        "summary_json": str(out / "stage131_mt5_runtime_heartbeat_indicator_and_collector_summary.json"),
        "report_md": str(out / "stage131_mt5_runtime_heartbeat_indicator_and_collector_report.md"),
        "next": [
            "If heartbeat is not found, compile and attach XAUUSD_Stage131_RuntimeHeartbeatIndicator to the XAUUSD H1 chart.",
            "If heartbeat is fresh while observer files remain stale, the next controlled step is telemetry-only writer instrumentation in the existing observer EA.",
            "No order, broker, paper-live, live, or EA trading-logic change is performed by Stage131.",
        ],
    }
    write_json(out / "stage131_mt5_runtime_heartbeat_indicator_and_collector_summary.json", summary)

    report = [
        f"# {STAGE}",
        "",
        f"Status: `{STATUS}`",
        f"Decision: `{decision}`",
        "",
        "## Heartbeat",
        "",
        f"- exists: {exists}",
        f"- fresh: {fresh}",
        f"- age sec: {row['heartbeat_age_sec']}",
        f"- symbol: {row['symbol']}",
        f"- period: {row['period']}",
        "",
        "## Governance",
        "",
        "\n".join(f"- {b}" for b in HARD_BLOCKS),
    ]
    (out / "stage131_mt5_runtime_heartbeat_indicator_and_collector_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--mt5-indicators", default=DEFAULT_MT5_INDICATORS)
    ap.add_argument("--stale-after-sec", type=float, default=180.0)
    ap.add_argument("--write-mt5-status-kv", action="store_true")
    ap.add_argument("--write-mql5-indicator", action="store_true")
    args = ap.parse_args()
    collect(
        root=Path(args.root),
        mt5_files=Path(args.mt5_files),
        stale_after_sec=args.stale_after_sec,
        write_mt5_status_kv=args.write_mt5_status_kv,
        write_mql5_indicator=args.write_mql5_indicator,
        mt5_indicators=Path(args.mt5_indicators),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
