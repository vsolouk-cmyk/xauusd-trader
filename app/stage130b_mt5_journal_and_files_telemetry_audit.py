#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage130B_MT5_JOURNAL_AND_FILES_TELEMETRY_AUDIT"
STATUS = "STAGE130B_COMPLETE_MT5_JOURNAL_AND_FILES_TELEMETRY_READY_NO_ORDER"
CLASSIFICATION = "MT5_JOURNAL_AND_FILE_TELEMETRY_AUDIT_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE130B",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE130B",
    "NO_INDICATOR_UI_CHANGE_FROM_STAGE130B",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)

EVENT_PATTERNS = {
    "unified_ea": re.compile(r"Unified_ObserverOnly_EA|Unified Observer|unified_observer", re.IGNORECASE),
    "rule8_stage124f": re.compile(r"Stage124F|Rule8|rule8", re.IGNORECASE),
    "rule9_stage126": re.compile(r"Stage126|Rule9|rule9|Stage127", re.IGNORECASE),
    "stage130": re.compile(r"Stage130", re.IGNORECASE),
    "order_safety": re.compile(r"No orders are sent|Trading remains disabled|allow_trading=false|AllowTrading=false|NO_ORDER|NO_TRADE", re.IGNORECASE),
    "order_risk": re.compile(r"OrderSend|CTrade|Buy\(|Sell\(|allow_trading=true|AllowTrading=true", re.IGNORECASE),
}

