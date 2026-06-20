#!/usr/bin/env python3
"""
Stage54 Ops Readiness Report for XAUUSD project.

Purpose:
- Does not create trades, signals, orders, EA, paper-live, or live execution.
- Audits local operational readiness while the market is closed or before the next AMarkets update.
- Checks Git hygiene for large local DB/runtime files.
- Checks AMarkets export freshness and persistent SQLite metadata.
- Checks Stage52 true-forward watermark and Stage53 gate state.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

TIMEFRAME_FILES = {
    "M1": ["amarkets_xauusd_1m.csv", "amarkets_xauusd_m1.csv"],
    "M5": ["amarkets_xauusd_5m.csv", "amarkets_xauusd_m5.csv"],
    "M15": ["amarkets_xauusd_15m.csv", "amarkets_xauusd_m15.csv"],
    "M30": ["amarkets_xauusd_30m.csv", "amarkets_xauusd_m30.csv"],
    "H1": ["amarkets_xauusd_1h.csv", "amarkets_xauusd_h1.csv", "amarkets_xauusd_60m.csv"],
}

REQUIRED_GITIGNORE_PATTERNS = [
    "data/broker_normalized/",
    "data/shadow/",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.zip",
    "_incoming*/",
]

LOCAL_DATA_TRACK_PATTERNS = [
    "data/broker_normalized",
    "data/shadow",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.duckdb",
    "*.zip",
]

NO_PROMOTION_BLOCK = {
    "promotion": "NO_GO",
    "EA": "NO_GO",
    "paper_live": "NO_GO",
    "live": "NO_GO",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_utc(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    s = str(value).strip()
    if not s or s.lower() in {"none", "null", "nan"}:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s[:-1] + "+00:00").astimezone(timezone.utc)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc), "_path": str(path)}


def run_git(root: Path, args: List[str]) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 999, "", str(exc)


def read_tail_lines(path: Path, max_bytes: int = 65536) -> List[str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(-max_bytes, os.SEEK_END)
            data = fh.read()
        text = data.decode("utf-8", errors="replace")
        return [ln.strip() for ln in text.splitlines() if ln.strip()]
    except Exception:
        return []


def normalize_header_token(token: str) -> str:
    token = token.strip().strip("\ufeff").strip()
    token = token.strip("<>").strip()
    return re.sub(r"[^A-Za-z0-9]+", "_", token).strip("_").lower()


def sniff_delimiter(line: str) -> str:
    if "\t" in line:
        return "\t"
    if ";" in line and line.count(";") >= line.count(","):
        return ";"
    return ","


def split_row(line: str, delimiter: str) -> List[str]:
    # MT5 tab exports are simple; use csv for comma/semicolon safety.
    try:
        return next(csv.reader([line], delimiter=delimiter))
    except Exception:
        return line.split(delimiter)


def parse_mt5_datetime(date_value: str, time_value: str, server_utc_offset_hours: float) -> Optional[datetime]:
    raw = f"{date_value.strip()} {time_value.strip()}"
    formats = [
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
    ]
    for fmt in formats:
        try:
            server_dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return server_dt - timedelta(hours=server_utc_offset_hours)
        except Exception:
            pass
    return None


def find_export_file(input_dir: Path, timeframe: str) -> Optional[Path]:
    for name in TIMEFRAME_FILES[timeframe]:
        path = input_dir / name
        if path.exists():
            return path
    return None


def inspect_export(path: Optional[Path], server_utc_offset_hours: float) -> Dict[str, Any]:
    if path is None:
        return {"found": False}
    info: Dict[str, Any] = {
        "found": True,
        "path": str(path),
        "size_bytes": None,
        "mtime_utc": None,
        "last_row_time_utc": None,
        "parse_ok": False,
        "error": None,
    }
    try:
        stat = path.stat()
        info["size_bytes"] = stat.st_size
        info["mtime_utc"] = dt_to_iso(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))
        lines = read_tail_lines(path)
        if not lines:
            info["error"] = "empty_or_unreadable_file"
            return info
        # Find header from first line in file if cheap.
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                header_line = fh.readline().strip()
        except Exception:
            header_line = lines[0]
        delimiter = sniff_delimiter(header_line)
        headers = [normalize_header_token(x) for x in split_row(header_line, delimiter)]
        date_idx = headers.index("date") if "date" in headers else None
        time_idx = headers.index("time") if "time" in headers else None
        if date_idx is None or time_idx is None:
            info["error"] = f"date_time_header_not_found headers={headers}"
            return info
        for line in reversed(lines):
            if line == header_line or "<DATE>" in line.upper():
                continue
            parts = split_row(line, delimiter)
            if len(parts) <= max(date_idx, time_idx):
                continue
            dt = parse_mt5_datetime(parts[date_idx], parts[time_idx], server_utc_offset_hours)
            if dt:
                info["last_row_time_utc"] = dt_to_iso(dt)
                info["parse_ok"] = True
                return info
        info["error"] = "no_parseable_data_row_in_tail"
        return info
    except Exception as exc:
        info["error"] = str(exc)
        return info


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def inspect_broker_db(db_path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"found": db_path.exists(), "path": str(db_path), "schema_ok": False, "timeframes": {}}
    if not db_path.exists():
        return info
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            if not sqlite_table_exists(conn, "amarkets_bars"):
                info["error"] = "amarkets_bars_table_missing"
                return info
            cols = [r[1] for r in conn.execute("PRAGMA table_info(amarkets_bars)").fetchall()]
            needed = {"timeframe", "time_utc", "open", "high", "low", "close"}
            info["columns"] = cols
            if not needed.issubset(set(cols)):
                info["error"] = f"required_columns_missing needed={sorted(needed - set(cols))}"
                return info
            info["schema_ok"] = True
            for tf, count, min_ts, max_ts in conn.execute(
                "SELECT timeframe, COUNT(*), MIN(time_utc), MAX(time_utc) "
                "FROM amarkets_bars GROUP BY timeframe ORDER BY timeframe"
            ).fetchall():
                info["timeframes"][tf] = {"rows": count, "start_utc": min_ts, "end_utc": max_ts}
            return info
        finally:
            conn.close()
    except Exception as exc:
        info["error"] = str(exc)
        return info


def inspect_shadow_state(state_db: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "found": state_db.exists(),
        "path": str(state_db),
        "schema_ok": False,
        "watermark_utc": None,
        "signals": {},
    }
    if not state_db.exists():
        return info
    try:
        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row
        try:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            info["tables"] = tables
            if "signals" not in tables:
                info["error"] = "signals_table_missing"
                return info
            info["schema_ok"] = True
            # Try kv table for watermark; tolerate unknown schema.
            if "kv" in tables:
                kv_cols = [r[1] for r in conn.execute("PRAGMA table_info(kv)").fetchall()]
                rows = conn.execute("SELECT * FROM kv").fetchall()
                candidates = []
                for row in rows:
                    rowd = dict(row)
                    text = json.dumps(rowd, default=str)
                    if "watermark" in text.lower():
                        candidates.append(rowd)
                info["watermark_kv_candidates"] = candidates[:20]
                for rowd in candidates:
                    for value in rowd.values():
                        dt = parse_iso_utc(value)
                        if dt:
                            info["watermark_utc"] = dt_to_iso(dt)
                            break
                    if info["watermark_utc"]:
                        break
            # Fallback: infer from max created/entry when rows exist; not a real watermark but useful.
            cols = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
            info["signal_columns"] = cols
            total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            backfill = 0
            true_forward = 0
            pending = 0
            evaluated = 0
            if "is_backfill" in cols:
                backfill = conn.execute("SELECT COUNT(*) FROM signals WHERE COALESCE(is_backfill,0)=1").fetchone()[0]
                true_forward = conn.execute("SELECT COUNT(*) FROM signals WHERE COALESCE(is_backfill,0)=0").fetchone()[0]
            if "status" in cols:
                pending = conn.execute("SELECT COUNT(*) FROM signals WHERE status='PENDING'").fetchone()[0]
                evaluated = conn.execute("SELECT COUNT(*) FROM signals WHERE status='EVALUATED'").fetchone()[0]
            info["signals"] = {
                "total": total,
                "backfill": backfill,
                "true_forward": true_forward,
                "pending": pending,
                "evaluated": evaluated,
            }
            return info
        finally:
            conn.close()
    except Exception as exc:
        info["error"] = str(exc)
        return info


def inspect_git_hygiene(root: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"is_git_repo": False, "gitignore": {}, "tracked_local_data": []}
    rc, out, err = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    info["is_git_repo"] = (rc == 0 and out.strip() == "true")
    ignore_path = root / ".gitignore"
    ignore_text = ignore_path.read_text(encoding="utf-8", errors="replace") if ignore_path.exists() else ""
    missing = [p for p in REQUIRED_GITIGNORE_PATTERNS if p not in ignore_text]
    info["gitignore"] = {
        "path": str(ignore_path),
        "found": ignore_path.exists(),
        "required_patterns": REQUIRED_GITIGNORE_PATTERNS,
        "missing_patterns": missing,
        "ok": bool(ignore_path.exists()) and not missing,
    }
    if info["is_git_repo"]:
        tracked: List[str] = []
        for pat in LOCAL_DATA_TRACK_PATTERNS:
            rc, out, _ = run_git(root, ["ls-files", pat])
            if rc == 0 and out:
                tracked.extend([x for x in out.splitlines() if x.strip()])
        info["tracked_local_data"] = sorted(set(tracked))
        info["tracked_local_data_ok"] = not info["tracked_local_data"]
        rc, out, err = run_git(root, ["status", "--short"])
        info["status_short"] = out if rc == 0 else err
    return info


def load_stage_summaries(paths: Dict[str, Path]) -> Dict[str, Any]:
    return {name: read_json(path) for name, path in paths.items()}


def compare_times(a: Optional[str], b: Optional[str]) -> Optional[int]:
    da = parse_iso_utc(a)
    db = parse_iso_utc(b)
    if not da or not db:
        return None
    if da > db:
        return 1
    if da < db:
        return -1
    return 0


def build_checks(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    git = summary["git"]
    db = summary["broker_db"]
    shadow = summary["shadow_state"]
    exports = summary["exports"]
    stage52 = summary["stage_summaries"].get("stage52_forward_summary") or {}
    runner = summary["stage_summaries"].get("stage52_runner_summary") or {}
    gate = summary["stage_summaries"].get("stage53_gate_summary") or {}

    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: str, severity: str = "INFO") -> None:
        checks.append({
            "check": name,
            "passed": bool(passed),
            "observed": observed,
            "expected": expected,
            "severity": severity,
        })

    add("gitignore_contains_local_data_patterns", git.get("gitignore", {}).get("ok", False), git.get("gitignore", {}).get("missing_patterns"), "no missing .gitignore data patterns", "HIGH")
    add("no_local_data_tracked_by_git", git.get("tracked_local_data_ok", False), git.get("tracked_local_data"), "no tracked DB/zip/runtime local data", "HIGH")
    add("broker_db_schema_ok", db.get("schema_ok", False), db.get("error"), "amarkets_bars schema is readable", "HIGH")
    for tf in ["M1", "M5", "M15", "M30", "H1"]:
        add(f"export_{tf}_present", exports.get(tf, {}).get("found", False), exports.get(tf, {}).get("path"), "AMarkets export file found", "MEDIUM")
        add(f"export_{tf}_tail_parse_ok", exports.get(tf, {}).get("parse_ok", False), exports.get(tf, {}).get("error"), "last row timestamp parseable", "MEDIUM")
        add(f"db_{tf}_present", tf in db.get("timeframes", {}), db.get("timeframes", {}).get(tf), "timeframe exists in broker DB", "MEDIUM")
    add("shadow_state_schema_ok", shadow.get("schema_ok", False), shadow.get("error"), "Stage52 shadow DB is readable", "HIGH")
    add("shadow_state_no_backfill", shadow.get("signals", {}).get("backfill", 0) == 0, shadow.get("signals", {}).get("backfill"), "backfill signal count must be zero", "HIGH")
    add("stage52_runner_available", bool(runner), runner.get("status") if isinstance(runner, dict) else None, "Stage52 runner summary exists", "MEDIUM")
    add("stage52_forward_summary_available", bool(stage52), stage52.get("status") if isinstance(stage52, dict) else None, "Stage52 forward summary exists", "MEDIUM")
    add("stage53_gate_summary_available", bool(gate), gate.get("decision") if isinstance(gate, dict) else None, "Stage53 gate summary exists", "LOW")

    watermark = None
    if isinstance(stage52, dict):
        watermark = stage52.get("new_watermark_utc") or stage52.get("latest_m15_time_utc")
    watermark = watermark or shadow.get("watermark_utc")
    db_m15_latest = db.get("timeframes", {}).get("M15", {}).get("end_utc")
    export_m15_latest = exports.get("M15", {}).get("last_row_time_utc")
    add("m15_db_not_behind_watermark", compare_times(db_m15_latest, watermark) in {0, 1, None}, {"db_m15_latest": db_m15_latest, "watermark": watermark}, "DB M15 latest should be >= watermark when comparable", "MEDIUM")
    add("m15_export_not_older_than_db", compare_times(export_m15_latest, db_m15_latest) in {0, 1, None}, {"export_m15_latest": export_m15_latest, "db_m15_latest": db_m15_latest}, "export M15 latest should be >= DB M15 latest when comparable", "MEDIUM")

    return checks


def decide(summary: Dict[str, Any], checks: List[Dict[str, Any]]) -> Tuple[str, str]:
    high_failures = [c["check"] for c in checks if not c["passed"] and c["severity"] == "HIGH"]
    if high_failures:
        return "OPS_READINESS_BLOCKED_FIX_HIGH_SEVERITY_CHECKS_NO_PROMOTION", "FIX_HIGH_SEVERITY_OPS_CHECKS_NO_PROMOTION"
    stage52 = summary["stage_summaries"].get("stage52_forward_summary") or {}
    watermark = stage52.get("new_watermark_utc") or stage52.get("latest_m15_time_utc")
    db_m15_latest = summary["broker_db"].get("timeframes", {}).get("M15", {}).get("end_utc")
    if compare_times(db_m15_latest, watermark) == 1:
        return "OPS_READY_NEW_DB_BARS_AVAILABLE_RUN_STAGE52_STAGE53_NO_PROMOTION", "RUN_STAGE52_THEN_STAGE53_NO_PROMOTION"
    return "OPS_READY_WAIT_FOR_NEW_AMARKETS_M15_BARS_NO_PROMOTION", "UPDATE_AMARKETS_AFTER_MARKET_REOPEN_THEN_RUN_STAGE52_STAGE53_NO_PROMOTION"


def write_outputs(summary: Dict[str, Any], checks: List[Dict[str, Any]], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "stage54_ops_readiness_summary.json"
    report_path = out / "stage54_ops_readiness_report.md"
    checks_path = out / "stage54_ops_readiness_checks.csv"

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with checks_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["check", "passed", "observed", "expected", "severity"])
        writer.writeheader()
        for row in checks:
            writer.writerow(row)

    db = summary["broker_db"]
    shadow = summary["shadow_state"]
    exports = summary["exports"]
    git = summary["git"]
    lines: List[str] = []
    lines.append("# Stage54 Ops Readiness Report")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- decision: `{summary['decision']}`")
    lines.append(f"- next_allowed_step: `{summary['next_allowed_step']}`")
    lines.append("- promotion: `NO_GO`")
    lines.append("- EA: `NO_GO`")
    lines.append("- paper_live: `NO_GO`")
    lines.append("- live: `NO_GO`")
    lines.append("")
    lines.append("## Git hygiene")
    lines.append("")
    lines.append(f"- gitignore_ok: `{git.get('gitignore', {}).get('ok')}`")
    lines.append(f"- tracked_local_data_count: `{len(git.get('tracked_local_data', []))}`")
    if git.get("tracked_local_data"):
        for item in git["tracked_local_data"][:20]:
            lines.append(f"  - `{item}`")
    lines.append("")
    lines.append("## AMarkets exports")
    lines.append("")
    for tf in ["M1", "M5", "M15", "M30", "H1"]:
        ex = exports.get(tf, {})
        lines.append(f"- {tf}: found=`{ex.get('found')}` parse_ok=`{ex.get('parse_ok')}` last_row_time_utc=`{ex.get('last_row_time_utc')}` path=`{ex.get('path')}`")
    lines.append("")
    lines.append("## Broker DB")
    lines.append("")
    lines.append(f"- found: `{db.get('found')}`")
    lines.append(f"- schema_ok: `{db.get('schema_ok')}`")
    for tf in ["M1", "M5", "M15", "M30", "H1"]:
        meta = db.get("timeframes", {}).get(tf, {})
        lines.append(f"- {tf}: rows=`{meta.get('rows')}` start=`{meta.get('start_utc')}` end=`{meta.get('end_utc')}`")
    lines.append("")
    lines.append("## Stage52 shadow state")
    lines.append("")
    lines.append(f"- found: `{shadow.get('found')}`")
    lines.append(f"- schema_ok: `{shadow.get('schema_ok')}`")
    lines.append(f"- watermark_utc: `{shadow.get('watermark_utc')}`")
    sig = shadow.get("signals", {})
    lines.append(f"- total_signals: `{sig.get('total')}`")
    lines.append(f"- true_forward_signals: `{sig.get('true_forward')}`")
    lines.append(f"- backfill_signals: `{sig.get('backfill')}`")
    lines.append(f"- pending_signals: `{sig.get('pending')}`")
    lines.append(f"- evaluated_signals: `{sig.get('evaluated')}`")
    lines.append("")
    lines.append("## Failed checks")
    lines.append("")
    failed = [c for c in checks if not c["passed"]]
    if not failed:
        lines.append("- none")
    else:
        for c in failed:
            lines.append(f"- `{c['check']}` severity=`{c['severity']}` observed=`{c['observed']}` expected=`{c['expected']}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("This stage is an operational readiness report only. It checks local data hygiene, AMarkets export freshness, persistent broker DB metadata, and Stage52/Stage53 state. It does not authorize promotion, EA, paper-live, live trading, or order submission.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage54 ops readiness report")
    parser.add_argument("--root", default=".")
    parser.add_argument("--input-dir", default="~/Downloads")
    parser.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    parser.add_argument("--state-db", default="data/shadow/stage52_forward_shadow.sqlite")
    parser.add_argument("--stage52-summary", default="reports/stage52_forward_shadow/stage52_volatility_squeeze_forward_shadow_summary.json")
    parser.add_argument("--runner-summary", default="reports/stage52_forward_shadow/stage52_import_then_forward_shadow_summary.json")
    parser.add_argument("--stage53-gate-summary", default="reports/stage53_forward_shadow_prep/stage53_forward_shadow_gate_summary.json")
    parser.add_argument("--server-utc-offset-hours", type=float, default=3.0)
    parser.add_argument("--out", default="reports/stage54_ops_readiness")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    out = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()
    db_path = (root / args.db).resolve() if not Path(args.db).is_absolute() else Path(args.db).resolve()
    state_db = (root / args.state_db).resolve() if not Path(args.state_db).is_absolute() else Path(args.state_db).resolve()

    exports = {tf: inspect_export(find_export_file(input_dir, tf), args.server_utc_offset_hours) for tf in TIMEFRAME_FILES}
    broker_db = inspect_broker_db(db_path)
    shadow_state = inspect_shadow_state(state_db)
    git = inspect_git_hygiene(root)
    stage_summaries = load_stage_summaries({
        "stage52_forward_summary": root / args.stage52_summary,
        "stage52_runner_summary": root / args.runner_summary,
        "stage53_gate_summary": root / args.stage53_gate_summary,
    })

    summary: Dict[str, Any] = {
        "stage": "Stage54_OPS_READINESS_AND_DATA_GIT_HYGIENE_NO_PROMOTION",
        "patch": "STAGE54_OPS_READINESS_REPORT_NO_PROMOTION",
        "status": "OPS_READINESS_REPORT_COMPLETE_NO_PROMOTION",
        **NO_PROMOTION_BLOCK,
        "root": str(root),
        "input_dir": str(input_dir),
        "db": str(db_path),
        "state_db": str(state_db),
        "exports": exports,
        "broker_db": broker_db,
        "shadow_state": shadow_state,
        "git": git,
        "stage_summaries": stage_summaries,
        "generated_utc": iso_now(),
    }
    checks = build_checks(summary)
    decision, next_step = decide(summary, checks)
    summary["decision"] = decision
    summary["next_allowed_step"] = next_step
    summary["checks"] = checks
    summary["failed_checks"] = [c["check"] for c in checks if not c["passed"]]
    write_outputs(summary, checks, out)

    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "decision": summary["decision"],
        "failed_checks": summary["failed_checks"],
        "out": str(out),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
