#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage130_FORWARD_SHADOW_TELEMETRY_COLLECTOR"
STATUS = "STAGE130_COMPLETE_FORWARD_SHADOW_TELEMETRY_COLLECTOR_READY_NO_ORDER"
DECISION = "STAGE130_FORWARD_SHADOW_TELEMETRY_COLLECTION_ONLY_NO_PROMOTION"
CLASSIFICATION = "MARKET_OPEN_FORWARD_SHADOW_TELEMETRY_NO_ORDER"

HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_TRADE_REQUEST_FROM_STAGE130",
    "NO_ORDER_SEND",
    "NO_CTRADE_USAGE",
    "NO_MT5_EA_CHANGE_FROM_STAGE130",
    "NO_INDICATOR_UI_CHANGE_FROM_STAGE130",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_MT5_FILES = (
    "/Users/vahid/Library/Application Support/net.metaquotes.wine.metatrader5/"
    "drive_c/Program Files/MetaTrader 5/MQL5/Files"
)

EXPECTED_FILES = {
    "rule8_stage124f": "xauusd_stage124f_rule8_overlay_kv.csv",
    "rule9_stage126": "xauusd_stage126_rule9_frontier_status_kv.csv",
    "rule9_stage127_review": "xauusd_stage127_rule9_review_status_kv.csv",
    "stage128_status": "xauusd_stage128_forward_shadow_and_megascan_status_kv.csv",
    "stage129_status": "xauusd_stage129_dual_track_status_kv.csv",
}

DEFAULT_GLOBS = [
    "xauusd_stage*_*.csv",
    "*observer*.csv",
    "*Observer*.csv",
    "*unified*.csv",
    "*Unified*.csv",
]

