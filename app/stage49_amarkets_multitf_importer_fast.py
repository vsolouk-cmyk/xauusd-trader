#!/usr/bin/env python3
"""
Stage49 AMarkets Multi-Timeframe Fast Persistent Importer.

Purpose:
- Import AMarkets/MT5 tab-separated XAUUSD exports for M1/M5/M15/M30/H1.
- Persist normalized bars in SQLite.
- Skip unchanged files and append only newly appended rows when safe.
- Avoid slow full CSV rewrites by default.

This is a data/import utility only. It does not generate trading signals.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

TIMEFRAMES = {
    "m1": "M1",
    "m5": "M5",
    "m15": "M15",
    "m30": "M30",
    "h1": "H1",
}
DEFAULT_FILENAMES = {
    "M1": "amarkets_xauusd_1m.csv",
    "M5": "amarkets_xauusd_5m.csv",
    "M15": "amarkets_xauusd_15m.csv",
    "M30": "amarkets_xauusd_30m.csv",
    "H1": "amarkets_xauusd_1h.csv",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def expand_path(p: str | Path) -> Path:
    return Path(os.path.expanduser(str(p))).resolve()


def norm_header(name: str) -> str:
    s = (name or "").strip().strip("\ufeff").strip()
    if s.startswith("<") and s.endswith(">"):
        s = s[1:-1]
    return s.strip().lower().replace(" ", "_")


def detect_delimiter(header_line: str) -> str:
    if "\t" in header_line:
        return "\t"
    if ";" in header_line and header_line.count(";") > header_line.count(","):
        return ";"
    return ","


def first_bytes_hash(path: Path, n: int = 4096) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(n))
    return h.hexdigest()


def parse_server_datetime(date_s: str, time_s: str, server_utc_offset_hours: float) -> Tuple[str, str]:
    date_s = str(date_s).strip()
    time_s = str(time_s).strip()
    # MT5 export example: 2022.05.02 + 01:00:00
    candidates = [
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M",
    ]
    raw = f"{date_s} {time_s}"
    parsed = None
    for fmt in candidates:
        try:
            parsed = dt.datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        # Last resort: ISO-like parse after replacing dots in date.
        try:
            parsed = dt.datetime.fromisoformat(raw.replace(".", "-"))
        except Exception as exc:
            raise ValueError(f"cannot parse server datetime: {raw!r}") from exc
    server_time = parsed.replace(microsecond=0).isoformat(sep=" ")
    utc_dt = parsed - dt.timedelta(hours=server_utc_offset_hours)
    time_utc = utc_dt.replace(tzinfo=dt.timezone.utc, microsecond=0).isoformat().replace("+00:00", "Z")
    return server_time, time_utc


def safe_float(x: object) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        v = float(s)
    except Exception:
        return None
    if not math.isfinite(v):
        return None
    return v


def safe_int_from_float(x: object) -> Optional[int]:
    v = safe_float(x)
    if v is None:
        return None
    return int(v)


def ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS amarkets_bars (
            broker TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            time_utc TEXT NOT NULL,
            server_time TEXT,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            tick_volume INTEGER,
            real_volume INTEGER,
            spread_points REAL,
            spread_price REAL,
            spread_cost_bps REAL,
            source_file TEXT,
            imported_utc TEXT NOT NULL,
            PRIMARY KEY (broker, symbol, timeframe, time_utc)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_amarkets_bars_tf_time ON amarkets_bars(timeframe, time_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_amarkets_bars_time ON amarkets_bars(time_utc)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS amarkets_import_manifest (
            timeframe TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            source_size INTEGER NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            byte_offset INTEGER NOT NULL,
            first_bytes_sha256 TEXT NOT NULL,
            header_line TEXT NOT NULL,
            raw_rows_seen INTEGER NOT NULL,
            accepted_rows_total INTEGER NOT NULL,
            last_time_utc TEXT,
            last_imported_utc TEXT NOT NULL,
            import_mode TEXT NOT NULL
        )
        """
    )
    conn.commit()


def get_manifest(conn: sqlite3.Connection, timeframe: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM amarkets_import_manifest WHERE timeframe=?", (timeframe,)).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM amarkets_import_manifest LIMIT 0").description]
    return dict(zip(cols, row))


