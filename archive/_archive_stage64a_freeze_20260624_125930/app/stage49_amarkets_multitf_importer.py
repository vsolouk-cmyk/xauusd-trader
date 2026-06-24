#!/usr/bin/env python3
"""
Stage49 AMarkets Multi-Timeframe Importer

Purpose:
  Normalize periodically-updated AMarkets MT5 exports for XAUUSD across
  M1, M5, M15, M30, H1 into reproducible CSV + SQLite artifacts.

This is a data import/audit utility only. It does not produce trading signals,
EA instructions, paper-live actions, or live orders.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

TIMEFRAMES = {
    "M1": {"minutes": 1, "aliases": ["m1", "1m", "1min"]},
    "M5": {"minutes": 5, "aliases": ["m5", "5m", "5min"]},
    "M15": {"minutes": 15, "aliases": ["m15", "15m", "15min"]},
    "M30": {"minutes": 30, "aliases": ["m30", "30m", "30min"]},
    "H1": {"minutes": 60, "aliases": ["h1", "1h", "60m", "60min"]},
}

DEFAULT_PATTERNS = {
    "M1": ["amarkets_xauusd_1m.csv", "amarkets_xauusd_m1.csv"],
    "M5": ["amarkets_xauusd_5m.csv", "amarkets_xauusd_m5.csv"],
    "M15": ["amarkets_xauusd_15m.csv", "amarkets_xauusd_m15.csv"],
    "M30": ["amarkets_xauusd_30m.csv", "amarkets_xauusd_m30.csv"],
    "H1": ["amarkets_xauusd_1h.csv", "amarkets_xauusd_h1.csv", "amarkets_xauusd_60m.csv"],
}

TS_ALIASES = ["time_utc", "timestamp", "datetime", "date_time", "time", "<TIME_UTC>"]
DATE_ALIASES = ["date", "<DATE>"]
TIME_ALIASES = ["time", "<TIME>"]
OPEN_ALIASES = ["open", "<OPEN>"]
HIGH_ALIASES = ["high", "<HIGH>"]
LOW_ALIASES = ["low", "<LOW>"]
CLOSE_ALIASES = ["close", "<CLOSE>"]
TICKVOL_ALIASES = ["tick_volume", "tickvol", "tick_vol", "<TICKVOL>"]
VOL_ALIASES = ["volume", "vol", "real_volume", "<VOL>"]
SPREAD_ALIASES = ["spread", "spread_points", "<SPREAD>"]
SYMBOL_ALIASES = ["symbol", "<SYMBOL>"]
TIMEFRAME_ALIASES = ["timeframe", "interval", "tf", "<TIMEFRAME>"]


def norm_name(s: str) -> str:
    return (s or "").strip().lower().replace("\ufeff", "")


def clean_header(s: str) -> str:
    return (s or "").strip().replace("\ufeff", "")


def find_col(fieldnames: Sequence[str], aliases: Sequence[str]) -> Optional[str]:
    by_norm = {norm_name(x): x for x in fieldnames}
    for a in aliases:
        n = norm_name(a)
        if n in by_norm:
            return by_norm[n]
    # Also support angle-bracket-insensitive matching.
    simplified = {norm_name(x).strip("<>"): x for x in fieldnames}
    for a in aliases:
        n = norm_name(a).strip("<>")
        if n in simplified:
            return simplified[n]
    return None


def detect_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    first = sample.splitlines()[0] if sample.splitlines() else ""
    if "\t" in first:
        return "\t"
    try:
        return csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"]).delimiter
    except csv.Error:
        return ","


def parse_float(value: object) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "false"}:
        return None
    try:
        v = float(s.replace(",", ""))
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v


def parse_intish(value: object) -> Optional[int]:
    v = parse_float(value)
    return None if v is None else int(round(v))


def parse_datetime_any(value: str) -> Optional[datetime]:
    s = (value or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y.%m.%d",
    ):
        try:
            dt = datetime.strptime(s2, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ImportMeta:
    timeframe: str
    input_path: str
    output_csv: str
    raw_rows: int = 0
    accepted_rows: int = 0
    duplicate_rows: int = 0
    parse_fail_rows: int = 0
    bad_timestamp_rows: int = 0
    bad_ohlc_rows: int = 0
    numeric_spread_rows: int = 0
    spread_coverage_pct: float = 0.0
    start_utc: Optional[str] = None
    end_utc: Optional[str] = None
    coverage_days: float = 0.0
    delimiter: str = ","
    sha256: str = ""
    fieldnames: List[str] = None  # type: ignore[assignment]
    mapping: Dict[str, Optional[str]] = None  # type: ignore[assignment]
    status: str = "NOT_RUN"
    error: Optional[str] = None


def discover_inputs(input_dir: Path) -> Dict[str, Path]:
    found: Dict[str, Path] = {}
    for tf, names in DEFAULT_PATTERNS.items():
        for name in names:
            p = input_dir / name
            if p.exists():
                found[tf] = p
                break
    return found


def resolve_inputs(args: argparse.Namespace) -> Dict[str, Path]:
    base = Path(args.input_dir).expanduser() if args.input_dir else Path("~/Downloads").expanduser()
    discovered = discover_inputs(base)
    explicit: Dict[str, Optional[str]] = {
        "M1": args.m1,
        "M5": args.m5,
        "M15": args.m15,
        "M30": args.m30,
        "H1": args.h1,
    }
    for tf, val in explicit.items():
        if val:
            discovered[tf] = Path(val).expanduser()
    return discovered


def normalize_file(
    *,
    timeframe: str,
    input_path: Path,
    output_csv: Path,
    db_path: Path,
    server_utc_offset_hours: float,
    point_size: float,
    broker: str,
    symbol: str,
) -> ImportMeta:
    meta = ImportMeta(timeframe=timeframe, input_path=str(input_path), output_csv=str(output_csv), fieldnames=[], mapping={})
    if not input_path.exists():
        meta.status = "MISSING_INPUT"
        meta.error = f"Input file does not exist: {input_path}"
        return meta

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    meta.sha256 = sha256_file(input_path)
    delimiter = detect_delimiter(input_path)
    meta.delimiter = delimiter

    seen_keys = set()
    rows: List[Dict[str, object]] = []

    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            if not reader.fieldnames:
                meta.status = "EMPTY_OR_NO_HEADER"
                return meta
            fieldnames = [clean_header(x) for x in reader.fieldnames]
            # DictReader keeps original names; normalize rows by cleaned header.
            meta.fieldnames = fieldnames
            date_col = find_col(fieldnames, DATE_ALIASES)
            time_col = find_col(fieldnames, TIME_ALIASES)
            ts_col = None if (date_col and time_col) else find_col(fieldnames, TS_ALIASES)
            open_col = find_col(fieldnames, OPEN_ALIASES)
            high_col = find_col(fieldnames, HIGH_ALIASES)
            low_col = find_col(fieldnames, LOW_ALIASES)
            close_col = find_col(fieldnames, CLOSE_ALIASES)
            tickvol_col = find_col(fieldnames, TICKVOL_ALIASES)
            vol_col = find_col(fieldnames, VOL_ALIASES)
            spread_col = find_col(fieldnames, SPREAD_ALIASES)
            symbol_col = find_col(fieldnames, SYMBOL_ALIASES)
            tf_col = find_col(fieldnames, TIMEFRAME_ALIASES)
            meta.mapping = {
                "date": date_col,
                "time": time_col,
                "ts": ts_col,
                "open": open_col,
                "high": high_col,
                "low": low_col,
                "close": close_col,
                "tick_volume": tickvol_col,
                "volume": vol_col,
                "spread": spread_col,
                "symbol": symbol_col,
                "timeframe": tf_col,
            }
            required = [open_col, high_col, low_col, close_col]
            if not ((date_col and time_col) or ts_col) or any(x is None for x in required):
                meta.status = "SCHEMA_UNSUPPORTED"
                meta.error = "Missing required date/time or OHLC columns"
                return meta

            for raw in reader:
                meta.raw_rows += 1
                # Clean keys so '<DATE>' can be accessed even if DictReader kept BOM/spaces.
                r = {clean_header(k): v for k, v in raw.items() if k is not None}
                if date_col and time_col:
                    server_dt = parse_datetime_any(f"{r.get(date_col, '')} {r.get(time_col, '')}")
                else:
                    server_dt = parse_datetime_any(str(r.get(ts_col or "", "")))
                if server_dt is None:
                    meta.bad_timestamp_rows += 1
                    continue
                # Treat MT5 export time as broker server time and convert to UTC.
                time_utc_dt = server_dt - timedelta(hours=server_utc_offset_hours)
                time_utc_dt = time_utc_dt.astimezone(timezone.utc)
                time_utc = time_utc_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                server_time = server_dt.replace(tzinfo=None).isoformat(sep=" ")

                o = parse_float(r.get(open_col or ""))
                h = parse_float(r.get(high_col or ""))
                l = parse_float(r.get(low_col or ""))
                c = parse_float(r.get(close_col or ""))
                if o is None or h is None or l is None or c is None or h < max(o, c, l) or l > min(o, c, h):
                    meta.bad_ohlc_rows += 1
                    continue
                spread_points = parse_float(r.get(spread_col or "")) if spread_col else None
                if spread_points is not None:
                    meta.numeric_spread_rows += 1
                tick_volume = parse_intish(r.get(tickvol_col or "")) if tickvol_col else None
                volume = parse_intish(r.get(vol_col or "")) if vol_col else None
                sym = str(r.get(symbol_col, symbol)).strip() if symbol_col else symbol
                tf_val = str(r.get(tf_col, timeframe)).strip() if tf_col else timeframe

                key = (broker, sym, timeframe, time_utc)
                if key in seen_keys:
                    meta.duplicate_rows += 1
                    continue
                seen_keys.add(key)
                spread_price = None if spread_points is None else spread_points * point_size
                spread_cost_bps = None if spread_price is None or c == 0 else (spread_price / c) * 10000.0
                rows.append({
                    "time_utc": time_utc,
                    "server_time": server_time,
                    "broker": broker,
                    "symbol": sym,
                    "timeframe": timeframe,
                    "source_timeframe": tf_val,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "tick_volume": tick_volume,
                    "real_volume": volume,
                    "spread_points": spread_points,
                    "point_size": point_size,
                    "spread_price": spread_price,
                    "spread_cost_bps": spread_cost_bps,
                    "source_file": str(input_path),
                    "imported_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                })
    except Exception as exc:  # pragma: no cover - defensive top-level ingest failure reporting
        meta.status = "READ_ERROR"
        meta.error = repr(exc)
        return meta

    rows.sort(key=lambda x: str(x["time_utc"]))
    meta.accepted_rows = len(rows)
    if rows:
        meta.start_utc = str(rows[0]["time_utc"])
        meta.end_utc = str(rows[-1]["time_utc"])
        dt0 = parse_datetime_any(meta.start_utc)
        dt1 = parse_datetime_any(meta.end_utc)
        if dt0 and dt1:
            meta.coverage_days = (dt1 - dt0).total_seconds() / 86400.0
    meta.spread_coverage_pct = round((meta.numeric_spread_rows / meta.accepted_rows) * 100.0, 6) if meta.accepted_rows else 0.0

    columns = [
        "time_utc", "server_time", "broker", "symbol", "timeframe", "source_timeframe",
        "open", "high", "low", "close", "tick_volume", "real_volume",
        "spread_points", "point_size", "spread_price", "spread_cost_bps", "source_file", "imported_utc",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS amarkets_bars (
                time_utc TEXT NOT NULL,
                server_time TEXT,
                broker TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                source_timeframe TEXT,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                tick_volume INTEGER,
                real_volume INTEGER,
                spread_points REAL,
                point_size REAL,
                spread_price REAL,
                spread_cost_bps REAL,
                source_file TEXT,
                imported_utc TEXT,
                PRIMARY KEY (broker, symbol, timeframe, time_utc)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS amarkets_import_runs (
                run_id TEXT PRIMARY KEY,
                timeframe TEXT,
                input_path TEXT,
                output_csv TEXT,
                sha256 TEXT,
                raw_rows INTEGER,
                accepted_rows INTEGER,
                duplicate_rows INTEGER,
                parse_fail_rows INTEGER,
                bad_timestamp_rows INTEGER,
                bad_ohlc_rows INTEGER,
                numeric_spread_rows INTEGER,
                spread_coverage_pct REAL,
                start_utc TEXT,
                end_utc TEXT,
                coverage_days REAL,
                status TEXT,
                error TEXT,
                created_utc TEXT
            )
            """
        )
        if rows:
            conn.executemany(
                """
                INSERT OR REPLACE INTO amarkets_bars (
                    time_utc, server_time, broker, symbol, timeframe, source_timeframe,
                    open, high, low, close, tick_volume, real_volume,
                    spread_points, point_size, spread_price, spread_cost_bps, source_file, imported_utc
                ) VALUES (
                    :time_utc, :server_time, :broker, :symbol, :timeframe, :source_timeframe,
                    :open, :high, :low, :close, :tick_volume, :real_volume,
                    :spread_points, :point_size, :spread_price, :spread_cost_bps, :source_file, :imported_utc
                )
                """,
                rows,
            )
        run_id = hashlib.sha256(f"{timeframe}|{input_path}|{meta.sha256}|{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:24]
        conn.execute(
            """
            INSERT OR REPLACE INTO amarkets_import_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                timeframe,
                str(input_path),
                str(output_csv),
                meta.sha256,
                meta.raw_rows,
                meta.accepted_rows,
                meta.duplicate_rows,
                meta.parse_fail_rows,
                meta.bad_timestamp_rows,
                meta.bad_ohlc_rows,
                meta.numeric_spread_rows,
                meta.spread_coverage_pct,
                meta.start_utc,
                meta.end_utc,
                meta.coverage_days,
                "IMPORTED" if meta.accepted_rows else "NO_ACCEPTED_ROWS",
                meta.error,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    meta.status = "IMPORTED" if meta.accepted_rows else "NO_ACCEPTED_ROWS"
    return meta


def write_report(out_dir: Path, metas: List[ImportMeta], db_path: Path, normalized_dir: Path) -> Dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ready_tfs = [m.timeframe for m in metas if m.status == "IMPORTED" and m.accepted_rows > 0]
    failed = [m for m in metas if m.status != "IMPORTED"]
    summary = {
        "stage": "Stage49_AMARKETS_MULTITF_IMPORTER",
        "status": "AMARKETS_MULTITF_IMPORT_COMPLETE_NO_PROMOTION" if ready_tfs else "AMARKETS_MULTITF_IMPORT_FAILED_NO_PROMOTION",
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "ready_timeframes": ready_tfs,
        "missing_or_failed_timeframes": [m.timeframe for m in failed],
        "timeframe_count": len(ready_tfs),
        "sqlite_db": str(db_path),
        "normalized_dir": str(normalized_dir),
        "metas": [asdict(m) for m in metas],
    }
    (out_dir / "stage49_amarkets_multitf_import_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    with (out_dir / "stage49_amarkets_multitf_import_inventory.csv").open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "timeframe", "status", "input_path", "output_csv", "raw_rows", "accepted_rows",
            "numeric_spread_rows", "spread_coverage_pct", "start_utc", "end_utc", "coverage_days", "error",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in metas:
            writer.writerow({k: getattr(m, k) for k in fieldnames})

    lines = [
        "# Stage49 AMarkets Multi-Timeframe Importer",
        "",
        f"- status: `{summary['status']}`",
        "- promotion: `NO_GO`",
        "- EA: `NO_GO`",
        "- paper_live: `NO_GO`",
        "- live: `NO_GO`",
        "",
        "## Ready timeframes",
        "",
    ]
    for m in metas:
        lines.append(
            f"- `{m.timeframe}` status=`{m.status}` rows=`{m.accepted_rows}` coverage_days=`{m.coverage_days:.4f}` spread_coverage_pct=`{m.spread_coverage_pct:.4f}` input=`{m.input_path}`"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "This importer normalizes periodically-updated AMarkets MT5 exports into reproducible broker-real artifacts. It does not generate signals and does not authorize EA, paper-live, or live trading.",
    ]
    (out_dir / "stage49_amarkets_multitf_import_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize AMarkets XAUUSD MT5 multi-timeframe CSV exports.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--input-dir", default="~/Downloads", help="Directory containing AMarkets CSV exports")
    parser.add_argument("--m1")
    parser.add_argument("--m5")
    parser.add_argument("--m15")
    parser.add_argument("--m30")
    parser.add_argument("--h1")
    parser.add_argument("--broker", default="AMarkets")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--server-utc-offset-hours", type=float, default=3.0, help="MT5 server time offset relative to UTC; UTC=server_time-offset")
    parser.add_argument("--point-size", type=float, default=0.01)
    parser.add_argument("--out", default="reports/stage49_broker_multitf")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out_dir = root / args.out
    normalized_dir = root / "data" / "broker_normalized" / "amarkets"
    db_path = root / "data" / "broker_normalized" / "amarkets_multitf.sqlite"
    inputs = resolve_inputs(args)

    metas: List[ImportMeta] = []
    for tf in ["M1", "M5", "M15", "M30", "H1"]:
        if tf not in inputs:
            metas.append(ImportMeta(timeframe=tf, input_path="", output_csv="", status="MISSING_INPUT", error="No default or explicit path found", fieldnames=[], mapping={}))
            continue
        output_csv = normalized_dir / f"amarkets_xauusd_{tf.lower()}_normalized.csv"
        metas.append(
            normalize_file(
                timeframe=tf,
                input_path=inputs[tf].expanduser(),
                output_csv=output_csv,
                db_path=db_path,
                server_utc_offset_hours=args.server_utc_offset_hours,
                point_size=args.point_size,
                broker=args.broker,
                symbol=args.symbol,
            )
        )

    summary = write_report(out_dir, metas, db_path, normalized_dir)
    print(json.dumps({
        "stage": summary["stage"],
        "status": summary["status"],
        "ready_timeframes": summary["ready_timeframes"],
        "sqlite_db": summary["sqlite_db"],
        "out": str(out_dir),
    }, ensure_ascii=False))
    return 0 if summary["ready_timeframes"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
