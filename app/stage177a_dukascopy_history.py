#!/usr/bin/env python3
"""Chunked, resumable-in-run Dukascopy XAUUSD downloader for GitHub Actions.

Uses a pinned dukascopy-node CLI, validates every output chunk, compresses it, and
emits a manifest. No GitHub Actions cache is used: outputs are uploaded as a
1-day artifact by the workflow.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

PINNED_DUKASCOPY_NODE = "1.49.0"
ALLOWED_TIMEFRAMES = {"m5": 300_000, "m15": 900_000, "h1": 3_600_000, "h4": 14_400_000, "d1": 86_400_000}


@dataclass
class ChunkResult:
    instrument: str
    timeframe: str
    price_type: str
    date_from: str
    date_to: str
    status: str
    csv_gz: str | None = None
    rows: int = 0
    first_timestamp_ms: int | None = None
    last_timestamp_ms: int | None = None
    duplicate_timestamps: int = 0
    non_monotonic_timestamps: int = 0
    ohlc_violations: int = 0
    negative_volume_rows: int = 0
    large_gap_count: int = 0
    max_gap_hours: float = 0.0
    sha256: str | None = None
    compressed_bytes: int = 0
    error: str | None = None
    elapsed_seconds: float = 0.0


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def add_months(value: dt.date, months: int) -> dt.date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    day = min(value.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return dt.date(year, month, day)


def iter_chunks(start: dt.date, end: dt.date, chunk_months: int) -> Iterable[tuple[dt.date, dt.date]]:
    cursor = start
    while cursor < end:
        next_cursor = min(add_months(cursor, chunk_months), end)
        if next_cursor <= cursor:
            raise RuntimeError("Chunk boundary did not advance")
        yield cursor, next_cursor
        cursor = next_cursor


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_csv(path: Path, timeframe: str) -> dict[str, int | float | None]:
    expected = {"timestamp", "open", "high", "low", "close", "volume"}
    rows = 0
    first_ts: int | None = None
    last_ts: int | None = None
    duplicates = 0
    non_monotonic = 0
    ohlc_violations = 0
    negative_volume = 0
    large_gap_count = 0
    max_gap_ms = 0
    interval_ms = ALLOWED_TIMEFRAMES[timeframe]
    seen: set[int] = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = {str(name).strip().lower() for name in (reader.fieldnames or [])}
        if not expected.issubset(fields):
            raise ValueError(f"Unexpected Dukascopy CSV columns: {reader.fieldnames}")
        for raw in reader:
            row = {str(key).strip().lower(): value for key, value in raw.items()}
            ts = int(float(row["timestamp"]))
            open_ = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = float(row["volume"] or 0)
            if not all(value > 0 for value in (open_, high, low, close)):
                ohlc_violations += 1
            if high < max(open_, close, low) or low > min(open_, close, high):
                ohlc_violations += 1
            if volume < 0:
                negative_volume += 1
            if ts in seen:
                duplicates += 1
            seen.add(ts)
            if last_ts is not None:
                if ts <= last_ts:
                    non_monotonic += 1
                gap = ts - last_ts
                max_gap_ms = max(max_gap_ms, gap)
                # Weekend/holiday gaps are expected. Only inventory gaps above 96h are flagged.
                if gap > max(interval_ms * 4, 96 * 3_600_000):
                    large_gap_count += 1
            if first_ts is None:
                first_ts = ts
            last_ts = ts
            rows += 1

    if rows == 0:
        raise ValueError("Dukascopy CSV is empty")
    if duplicates or non_monotonic or ohlc_violations or negative_volume:
        raise ValueError(
            f"CSV validation failed: duplicates={duplicates} non_monotonic={non_monotonic} "
            f"ohlc_violations={ohlc_violations} negative_volume={negative_volume}"
        )
    return {
        "rows": rows,
        "first_timestamp_ms": first_ts,
        "last_timestamp_ms": last_ts,
        "duplicate_timestamps": duplicates,
        "non_monotonic_timestamps": non_monotonic,
        "ohlc_violations": ohlc_violations,
        "negative_volume_rows": negative_volume,
        "large_gap_count": large_gap_count,
        "max_gap_hours": round(max_gap_ms / 3_600_000, 3),
    }


def gzip_file(source: Path, destination: Path) -> None:
    with source.open("rb") as src, destination.open("wb") as raw_dst:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_dst, compresslevel=9, mtime=0) as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)


def resolve_preset(args: argparse.Namespace) -> tuple[str, dt.date, dt.date, int]:
    today = dt.datetime.now(dt.timezone.utc).date()
    if args.preset == "smoke_h1_2025":
        return "h1", dt.date(2025, 1, 1), dt.date(2025, 2, 1), 1
    if args.preset == "h1_full":
        return "h1", dt.date(2003, 5, 5), today, 24
    if args.preset == "m5_full":
        return "m5", dt.date(2010, 1, 1), today, 12
    if args.preset == "custom":
        if not args.timeframe or not args.date_from or not args.date_to:
            raise ValueError("custom preset requires --timeframe, --date-from and --date-to")
        return args.timeframe, args.date_from, args.date_to, args.chunk_months
    raise ValueError(f"Unknown preset {args.preset}")


def run_chunk(
    *, output_dir: Path, cache_dir: Path, timeframe: str, price_type: str,
    date_from: dt.date, date_to: dt.date, batch_size: int, batch_pause_ms: int,
) -> ChunkResult:
    started = time.monotonic()
    stem = f"xauusd_{timeframe}_{price_type}_{date_from.isoformat()}_{date_to.isoformat()}"
    raw_dir = output_dir / "raw"
    chunks_dir = output_dir / "chunks"
    raw_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    csv_path = raw_dir / f"{stem}.csv"
    gz_path = chunks_dir / f"{stem}.csv.gz"

    result = ChunkResult(
        instrument="xauusd", timeframe=timeframe, price_type=price_type,
        date_from=date_from.isoformat(), date_to=date_to.isoformat(), status="RUNNING",
    )
    command = [
        "npx", "--yes", f"dukascopy-node@{PINNED_DUKASCOPY_NODE}",
        "-i", "xauusd", "-from", date_from.isoformat(), "-to", date_to.isoformat(),
        "-t", timeframe, "-p", price_type, "--volumes", "--volume-units", "units",
        "-f", "csv", "-dir", str(raw_dir), "-fn", stem,
        "-bs", str(batch_size), "-bp", str(batch_pause_ms),
        "--cache", "--cache-path", str(cache_dir),
        "--retries", "3", "--retry-on-empty", "--no-fail-after-retries", "--retry-pause", "2000",
    ]
    print(f"[Stage177A][download] {date_from} -> {date_to} tf={timeframe} price={price_type}", flush=True)
    try:
        completed = subprocess.run(command, check=False, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"dukascopy-node exit code {completed.returncode}")
        # Some CLI versions may add .csv automatically or respect filename verbatim.
        candidates = [csv_path, raw_dir / stem, raw_dir / f"{stem}.csv.csv"]
        actual = next((candidate for candidate in candidates if candidate.exists() and candidate.stat().st_size > 0), None)
        if actual is None:
            matches = sorted(raw_dir.glob(f"{stem}*.csv"))
            actual = matches[0] if matches else None
        if actual is None:
            raise FileNotFoundError(f"No CSV generated for {stem}")
        metrics = validate_csv(actual, timeframe)
        gzip_file(actual, gz_path)
        result.status = "PASS"
        result.csv_gz = str(gz_path.relative_to(output_dir))
        for key, value in metrics.items():
            setattr(result, key, value)
        result.sha256 = sha256_file(gz_path)
        result.compressed_bytes = gz_path.stat().st_size
        actual.unlink(missing_ok=True)
    except Exception as exc:
        result.status = "FAIL"
        result.error = f"{type(exc).__name__}:{exc}"
    result.elapsed_seconds = round(time.monotonic() - started, 3)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", choices=("smoke_h1_2025", "h1_full", "m5_full", "custom"), default="smoke_h1_2025")
    parser.add_argument("--timeframe", choices=tuple(ALLOWED_TIMEFRAMES))
    parser.add_argument("--date-from", type=parse_date)
    parser.add_argument("--date-to", type=parse_date)
    parser.add_argument("--chunk-months", type=int, default=12)
    parser.add_argument("--price-type", choices=("bid", "ask", "both"), default="bid")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--batch-pause-ms", type=int, default=1500)
    parser.add_argument("--output-dir", default="reports/stage177a_dukascopy_history")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timeframe, start, end, chunk_months = resolve_preset(args)
    if start >= end:
        raise ValueError("date-from must be before date-to")
    if chunk_months < 1 or chunk_months > 36:
        raise ValueError("chunk-months must be between 1 and 36")
    output_dir = Path(args.output_dir).resolve()
    cache_dir = output_dir / ".dukascopy-cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    price_types = ("bid", "ask") if args.price_type == "both" else (args.price_type,)
    results: list[ChunkResult] = []
    chunks = list(iter_chunks(start, end, chunk_months))
    total = len(chunks) * len(price_types)
    index = 0
    for price_type in price_types:
        for chunk_start, chunk_end in chunks:
            index += 1
            print(f"[Stage177A][progress] chunk={index}/{total} {(index-1)/max(total,1)*100:.1f}%", flush=True)
            result = run_chunk(
                output_dir=output_dir, cache_dir=cache_dir, timeframe=timeframe, price_type=price_type,
                date_from=chunk_start, date_to=chunk_end,
                batch_size=args.batch_size, batch_pause_ms=args.batch_pause_ms,
            )
            results.append(result)
            manifest = {
                "stage": "Stage177A_DUKASCOPY_HISTORY",
                "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "dukascopy_node_version": PINNED_DUKASCOPY_NODE,
                "preset": args.preset,
                "timeframe": timeframe,
                "price_type": args.price_type,
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "chunk_months": chunk_months,
                "chunks_total": total,
                "chunks_pass": sum(item.status == "PASS" for item in results),
                "chunks_fail": sum(item.status == "FAIL" for item in results),
                "results": [asdict(item) for item in results],
            }
            with (output_dir / "stage177a_dukascopy_manifest.json").open("w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, sort_keys=True)
                handle.write("\n")
            print(f"[Stage177A][result] status={result.status} rows={result.rows} file={result.csv_gz} error={result.error}", flush=True)

    shutil.rmtree(cache_dir, ignore_errors=True)
    failures = [item for item in results if item.status != "PASS"]
    summary = {
        "decision": "PASS_DOWNLOAD_COMPLETE" if not failures else "PARTIAL_DOWNLOAD_REQUIRES_RERUN",
        "chunks_total": len(results),
        "chunks_pass": len(results) - len(failures),
        "chunks_fail": len(failures),
        "rows_total": sum(item.rows for item in results),
        "compressed_bytes_total": sum(item.compressed_bytes for item in results),
    }
    with (output_dir / "stage177a_dukascopy_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
