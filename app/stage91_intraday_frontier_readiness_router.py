#!/usr/bin/env python3
"""Stage91 Intraday Frontier Readiness Router.

Purpose: after macro-only residual search is exhausted, determine whether local
AMarkets/SQLite intraday data is ready for a thesis-first session discovery stage.
No order authorization, no MT5/EA change, no threshold tuning.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

TIME_COL_CANDIDATES = [
    "utc_time", "time_utc", "datetime", "date_time", "date", "time", "timestamp", "feature_date_utc"
]
OHLC_COLS = {"open", "high", "low", "close"}
SPREAD_COL_CANDIDATES = {"spread", "spread_median", "bid_ask_spread", "ask_bid_spread"}
VOLUME_COL_CANDIDATES = {"volume", "tick_volume", "real_volume"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def sha256_file(path: Path, max_bytes: Optional[int] = None) -> str:
    h = hashlib.sha256()
    read = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            if max_bytes is not None and read + len(chunk) > max_bytes:
                chunk = chunk[: max_bytes - read]
            h.update(chunk)
            read += len(chunk)
            if max_bytes is not None and read >= max_bytes:
                break
    return h.hexdigest()


def expand_user_path(p: str, root: Path) -> Path:
    p = os.path.expanduser(p)
    pp = Path(p)
    if pp.is_absolute():
        return pp
    return root / pp


def infer_timeframe_from_name(name: str) -> str:
    low = name.lower()
    tests = [
        ("m1", ["m1", "_1m", "1min", "1_min", "1-minute"]),
        ("m5", ["m5", "_5m", "5min", "5_min", "5-minute"]),
        ("m15", ["m15", "_15m", "15min", "15_min", "15-minute"]),
        ("m30", ["m30", "_30m", "30min", "30_min", "30-minute"]),
        ("h1", ["h1", "_1h", "60min", "1hour", "1_hour"]),
    ]
    for tf, needles in tests:
        if any(n in low for n in needles):
            return tf
    return "unknown"


def sniff_csv(path: Path) -> Tuple[List[str], int, str, List[Dict[str, str]]]:
    # Read a modest sample, sniff delimiter, count rows streaming.
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        headers = reader.fieldnames or []
        rows_preview: List[Dict[str, str]] = []
        count = 0
        for row in reader:
            count += 1
            if len(rows_preview) < 5:
                rows_preview.append({str(k): str(v) for k, v in row.items() if k is not None})
        delim = getattr(dialect, "delimiter", ",")
    return headers, count, delim, rows_preview


def detect_csv_schema(headers: List[str]) -> Dict[str, Any]:
    h_lower = {h.lower().strip(): h for h in headers}
    time_col = ""
    for c in TIME_COL_CANDIDATES:
        if c in h_lower:
            time_col = h_lower[c]
            break
    ohlc_present = sorted([c for c in OHLC_COLS if c in h_lower])
    spread_cols = sorted([h_lower[c] for c in SPREAD_COL_CANDIDATES if c in h_lower])
    volume_cols = sorted([h_lower[c] for c in VOLUME_COL_CANDIDATES if c in h_lower])
    return {
        "time_col": time_col,
        "ohlc_present": "|".join(ohlc_present),
        "ohlc_complete": all(c in h_lower for c in OHLC_COLS),
        "spread_cols": "|".join(spread_cols),
        "spread_present": bool(spread_cols),
        "volume_cols": "|".join(volume_cols),
        "volume_present": bool(volume_cols),
    }


def candidate_csv_paths(root: Path, config: Dict[str, Any]) -> List[Path]:
    paths: List[Path] = []
    for p in config.get("external_csv_paths", []):
        paths.append(expand_user_path(str(p), root))
    # Add repo-local likely CSVs without recursive explosion.
    for d in config.get("repo_data_dirs", []):
        dd = expand_user_path(str(d), root)
        if dd.exists() and dd.is_dir():
            for pat in ["*xau*.csv", "*XAU*.csv", "*gold*.csv", "*GOLD*.csv", "*amarkets*.csv"]:
                paths.extend(dd.glob(pat))
    # De-duplicate preserving order.
    seen = set()
    out = []
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def inventory_csvs(root: Path, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in candidate_csv_paths(root, config):
        row: Dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "filename": path.name,
            "timeframe_inferred": infer_timeframe_from_name(path.name),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "status": "MISSING",
        }
        if path.exists() and path.is_file():
            try:
                headers, count, delim, _preview = sniff_csv(path)
                schema = detect_csv_schema(headers)
                row.update({
                    "status": "READ_OK",
                    "row_count": count,
                    "header_count": len(headers),
                    "delimiter": delim,
                    "headers": "|".join(headers),
                    "sha256_head_1mb": sha256_file(path, max_bytes=1024 * 1024),
                })
                row.update(schema)
            except Exception as exc:
                row.update({"status": "READ_ERROR", "error": repr(exc)})
        rows.append(row)
    return rows


def inventory_sqlite(root: Path, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    db_paths: List[Path] = []
    for pat in config.get("sqlite_globs", []):
        db_paths.extend(Path(p) for p in glob.glob(str(expand_user_path(str(pat), root))))
    seen = set()
    db_paths = [p for p in db_paths if not (str(p) in seen or seen.add(str(p)))]
    rows: List[Dict[str, Any]] = []
    for db in db_paths:
        base: Dict[str, Any] = {"db_path": str(db), "exists": db.exists(), "size_bytes": db.stat().st_size if db.exists() else 0}
        if not db.exists():
            rows.append({**base, "status": "MISSING"})
            continue
        try:
            con = sqlite3.connect(str(db))
            cur = con.cursor()
            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if not tables:
                rows.append({**base, "status": "READ_OK_NO_TABLES", "tables": ""})
                con.close()
                continue
            for table in tables:
                try:
                    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
                    count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    lower = {c.lower(): c for c in cols}
                    tf_counts = ""
                    src_counts = ""
                    if "timeframe" in lower:
                        tf_rows = cur.execute(f"SELECT {lower['timeframe']}, COUNT(*) FROM {table} GROUP BY {lower['timeframe']} LIMIT 20").fetchall()
                        tf_counts = "|".join(f"{a}:{b}" for a, b in tf_rows)
                    if "source" in lower:
                        src_rows = cur.execute(f"SELECT {lower['source']}, COUNT(*) FROM {table} GROUP BY {lower['source']} LIMIT 20").fetchall()
                        src_counts = "|".join(f"{a}:{b}" for a, b in src_rows)
                    rows.append({
                        **base,
                        "status": "READ_OK",
                        "table": table,
                        "row_count": count,
                        "columns": "|".join(cols),
                        "has_ohlc": all(c in lower for c in OHLC_COLS),
                        "has_time_col": any(c in lower for c in TIME_COL_CANDIDATES),
                        "has_spread": any(c in lower for c in SPREAD_COL_CANDIDATES),
                        "timeframe_counts": tf_counts,
                        "source_counts": src_counts,
                    })
                except Exception as exc:
                    rows.append({**base, "status": "TABLE_READ_ERROR", "table": table, "error": repr(exc)})
            con.close()
        except Exception as exc:
            rows.append({**base, "status": "DB_READ_ERROR", "error": repr(exc)})
    return rows


def readiness_from_inventory(csv_rows: List[Dict[str, Any]], db_rows: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    minimums = config.get("minimums", {})
    tf_rows: Dict[str, int] = {}
    tf_spread: Dict[str, bool] = {}
    for r in csv_rows:
        if r.get("status") != "READ_OK":
            continue
        tf = str(r.get("timeframe_inferred") or "unknown")
        count = int(r.get("row_count") or 0)
        if tf != "unknown":
            tf_rows[tf] = max(tf_rows.get(tf, 0), count)
            tf_spread[tf] = tf_spread.get(tf, False) or bool(r.get("spread_present"))
    # Include DB timeframes if table has explicit counts.
    for r in db_rows:
        if r.get("status") != "READ_OK":
            continue
        counts = str(r.get("timeframe_counts") or "")
        for part in counts.split("|"):
            if not part or ":" not in part:
                continue
            tf, cnt_s = part.split(":", 1)
            tf = tf.lower().strip()
            try:
                cnt = int(cnt_s)
            except Exception:
                cnt = 0
            tf_rows[tf] = max(tf_rows.get(tf, 0), cnt)
            tf_spread[tf] = tf_spread.get(tf, False) or bool(r.get("has_spread"))
    ready_tfs = []
    for tf, min_key in [("m1", "m1_min_rows"), ("m5", "m5_min_rows"), ("m15", "m15_min_rows"), ("h1", "h1_min_rows")]:
        if tf_rows.get(tf, 0) >= int(minimums.get(min_key, 10**12)):
            ready_tfs.append(tf)
    score = min(100, 10 + 20 * len(ready_tfs))
    if tf_rows.get("m1", 0) >= int(minimums.get("m1_min_rows", 100000)):
        score += 15
    if tf_rows.get("m5", 0) >= int(minimums.get("m5_min_rows", 50000)):
        score += 10
    if any(tf_spread.values()):
        score += 10
    score = min(100, score)
    enough = len(ready_tfs) >= int(minimums.get("min_distinct_timeframes_ready", 2))
    if enough and ("m1" in ready_tfs or "m5" in ready_tfs):
        decision = "STAGE91_INTRADAY_FRONTIER_READY_FOR_STAGE92_THESIS_DISCOVERY_NO_ORDER"
        classification = "S91_INTRADAY_FRONTIER_READY"
        disposition = "INTRADAY_FRONTIER_READY_FOR_STAGE92"
    else:
        decision = "STAGE91_INTRADAY_FRONTIER_NOT_READY_COLLECT_DATA_NO_ORDER"
        classification = "S91_INTRADAY_FRONTIER_NOT_READY"
        disposition = "INTRADAY_FRONTIER_NOT_READY"
    return {
        "readiness_score": score,
        "timeframe_rows": tf_rows,
        "timeframe_spread_present": tf_spread,
        "ready_timeframes": ready_tfs,
        "decision": decision,
        "classification": classification,
        "disposition": disposition,
    }


def thesis_queue(readiness: Dict[str, Any]) -> List[Dict[str, Any]]:
    ready = set(readiness.get("ready_timeframes") or [])
    rows: List[Dict[str, Any]] = []
    def add(priority: int, family: str, required: str, rationale: str, status: str) -> None:
        rows.append({"priority": priority, "thesis_family": family, "required_data": required, "rationale": rationale, "stage_status": status})
    base_status = "QUEUED_FOR_STAGE92_NO_ORDER" if readiness["disposition"] == "INTRADAY_FRONTIER_READY_FOR_STAGE92" else "WAIT_FOR_DATA"
    add(1, "I01_SESSION_RANGE_BREAKOUT_FILTERED_BY_MACRO_STATE", "m5_or_m15 + session calendar + current unified macro states", "Test whether London/NY breakouts add residual edge only when macro portfolio is inactive or near active.", base_status)
    add(2, "I02_LIQUIDITY_SWEEP_REVERSAL_WITH_SPREAD_GUARD", "m1_or_m5 + high/low + spread proxy", "Revisit liquidity sweep thesis as residual intraday frontier, not as old candidate-first promotion.", base_status)
    add(3, "I03_ASIA_RANGE_COMPRESSION_TO_NY_EXPANSION", "m5/m15 + session segmentation", "Orthogonal session-volatility structure may add exposure outside daily macro triggers.", base_status)
    add(4, "I04_INTRADAY_DOW_EVENT_WINDOW_OBSERVER_ONLY", "m5/m15 + event calendar if available", "Event windows need surprise/timestamp later; for now only readiness/segmentation.", "WAIT_FOR_EVENT_SURPRISE" if base_status.startswith("QUEUED") else "WAIT_FOR_DATA")
    return rows


def data_requirements(readiness: Dict[str, Any]) -> List[Dict[str, Any]]:
    tf_rows = readiness.get("timeframe_rows") or {}
    reqs = []
    for tf, target in [("m1", 100000), ("m5", 50000), ("m15", 20000), ("h1", 10000)]:
        have = int(tf_rows.get(tf, 0) or 0)
        reqs.append({
            "data_item": f"AMarkets XAUUSD {tf.upper()} CSV or DB bars",
            "required_for": "Stage92 intraday/session thesis discovery",
            "current_rows_detected": have,
            "target_rows": target,
            "status": "READY" if have >= target else "NEEDS_DATA",
        })
    reqs.append({
        "data_item": "spread column or reliable spread proxy",
        "required_for": "cost/slippage guard on intraday thesis",
        "current_rows_detected": "see inventory",
        "target_rows": "nonzero spread/proxy coverage preferred",
        "status": "READY_IF_PRESENT_ELSE_PROXY_NEEDED",
    })
    return reqs


def make_report(summary: Dict[str, Any], csv_rows: List[Dict[str, Any]], db_rows: List[Dict[str, Any]], tq: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("# Stage91 Intraday Frontier Readiness Router")
    lines.append("")
    lines.append("## Decision")
    for k in ["status", "decision", "classification", "disposition"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Readiness")
    lines.append(f"- readiness_score: `{summary['intraday_readiness']['readiness_score']}`")
    lines.append(f"- ready_timeframes: `{','.join(summary['intraday_readiness'].get('ready_timeframes') or [])}`")
    lines.append(f"- timeframe_rows: `{summary['intraday_readiness'].get('timeframe_rows')}`")
    lines.append("")
    lines.append("## CSV inventory snapshot")
    for r in csv_rows[:12]:
        lines.append(f"- `{Path(str(r.get('path'))).name}` exists=`{r.get('exists')}` status=`{r.get('status')}` tf=`{r.get('timeframe_inferred')}` rows=`{r.get('row_count','')}` spread=`{r.get('spread_present','')}`")
    lines.append("")
    lines.append("## SQLite inventory snapshot")
    if not db_rows:
        lines.append("- none detected")
    for r in db_rows[:12]:
        lines.append(f"- `{Path(str(r.get('db_path'))).name}` status=`{r.get('status')}` table=`{r.get('table','')}` rows=`{r.get('row_count','')}` timeframes=`{r.get('timeframe_counts','')}`")
    lines.append("")
    lines.append("## Thesis queue")
    for r in tq:
        lines.append(f"- `{r['thesis_family']}`: {r['stage_status']}")
    lines.append("")
    lines.append("## Hard blocks")
    for b in summary["hard_blocks"]:
        lines.append(f"- `{b}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = root / config_path
    out_dir = Path(args.out).expanduser()
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    config = load_json(config_path)

    stage90_path = expand_user_path(config.get("stage90_summary_path", ""), root)
    stage90_ref: Dict[str, Any] = {"path": str(stage90_path), "exists": stage90_path.exists()}
    if stage90_path.exists():
        try:
            s90 = load_json(stage90_path)
            stage90_ref.update({"read_ok": True, "decision": s90.get("decision"), "selected_frontier": s90.get("selected_frontier")})
        except Exception as exc:
            stage90_ref.update({"read_ok": False, "error": repr(exc)})

    csv_rows = inventory_csvs(root, config)
    db_rows = inventory_sqlite(root, config)
    readiness = readiness_from_inventory(csv_rows, db_rows, config)
    tq = thesis_queue(readiness)
    reqs = data_requirements(readiness)

    status = "STAGE91_COMPLETE_NO_PROMOTION"
    summary = {
        "stage": "Stage91_INTRADAY_FRONTIER_READINESS_ROUTER",
        "root": str(root),
        "config": str(config_path),
        "generated_utc": utc_now(),
        "status": status,
        "decision": readiness["decision"],
        "classification": readiness["classification"],
        "disposition": readiness["disposition"],
        "principle": "Route to intraday/session thesis discovery only if local AMarkets/SQLite intraday data is actually ready. No orders and no MT5/EA change.",
        "stage90_reference": stage90_ref,
        "intraday_readiness": readiness,
        "csv_file_count": len(csv_rows),
        "csv_read_ok_count": sum(1 for r in csv_rows if r.get("status") == "READ_OK"),
        "db_inventory_count": len(db_rows),
        "thesis_queue_count": len(tq),
        "hard_blocks": [
            "NO_AUTOMATED_ORDER",
            "NO_PAPER_ORDER",
            "NO_BROKER_CONNECTION",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE91",
            "NO_THRESHOLD_TUNING_FROM_STAGE91_ROUTER",
            "NO_DIRECT_MT5_OR_EA_CHANGE_FROM_STAGE91",
        ],
        "outputs": {},
    }

    names = config.get("output_names", {})
    summary_path = out_dir / names.get("summary_json", "stage91_intraday_frontier_readiness_router_summary.json")
    report_path = out_dir / names.get("report_md", "stage91_intraday_frontier_readiness_router_report.md")
    csv_inv_path = out_dir / names.get("file_inventory_csv", "stage91_intraday_file_inventory.csv")
    db_inv_path = out_dir / names.get("db_inventory_csv", "stage91_intraday_db_inventory.csv")
    tq_path = out_dir / names.get("thesis_queue_csv", "stage91_intraday_thesis_queue.csv")
    req_path = out_dir / names.get("data_requirements_csv", "stage91_intraday_data_requirements.csv")

    write_csv(csv_inv_path, csv_rows)
    write_csv(db_inv_path, db_rows)
    write_csv(tq_path, tq)
    write_csv(req_path, reqs)
    summary["outputs"] = {
        "summary_json": str(summary_path),
        "report_md": str(report_path),
        "file_inventory_csv": str(csv_inv_path),
        "db_inventory_csv": str(db_inv_path),
        "thesis_queue_csv": str(tq_path),
        "data_requirements_csv": str(req_path),
    }
    write_json(summary_path, summary)
    report_path.write_text(make_report(summary, csv_rows, db_rows, tq), encoding="utf-8")
    print(json.dumps({"stage": summary["stage"], "status": status, "decision": summary["decision"], "summary_json": str(summary_path), "report_md": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
