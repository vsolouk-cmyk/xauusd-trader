#!/usr/bin/env python3
"""
Stage38D — Derive M5/M15 bars from M1 bars, then re-audit.

Purpose
-------
Create deterministic M5/M15 OHLCV rows inside the existing SQLite bars table
from the validated AMarkets XAUUSD M1 feed. This is a data-preparation step
only. It does not create signals, strategies, orders, paper-live, EA, or live
execution.

Design rules
------------
- Source rows: M1 bars for a single source/symbol.
- Output rows: M5 and/or M15 rows in the same bars table.
- Bucket timestamp: UTC floor of M1 utc_time to the target interval.
- Open: first M1 open in bucket.
- High: max M1 high in bucket.
- Low: min M1 low in bucket.
- Close: last M1 close in bucket.
- tick_volume / volume / real_volume: sum across M1 rows when present.
- spread: first non-null spread in the bucket. This approximates the spread at
  bucket open and avoids inflating costs by using max spread.
- Missing M1 minutes are not filled. Partial buckets are retained but audited.

Expected inherited bars schema from current repo:
source, symbol, timeframe, utc_time, open, high, low, close, tick_volume,
spread, real_volume, source_time, imported_utc, raw_json, volume, ingested_at

The script is schema-tolerant and will only populate columns that exist.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TIMESTAMP_CANDIDATES = [
    "utc_time",
    "ts_utc",
    "timestamp_utc",
    "datetime_utc",
    "bar_ts_utc",
    "time_utc",
    "open_time_utc",
    "bar_time_utc",
    "open_time",
    "source_time",
    "timestamp",
    "datetime",
    "time",
    "ts",
]

NUMERIC_PRICE_COLS = ["open", "high", "low", "close"]
VOLUME_COLS = ["tick_volume", "volume", "real_volume"]
OPTIONAL_DIRECT_COLS = ["spread"]
TIMEFRAME_M1_CANDIDATES = ["M1", "1M", "1MIN", "1MINUTE", "1MINUTES", "1m", "1min", "1minute"]


@dataclass
class ColumnInfo:
    name: str
    type: str
    notnull: int
    default: Any
    pk: int


@dataclass
class DeriveSummary:
    timeframe: str
    interval_minutes: int
    source_rows: int
    existing_before: int
    deleted_existing: int
    output_rows: int
    inserted_rows: int
    min_ts_utc: Optional[str]
    max_ts_utc: Optional[str]
    full_bucket_count: int
    partial_bucket_count: int
    min_m1_count_per_bucket: Optional[int]
    max_m1_count_per_bucket: Optional[int]
    avg_m1_count_per_bucket: Optional[float]
    status: str
    note: Optional[str]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Derive M5/M15 bars from validated M1 bars in SQLite.")
    p.add_argument("--db", default="data/local/xauusd_local_store.sqlite", help="SQLite DB path")
    p.add_argument("--bars-table", default="bars", help="Bars table name")
    p.add_argument("--source", default="amarkets_mt5", help="Source name")
    p.add_argument("--symbol", default="XAUUSD", help="Symbol")
    p.add_argument("--m1-timeframe", default="M1", help="Preferred M1 timeframe label; variants are auto-detected")
    p.add_argument("--target-timeframes", default="M5,M15", help="Comma-separated targets: M5,M15")
    p.add_argument("--reports-dir", default="data/reports/stage38d_derive_m5_m15_from_m1", help="Report directory")
    p.add_argument(
        "--mode",
        choices=["replace", "skip_existing", "fail_if_existing"],
        default="replace",
        help="How to handle existing target rows for source/symbol/timeframe",
    )
    p.add_argument("--batch-size", type=int, default=5000, help="SQLite insert batch size")
    return p.parse_args()


def qident(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe identifier: {name!r}")
    return '"' + name.replace('"', '""') + '"'


def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")
    return con


def get_columns(con: sqlite3.Connection, table: str) -> List[ColumnInfo]:
    rows = con.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    if not rows:
        raise RuntimeError(f"Table not found or has no columns: {table}")
    return [ColumnInfo(r[1], r[2], r[3], r[4], r[5]) for r in rows]


def column_names(cols: Sequence[ColumnInfo]) -> List[str]:
    return [c.name for c in cols]


def require_col(cols: Sequence[str], candidates: Sequence[str], label: str) -> str:
    lower_map = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    raise RuntimeError(f"Cannot detect {label}. Tried {candidates}. Existing columns: {cols}")


def parse_time_utc(value: Any) -> datetime:
    if value is None:
        raise ValueError("timestamp is null")
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if not s:
            raise ValueError("timestamp is empty")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def floor_bucket(dt: datetime, interval_minutes: int) -> datetime:
    dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    minute = (dt.minute // interval_minutes) * interval_minutes
    return dt.replace(minute=minute)


def parse_targets(raw: str) -> List[Tuple[str, int]]:
    targets: List[Tuple[str, int]] = []
    for part in raw.split(","):
        label = part.strip().upper()
        if not label:
            continue
        if label in {"M5", "5M", "5MIN"}:
            targets.append(("M5", 5))
        elif label in {"M15", "15M", "15MIN"}:
            targets.append(("M15", 15))
        else:
            raise ValueError(f"Unsupported target timeframe: {part!r}; supported: M5,M15")
    if not targets:
        raise ValueError("No valid target timeframes requested")
    # De-duplicate while preserving order.
    seen = set()
    out = []
    for tf, minutes in targets:
        if tf not in seen:
            seen.add(tf)
            out.append((tf, minutes))
    return out


def detect_m1_timeframe(con: sqlite3.Connection, table: str, source_col: str, symbol_col: str, timeframe_col: str, source: str, symbol: str, preferred: str) -> str:
    rows = con.execute(
        f"""
        SELECT DISTINCT {qident(timeframe_col)} AS tf
        FROM {qident(table)}
        WHERE {qident(source_col)} = ? AND {qident(symbol_col)} = ?
        """,
        (source, symbol),
    ).fetchall()
    existing = [str(r["tf"]) for r in rows if r["tf"] is not None]
    if not existing:
        raise RuntimeError(f"No bars found for source={source!r}, symbol={symbol!r}")
    by_upper = {x.upper(): x for x in existing}
    if preferred.upper() in by_upper:
        return by_upper[preferred.upper()]
    for cand in TIMEFRAME_M1_CANDIDATES:
        if cand.upper() in by_upper:
            return by_upper[cand.upper()]
    raise RuntimeError(f"Cannot detect M1 timeframe. Existing timeframes for {source}/{symbol}: {existing}")


def count_rows(con: sqlite3.Connection, table: str, source_col: str, symbol_col: str, timeframe_col: str, source: str, symbol: str, timeframe: str) -> int:
    return int(
        con.execute(
            f"""
            SELECT COUNT(*)
            FROM {qident(table)}
            WHERE {qident(source_col)} = ?
              AND {qident(symbol_col)} = ?
              AND {qident(timeframe_col)} = ?
            """,
            (source, symbol, timeframe),
        ).fetchone()[0]
    )


def build_insert_sql(table: str, cols: Sequence[str]) -> str:
    placeholders = ", ".join(["?"] * len(cols))
    col_sql = ", ".join(qident(c) for c in cols)
    return f"INSERT INTO {qident(table)} ({col_sql}) VALUES ({placeholders})"


def value_for_output_col(
    col: str,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    ts: str,
    bucket: Dict[str, Any],
    now_utc: str,
    derived_raw_json: str,
    source_col: str,
    symbol_col: str,
    timeframe_col: str,
    ts_col: str,
) -> Any:
    cl = col.lower()
    if col == source_col:
        return source
    if col == symbol_col:
        return symbol
    if col == timeframe_col:
        return timeframe
    if col == ts_col:
        return ts
    if cl == "open":
        return bucket["open"]
    if cl == "high":
        return bucket["high"]
    if cl == "low":
        return bucket["low"]
    if cl == "close":
        return bucket["close"]
    if cl == "tick_volume":
        return bucket.get("tick_volume_sum")
    if cl == "volume":
        return bucket.get("volume_sum")
    if cl == "real_volume":
        return bucket.get("real_volume_sum")
    if cl == "spread":
        return bucket.get("spread_first")
    if cl == "source_time":
        return ts
    if cl in {"imported_utc", "ingested_at", "created_at", "updated_at"}:
        return now_utc
    if cl == "raw_json":
        return derived_raw_json
    return None


def flush_insert_batch(con: sqlite3.Connection, insert_sql: str, rows: List[Tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    con.executemany(insert_sql, rows)
    n = len(rows)
    rows.clear()
    return n


def derive_one_timeframe(
    con: sqlite3.Connection,
    *,
    table: str,
    cols: Sequence[str],
    source_col: str,
    symbol_col: str,
    timeframe_col: str,
    ts_col: str,
    source: str,
    symbol: str,
    m1_timeframe: str,
    target_tf: str,
    interval_minutes: int,
    mode: str,
    batch_size: int,
) -> DeriveSummary:
    source_rows = count_rows(con, table, source_col, symbol_col, timeframe_col, source, symbol, m1_timeframe)
    if source_rows <= 0:
        return DeriveSummary(
            target_tf, interval_minutes, source_rows, 0, 0, 0, 0, None, None, 0, 0, None, None, None,
            "FAIL", "no_source_m1_rows"
        )

    existing_before = count_rows(con, table, source_col, symbol_col, timeframe_col, source, symbol, target_tf)
    deleted_existing = 0
    if existing_before > 0:
        if mode == "fail_if_existing":
            return DeriveSummary(
                target_tf, interval_minutes, source_rows, existing_before, 0, 0, 0, None, None, 0, 0,
                None, None, None, "SKIPPED", "target_rows_exist"
            )
        if mode == "skip_existing":
            return DeriveSummary(
                target_tf, interval_minutes, source_rows, existing_before, 0, existing_before, 0, None, None,
                0, 0, None, None, None, "SKIPPED", "target_rows_exist_skip_existing"
            )
        con.execute(
            f"""
            DELETE FROM {qident(table)}
            WHERE {qident(source_col)} = ?
              AND {qident(symbol_col)} = ?
              AND {qident(timeframe_col)} = ?
            """,
            (source, symbol, target_tf),
        )
        deleted_existing = existing_before
        con.commit()

    needed_select_cols = [ts_col, "open", "high", "low", "close"]
    for c in ["tick_volume", "volume", "real_volume", "spread"]:
        if c in cols:
            needed_select_cols.append(c)
    select_sql = ", ".join(qident(c) for c in needed_select_cols)
    query = f"""
        SELECT {select_sql}
        FROM {qident(table)}
        WHERE {qident(source_col)} = ?
          AND {qident(symbol_col)} = ?
          AND {qident(timeframe_col)} = ?
        ORDER BY {qident(ts_col)} ASC
    """

    insert_cols = list(cols)
    insert_sql = build_insert_sql(table, insert_cols)
    now_utc = fmt_utc(datetime.now(timezone.utc))
    derived_raw_json = json.dumps(
        {
            "stage": "Stage38D",
            "derived_from_timeframe": m1_timeframe,
            "target_timeframe": target_tf,
            "aggregation": "ohlc_from_m1",
            "spread_rule": "first_non_null_in_bucket",
            "missing_minutes": "not_filled",
        },
        separators=(",", ":"),
    )

    current_key: Optional[str] = None
    bucket: Optional[Dict[str, Any]] = None
    batch: List[Tuple[Any, ...]] = []
    inserted = 0
    output_rows = 0
    full_bucket_count = 0
    partial_bucket_count = 0
    bucket_counts: List[int] = []
    min_ts: Optional[str] = None
    max_ts: Optional[str] = None

    def finalize_bucket(b: Dict[str, Any]) -> None:
        nonlocal inserted, output_rows, full_bucket_count, partial_bucket_count, min_ts, max_ts
        ts = b["bucket_ts"]
        count = int(b["m1_count"])
        if count >= interval_minutes:
            full_bucket_count += 1
        else:
            partial_bucket_count += 1
        bucket_counts.append(count)
        if min_ts is None or ts < min_ts:
            min_ts = ts
        if max_ts is None or ts > max_ts:
            max_ts = ts
        row = tuple(
            value_for_output_col(
                col,
                source=source,
                symbol=symbol,
                timeframe=target_tf,
                ts=ts,
                bucket=b,
                now_utc=now_utc,
                derived_raw_json=derived_raw_json,
                source_col=source_col,
                symbol_col=symbol_col,
                timeframe_col=timeframe_col,
                ts_col=ts_col,
            )
            for col in insert_cols
        )
        batch.append(row)
        output_rows += 1
        if len(batch) >= batch_size:
            inserted += flush_insert_batch(con, insert_sql, batch)

    cur = con.execute(query, (source, symbol, m1_timeframe))
    for row in cur:
        try:
            dt = parse_time_utc(row[ts_col])
        except Exception:
            # M1 audit already checked parse errors. Skip impossible rows defensively.
            continue
        bucket_dt = floor_bucket(dt, interval_minutes)
        bucket_key = fmt_utc(bucket_dt)

        o = row["open"]
        h = row["high"]
        l = row["low"]
        c = row["close"]
        if o is None or h is None or l is None or c is None:
            continue

        if current_key != bucket_key:
            if bucket is not None:
                finalize_bucket(bucket)
            current_key = bucket_key
            bucket = {
                "bucket_ts": bucket_key,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "m1_count": 1,
                "tick_volume_sum": 0.0,
                "volume_sum": 0.0,
                "real_volume_sum": 0.0,
                "spread_first": None,
            }
        else:
            assert bucket is not None
            bucket["high"] = max(float(bucket["high"]), float(h))
            bucket["low"] = min(float(bucket["low"]), float(l))
            bucket["close"] = float(c)
            bucket["m1_count"] += 1

        assert bucket is not None
        if "tick_volume" in row.keys() and row["tick_volume"] is not None:
            bucket["tick_volume_sum"] += float(row["tick_volume"])
        if "volume" in row.keys() and row["volume"] is not None:
            bucket["volume_sum"] += float(row["volume"])
        if "real_volume" in row.keys() and row["real_volume"] is not None:
            bucket["real_volume_sum"] += float(row["real_volume"])
        if "spread" in row.keys() and bucket["spread_first"] is None and row["spread"] is not None:
            bucket["spread_first"] = float(row["spread"])

    if bucket is not None:
        finalize_bucket(bucket)
    inserted += flush_insert_batch(con, insert_sql, batch)
    con.commit()

    min_count = min(bucket_counts) if bucket_counts else None
    max_count = max(bucket_counts) if bucket_counts else None
    avg_count = (sum(bucket_counts) / len(bucket_counts)) if bucket_counts else None
    status = "PASS" if inserted > 0 else "FAIL"
    notes = []
    if partial_bucket_count:
        notes.append(f"partial_buckets={partial_bucket_count}")
    if deleted_existing:
        notes.append(f"deleted_existing={deleted_existing}")
    note = ";".join(notes) if notes else None
    return DeriveSummary(
        target_tf,
        interval_minutes,
        source_rows,
        existing_before,
        deleted_existing,
        output_rows,
        inserted,
        min_ts,
        max_ts,
        full_bucket_count,
        partial_bucket_count,
        min_count,
        max_count,
        avg_count,
        status,
        note,
    )


def ensure_output_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS stage38d_derived_tf_summary (
            run_id TEXT,
            created_utc TEXT,
            timeframe TEXT,
            interval_minutes INTEGER,
            source_rows INTEGER,
            existing_before INTEGER,
            deleted_existing INTEGER,
            output_rows INTEGER,
            inserted_rows INTEGER,
            min_ts_utc TEXT,
            max_ts_utc TEXT,
            full_bucket_count INTEGER,
            partial_bucket_count INTEGER,
            min_m1_count_per_bucket INTEGER,
            max_m1_count_per_bucket INTEGER,
            avg_m1_count_per_bucket REAL,
            status TEXT,
            note TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS stage38d_derive_tf_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            created_utc TEXT,
            status TEXT,
            decision TEXT,
            db_path TEXT,
            bars_table TEXT,
            source TEXT,
            symbol TEXT,
            m1_timeframe TEXT,
            target_timeframes TEXT,
            source_m1_rows INTEGER,
            targets_requested INTEGER,
            targets_passed INTEGER,
            targets_failed INTEGER,
            output_rows_total INTEGER,
            warning_count INTEGER,
            note_count INTEGER,
            json_report TEXT,
            md_report TEXT
        )
        """
    )
    con.commit()