LOG_TIME_RE = re.compile(r"^(?P<ts>\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+(?P<body>.*)$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def iso_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    tmp.replace(path)


def append_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as f:
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


def derive_log_dirs(mt5_files: Path, extra_log_dirs: List[str]) -> List[Path]:
    mt5_files = mt5_files.expanduser()
    dirs: List[Path] = []
    try:
        mql5_root = mt5_files.parent
        terminal_root = mql5_root.parent
        dirs.extend([mql5_root / "Logs", terminal_root / "logs", terminal_root / "Logs"])
    except Exception:
        pass
    dirs.extend([Path(x).expanduser() for x in extra_log_dirs])
    out: List[Path] = []
    seen = set()
    for d in dirs:
        s = str(d)
        if s not in seen:
            out.append(d)
            seen.add(s)
    return out


def find_log_files(log_dirs: List[Path], max_files: int) -> List[Path]:
    files: List[Path] = []
    for d in log_dirs:
        if d.exists():
            files.extend(Path(x) for x in glob.glob(str(d / "*.log")))
            files.extend(Path(x) for x in glob.glob(str(d / "*.txt")))
    files = [p for p in files if p.exists() and p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:max_files]


def read_tail(path: Path, max_bytes: int) -> str:
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > max_bytes:
            f.seek(max(0, size - max_bytes))
        raw = f.read()
    return raw.decode("utf-8", errors="replace")


def classify_line(line: str) -> Tuple[List[str], bool, bool]:
    cats = []
    for name, pat in EVENT_PATTERNS.items():
        if pat.search(line):
            cats.append(name)
    relevant = bool(cats)
    risk = "order_risk" in cats
    safe = "order_safety" in cats
    return cats, risk, safe if relevant else False


EVENT_FIELDS = [
    "scan_utc",
    "log_file",
    "log_file_mtime_utc",
    "line_time_raw",
    "category_flags",
    "source_hint",
    "risk_flag",
    "safety_flag",
    "message",
]


def parse_log_file(path: Path, max_bytes: int, scan_utc: str) -> List[Dict[str, Any]]:
    text = read_tail(path, max_bytes)
    rows: List[Dict[str, Any]] = []
    mtime = iso_from_epoch(path.stat().st_mtime)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        cats, risk, safe = classify_line(line)
        if not cats:
            continue
        match = LOG_TIME_RE.match(line)
        line_ts = ""
        body = line
        if match:
            line_ts = match.group("ts")
            body = match.group("body")
        source = ""
        if "Unified_ObserverOnly_EA" in line:
            source = "Unified_ObserverOnly_EA"
        elif "Stage124F" in line:
            source = "Stage124F_Rule8Indicator"
        elif "Stage126" in line:
            source = "Stage126_Rule9Indicator"
        elif "Stage127" in line:
            source = "Stage127_Rule9Review"
        elif "Stage130" in line:
            source = "Stage130Collector"
        rows.append({
            "scan_utc": scan_utc,
            "log_file": str(path),
            "log_file_mtime_utc": mtime,
            "line_time_raw": line_ts,
            "category_flags": ";".join(cats),
            "source_hint": source,
            "risk_flag": str(bool(risk)).lower(),
            "safety_flag": str(bool(safe)).lower(),
            "message": body[-1500:],
        })
    return rows


def read_stage130_latest(root: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    p = root / "reports/stage130_forward_shadow_telemetry_collector/stage130_latest_shadow_snapshot.csv"
    if not p.exists():
        return [], {"stage130_latest_seen": False}
    rows: List[Dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(dict(r))
    except Exception:
        return [], {"stage130_latest_seen": False, "stage130_latest_read_error": True}
    return rows, {
        "stage130_latest_seen": True,
        "stage130_latest_rows": len(rows),
        "stage130_fresh_file_count": sum(1 for r in rows if r.get("freshness") == "FRESH"),
        "stage130_stale_file_count": sum(1 for r in rows if r.get("freshness") == "STALE"),
        "stage130_missing_file_count": sum(1 for r in rows if r.get("freshness") == "MISSING"),
        "stage130_rule8_seen": any(r.get("label") == "rule8_stage124f" and str(r.get("exists")).lower() == "true" for r in rows),
        "stage130_rule9_seen": any(r.get("label") in {"rule9_stage126", "rule9_stage127_review"} and str(r.get("exists")).lower() == "true" for r in rows),
    }


HEALTH_FIELDS = [
    "scan_utc",
    "log_files_seen",
    "runtime_log_events",
    "unified_ea_log_events",
    "rule8_log_events",
    "rule9_log_events",
    "order_risk_events",
    "order_safety_events",
    "stage130_latest_seen",
    "stage130_fresh_file_count",
    "stage130_stale_file_count",
    "stage130_rule8_seen",
    "stage130_rule9_seen",
    "decision",
]


def summarize(events: List[Dict[str, Any]], latest_meta: Dict[str, Any]) -> Dict[str, Any]:
    def count_cat(cat: str) -> int:
        return sum(1 for e in events if cat in str(e.get("category_flags", "")).split(";"))
    order_risk = count_cat("order_risk")
    unified = count_cat("unified_ea")
    rule8 = count_cat("rule8_stage124f")
    rule9 = count_cat("rule9_stage126")
    safety = count_cat("order_safety")
    if order_risk > 0:
        decision = "STAGE130B_ORDER_RISK_LOG_REVIEW_REQUIRED_NO_ORDER"
    elif not events:
        decision = "STAGE130B_NO_RELEVANT_MT5_JOURNAL_EVENTS_FOUND"
    elif unified == 0:
        decision = "STAGE130B_MT5_LOGS_FOUND_BUT_UNIFIED_EA_NOT_CONFIRMED"
    else:
        decision = "STAGE130B_MT5_JOURNAL_RUNTIME_TELEMETRY_READY_NO_ORDER"
    return {
        "runtime_log_events": len(events),
        "unified_ea_log_events": unified,
        "rule8_log_events": rule8,
        "rule9_log_events": rule9,
        "order_risk_events": order_risk,
        "order_safety_events": safety,
        "decision": decision,
        **latest_meta,
    }


def run(
    root: Path,
    mt5_files: Path,
    extra_log_dirs: List[str],
    max_log_files: int,
    max_bytes_per_log: int,
    write_mt5_status_kv: bool,
) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    scan_utc = utc_now()
    out = ensure_dir(root / "reports/stage130b_mt5_journal_and_files_telemetry_audit")
    data = ensure_dir(root / "data/forward_shadow_telemetry")

    log_dirs = derive_log_dirs(mt5_files, extra_log_dirs)
    log_files = find_log_files(log_dirs, max_files=max_log_files)
    events: List[Dict[str, Any]] = []
    for lf in log_files:
        events.extend(parse_log_file(lf, max_bytes_per_log, scan_utc))

    latest_rows, latest_meta = read_stage130_latest(root)
    meta = summarize(events, latest_meta)
    meta["log_files_seen"] = len(log_files)

    events_path = out / "stage130b_mt5_journal_runtime_events.csv"
    history_path = data / "stage130b_mt5_journal_runtime_events.csv"
    health_path = out / "stage130b_runtime_health_summary.csv"
    governance_path = out / "stage130b_governance_no_order_manifest.csv"
    kv_repo = data / "stage130b_mt5_journal_telemetry_status_kv.csv"
    kv_report = out / "stage130b_mt5_journal_telemetry_status_kv.csv"

    write_rows(events_path, events, EVENT_FIELDS)
    if events:
        append_rows(history_path, events, EVENT_FIELDS)
    health_row = {
        "scan_utc": scan_utc,
        "log_files_seen": len(log_files),
        "runtime_log_events": meta.get("runtime_log_events", 0),
        "unified_ea_log_events": meta.get("unified_ea_log_events", 0),
        "rule8_log_events": meta.get("rule8_log_events", 0),
        "rule9_log_events": meta.get("rule9_log_events", 0),
        "order_risk_events": meta.get("order_risk_events", 0),
        "order_safety_events": meta.get("order_safety_events", 0),
        "stage130_latest_seen": meta.get("stage130_latest_seen", False),
        "stage130_fresh_file_count": meta.get("stage130_fresh_file_count", ""),
        "stage130_stale_file_count": meta.get("stage130_stale_file_count", ""),
        "stage130_rule8_seen": meta.get("stage130_rule8_seen", ""),
        "stage130_rule9_seen": meta.get("stage130_rule9_seen", ""),
        "decision": meta.get("decision", ""),
    }
    write_rows(health_path, [health_row], HEALTH_FIELDS)
    write_rows(governance_path, [{"block": b, "status": "ACTIVE"} for b in HARD_BLOCKS], ["block", "status"])

    kv = {
        "stage": STAGE,
        "status": STATUS,
        "decision": meta.get("decision", ""),
        "generated_utc": scan_utc,
        "allow_trading": "false",
        "order_send": "false",
        "log_files_seen": len(log_files),
        "runtime_log_events": meta.get("runtime_log_events", 0),
        "unified_ea_log_events": meta.get("unified_ea_log_events", 0),
        "rule8_log_events": meta.get("rule8_log_events", 0),
        "rule9_log_events": meta.get("rule9_log_events", 0),
        "order_risk_events": meta.get("order_risk_events", 0),
        "stage130_fresh_file_count": meta.get("stage130_fresh_file_count", ""),
        "stage130_stale_file_count": meta.get("stage130_stale_file_count", ""),
    }
    write_kv(kv_repo, kv)
    write_kv(kv_report, kv)
    mt5_status = ""
    if write_mt5_status_kv:
        p = mt5_files / "xauusd_stage130b_mt5_journal_telemetry_status_kv.csv"
        write_kv(p, kv)
        mt5_status = str(p)

    summary = {
        "stage": STAGE,
        "generated_utc": scan_utc,
        "status": STATUS,
        "decision": meta.get("decision", ""),
        "classification": CLASSIFICATION,
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "mt5_files": str(mt5_files),
        "log_dirs_checked": [str(d) for d in log_dirs],
        "log_files_seen": len(log_files),
        "log_files": [str(p) for p in log_files],
        **meta,
        "events_csv": str(events_path),
        "events_history_csv": str(history_path),
        "runtime_health_summary": str(health_path),
        "status_kv_repo": str(kv_repo),
        "status_kv_report": str(kv_report),
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": mt5_status,
        "governance_no_order_manifest": str(governance_path),
        "summary_json": str(out / "stage130b_mt5_journal_and_files_telemetry_audit_summary.json"),
        "report_md": str(out / "stage130b_mt5_journal_and_files_telemetry_audit_report.md"),
        "next": [
            "If unified_ea_log_events is zero, the current no-change telemetry route cannot confirm live 7-rule observer runtime.",
            "If logs confirm Unified_ObserverOnly_EA but file freshness remains stale, add a telemetry-only writer to the EA in a later controlled patch.",
            "No order, EA change, indicator UI change, broker connection, paper-live, or live path is opened by Stage130B.",
        ],
    }
    write_json(out / "stage130b_mt5_journal_and_files_telemetry_audit_summary.json", summary)
    report = [
        f"# {STAGE}",
        "",
        f"Status: `{STATUS}`",
        f"Decision: `{meta.get('decision', '')}`",
        "",
        "## MT5 journal events",
        "",
        f"- log files seen: {len(log_files)}",
        f"- runtime log events: {meta.get('runtime_log_events', 0)}",
        f"- unified EA events: {meta.get('unified_ea_log_events', 0)}",
        f"- Rule8 events: {meta.get('rule8_log_events', 0)}",
        f"- Rule9 events: {meta.get('rule9_log_events', 0)}",
        f"- order-risk events: {meta.get('order_risk_events', 0)}",
        "",
        "## Stage130 file snapshot context",
        "",
        f"- Stage130 latest seen: {meta.get('stage130_latest_seen')}",
        f"- Stage130 fresh files: {meta.get('stage130_fresh_file_count', '')}",
        f"- Stage130 stale files: {meta.get('stage130_stale_file_count', '')}",
        "",
        "## No-order governance",
        "",
        "\n".join(f"- {b}" for b in HARD_BLOCKS),
    ]
    (out / "stage130b_mt5_journal_and_files_telemetry_audit_report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--log-dir", action="append", default=[], help="Additional MT5 log directory to scan")
    ap.add_argument("--max-log-files", type=int, default=12)
    ap.add_argument("--max-bytes-per-log", type=int, default=2_000_000)
    ap.add_argument("--write-mt5-status-kv", action="store_true")
    args = ap.parse_args()
    run(
        root=Path(args.root),
        mt5_files=Path(args.mt5_files),
        extra_log_dirs=args.log_dir,
        max_log_files=args.max_log_files,
        max_bytes_per_log=args.max_bytes_per_log,
        write_mt5_status_kv=args.write_mt5_status_kv,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
