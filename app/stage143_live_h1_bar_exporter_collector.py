#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

STAGE = "Stage143_LIVE_H1_BAR_EXPORTER"
STATUS = "STAGE143_COMPLETE_LIVE_H1_BAR_EXPORTER_COLLECTOR_READY"

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)
DEFAULT_MT5_INDICATORS = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Indicators/XAUUSD"
)

INDICATOR_NAME = "Stage143_LiveH1BarExporter.mq5"
DEFAULT_BARS_FILE = "xauusd_stage143_live_h1_bars.csv"
DEFAULT_KV_FILE = "xauusd_stage143_live_h1_bar_exporter_kv.csv"

RISK_BLOCKS = [
    "NO_ORDER_SEND_IN_STAGE143",
    "NO_POSITION_MODIFICATION_IN_STAGE143",
    "READ_ONLY_BAR_EXPORTER",
    "MT5_H1_FEED_BRIDGE_FOR_STAGE138",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_dt(date_s: str, time_s: str) -> datetime | None:
    raw = f"{date_s.strip()} {time_s.strip()}"
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def read_mt5_tab_bars(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not path.exists() or path.stat().st_size <= 0:
        return [], {"exists": False, "format": "MISSING_OR_EMPTY"}
    text = path.read_text(encoding="utf-8", errors="replace")
    sample = text.splitlines()[:5]
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, dialect=csv.excel_tab)
        for r in reader:
            if not r:
                continue
            date_s = r.get("<DATE>") or r.get("DATE") or r.get("date") or ""
            time_s = r.get("<TIME>") or r.get("TIME") or r.get("time") or ""
            dt = parse_dt(date_s, time_s)
            if dt is None:
                continue
            try:
                close = float(r.get("<CLOSE>") or r.get("CLOSE") or r.get("close") or "nan")
            except Exception:
                close = None
            rows.append({"utc_time": dt, "close": close, "raw": r})
    return rows, {"exists": True, "format": "MT5_TAB", "sample": sample}


def read_kv(path: Path) -> Dict[str, str]:
    if not path.exists() or path.stat().st_size <= 0:
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "|" in line:
            k, v = line.split("|", 1)
            out[k.strip()] = v.strip()
        elif "," in line:
            k, v = line.split(",", 1)
            out[k.strip()] = v.strip()
    return out


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
    "collector_decision",
    "bars_file",
    "kv_file",
    "bars_exists",
    "bars_file_age_sec",
    "bar_count",
    "bar_min_utc",
    "bar_max_utc",
    "last_closed_bar_utc",
    "exporter_generated_utc",
    "exporter_symbol",
    "exporter_period",
    "exporter_bars_written",
]