def write_db_reports(
    con: sqlite3.Connection,
    *,
    run_id: str,
    created_utc: str,
    summaries: Sequence[DeriveSummary],
    db_path: str,
    bars_table: str,
    source: str,
    symbol: str,
    m1_timeframe: str,
    targets: Sequence[str],
    json_report: str,
    md_report: str,
) -> Tuple[str, str, int, int, int, int, int]:
    ensure_output_tables(con)
    con.execute("DELETE FROM stage38d_derived_tf_summary")
    rows = [
        (
            run_id,
            created_utc,
            s.timeframe,
            s.interval_minutes,
            s.source_rows,
            s.existing_before,
            s.deleted_existing,
            s.output_rows,
            s.inserted_rows,
            s.min_ts_utc,
            s.max_ts_utc,
            s.full_bucket_count,
            s.partial_bucket_count,
            s.min_m1_count_per_bucket,
            s.max_m1_count_per_bucket,
            s.avg_m1_count_per_bucket,
            s.status,
            s.note,
        )
        for s in summaries
    ]
    con.executemany(
        """
        INSERT INTO stage38d_derived_tf_summary (
            run_id, created_utc, timeframe, interval_minutes, source_rows,
            existing_before, deleted_existing, output_rows, inserted_rows,
            min_ts_utc, max_ts_utc, full_bucket_count, partial_bucket_count,
            min_m1_count_per_bucket, max_m1_count_per_bucket,
            avg_m1_count_per_bucket, status, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    targets_passed = sum(1 for s in summaries if s.status == "PASS")
    targets_failed = sum(1 for s in summaries if s.status == "FAIL")
    output_total = sum(s.inserted_rows for s in summaries)
    warning_count = targets_failed
    note_count = sum(1 for s in summaries if s.note)
    status = "PASS" if targets_passed == len(summaries) and targets_failed == 0 else "WARN" if targets_passed else "FAIL"
    if status == "PASS":
        decision = "RE_RUN_STAGE38D_AVAILABILITY_AUDIT"
    elif targets_passed:
        decision = "PARTIAL_DERIVATION_REVIEW_BEFORE_REAUDIT"
    else:
        decision = "DO_NOT_PROCEED_M5_M15_UNAVAILABLE"
    source_m1_rows = summaries[0].source_rows if summaries else 0
    con.execute(
        """
        INSERT INTO stage38d_derive_tf_audit (
            run_id, created_utc, status, decision, db_path, bars_table, source,
            symbol, m1_timeframe, target_timeframes, source_m1_rows,
            targets_requested, targets_passed, targets_failed, output_rows_total,
            warning_count, note_count, json_report, md_report
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            created_utc,
            status,
            decision,
            db_path,
            bars_table,
            source,
            symbol,
            m1_timeframe,
            ",".join(targets),
            source_m1_rows,
            len(summaries),
            targets_passed,
            targets_failed,
            output_total,
            warning_count,
            note_count,
            json_report,
            md_report,
        ),
    )
    con.commit()
    return status, decision, targets_passed, targets_failed, output_total, warning_count, note_count