SNAPSHOT_FIELDS = [
    "snapshot_utc", "label", "discovery_source", "file_path", "file_name", "exists", "file_size_bytes",
    "file_mtime_utc", "file_age_sec", "freshness", "kv_count", "kv_format", "csv_header",
    "csv_preview_row_count", "status", "decision", "rule_id", "signal_active", "allow_trading",
    "order_send", "cost10_mean_bps", "last_signal_time_utc", "hard_no_order_ok", "parse_keys",
]


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utc_now() -> str:
    return utc_now_dt().isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def iso_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_age_sec(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def read_text_head(path: Path, max_bytes: int = 32768) -> str:
    if not path.exists() or path.stat().st_size <= 0:
        return ""
    with path.open("rb") as fh:
        raw = fh.read(max_bytes)
    return raw.decode("utf-8", errors="replace")


def parse_kv_text(text: str) -> Tuple[Dict[str, str], str]:
    kv: Dict[str, str] = {}
    fmt = "UNKNOWN"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        sep = None
        if "|" in line:
            sep = "|"
            fmt = "PIPE"
        elif "," in line and len(line.split(",", 1)[0]) < 80:
            sep = ","
            if fmt == "UNKNOWN":
                fmt = "COMMA"
        if sep is None:
            continue
        k, v = line.split(sep, 1)
        k = k.strip().strip('"').strip("'")
        v = v.strip().strip('"').strip("'")
        if not k:
            continue
        bad_header_keys = {"time", "utc_time", "date", "open", "high", "low", "close", "volume", "spread"}
        if k.lower() in bad_header_keys:
            continue
        kv[k] = v
    if kv and fmt == "UNKNOWN":
        fmt = "KV"
    return kv, fmt


def parse_csv_header(path: Path) -> Tuple[List[str], int]:
    if not path.exists() or path.stat().st_size <= 0:
        return [], 0
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            rows = []
            for i, row in enumerate(reader):
                rows.append(row)
                if i >= 50:
                    break
        if not rows:
            return [], 0
        return [str(x) for x in rows[0]], max(0, len(rows) - 1)
    except Exception:
        return [], 0


def common_get(kv: Dict[str, str], keys: Iterable[str]) -> str:
    low = {k.lower(): v for k, v in kv.items()}
    for key in keys:
        if key in kv:
            return kv[key]
        if key.lower() in low:
            return low[key.lower()]
    return ""


def discover_files(mt5_files: Path, include_globs: List[str]) -> List[Tuple[str, Path, str]]:
    items: List[Tuple[str, Path, str]] = []
    seen = set()
    for label, fn in EXPECTED_FILES.items():
        p = mt5_files / fn
        items.append((label, p, "expected"))
        seen.add(str(p))
    for pat in include_globs:
        for match in sorted(glob.glob(str(mt5_files / pat))):
            p = Path(match)
            if str(p) in seen:
                continue
            items.append((p.stem, p, f"glob:{pat}"))
            seen.add(str(p))
    return items


def snapshot_file(label: str, path: Path, discovery_source: str, stale_after_sec: float, snapshot_utc: str) -> Dict[str, Any]:
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    mtime = path.stat().st_mtime if exists else None
    age = file_age_sec(path) if exists else None
    text = read_text_head(path)
    kv, fmt = parse_kv_text(text)
    header, preview_rows = parse_csv_header(path)

    allow = common_get(kv, ["allow_trading", "execution_allowed", "trading_allowed", "allow"])
    order_send = common_get(kv, ["order_send", "ordersend", "send_order"])
    status = common_get(kv, ["status", "stage127_status", "replay_status", "decision"])
    decision = common_get(kv, ["decision"])
    rule_id = common_get(kv, ["rule_id", "rule", "active_rule", "candidate_id"])
    active = common_get(kv, ["signal_active", "any_signal_active", "active", "rule_active"])
    cost10 = common_get(kv, ["cost10_mean_bps", "tail_cost10_mean_bps", "nonoverlap_cost10_mean_bps"])
    last_signal = common_get(kv, ["last_signal", "last_signal_time_utc", "last_signal_utc", "signal_time_utc"])

    freshness = "MISSING"
    if exists and size > 0:
        freshness = "FRESH" if age is not None and age <= stale_after_sec else "STALE"
    elif exists:
        freshness = "EMPTY"

    no_order_ok = (str(allow).lower() not in {"true", "1", "yes"} and str(order_send).lower() not in {"true", "1", "yes"})

    return {
        "snapshot_utc": snapshot_utc,
        "label": label,
        "discovery_source": discovery_source,
        "file_path": str(path),
        "file_name": path.name,
        "exists": exists,
        "file_size_bytes": size,
        "file_mtime_utc": iso_from_epoch(mtime) if mtime is not None else "",
        "file_age_sec": round(age, 2) if age is not None else "",
        "freshness": freshness,
        "kv_count": len(kv),
        "kv_format": fmt,
        "csv_header": ",".join(header[:30]),
        "csv_preview_row_count": preview_rows,
        "status": status,
        "decision": decision,
        "rule_id": rule_id,
        "signal_active": active,
        "allow_trading": allow,
        "order_send": order_send,
        "cost10_mean_bps": cost10,
        "last_signal_time_utc": last_signal,
        "hard_no_order_ok": str(no_order_ok).lower(),
        "parse_keys": ";".join(sorted(kv.keys())[:80]),
    }


def append_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def write_rows(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    tmp.replace(path)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def write_kv(path: Path, kv: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}|{'' if v is None else v}\n")
    tmp.replace(path)


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    expected = [r for r in rows if r["discovery_source"] == "expected"]
    expected_seen = [r for r in expected if r["exists"] and int(r["file_size_bytes"] or 0) > 0]
    fresh = [r for r in rows if r["freshness"] == "FRESH"]
    stale = [r for r in rows if r["freshness"] == "STALE"]
    missing = [r for r in rows if r["freshness"] == "MISSING"]
    no_order_violations = [r for r in rows if str(r.get("hard_no_order_ok", "")).lower() != "true" and r.get("exists")]
    return {
        "snapshot_file_count": len(rows),
        "expected_file_count": len(expected),
        "expected_seen_count": len(expected_seen),
        "fresh_file_count": len(fresh),
        "stale_file_count": len(stale),
        "missing_file_count": len(missing),
        "no_order_violation_count": len(no_order_violations),
        "rule8_seen": any(r["label"] == "rule8_stage124f" and r["exists"] for r in rows),
        "rule9_seen": any(r["label"] in {"rule9_stage126", "rule9_stage127_review"} and r["exists"] for r in rows),
        "fresh_labels": [r["label"] for r in fresh],
        "stale_labels": [r["label"] for r in stale],
        "missing_expected_labels": [r["label"] for r in expected if not r["exists"]],
    }


def collect_once(root: Path, mt5_files: Path, include_globs: List[str], stale_after_sec: float, write_mt5_status_kv: bool) -> Dict[str, Any]:
    out_dir = ensure_dir(root / "reports/stage130_forward_shadow_telemetry_collector")
    data_dir = ensure_dir(root / "data/forward_shadow_telemetry")
    snapshot_utc = utc_now()

    files = discover_files(mt5_files, include_globs)
    rows = [snapshot_file(label, path, source, stale_after_sec, snapshot_utc) for label, path, source in files]

    history_path = data_dir / "stage130_market_open_shadow_snapshots.csv"
    latest_path = out_dir / "stage130_latest_shadow_snapshot.csv"
    health_path = out_dir / "stage130_shadow_file_health.csv"
    governance_path = out_dir / "stage130_governance_no_order_manifest.csv"
    status_kv_repo = data_dir / "stage130_forward_shadow_telemetry_status_kv.csv"
    status_kv_report = out_dir / "stage130_forward_shadow_telemetry_status_kv.csv"

    append_rows(history_path, rows, SNAPSHOT_FIELDS)
    write_rows(latest_path, rows, SNAPSHOT_FIELDS)
    write_rows(health_path, rows, SNAPSHOT_FIELDS)
    write_rows(governance_path, [{"block": b, "status": "ACTIVE"} for b in HARD_BLOCKS], ["block", "status"])

    s = summarize(rows)
    decision = DECISION
    if s["no_order_violation_count"] > 0:
        decision = "STAGE130_FORWARD_SHADOW_TELEMETRY_NO_ORDER_VIOLATION_REVIEW_REQUIRED"
    elif s["expected_seen_count"] < 2:
        decision = "STAGE130_FORWARD_SHADOW_TELEMETRY_INSUFFICIENT_RUNTIME_FILES"

    kv = {
        "stage": STAGE,
        "status": STATUS,
        "decision": decision,
        "generated_utc": snapshot_utc,
        "allow_trading": "false",
        "order_send": "false",
        "snapshot_file_count": s["snapshot_file_count"],
        "expected_seen_count": s["expected_seen_count"],
        "fresh_file_count": s["fresh_file_count"],
        "stale_file_count": s["stale_file_count"],
        "missing_file_count": s["missing_file_count"],
        "rule8_seen": str(s["rule8_seen"]).lower(),
        "rule9_seen": str(s["rule9_seen"]).lower(),
        "no_order_violation_count": s["no_order_violation_count"],
    }
    write_kv(status_kv_repo, kv)
    write_kv(status_kv_report, kv)
    mt5_status_kv = ""
    if write_mt5_status_kv:
        mt5_status = mt5_files / "xauusd_stage130_forward_shadow_telemetry_status_kv.csv"
        write_kv(mt5_status, kv)
        mt5_status_kv = str(mt5_status)

    summary = {
        "stage": STAGE,
        "generated_utc": snapshot_utc,
        "status": STATUS,
        "decision": decision,
        "classification": CLASSIFICATION,
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "mt5_files": str(mt5_files),
        "stale_after_sec": stale_after_sec,
        **s,
        "history_csv": str(history_path),
        "latest_snapshot_csv": str(latest_path),
        "health_csv": str(health_path),
        "status_kv_repo": str(status_kv_repo),
        "status_kv_report": str(status_kv_report),
        "mt5_status_kv_written": bool(write_mt5_status_kv),
        "mt5_status_kv": mt5_status_kv,
        "governance_no_order_manifest": str(governance_path),
        "summary_json": str(out_dir / "stage130_forward_shadow_telemetry_collector_summary.json"),
        "report_md": str(out_dir / "stage130_forward_shadow_telemetry_collector_report.md"),
        "next": [
            "Run this collector periodically while the market is open to build a forward-shadow telemetry history.",
            "Do not promote Rule8/Rule9 from telemetry alone; review only after enough fresh runtime snapshots are collected.",
            "No EA, indicator UI, broker, paper-order, or live-order change is performed by Stage130.",
        ],
    }
    write_json(out_dir / "stage130_forward_shadow_telemetry_collector_summary.json", summary)

    report = [
        f"# {STAGE}", "", f"Status: `{STATUS}`", f"Decision: `{decision}`", "", "## Runtime health", "",
        f"- Expected seen: {s['expected_seen_count']} / {s['expected_file_count']}",
        f"- Fresh: {s['fresh_file_count']}",
        f"- Stale: {s['stale_file_count']}",
        f"- Missing: {s['missing_file_count']}",
        f"- Rule8 seen: {s['rule8_seen']}",
        f"- Rule9 seen: {s['rule9_seen']}",
        f"- No-order violations: {s['no_order_violation_count']}", "", "## No-order governance", "",
        "\n".join(f"- {b}" for b in HARD_BLOCKS),
    ]
    (out_dir / "stage130_forward_shadow_telemetry_collector_report.md").write_text("\n".join(report), encoding="utf-8")
    return summary


def run_loop(root: Path, mt5_files: Path, include_globs: List[str], stale_after_sec: float, poll_seconds: float, duration_minutes: float, write_mt5_status_kv: bool) -> Dict[str, Any]:
    end_at = time.time() + max(0.0, duration_minutes) * 60.0
    count = 0
    last_summary: Dict[str, Any] = {}
    while True:
        count += 1
        last_summary = collect_once(root, mt5_files, include_globs, stale_after_sec, write_mt5_status_kv)
        print(json.dumps({"snapshot_no": count, "generated_utc": last_summary["generated_utc"], "decision": last_summary["decision"], "fresh_file_count": last_summary["fresh_file_count"]}, ensure_ascii=False), flush=True)
        if duration_minutes <= 0:
            break
        if time.time() + poll_seconds > end_at:
            break
        time.sleep(max(1.0, poll_seconds))
    last_summary["loop_snapshot_count"] = count
    return last_summary


def main() -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--mt5-files", default=DEFAULT_MT5_FILES)
    ap.add_argument("--stale-after-sec", type=float, default=900.0)
    ap.add_argument("--poll-seconds", type=float, default=300.0)
    ap.add_argument("--duration-minutes", type=float, default=0.0, help="0 means collect one snapshot and exit")
    ap.add_argument("--write-mt5-status-kv", action="store_true")
    ap.add_argument("--include-glob", action="append", default=[], help="Additional glob pattern inside MQL5/Files")
    ap.add_argument("--no-default-globs", action="store_true")
    args = ap.parse_args()

    globs = [] if args.no_default_globs else list(DEFAULT_GLOBS)
    globs.extend(args.include_glob)
    summary = run_loop(Path(args.root).expanduser(), Path(args.mt5_files).expanduser(), globs, args.stale_after_sec, args.poll_seconds, args.duration_minutes, args.write_mt5_status_kv)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