def read_header(path: Path) -> Tuple[str, str, List[str], Dict[str, int], int, str]:
    with path.open("rb") as f:
        header_bytes = f.readline()
        header_offset = f.tell()
    header_line = header_bytes.decode("utf-8-sig", errors="replace").rstrip("\r\n")
    delimiter = detect_delimiter(header_line)
    raw_fields = header_line.split(delimiter)
    fields = [norm_header(x) for x in raw_fields]
    idx = {name: i for i, name in enumerate(fields)}
    return header_line, delimiter, fields, idx, header_offset, hashlib.sha256(header_bytes).hexdigest()


def require_columns(idx: Dict[str, int], names: Iterable[str], path: Path) -> None:
    missing = [n for n in names if n not in idx]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}; available={sorted(idx)}")


def parse_lines(
    path: Path,
    timeframe: str,
    broker: str,
    symbol: str,
    server_utc_offset_hours: float,
    point_size: float,
    start_byte: int,
    delimiter: str,
    idx: Dict[str, int],
    source_label: str,
    batch_size: int = 10000,
) -> Tuple[List[Tuple], dict]:
    require_columns(idx, ["date", "time", "open", "high", "low", "close", "spread"], path)
    imported_at = utc_now()
    rows: List[Tuple] = []
    stats = {
        "raw_rows": 0,
        "accepted_rows": 0,
        "parse_fail_rows": 0,
        "bad_ohlc_rows": 0,
        "bad_timestamp_rows": 0,
        "numeric_spread_rows": 0,
        "last_time_utc": None,
        "end_byte": start_byte,
    }
    with path.open("rb") as f:
        f.seek(start_byte)
        for line_b in f:
            stats["end_byte"] = f.tell()
            if not line_b.strip():
                continue
            stats["raw_rows"] += 1
            line = line_b.decode("utf-8-sig", errors="replace").rstrip("\r\n")
            parts = line.split(delimiter)
            try:
                max_idx = max(idx.values())
                if len(parts) <= max_idx:
                    raise ValueError("not enough columns")
                server_time, time_utc = parse_server_datetime(parts[idx["date"]], parts[idx["time"]], server_utc_offset_hours)
            except Exception:
                stats["bad_timestamp_rows"] += 1
                stats["parse_fail_rows"] += 1
                continue
            o = safe_float(parts[idx["open"]]); h = safe_float(parts[idx["high"]]); l = safe_float(parts[idx["low"]]); c = safe_float(parts[idx["close"]])
            if o is None or h is None or l is None or c is None or h < max(o, c, l) or l > min(o, c, h) or c <= 0:
                stats["bad_ohlc_rows"] += 1
                stats["parse_fail_rows"] += 1
                continue
            spread_points = safe_float(parts[idx["spread"]])
            spread_price = spread_points * point_size if spread_points is not None else None
            spread_cost_bps = (spread_price / c * 10000.0) if spread_price is not None and c else None
            if spread_points is not None:
                stats["numeric_spread_rows"] += 1
            tick_volume = safe_int_from_float(parts[idx["tickvol"]]) if "tickvol" in idx else None
            real_volume = safe_int_from_float(parts[idx["vol"]]) if "vol" in idx else None
            rows.append((
                broker, symbol, timeframe, time_utc, server_time,
                o, h, l, c, tick_volume, real_volume,
                spread_points, spread_price, spread_cost_bps, source_label, imported_at,
            ))
            stats["accepted_rows"] += 1
            stats["last_time_utc"] = time_utc
    return rows, stats


