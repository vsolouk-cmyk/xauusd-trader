#!/usr/bin/env python3
"""
Stage48B Execution Realism and Data Source Feasibility Precheck

Research-only audit. This script does not generate trading signals and does not promote
any strategy. It checks whether the repository contains the data needed for a genuinely
new Stage48 thesis that depends on broker-real execution evidence rather than another
candle-only rule scan.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage48B_EXECUTION_REALISM_AND_DATA_SOURCE_FEASIBILITY_PRECHECK"
PATCH = "Stage48B_REPOSITORY_DATA_FEASIBILITY_PRECHECK_NO_TRADING_SCAN"

TS_ALIASES = {
    "time_utc", "timestamp_utc", "utc_timestamp", "candle_timestamp_utc",
    "timestamp", "datetime", "date", "time", "open_time", "bar_time", "time_iso",
}
SYMBOL_ALIASES = {"symbol", "instrument", "pair", "ticker"}
TIMEFRAME_ALIASES = {"timeframe", "interval", "tf", "granularity"}
SESSION_ALIASES = {"session", "session_utc", "market_session"}
BID_ALIASES = {"bid", "bid_close", "close_bid", "bid_price", "bidclose"}
ASK_ALIASES = {"ask", "ask_close", "close_ask", "ask_price", "askclose"}
SPREAD_ALIASES = {
    "spread", "spread_close", "close_spread", "spread_points", "spread_pips",
    "broker_spread", "ask_bid_spread", "spread_bps", "spread_point", "spread_in_points",
}
BOOLEAN_SPREAD_METADATA = {"spread_available", "has_spread", "is_spread_available", "spread_present"}
OHLC_ALIASES = {
    "open": {"open", "o", "open_price"},
    "high": {"high", "h", "high_price"},
    "low": {"low", "l", "low_price"},
    "close": {"close", "c", "close_price", "mid", "mid_close"},
}
NEWS_KEYWORDS = ("news", "calendar", "event", "events", "econ", "economic", "macro", "fomc", "cpi", "nfp")
MT5_KEYWORDS = ("mt5", "metatrader", "broker", "terminal", "bidask", "ticks", "tick")
XAU_MARKERS = ("xau", "gold", "xauusd", "xau_usd", "xau/usd")
TF5_MARKERS = ("5min", "m5", "5m")
EXCLUDE_DIR_PARTS = {".git", ".venv", "venv", "__pycache__", "node_modules", "archive"}


def norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def first_col(cols: Iterable[str], aliases: Iterable[str]) -> Optional[str]:
    aliases = set(aliases)
    for c in cols:
        if norm_col(c) in aliases:
            return c
    return None


def is_numeric_text(x: Any) -> bool:
    if x is None:
        return False
    s = str(x).strip()
    if not s or s.lower() in {"true", "false", "nan", "none", "null"}:
        return False
    try:
        float(s)
        return True
    except Exception:
        return False


def parse_time(x: Any) -> Optional[dt.datetime]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    # Common normalized forms: 2026-03-21T05:20:00Z or 2026-06-02 12:25:00+00:00
    variants = [s]
    if s.endswith("Z"):
        variants.append(s[:-1] + "+00:00")
    if " " in s and "T" not in s:
        variants.append(s.replace(" ", "T"))
    for v in variants:
        try:
            d = dt.datetime.fromisoformat(v)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            else:
                d = d.astimezone(dt.timezone.utc)
            return d
        except Exception:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = dt.datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            else:
                d = d.astimezone(dt.timezone.utc)
            return d
        except Exception:
            pass
    return None


def should_skip_path(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & EXCLUDE_DIR_PARTS)


def discover_files(root: Path) -> Dict[str, List[Path]]:
    search_roots = [root / "data", root / "reports"]
    files = {"csv": [], "sqlite": [], "news_like": [], "mt5_like": []}
    for base in search_roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if should_skip_path(p) or not p.is_file():
                continue
            name = str(p).lower()
            if p.suffix.lower() == ".csv":
                files["csv"].append(p)
            if p.suffix.lower() in {".sqlite", ".db", ".sqlite3"}:
                files["sqlite"].append(p)
            if any(k in name for k in NEWS_KEYWORDS) and p.suffix.lower() in {".csv", ".json", ".jsonl", ".txt"}:
                files["news_like"].append(p)
            if any(k in name for k in MT5_KEYWORDS):
                files["mt5_like"].append(p)
    for k in files:
        files[k] = sorted(set(files[k]))
    return files


def inspect_csv(path: Path, max_sample: int = 5) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "kind": "csv", "path": str(path), "error": None,
        "raw_rows": 0, "xau_m5_like_rows": 0, "timestamp_rows": 0,
        "start_utc": None, "end_utc": None, "coverage_days": 0.0,
        "fieldnames": [], "mapping": {}, "sample_rows_limited": [],
        "bidask_rows": 0, "numeric_spread_rows": 0,
        "has_bid_col": False, "has_ask_col": False, "has_numeric_spread_col": False,
        "has_boolean_spread_metadata": False,
        "has_session_col": False, "provider_values_limited": [],
        "is_xau_name": any(m in str(path).lower() for m in XAU_MARKERS),
        "is_m5_name": any(m in str(path).lower() for m in TF5_MARKERS),
    }
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
            except Exception:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            if not reader.fieldnames:
                meta["error"] = "NO_HEADER"
                return meta
            cols = list(reader.fieldnames)
            ncols = [norm_col(c) for c in cols]
            meta["fieldnames"] = cols
            col_by_norm = {norm_col(c): c for c in cols}
            ts_col = first_col(cols, TS_ALIASES)
            symbol_col = first_col(cols, SYMBOL_ALIASES)
            timeframe_col = first_col(cols, TIMEFRAME_ALIASES)
            session_col = first_col(cols, SESSION_ALIASES)
            bid_col = first_col(cols, BID_ALIASES)
            ask_col = first_col(cols, ASK_ALIASES)
            spread_col = first_col([c for c in cols if norm_col(c) not in BOOLEAN_SPREAD_METADATA], SPREAD_ALIASES)
            provider_col = col_by_norm.get("provider")
            meta["mapping"] = {
                "ts": ts_col, "symbol": symbol_col, "timeframe": timeframe_col, "session": session_col,
                "bid": bid_col, "ask": ask_col, "spread": spread_col,
            }
            meta["has_bid_col"] = bool(bid_col)
            meta["has_ask_col"] = bool(ask_col)
            meta["has_numeric_spread_col"] = bool(spread_col)
            meta["has_boolean_spread_metadata"] = any(c in BOOLEAN_SPREAD_METADATA for c in ncols)
            meta["has_session_col"] = bool(session_col)
            provider_values = []
            start: Optional[dt.datetime] = None
            end: Optional[dt.datetime] = None
            for row in reader:
                meta["raw_rows"] += 1
                if len(meta["sample_rows_limited"]) < max_sample:
                    meta["sample_rows_limited"].append({k: row.get(k) for k in cols[:12]})
                symbol_ok = True
                tf_ok = True
                if symbol_col:
                    sv = str(row.get(symbol_col, "")).lower().replace(" ", "")
                    symbol_ok = "xau" in sv or "gold" in sv
                if timeframe_col:
                    tv = str(row.get(timeframe_col, "")).lower().replace(" ", "")
                    tf_ok = tv in {"m5", "5m", "5min", "5minute", "5minutes"}
                else:
                    tf_ok = meta["is_m5_name"]
                if symbol_ok and tf_ok:
                    meta["xau_m5_like_rows"] += 1
                if ts_col:
                    t = parse_time(row.get(ts_col))
                    if t:
                        meta["timestamp_rows"] += 1
                        if symbol_ok and tf_ok:
                            start = t if start is None or t < start else start
                            end = t if end is None or t > end else end
                if bid_col and ask_col and is_numeric_text(row.get(bid_col)) and is_numeric_text(row.get(ask_col)):
                    meta["bidask_rows"] += 1
                if spread_col and is_numeric_text(row.get(spread_col)):
                    meta["numeric_spread_rows"] += 1
                if provider_col and len(provider_values) < 5:
                    pv = row.get(provider_col)
                    if pv and pv not in provider_values:
                        provider_values.append(pv)
            if start and end:
                meta["start_utc"] = start.isoformat().replace("+00:00", "Z")
                meta["end_utc"] = end.isoformat().replace("+00:00", "Z")
                meta["coverage_days"] = (end - start).total_seconds() / 86400.0
            meta["provider_values_limited"] = provider_values
    except Exception as e:
        meta["error"] = repr(e)
    return meta


def inspect_sqlite(path: Path, max_tables: int = 50) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "kind": "sqlite", "path": str(path), "error": None, "tables": [],
        "has_bidask_table": False, "has_numeric_spread_table": False,
        "tables_with_execution_columns": [],
    }
    try:
        con = sqlite3.connect(str(path))
        cur = con.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        for tbl in tables[:max_tables]:
            try:
                cols = [r[1] for r in cur.execute(f"PRAGMA table_info({tbl})").fetchall()]
                ncols = {norm_col(c) for c in cols}
                row_count = None
                try:
                    row_count = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                except Exception:
                    pass
                has_bidask = bool(ncols & BID_ALIASES) and bool(ncols & ASK_ALIASES)
                has_spread = bool((ncols & SPREAD_ALIASES) - BOOLEAN_SPREAD_METADATA)
                table_meta = {"table": tbl, "columns": cols, "row_count": row_count, "has_bidask_cols": has_bidask, "has_numeric_spread_cols": has_spread}
                meta["tables"].append(table_meta)
                if has_bidask:
                    meta["has_bidask_table"] = True
                    meta["tables_with_execution_columns"].append(table_meta)
                if has_spread:
                    meta["has_numeric_spread_table"] = True
                    if table_meta not in meta["tables_with_execution_columns"]:
                        meta["tables_with_execution_columns"].append(table_meta)
            except Exception as e:
                meta["tables"].append({"table": tbl, "error": repr(e)})
        con.close()
    except Exception as e:
        meta["error"] = repr(e)
    return meta


def compute_decision(csv_metas: List[Dict[str, Any]], sqlite_metas: List[Dict[str, Any]], news_files: List[Path], mt5_files: List[Path], min_rows: int, min_days: float) -> Dict[str, Any]:
    best_ref = None
    for m in csv_metas:
        if m.get("xau_m5_like_rows", 0) >= min_rows and m.get("coverage_days", 0.0) >= min_days:
            if best_ref is None or m.get("xau_m5_like_rows", 0) > best_ref.get("xau_m5_like_rows", 0):
                best_ref = m
    csv_broker_ready = []
    for m in csv_metas:
        enough_time = m.get("coverage_days", 0.0) >= min_days if m.get("coverage_days") else False
        if (m.get("bidask_rows", 0) >= min_rows or m.get("numeric_spread_rows", 0) >= min_rows) and enough_time:
            csv_broker_ready.append(m)
    sqlite_execution_candidates = [m for m in sqlite_metas if m.get("has_bidask_table") or m.get("has_numeric_spread_table")]
    broker_real_ready = bool(csv_broker_ready)  # SQLite needs later row-level audit; schema alone is not enough.
    broker_schema_candidate = bool(sqlite_execution_candidates or mt5_files)
    news_event_candidate = bool(news_files)
    reference_ready = bool(best_ref)

    if broker_real_ready and reference_ready:
        status = "EXECUTION_REALISM_READY_FOR_STAGE48C_THESIS_DESIGN_NO_PROMOTION"
        next_allowed = "STAGE48C_BROKER_REAL_STRUCTURAL_THESIS_DESIGN"
        stop_reason = None
    elif reference_ready and broker_schema_candidate:
        status = "BROKER_SCHEMA_CANDIDATE_NEEDS_ROW_LEVEL_SPREAD_AUDIT_NO_PROMOTION"
        next_allowed = "STAGE48C_BROKER_SPREAD_ROW_LEVEL_AUDIT"
        stop_reason = "broker_schema_or_files_exist_but_no_confirmed_bidask_or_numeric_spread_coverage"
    elif reference_ready:
        status = "REFERENCE_ONLY_NO_BROKER_REALISM_STOP_NO_PROMOTION"
        next_allowed = "STAGE48C_MT5_OR_BROKER_FEED_COLLECTION_DESIGN_OR_PAUSE"
        stop_reason = "reference_ohlc_ready_but_no_broker_real_bidask_or_spread_history"
    else:
        status = "INSUFFICIENT_REFERENCE_AND_BROKER_DATA_STOP_NO_PROMOTION"
        next_allowed = "DATA_COLLECTION_OR_PROJECT_PAUSE"
        stop_reason = "no_sufficient_reference_history_and_no_broker_real_execution_history"

    return {
        "status": status,
        "next_allowed_step": next_allowed,
        "stop_reason": stop_reason,
        "reference_ohlc_ready": reference_ready,
        "best_reference_csv": str(best_ref["path"]) if best_ref else None,
        "best_reference_rows": best_ref.get("xau_m5_like_rows") if best_ref else 0,
        "best_reference_coverage_days": best_ref.get("coverage_days") if best_ref else 0.0,
        "broker_real_ready": broker_real_ready,
        "broker_ready_csv_files": [str(m["path"]) for m in csv_broker_ready],
        "broker_schema_candidate": broker_schema_candidate,
        "sqlite_execution_candidate_count": len(sqlite_execution_candidates),
        "mt5_like_file_count": len(mt5_files),
        "news_event_candidate": news_event_candidate,
        "news_like_file_count": len(news_files),
    }


def write_inventory(out_dir: Path, csv_metas: List[Dict[str, Any]], sqlite_metas: List[Dict[str, Any]], news_files: List[Path], mt5_files: List[Path]) -> str:
    p = out_dir / "stage48b_data_source_inventory.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "path", "rows_or_tables", "xau_m5_like_rows", "coverage_days", "bidask_rows", "numeric_spread_rows", "notes"])
        for m in csv_metas:
            w.writerow([
                "csv", m.get("path"), m.get("raw_rows"), m.get("xau_m5_like_rows"), f"{m.get('coverage_days',0.0):.6f}",
                m.get("bidask_rows"), m.get("numeric_spread_rows"), m.get("error") or "",
            ])
        for m in sqlite_metas:
            w.writerow([
                "sqlite", m.get("path"), len(m.get("tables", [])), "", "", "schema" if m.get("has_bidask_table") else "", "schema" if m.get("has_numeric_spread_table") else "", m.get("error") or "",
            ])
        for pth in news_files:
            w.writerow(["news_like", str(pth), "", "", "", "", "", "name_match"])
        for pth in mt5_files:
            w.writerow(["mt5_like", str(pth), "", "", "", "", "", "name_match"])
    return str(p)


def write_report(out_dir: Path, summary: Dict[str, Any]) -> str:
    p = out_dir / "stage48b_execution_realism_precheck_report.md"
    d = summary["decision"]
    lines = []
    lines.append("# Stage48B Execution Realism and Data Source Feasibility Precheck")
    lines.append("")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- next_allowed_step: `{summary['next_allowed_step']}`")
    lines.append(f"- promotion: `{summary['promotion']}`")
    lines.append(f"- EA: `{summary['EA']}`")
    lines.append(f"- paper_live: `{summary['paper_live']}`")
    lines.append(f"- live: `{summary['live']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- reference_ohlc_ready: `{d['reference_ohlc_ready']}`")
    lines.append(f"- best_reference_rows: `{d['best_reference_rows']}`")
    lines.append(f"- best_reference_coverage_days: `{d['best_reference_coverage_days']}`")
    lines.append(f"- best_reference_csv: `{d['best_reference_csv']}`")
    lines.append(f"- broker_real_ready: `{d['broker_real_ready']}`")
    lines.append(f"- broker_schema_candidate: `{d['broker_schema_candidate']}`")
    lines.append(f"- news_event_candidate: `{d['news_event_candidate']}`")
    if d.get("stop_reason"):
        lines.append(f"- stop_reason: `{d['stop_reason']}`")
    lines.append("")
    lines.append("## Inventory counts")
    lines.append("")
    lines.append(f"- csv_files_inspected: `{summary['csv_files_inspected']}`")
    lines.append(f"- sqlite_files_inspected: `{summary['sqlite_files_inspected']}`")
    lines.append(f"- news_like_file_count: `{d['news_like_file_count']}`")
    lines.append(f"- mt5_like_file_count: `{d['mt5_like_file_count']}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    if summary["status"] == "REFERENCE_ONLY_NO_BROKER_REALISM_STOP_NO_PROMOTION":
        lines.append("The repository has sufficient reference OHLC history, but no confirmed broker-real bid/ask or numeric spread history. A new candle-only trading scan is not recommended. The next useful step is MT5/broker-feed collection or a row-level spread audit if such data exists outside the current repository.")
    elif summary["status"] == "BROKER_SCHEMA_CANDIDATE_NEEDS_ROW_LEVEL_SPREAD_AUDIT_NO_PROMOTION":
        lines.append("The repository contains broker/MT5-like files or SQLite schema candidates, but this precheck did not confirm enough row-level bid/ask or numeric spread history. A focused row-level audit is allowed before any trading thesis design.")
    elif summary["status"] == "EXECUTION_REALISM_READY_FOR_STAGE48C_THESIS_DESIGN_NO_PROMOTION":
        lines.append("The repository appears to contain enough reference history and broker-real execution data to design a new structural thesis. This is not a promotion; it only allows Stage48C design.")
    else:
        lines.append("Neither sufficient reference history nor broker-real execution history was confirmed. Data collection or project pause is preferred over new scans.")
    lines.append("")
    lines.append("No EA, paper-live, live trading, or trading-signal promotion is allowed from this stage.")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def run_smoke(out_dir: Path) -> int:
    tmp = out_dir / "_stage48b_smoke_repo"
    data = tmp / "data" / "normalized"
    data.mkdir(parents=True, exist_ok=True)
    p = data / "normalized_twelvedata_XAU_USD_5min_smoke.csv"
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "open", "high", "low", "close", "symbol", "interval", "provider", "spread_available", "session_utc"])
        for i in range(6000):
            t = start + dt.timedelta(minutes=5*i)
            w.writerow([t.isoformat().replace("+00:00", "Z"), 2000+i*0.01, 2001+i*0.01, 1999+i*0.01, 2000.5+i*0.01, "XAU/USD", "5min", "smoke", "False", "london"])
    return main(["--root", str(tmp), "--out", str(out_dir / "smoke_out"), "--min-reference-rows", "5000", "--min-reference-days", "20"])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    ap.add_argument("--out", default="reports/stage48b", help="Output directory.")
    ap.add_argument("--min-reference-rows", type=int, default=5000)
    ap.add_argument("--min-reference-days", type=float, default=20.0)
    ap.add_argument("--min-broker-rows", type=int, default=5000)
    ap.add_argument("--min-broker-days", type=float, default=20.0)
    ap.add_argument("--smoke-test", action="store_true")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.smoke_test:
        return run_smoke(out_dir)

    repo_root = Path(args.root).expanduser().resolve()
    files = discover_files(repo_root)
    csv_metas = [inspect_csv(p) for p in files["csv"]]
    sqlite_metas = [inspect_sqlite(p) for p in files["sqlite"]]
    decision = compute_decision(csv_metas, sqlite_metas, files["news_like"], files["mt5_like"], args.min_reference_rows, args.min_reference_days)
    summary: Dict[str, Any] = {
        "stage": STAGE,
        "patch": PATCH,
        "status": decision["status"],
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": decision["next_allowed_step"],
        "root": str(repo_root),
        "min_reference_rows": args.min_reference_rows,
        "min_reference_days": args.min_reference_days,
        "min_broker_rows": args.min_broker_rows,
        "min_broker_days": args.min_broker_days,
        "csv_files_inspected": len(csv_metas),
        "sqlite_files_inspected": len(sqlite_metas),
        "decision": decision,
        "csv_metas_limited": csv_metas[:25],
        "sqlite_metas_limited": sqlite_metas[:10],
        "news_like_files_limited": [str(p) for p in files["news_like"][:50]],
        "mt5_like_files_limited": [str(p) for p in files["mt5_like"][:50]],
    }
    inventory_path = write_inventory(out_dir, csv_metas, sqlite_metas, files["news_like"], files["mt5_like"])
    summary["inventory_csv"] = inventory_path
    report_path = write_report(out_dir, summary)
    summary["report_md"] = report_path
    summary_path = out_dir / "stage48b_execution_realism_precheck_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "stage": STAGE,
        "status": summary["status"],
        "next_allowed_step": summary["next_allowed_step"],
        "reference_ohlc_ready": decision["reference_ohlc_ready"],
        "broker_real_ready": decision["broker_real_ready"],
        "broker_schema_candidate": decision["broker_schema_candidate"],
        "out": str(out_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