def write_file_reports(
    *,
    reports_dir: Path,
    run_id: str,
    created_utc: str,
    audit: Dict[str, Any],
    summaries: Sequence[DeriveSummary],
) -> Tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38d_derive_m5_m15_from_m1.json"
    md_path = reports_dir / "stage38d_derive_m5_m15_from_m1.md"
    payload = {
        "run_id": run_id,
        "created_utc": created_utc,
        "audit": audit,
        "summaries": [s.__dict__ for s in summaries],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Stage38D Derive M5/M15 From M1",
        "",
        f"- run_id: `{run_id}`",
        f"- created_utc: `{created_utc}`",
        f"- status: `{audit['status']}`",
        f"- decision: `{audit['decision']}`",
        f"- source_m1_rows: `{audit['source_m1_rows']}`",
        f"- output_rows_total: `{audit['output_rows_total']}`",
        "",
        "## Target summaries",
        "",
        "| timeframe | status | inserted | range | full buckets | partial buckets | note |",
        "|---|---:|---:|---|---:|---:|---|",
    ]
    for s in summaries:
        rng = f"{s.min_ts_utc} -> {s.max_ts_utc}" if s.min_ts_utc else "n/a"
        lines.append(
            f"| {s.timeframe} | {s.status} | {s.inserted_rows} | {rng} | "
            f"{s.full_bucket_count} | {s.partial_bucket_count} | {s.note or ''} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")
    targets = parse_targets(args.target_timeframes)
    target_labels = [x[0] for x in targets]
    reports_dir = Path(args.reports_dir)
    run_id = datetime.now(timezone.utc).strftime("stage38d_derive_%Y%m%dT%H%M%SZ")
    created_utc = fmt_utc(datetime.now(timezone.utc))

    con = connect(str(db_path))
    cols_info = get_columns(con, args.bars_table)
    cols = column_names(cols_info)
    source_col = require_col(cols, ["source"], "source column")
    symbol_col = require_col(cols, ["symbol"], "symbol column")
    timeframe_col = require_col(cols, ["timeframe", "tf"], "timeframe column")
    ts_col = require_col(cols, TIMESTAMP_CANDIDATES, "timestamp column")
    for c in NUMERIC_PRICE_COLS:
        require_col(cols, [c], f"{c} column")

    m1_tf = detect_m1_timeframe(
        con, args.bars_table, source_col, symbol_col, timeframe_col, args.source, args.symbol, args.m1_timeframe
    )

    summaries: List[DeriveSummary] = []
    for target_tf, minutes in targets:
        summaries.append(
            derive_one_timeframe(
                con,
                table=args.bars_table,
                cols=cols,
                source_col=source_col,
                symbol_col=symbol_col,
                timeframe_col=timeframe_col,
                ts_col=ts_col,
                source=args.source,
                symbol=args.symbol,
                m1_timeframe=m1_tf,
                target_tf=target_tf,
                interval_minutes=minutes,
                mode=args.mode,
                batch_size=args.batch_size,
            )
        )

    # First compute audit paths, then write DB audit with final paths.
    json_report = str(reports_dir / "stage38d_derive_m5_m15_from_m1.json")
    md_report = str(reports_dir / "stage38d_derive_m5_m15_from_m1.md")
    status, decision, targets_passed, targets_failed, output_total, warning_count, note_count = write_db_reports(
        con,
        run_id=run_id,
        created_utc=created_utc,
        summaries=summaries,
        db_path=str(db_path),
        bars_table=args.bars_table,
        source=args.source,
        symbol=args.symbol,
        m1_timeframe=m1_tf,
        targets=target_labels,
        json_report=json_report,
        md_report=md_report,
    )
    audit = {
        "status": status,
        "decision": decision,
        "db_path": str(db_path),
        "bars_table": args.bars_table,
        "source": args.source,
        "symbol": args.symbol,
        "m1_timeframe": m1_tf,
        "target_timeframes": target_labels,
        "source_m1_rows": summaries[0].source_rows if summaries else 0,
        "targets_requested": len(summaries),
        "targets_passed": targets_passed,
        "targets_failed": targets_failed,
        "output_rows_total": output_total,
        "warning_count": warning_count,
        "note_count": note_count,
        "json_report": json_report,
        "md_report": md_report,
    }
    write_file_reports(reports_dir=reports_dir, run_id=run_id, created_utc=created_utc, audit=audit, summaries=summaries)

    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if status in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