def collect(root: Path, mt5_files: Path, mt5_indicators: Path, bars_file: str, kv_file: str, stale_after_sec: float, install_indicator_flag: bool, write_mt5_status_kv: bool) -> Dict[str, Any]:
    root = root.expanduser()
    mt5_files = mt5_files.expanduser()
    mt5_indicators = mt5_indicators.expanduser()
    out = ensure_dir(root / "reports/stage143_live_h1_bar_exporter")
    data = ensure_dir(root / "data/demo_execution")
    snapshot = utc_now()

    installed_to = ""
    if install_indicator_flag:
        installed_to = install_indicator(root, mt5_indicators)

    bars_path = mt5_files / bars_file
    kv_path = mt5_files / kv_file
    rows, meta = read_mt5_tab_bars(bars_path)
    kv = read_kv(kv_path)

    bars_age = max(0.0, time.time() - bars_path.stat().st_mtime) if bars_path.exists() and bars_path.stat().st_size > 0 else None
    bar_min = min((r["utc_time"] for r in rows), default=None)
    bar_max = max((r["utc_time"] for r in rows), default=None)

    if not bars_path.exists() or bars_path.stat().st_size <= 0:
        decision = "STAGE143_EXPORT_FILE_MISSING_ATTACH_INDICATOR"
    elif bars_age is not None and bars_age > stale_after_sec:
        decision = "STAGE143_EXPORT_FILE_STALE_REATTACH_OR_WAIT"
    elif len(rows) < 100:
        decision = "STAGE143_TOO_FEW_BARS_CHECK_INDICATOR_INPUTS"
    else:
        decision = "STAGE143_LIVE_H1_EXPORT_READY_FOR_STAGE138"

    row = {
        "snapshot_utc": snapshot,
        "collector_decision": decision,
        "bars_file": str(bars_path),
        "kv_file": str(kv_path),
        "bars_exists": str(bars_path.exists()).lower(),
        "bars_file_age_sec": round(bars_age, 2) if bars_age is not None else "",
        "bar_count": len(rows),
        "bar_min_utc": bar_min.isoformat().replace("+00:00", "Z") if bar_min else "",
        "bar_max_utc": bar_max.isoformat().replace("+00:00", "Z") if bar_max else "",
        "last_closed_bar_utc": kv.get("last_closed_bar_utc", ""),
        "exporter_generated_utc": kv.get("generated_utc", ""),
        "exporter_symbol": kv.get("symbol", ""),
        "exporter_period": kv.get("period", ""),
        "exporter_bars_written": kv.get("bars_written", ""),
    }

    latest_csv = out / "stage143_latest_live_h1_bar_exporter_snapshot.csv"
    history_csv = data / "stage143_live_h1_bar_exporter_snapshots.csv"
    risk_csv = out / "stage143_risk_manifest.csv"
    write_rows(latest_csv, [row], FIELDS)
    write_rows(risk_csv, [{"risk_block": b, "status": "ACTIVE"} for b in RISK_BLOCKS], ["risk_block", "status"])
    exists = history_csv.exists() and history_csv.stat().st_size > 0
    with history_csv.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)

    status_kv = {
        "stage": STAGE,
        "status": STATUS,
        "collector_decision": decision,
        "generated_utc": snapshot,
        "bar_count": len(rows),
        "bar_max_utc": row["bar_max_utc"],
        "bars_file": str(bars_path),
        "installed_to": installed_to,
    }
    status_repo = data / "stage143_live_h1_bar_exporter_collector_status_kv.csv"
    status_report = out / "stage143_live_h1_bar_exporter_collector_status_kv.csv"
    write_kv(status_repo, status_kv)
    write_kv(status_report, status_kv)

    mt5_status = ""
    if write_mt5_status_kv:
        mt5_status = str(mt5_files / "xauusd_stage143_live_h1_bar_exporter_collector_status_kv.csv")
        write_kv(Path(mt5_status), status_kv)

    summary = {
        "stage": STAGE,
        "generated_utc": snapshot,
        "status": STATUS,
        "decision": decision,
        "root": str(root),
        "mt5_files": str(mt5_files),
        "mt5_indicators": str(mt5_indicators),
        "indicator_name": INDICATOR_NAME,
        "installed_to": installed_to,
        **row,
        "latest_csv": str(latest_csv),
        "history_csv": str(history_csv),
        "risk_manifest_csv": str(risk_csv),
        "status_kv_repo": str(status_repo),
        "status_kv_report": str(status_report),
        "mt5_collector_status_kv": mt5_status,
        "summary_json": str(out / "stage143_live_h1_bar_exporter_summary.json"),
        "next": [
            "If decision is ready, point Stage138 slow refresh to this bars_file.",
            "If bar_max_utc remains stale, confirm MT5 chart history is updating and indicator is attached.",
            "Stage143 is read-only and does not send or modify orders.",
        ],
    }
    write_json(out / "stage143_live_h1_bar_exporter_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--mt5-indicators", default=DEFAULT_MT5_INDICATORS)
    ap.add_argument("--bars-file", default=DEFAULT_BARS_FILE)
    ap.add_argument("--kv-file", default=DEFAULT_KV_FILE)
    ap.add_argument("--stale-after-sec", type=float, default=240.0)
    ap.add_argument("--install-indicator", action="store_true")
    ap.add_argument("--write-mt5-status-kv", action="store_true")
    args = ap.parse_args()
    collect(
        root=Path(args.root),
        mt5_files=Path(args.mt5_files),
        mt5_indicators=Path(args.mt5_indicators),
        bars_file=args.bars_file,
        kv_file=args.kv_file,
        stale_after_sec=args.stale_after_sec,
        install_indicator_flag=args.install_indicator,
        write_mt5_status_kv=args.write_mt5_status_kv,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
