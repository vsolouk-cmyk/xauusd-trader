#!/usr/bin/env python3
"""
Stage48C Broker Spread Row-Level Audit

Purpose:
  Audit row-level numeric spread coverage in broker/schema-candidate SQLite sources
  before any new trading thesis or signal scan is designed.

No trading signal generation. No promotion.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple


STAGE = "Stage48C_BROKER_SPREAD_ROW_LEVEL_AUDIT"
PATCH = "Stage48C_SQLITE_ROW_LEVEL_SPREAD_AUDIT_NO_TRADING_SCAN"


TIME_ALIASES = [
    "utc_time", "time_utc", "timestamp", "ts", "bar_ts_utc", "event_ts_utc",
    "source_time", "date_time", "datetime"
]
SYMBOL_ALIASES = ["symbol", "instrument", "ticker", "pair"]
TIMEFRAME_ALIASES = ["timeframe", "interval", "tf"]
SESSION_ALIASES = ["session_utc", "session", "session_name"]
SPREAD_ALIASES = ["spread", "spread_close", "spread_points", "spread_pips", "spread_raw"]
OHLC_REQUIRED = ["open", "high", "low", "close"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm_col(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")


def pick_col(columns: Sequence[str], aliases: Sequence[str]) -> Optional[str]:
    norm_to_orig = {norm_col(c): c for c in columns}
    for a in aliases:
        if norm_col(a) in norm_to_orig:
            return norm_to_orig[norm_col(a)]
    return None


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Handle common SQLite/text UTC formats.
    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s
    try:
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.lower() in {"nan", "none", "null", "false", "true"}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    return x


def sample_quantiles(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {k: None for k in ["min", "p01", "p05", "p10", "p25", "median", "p75", "p90", "p95", "p99", "max", "mean"]}
    xs = sorted(values)
    n = len(xs)
    def q(p: float) -> float:
        if n == 1:
            return xs[0]
        idx = p * (n - 1)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            return xs[lo]
        return xs[lo] * (hi - idx) + xs[hi] * (idx - lo)
    return {
        "min": xs[0],
        "p01": q(0.01),
        "p05": q(0.05),
        "p10": q(0.10),
        "p25": q(0.25),
        "median": q(0.50),
        "p75": q(0.75),
        "p90": q(0.90),
        "p95": q(0.95),
        "p99": q(0.99),
        "max": xs[-1],
        "mean": sum(xs) / n,
    }


def infer_spread_units(median_spread: Optional[float], median_close: Optional[float]) -> str:
    if median_spread is None:
        return "UNKNOWN_NO_NUMERIC_SPREAD"
    # XAUUSD broker "spread" often stores points rather than raw price difference.
    # This is deliberately descriptive, not a conversion guarantee.
    if median_spread <= 0:
        return "INVALID_NONPOSITIVE"
    if median_close and median_close > 100:
        if median_spread < 0.5:
            return "PRICE_UNITS_OR_TIGHT_RAW_PRICE_SPREAD"
        if median_spread < 50:
            return "BROKER_POINTS_OR_PRICE_CENTS_LIKELY"
        return "LARGE_POINTS_OR_UNNORMALIZED_SPREAD"
    return "UNKNOWN_SCALE"


def compute_coverage_days(min_ts: Optional[str], max_ts: Optional[str]) -> float:
    a = parse_ts(min_ts)
    b = parse_ts(max_ts)
    if not a or not b or b < a:
        return 0.0
    return (b - a).total_seconds() / 86400.0


def sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows if not str(r[0]).startswith("sqlite_")]


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [r[1] for r in rows]


def count_table(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0])
    except Exception:
        return -1


def distinct_limited(conn: sqlite3.Connection, table: str, col: Optional[str], limit: int = 12) -> List[str]:
    if not col:
        return []
    try:
        rows = conn.execute(
            f"SELECT {quote_ident(col)}, COUNT(*) c FROM {quote_ident(table)} "
            f"GROUP BY {quote_ident(col)} ORDER BY c DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [f"{r[0]}:{r[1]}" for r in rows]
    except Exception:
        return []


def build_where(symbol_col: Optional[str], timeframe_col: Optional[str], symbol_hint: str, timeframe_hint: str) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if symbol_col:
        # Keep broad enough for XAUUSD, XAU/USD, GOLD, etc.
        clauses.append(f"UPPER(CAST({quote_ident(symbol_col)} AS TEXT)) LIKE ?")
        params.append("%XAU%")
    if timeframe_col:
        tf = timeframe_hint.upper()
        candidates = {
            "M1": ["M1", "1MIN", "1M", "1"],
            "M5": ["M5", "5MIN", "5M", "5"],
            "M15": ["M15", "15MIN", "15M", "15"],
            "H1": ["H1", "1H", "1HOUR", "60MIN", "60"],
        }.get(tf, [tf])
        tf_clauses = []
        for c in candidates:
            tf_clauses.append(f"UPPER(REPLACE(CAST({quote_ident(timeframe_col)} AS TEXT), ' ', '')) = ?")
            params.append(c)
        clauses.append("(" + " OR ".join(tf_clauses) + ")")
    if clauses:
        return " WHERE " + " AND ".join(clauses), params
    return "", []


def audit_table(conn: sqlite3.Connection, db_path: str, table: str, args: argparse.Namespace) -> Dict[str, Any]:
    cols = table_columns(conn, table)
    row_count = count_table(conn, table)

    ts_col = pick_col(cols, TIME_ALIASES)
    symbol_col = pick_col(cols, SYMBOL_ALIASES)
    timeframe_col = pick_col(cols, TIMEFRAME_ALIASES)
    session_col = pick_col(cols, SESSION_ALIASES)
    spread_col = pick_col(cols, SPREAD_ALIASES)
    ohlc_map = {c: pick_col(cols, [c]) for c in OHLC_REQUIRED}

    has_ohlc = all(ohlc_map.values())
    has_numeric_spread_col = spread_col is not None
    candidate = bool(ts_col and has_ohlc and has_numeric_spread_col)

    meta: Dict[str, Any] = {
        "db_path": db_path,
        "table": table,
        "row_count": row_count,
        "columns": cols,
        "mapping": {
            "ts": ts_col, "symbol": symbol_col, "timeframe": timeframe_col, "session": session_col,
            "spread": spread_col, **ohlc_map
        },
        "has_ohlc": has_ohlc,
        "has_numeric_spread_col": has_numeric_spread_col,
        "row_level_candidate": candidate,
        "symbol_values_limited": distinct_limited(conn, table, symbol_col),
        "timeframe_values_limited": distinct_limited(conn, table, timeframe_col),
        "session_values_limited": distinct_limited(conn, table, session_col),
    }
    if not candidate:
        meta["status"] = "NOT_ROW_LEVEL_SPREAD_CANDIDATE"
        return meta

    where, params = build_where(symbol_col, timeframe_col, args.symbol, args.timeframe)
    qcols = [ts_col, "open", "high", "low", "close", spread_col]
    if session_col:
        qcols.append(session_col)
    select_cols = ", ".join(quote_ident(c) for c in qcols if c)
    sql = f"SELECT {select_cols} FROM {quote_ident(table)}{where} ORDER BY {quote_ident(ts_col)}"
    # Avoid loading millions if filter fails; sample but also count first.
    count_sql = f"SELECT COUNT(*) FROM {quote_ident(table)}{where}"
    try:
        filtered_rows = int(conn.execute(count_sql, params).fetchone()[0])
    except Exception as e:
        meta["status"] = "COUNT_FILTER_FAILED"
        meta["error"] = repr(e)
        return meta

    # Compute min/max after filter.
    try:
        mm = conn.execute(
            f"SELECT MIN({quote_ident(ts_col)}), MAX({quote_ident(ts_col)}) FROM {quote_ident(table)}{where}",
            params,
        ).fetchone()
        start_raw, end_raw = mm[0], mm[1]
    except Exception:
        start_raw = end_raw = None

    limit_clause = ""
    query_params = params
    if filtered_rows > args.max_rows_scan:
        # Uniform exact sampling is hard in sqlite without random overhead.
        # Use full ordered head for metadata and report that scan was capped.
        limit_clause = f" LIMIT {int(args.max_rows_scan)}"
    try:
        rows = conn.execute(sql + limit_clause, query_params).fetchall()
    except Exception as e:
        meta["status"] = "ROW_SCAN_FAILED"
        meta["error"] = repr(e)
        return meta

    spreads: List[float] = []
    closes: List[float] = []
    non_null_spread_rows = 0
    positive_spread_rows = 0
    zero_spread_rows = 0
    negative_spread_rows = 0
    bad_spread_rows = 0
    parsed_ts_rows = 0
    first_bad_spread: Optional[Any] = None
    session_counts: Dict[str, int] = {}
    session_spreads: Dict[str, List[float]] = {}
    for r in rows:
        # qcols order: ts, open, high, low, close, spread, [session]
        ts = parse_ts(r[0])
        if ts:
            parsed_ts_rows += 1
        close = to_float(r[4])
        if close is not None:
            closes.append(close)
        sp = to_float(r[5])
        if sp is None:
            if r[5] is not None and str(r[5]).strip() != "" and first_bad_spread is None:
                first_bad_spread = r[5]
            bad_spread_rows += 1
        else:
            non_null_spread_rows += 1
            spreads.append(sp)
            if sp > 0:
                positive_spread_rows += 1
            elif sp == 0:
                zero_spread_rows += 1
            else:
                negative_spread_rows += 1
        if session_col and len(r) > 6:
            sess = str(r[6] or "UNKNOWN")
            session_counts[sess] = session_counts.get(sess, 0) + 1
            if sp is not None:
                session_spreads.setdefault(sess, []).append(sp)

    q = sample_quantiles(spreads)
    cq = sample_quantiles(closes)
    session_summary = {}
    for sess, vals in session_spreads.items():
        sq = sample_quantiles(vals)
        session_summary[sess] = {
            "rows": session_counts.get(sess, 0),
            "numeric_spread_rows": len(vals),
            "median_spread": sq["median"],
            "p90_spread": sq["p90"],
            "p95_spread": sq["p95"],
        }

    numeric_coverage_pct = (non_null_spread_rows / len(rows) * 100.0) if rows else 0.0
    coverage_days = compute_coverage_days(str(start_raw) if start_raw is not None else None, str(end_raw) if end_raw is not None else None)
    readiness = (
        filtered_rows >= args.min_rows and
        coverage_days >= args.min_days and
        numeric_coverage_pct >= args.min_numeric_spread_coverage_pct and
        positive_spread_rows > 0 and
        q["median"] is not None and
        q["median"] > 0
    )
    meta.update({
        "status": "ROW_LEVEL_AUDIT_COMPLETE",
        "filtered_rows": filtered_rows,
        "rows_scanned": len(rows),
        "scan_capped": filtered_rows > args.max_rows_scan,
        "start_raw": start_raw,
        "end_raw": end_raw,
        "coverage_days": coverage_days,
        "parsed_ts_rows": parsed_ts_rows,
        "numeric_spread_rows": non_null_spread_rows,
        "numeric_spread_coverage_pct_scanned": numeric_coverage_pct,
        "positive_spread_rows": positive_spread_rows,
        "zero_spread_rows": zero_spread_rows,
        "negative_spread_rows": negative_spread_rows,
        "bad_spread_rows": bad_spread_rows,
        "first_bad_spread_limited": str(first_bad_spread)[:120] if first_bad_spread is not None else None,
        "spread_distribution": q,
        "close_distribution": cq,
        "inferred_spread_units": infer_spread_units(q["median"], cq["median"]),
        "session_spread_summary": session_summary,
        "broker_spread_row_level_ready": readiness,
        "ready_failure_reasons": [],
    })
    if filtered_rows < args.min_rows:
        meta["ready_failure_reasons"].append(f"filtered_rows_lt_min_rows_{args.min_rows}")
    if coverage_days < args.min_days:
        meta["ready_failure_reasons"].append(f"coverage_days_lt_min_days_{args.min_days}")
    if numeric_coverage_pct < args.min_numeric_spread_coverage_pct:
        meta["ready_failure_reasons"].append(f"numeric_spread_coverage_pct_lt_{args.min_numeric_spread_coverage_pct}")
    if not positive_spread_rows:
        meta["ready_failure_reasons"].append("no_positive_spread_rows")
    if q["median"] is None or q["median"] <= 0:
        meta["ready_failure_reasons"].append("nonpositive_or_missing_median_spread")
    return meta


def discover_sqlite_paths(root: Path) -> List[Path]:
    candidates = [
        root / "data/local/xauusd_local_store.sqlite",
        root / "data/store/xauusd.sqlite",
    ]
    out: List[Path] = []
    for p in candidates:
        if p.exists() and p.is_file():
            out.append(p)
    return out


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "db_path", "table", "row_count", "filtered_rows", "coverage_days", "numeric_spread_rows",
        "numeric_spread_coverage_pct_scanned", "median_spread", "p90_spread", "p95_spread",
        "inferred_spread_units", "broker_spread_row_level_ready", "ready_failure_reasons"
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            sd = r.get("spread_distribution") or {}
            w.writerow({
                "db_path": r.get("db_path"),
                "table": r.get("table"),
                "row_count": r.get("row_count"),
                "filtered_rows": r.get("filtered_rows"),
                "coverage_days": r.get("coverage_days"),
                "numeric_spread_rows": r.get("numeric_spread_rows"),
                "numeric_spread_coverage_pct_scanned": r.get("numeric_spread_coverage_pct_scanned"),
                "median_spread": sd.get("median"),
                "p90_spread": sd.get("p90"),
                "p95_spread": sd.get("p95"),
                "inferred_spread_units": r.get("inferred_spread_units"),
                "broker_spread_row_level_ready": r.get("broker_spread_row_level_ready"),
                "ready_failure_reasons": ";".join(r.get("ready_failure_reasons") or []),
            })


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    best = summary.get("best_candidate") or {}
    lines = [
        "# Stage48C Broker Spread Row-Level Audit",
        "",
        f"- status: `{summary.get('status')}`",
        f"- next_allowed_step: `{summary.get('next_allowed_step')}`",
        f"- promotion: `{summary.get('promotion')}`",
        f"- EA: `{summary.get('EA')}`",
        f"- paper_live: `{summary.get('paper_live')}`",
        f"- live: `{summary.get('live')}`",
        "",
        "## Decision",
        "",
        f"- sqlite_files_audited: `{summary.get('sqlite_files_audited')}`",
        f"- row_level_candidates: `{summary.get('row_level_candidate_count')}`",
        f"- broker_spread_row_level_ready: `{summary.get('broker_spread_row_level_ready')}`",
        f"- stop_reason: `{summary.get('stop_reason')}`",
        "",
    ]
    if best:
        sd = best.get("spread_distribution") or {}
        lines += [
            "## Best candidate",
            "",
            f"- db_path: `{best.get('db_path')}`",
            f"- table: `{best.get('table')}`",
            f"- filtered_rows: `{best.get('filtered_rows')}`",
            f"- coverage_days: `{best.get('coverage_days')}`",
            f"- numeric_spread_rows: `{best.get('numeric_spread_rows')}`",
            f"- numeric_spread_coverage_pct_scanned: `{best.get('numeric_spread_coverage_pct_scanned')}`",
            f"- median_spread: `{sd.get('median')}`",
            f"- p90_spread: `{sd.get('p90')}`",
            f"- p95_spread: `{sd.get('p95')}`",
            f"- inferred_spread_units: `{best.get('inferred_spread_units')}`",
            "",
        ]
    lines += [
        "## Interpretation",
        "",
        "This stage only audits whether row-level broker/execution spread history is usable. It does not generate signals, does not tune a thesis, and does not allow EA, paper-live, or live promotion.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_smoke(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    db = out_dir / "_smoke_stage48c.sqlite"
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    try:
        conn.execute("""
        CREATE TABLE bars (
            source TEXT,
            symbol TEXT,
            timeframe TEXT,
            utc_time TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            spread REAL,
            tick_volume REAL
        )
        """)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = []
        for i in range(6000):
            ts = start.timestamp() + i * 300
            dt = datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")
            px = 2000 + math.sin(i / 100) * 10
            sp = 12 + (i % 20) * 0.1
            rows.append(("smoke", "XAUUSD", "M5", dt, px, px+1, px-1, px+0.2, sp, 0))
        conn.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
    finally:
        conn.close()
    args = argparse.Namespace(
        root=str(out_dir), db=str(db), out=str(out_dir), symbol="XAU", timeframe="M5",
        min_rows=5000, min_days=20.0, min_numeric_spread_coverage_pct=80.0,
        max_rows_scan=200000, smoke_test=False
    )
    return main_with_args(args)


def main_with_args(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    sqlite_paths = [Path(args.db).resolve()] if args.db else discover_sqlite_paths(root)
    table_audits: List[Dict[str, Any]] = []
    sqlite_file_metas: List[Dict[str, Any]] = []

    for db_path in sqlite_paths:
        db_meta = {"path": str(db_path), "error": None, "tables": []}
        if not db_path.exists():
            db_meta["error"] = "DB_NOT_FOUND"
            sqlite_file_metas.append(db_meta)
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                for table in sqlite_tables(conn):
                    cols = table_columns(conn, table)
                    tmeta_base = {
                        "table": table,
                        "columns": cols,
                        "row_count": count_table(conn, table),
                        "has_numeric_spread_col": pick_col(cols, SPREAD_ALIASES) is not None,
                        "has_ohlc": all(pick_col(cols, [c]) for c in OHLC_REQUIRED),
                        "has_ts": pick_col(cols, TIME_ALIASES) is not None,
                    }
                    db_meta["tables"].append(tmeta_base)
                    # Audit only tables that could plausibly represent row-level bars with spread.
                    if tmeta_base["has_numeric_spread_col"] and tmeta_base["has_ohlc"] and tmeta_base["has_ts"]:
                        table_audits.append(audit_table(conn, str(db_path), table, args))
            finally:
                conn.close()
        except Exception as e:
            db_meta["error"] = repr(e)
        sqlite_file_metas.append(db_meta)

    ready_candidates = [t for t in table_audits if t.get("broker_spread_row_level_ready")]
    row_level_candidate_count = len([t for t in table_audits if t.get("row_level_candidate")])

    def best_key(t: Dict[str, Any]) -> Tuple[int, float, float]:
        return (
            int(t.get("filtered_rows") or 0),
            float(t.get("coverage_days") or 0.0),
            float((t.get("spread_distribution") or {}).get("median") or 0.0),
        )
    best_candidate = max(table_audits, key=best_key) if table_audits else None

    if ready_candidates:
        status = "BROKER_SPREAD_ROW_LEVEL_READY_NO_PROMOTION"
        next_allowed = "STAGE48D_BROKER_REALISM_DECISION_MEMO"
        stop_reason = None
        broker_ready = True
    elif row_level_candidate_count:
        status = "BROKER_SPREAD_ROW_LEVEL_INSUFFICIENT_NO_PROMOTION"
        next_allowed = "BROKER_SPREAD_COLLECTOR_OR_MT5_EXPORT_DESIGN"
        stop_reason = "row_level_spread_schema_exists_but_coverage_or_quality_threshold_failed"
        broker_ready = False
    else:
        status = "NO_ROW_LEVEL_BROKER_SPREAD_TABLE_STOP_NO_PROMOTION"
        next_allowed = "BROKER_SPREAD_COLLECTOR_OR_MT5_EXPORT_DESIGN"
        stop_reason = "no_sqlite_table_with_ts_ohlc_numeric_spread"
        broker_ready = False

    summary = {
        "stage": STAGE,
        "patch": PATCH,
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": next_allowed,
        "root": str(root),
        "min_rows": args.min_rows,
        "min_days": args.min_days,
        "min_numeric_spread_coverage_pct": args.min_numeric_spread_coverage_pct,
        "sqlite_files_audited": len(sqlite_paths),
        "row_level_candidate_count": row_level_candidate_count,
        "broker_spread_row_level_ready": broker_ready,
        "stop_reason": stop_reason,
        "best_candidate": best_candidate,
        "table_audits_limited": table_audits[:20],
        "sqlite_file_metas_limited": sqlite_file_metas[:5],
        "generated_utc": utc_now(),
    }

    summary_path = out / "stage48c_broker_spread_row_level_audit_summary.json"
    report_path = out / "stage48c_broker_spread_row_level_audit_report.md"
    inventory_path = out / "stage48c_broker_spread_row_level_audit_inventory.csv"

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_report(report_path, summary)
    write_csv(inventory_path, table_audits)

    print(json.dumps({
        "stage": STAGE,
        "status": status,
        "broker_spread_row_level_ready": broker_ready,
        "row_level_candidate_count": row_level_candidate_count,
        "best_table": best_candidate.get("table") if best_candidate else None,
        "out": str(out),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--db", default=None, help="Optional explicit SQLite path.")
    p.add_argument("--out", default="reports/stage48c")
    p.add_argument("--symbol", default="XAU")
    p.add_argument("--timeframe", default="M5")
    p.add_argument("--min-rows", type=int, default=5000)
    p.add_argument("--min-days", type=float, default=20.0)
    p.add_argument("--min-numeric-spread-coverage-pct", type=float, default=80.0)
    p.add_argument("--max-rows-scan", type=int, default=250000)
    p.add_argument("--smoke-test", action="store_true")
    args = p.parse_args()
    if args.smoke_test:
        return run_smoke(Path(args.out))
    return main_with_args(args)


if __name__ == "__main__":
    raise SystemExit(main())