def insert_rows(conn: sqlite3.Connection, rows: List[Tuple]) -> int:
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT OR REPLACE INTO amarkets_bars (
            broker, symbol, timeframe, time_utc, server_time,
            open, high, low, close, tick_volume, real_volume,
            spread_points, spread_price, spread_cost_bps, source_file, imported_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def export_timeframe_csv(conn: sqlite3.Connection, out_dir: Path, timeframe: str) -> Optional[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"amarkets_xauusd_{timeframe.lower()}_normalized.csv"
    cur = conn.execute(
        """
        SELECT time_utc, server_time, symbol, timeframe, open, high, low, close,
               tick_volume, real_volume, spread_points, spread_price, spread_cost_bps, broker, source_file
        FROM amarkets_bars
        WHERE timeframe=?
        ORDER BY time_utc
        """,
        (timeframe,),
    )
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([d[0] for d in cur.description])
        for row in cur:
            w.writerow(row)
    return str(path)


def import_one(
    conn: sqlite3.Connection,
    path: Path,
    timeframe: str,
    broker: str,
    symbol: str,
    server_utc_offset_hours: float,
    point_size: float,
    force_rebuild: bool,
) -> dict:
    if not path.exists():
        return {"timeframe": timeframe, "path": str(path), "status": "MISSING", "changed": False}
    stat = path.stat()
    file_size = stat.st_size
    file_mtime_ns = stat.st_mtime_ns
    first_hash = first_bytes_hash(path)
    header_line, delimiter, fields, idx, header_offset, header_hash = read_header(path)
    manifest = get_manifest(conn, timeframe)
    mode = "full_refresh"
    start_byte = header_offset
    unchanged = False
    if manifest and not force_rebuild:
        if (
            manifest["source_path"] == str(path)
            and int(manifest["source_size"]) == file_size
            and int(manifest["source_mtime_ns"]) == file_mtime_ns
            and manifest["first_bytes_sha256"] == first_hash
        ):
            unchanged = True
        elif (
            manifest["source_path"] == str(path)
            and file_size >= int(manifest["byte_offset"])
            and manifest["first_bytes_sha256"] == first_hash
            and manifest["header_line"] == header_line
        ):
            mode = "append_only"
            start_byte = int(manifest["byte_offset"])
        else:
            mode = "full_refresh"
    if unchanged:
        rows_total = conn.execute("SELECT COUNT(*) FROM amarkets_bars WHERE timeframe=?", (timeframe,)).fetchone()[0]
        return {
            "timeframe": timeframe,
            "path": str(path),
            "status": "UNCHANGED_SKIPPED",
            "changed": False,
            "rows_in_db": rows_total,
            "file_size": file_size,
            "byte_offset": manifest["byte_offset"] if manifest else None,
        }
    if mode == "full_refresh":
        conn.execute("DELETE FROM amarkets_bars WHERE timeframe=?", (timeframe,))
        conn.commit()
    rows, stats = parse_lines(
        path=path,
        timeframe=timeframe,
        broker=broker,
        symbol=symbol,
        server_utc_offset_hours=server_utc_offset_hours,
        point_size=point_size,
        start_byte=start_byte,
        delimiter=delimiter,
        idx=idx,
        source_label=str(path),
    )
    inserted = insert_rows(conn, rows)
    rows_total = conn.execute("SELECT COUNT(*) FROM amarkets_bars WHERE timeframe=?", (timeframe,)).fetchone()[0]
    conn.execute(
        """
        INSERT OR REPLACE INTO amarkets_import_manifest (
            timeframe, source_path, source_size, source_mtime_ns, byte_offset,
            first_bytes_sha256, header_line, raw_rows_seen, accepted_rows_total,
            last_time_utc, last_imported_utc, import_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timeframe,
            str(path),
            file_size,
            file_mtime_ns,
            stats["end_byte"],
            first_hash,
            header_line,
            (manifest["raw_rows_seen"] if manifest and mode == "append_only" else 0) + stats["raw_rows"],
            rows_total,
            stats["last_time_utc"] or (manifest["last_time_utc"] if manifest else None),
            utc_now(),
            mode,
        ),
    )
    conn.commit()
    return {
        "timeframe": timeframe,
        "path": str(path),
        "status": "IMPORTED",
        "changed": True,
        "mode": mode,
        "delimiter": delimiter,
        "fieldnames": fields,
        "start_byte": start_byte,
        "end_byte": stats["end_byte"],
        "raw_rows_read_this_run": stats["raw_rows"],
        "accepted_rows_this_run": stats["accepted_rows"],
        "inserted_or_replaced_this_run": inserted,
        "rows_in_db": rows_total,
        "parse_fail_rows_this_run": stats["parse_fail_rows"],
        "bad_timestamp_rows_this_run": stats["bad_timestamp_rows"],
        "bad_ohlc_rows_this_run": stats["bad_ohlc_rows"],
        "numeric_spread_rows_this_run": stats["numeric_spread_rows"],
        "file_size": file_size,
    }


def build_report(summary: dict) -> str:
    lines = [
        "# Stage49 AMarkets Fast Persistent MultiTF Importer",
        "",
        f"- status: `{summary['status']}`",
        f"- changed_timeframes: `{summary['changed_timeframes']}`",
        f"- skipped_timeframes: `{summary['skipped_timeframes']}`",
        f"- db: `{summary['db_path']}`",
        "",
        "## Timeframes",
        "",
    ]
    for item in summary["imports"]:
        lines.append(f"- {item.get('timeframe')}: status=`{item.get('status')}` rows_in_db=`{item.get('rows_in_db')}` mode=`{item.get('mode','')}` path=`{item.get('path')}`")
    lines.extend([
        "",
        "## Notes",
        "",
        "This importer is persistent. Unchanged files are skipped. Safely appended files are imported from the previous byte offset. Full refresh is used when the file appears rewritten or incompatible with the previous manifest.",
        "",
        "No trading signal, promotion, EA, paper-live, or live action is authorized by this importer.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Fast persistent AMarkets multi-timeframe importer")
    ap.add_argument("--root", default=".")
    ap.add_argument("--input-dir", default="~/Downloads")
    ap.add_argument("--db", default="data/broker_normalized/amarkets_multitf.sqlite")
    ap.add_argument("--out", default="reports/stage49_broker_multitf")
    ap.add_argument("--broker", default="AMarkets")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--server-utc-offset-hours", type=float, default=3.0)
    ap.add_argument("--point-size", type=float, default=0.01)
    ap.add_argument("--timeframes", default="M1,M5,M15,M30,H1")
    ap.add_argument("--force-rebuild", action="store_true")
    ap.add_argument("--export-csv", choices=["never", "changed", "always"], default="never")
    args = ap.parse_args(argv)

    root = expand_path(args.root)
    input_dir = expand_path(args.input_dir)
    db_path = root / args.db
    out_dir = root / args.out
    db_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_out_dir = root / "data" / "broker_normalized" / "amarkets"

    conn = sqlite3.connect(str(db_path))
    ensure_db(conn)

    requested = [x.strip().upper() for x in args.timeframes.split(",") if x.strip()]
    imports = []
    exported = []
    for tf in requested:
        if tf not in DEFAULT_FILENAMES:
            imports.append({"timeframe": tf, "status": "UNKNOWN_TIMEFRAME", "changed": False})
            continue
        result = import_one(
            conn=conn,
            path=input_dir / DEFAULT_FILENAMES[tf],
            timeframe=tf,
            broker=args.broker,
            symbol=args.symbol,
            server_utc_offset_hours=args.server_utc_offset_hours,
            point_size=args.point_size,
            force_rebuild=args.force_rebuild,
        )
        imports.append(result)
        should_export = args.export_csv == "always" or (args.export_csv == "changed" and result.get("changed"))
        if should_export and result.get("status") != "MISSING":
            exported.append(export_timeframe_csv(conn, csv_out_dir, tf))
    conn.close()

    changed_count = sum(1 for x in imports if x.get("changed"))
    skipped_count = sum(1 for x in imports if x.get("status") == "UNCHANGED_SKIPPED")
    missing_count = sum(1 for x in imports if x.get("status") == "MISSING")
    status = "IMPORT_COMPLETE"
    if missing_count == len(imports):
        status = "NO_INPUT_FILES_FOUND"
    elif missing_count:
        status = "IMPORT_COMPLETE_WITH_MISSING_TIMEFRAMES"
    summary = {
        "stage": "Stage49_AMARKETS_FAST_PERSISTENT_MULTITF_IMPORTER",
        "patch": "Stage49B_FAST_PERSISTENT_IMPORTER_AND_HARD_AUDIT",
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "root": str(root),
        "input_dir": str(input_dir),
        "db_path": str(db_path),
        "server_utc_offset_hours": args.server_utc_offset_hours,
        "point_size": args.point_size,
        "changed_timeframes": changed_count,
        "skipped_timeframes": skipped_count,
        "missing_timeframes": missing_count,
        "export_csv_mode": args.export_csv,
        "exported_csvs": exported,
        "imports": imports,
        "generated_utc": utc_now(),
    }
    (out_dir / "stage49_fast_import_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "stage49_fast_import_report.md").write_text(build_report(summary), encoding="utf-8")
    with (out_dir / "stage49_fast_import_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["timeframe", "status", "mode", "changed", "rows_in_db", "raw_rows_read_this_run", "accepted_rows_this_run", "path"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for item in imports:
            w.writerow({k: item.get(k, "") for k in fieldnames})
    print(json.dumps({"stage": summary["stage"], "status": status, "changed_timeframes": changed_count, "skipped_timeframes": skipped_count, "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
