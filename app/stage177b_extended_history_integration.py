#!/usr/bin/env python3
"""Stage177B: validate and integrate Dukascopy H1/M5 artifacts.

The canonical contract is intentionally asymmetric:
- 2003-2009: direct Dukascopy H1 is retained.
- 2010 onward: M5 is the primary source and H1 is derived from M5.

This removes internal multi-timeframe contradictions from the research feed while
preserving the earlier H1-only history. No order, paper, demo, or live path is
implemented here.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import shutil
import sqlite3
import statistics
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

EXPECTED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
M5_MS = 300_000
H1_MS = 3_600_000


@dataclass(frozen=True)
class ArtifactContract:
    path: Path
    preset: str
    timeframe: str
    price_type: str
    manifest: dict[str, Any]
    summary: dict[str, Any]


@dataclass
class StreamAudit:
    rows: int = 0
    first_timestamp_ms: int | None = None
    last_timestamp_ms: int | None = None
    duplicate_timestamps: int = 0
    non_monotonic_timestamps: int = 0
    ohlc_violations: int = 0
    negative_volume_rows: int = 0
    null_rows: int = 0
    max_gap_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "first_timestamp_ms": self.first_timestamp_ms,
            "first_timestamp_utc": ms_to_iso(self.first_timestamp_ms),
            "last_timestamp_ms": self.last_timestamp_ms,
            "last_timestamp_utc": ms_to_iso(self.last_timestamp_ms),
            "duplicate_timestamps": self.duplicate_timestamps,
            "non_monotonic_timestamps": self.non_monotonic_timestamps,
            "ohlc_violations": self.ohlc_violations,
            "negative_volume_rows": self.negative_volume_rows,
            "null_rows": self.null_rows,
            "max_gap_hours": round(self.max_gap_ms / H1_MS, 6),
        }


def ms_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc).isoformat()


def sha256_bytes_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def safe_member_name(name: str) -> bool:
    path = Path(name)
    return not path.is_absolute() and ".." not in path.parts


def read_json_member(zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    try:
        raw = zf.read(name)
    except KeyError as exc:
        raise ValueError(f"Artifact is missing required member: {name}") from exc
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON in {name}")
    return payload


def validate_artifact(path: Path, expected_preset: str, expected_timeframe: str) -> ArtifactContract:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a ZIP artifact: {path}")

    with zipfile.ZipFile(path) as zf:
        bad = [name for name in zf.namelist() if not safe_member_name(name)]
        if bad:
            raise ValueError(f"Unsafe ZIP member(s): {bad[:3]}")
        manifest = read_json_member(zf, "stage177a_dukascopy_manifest.json")
        summary = read_json_member(zf, "stage177a_dukascopy_summary.json")

        if summary.get("decision") != "PASS_DOWNLOAD_COMPLETE":
            raise ValueError(f"Artifact did not pass Stage177A: {summary}")
        if int(summary.get("chunks_fail", -1)) != 0:
            raise ValueError("Artifact reports failed chunks")
        if manifest.get("preset") != expected_preset:
            raise ValueError(
                f"Expected preset={expected_preset}, got {manifest.get('preset')}"
            )
        if manifest.get("price_type") != "bid":
            raise ValueError("Stage177B currently accepts bid artifacts only")

        results = manifest.get("results")
        if not isinstance(results, list) or not results:
            raise ValueError("Manifest results are missing or empty")
        if len(results) != int(summary.get("chunks_total", -1)):
            raise ValueError("Manifest/summary chunk count mismatch")
        if any(item.get("status") != "PASS" for item in results):
            raise ValueError("At least one manifest chunk is not PASS")
        if any(item.get("timeframe") != expected_timeframe for item in results):
            raise ValueError("Unexpected timeframe inside artifact manifest")

        for item in results:
            member = str(item.get("csv_gz") or "")
            if not member or member not in zf.namelist():
                raise ValueError(f"Missing chunk member: {member}")
            with zf.open(member) as handle:
                actual_sha = sha256_bytes_stream(handle)
            if actual_sha != item.get("sha256"):
                raise ValueError(f"SHA-256 mismatch for {member}")
            if zf.getinfo(member).file_size != int(item.get("compressed_bytes", -1)):
                raise ValueError(f"Compressed byte count mismatch for {member}")

        rows_manifest = sum(int(item.get("rows", 0)) for item in results)
        if rows_manifest != int(summary.get("rows_total", -1)):
            raise ValueError("Manifest/summary row count mismatch")

    return ArtifactContract(
        path=path.resolve(),
        preset=expected_preset,
        timeframe=expected_timeframe,
        price_type="bid",
        manifest=manifest,
        summary=summary,
    )


def ordered_chunk_members(contract: ArtifactContract) -> list[dict[str, Any]]:
    results = list(contract.manifest["results"])
    results.sort(key=lambda item: (str(item["date_from"]), str(item["date_to"])))
    return results


def parse_float(raw: str, field: str) -> float:
    if raw is None or str(raw).strip() == "":
        raise ValueError(f"Missing {field}")
    value = float(raw)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"Non-finite {field}")
    return value


def iter_artifact_rows(
    contract: ArtifactContract,
    *,
    copy_root: Path | None = None,
) -> Iterator[tuple[int, float, float, float, float, float]]:
    """Yield validated rows in chronological chunk order.

    When copy_root is supplied, each original .csv.gz chunk is copied there and
    re-hashed before parsing. This preserves Stage177A provenance locally.
    """
    with zipfile.ZipFile(contract.path) as zf:
        for item in ordered_chunk_members(contract):
            member = str(item["csv_gz"])
            if copy_root is not None:
                destination = copy_root / Path(member).name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                with destination.open("rb") as copied:
                    copied_sha = sha256_bytes_stream(copied)
                if copied_sha != item["sha256"]:
                    raise ValueError(f"Copied chunk hash mismatch: {destination}")

            with zf.open(member) as zipped_member:
                with gzip.GzipFile(fileobj=zipped_member, mode="rb") as gz:
                    text = io.TextIOWrapper(gz, encoding="utf-8-sig", newline="")
                    reader = csv.DictReader(text)
                    normalized = [str(name).strip().lower() for name in (reader.fieldnames or [])]
                    if normalized != EXPECTED_COLUMNS:
                        raise ValueError(
                            f"Unexpected CSV schema in {member}: {reader.fieldnames}"
                        )
                    for raw in reader:
                        timestamp = int(float(raw["timestamp"]))
                        open_ = parse_float(raw["open"], "open")
                        high = parse_float(raw["high"], "high")
                        low = parse_float(raw["low"], "low")
                        close = parse_float(raw["close"], "close")
                        volume = parse_float(raw["volume"], "volume")
                        yield timestamp, open_, high, low, close, volume


def audit_row(
    audit: StreamAudit,
    row: tuple[int, float, float, float, float, float],
    *,
    previous_timestamp: int | None,
) -> None:
    timestamp, open_, high, low, close, volume = row
    if audit.first_timestamp_ms is None:
        audit.first_timestamp_ms = timestamp
    if previous_timestamp is not None:
        if timestamp == previous_timestamp:
            audit.duplicate_timestamps += 1
        if timestamp <= previous_timestamp:
            audit.non_monotonic_timestamps += 1
        audit.max_gap_ms = max(audit.max_gap_ms, timestamp - previous_timestamp)
    if min(open_, high, low, close) <= 0:
        audit.ohlc_violations += 1
    if high < max(open_, low, close) or low > min(open_, high, close):
        audit.ohlc_violations += 1
    if volume < 0:
        audit.negative_volume_rows += 1
    audit.rows += 1
    audit.last_timestamp_ms = timestamp


def create_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.executescript(
        """
        CREATE TABLE dukascopy_h1_direct (
            timestamp INTEGER PRIMARY KEY,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL
        );
        CREATE TABLE dukascopy_m5 (
            timestamp INTEGER PRIMARY KEY,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL
        );
        CREATE TABLE dukascopy_h1_from_m5 (
            timestamp INTEGER PRIMARY KEY,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            m5_bar_count INTEGER NOT NULL
        );
        CREATE TABLE dukascopy_h1_canonical (
            timestamp INTEGER PRIMARY KEY,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            source TEXT NOT NULL,
            m5_bar_count INTEGER
        );
        CREATE TABLE provenance (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    return connection


def insert_batches(
    connection: sqlite3.Connection,
    sql: str,
    rows: Iterable[tuple[Any, ...]],
    *,
    batch_size: int = 20_000,
) -> None:
    batch: list[tuple[Any, ...]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            connection.executemany(sql, batch)
            batch.clear()
    if batch:
        connection.executemany(sql, batch)


def ingest_h1(
    connection: sqlite3.Connection,
    contract: ArtifactContract,
    copy_root: Path,
) -> StreamAudit:
    audit = StreamAudit()
    previous: int | None = None
    batch: list[tuple[Any, ...]] = []
    for row in iter_artifact_rows(contract, copy_root=copy_root):
        audit_row(audit, row, previous_timestamp=previous)
        previous = row[0]
        batch.append(row)
        if len(batch) >= 20_000:
            connection.executemany(
                "INSERT INTO dukascopy_h1_direct VALUES (?, ?, ?, ?, ?, ?)", batch
            )
            batch.clear()
    if batch:
        connection.executemany(
            "INSERT INTO dukascopy_h1_direct VALUES (?, ?, ?, ?, ?, ?)", batch
        )
    if audit.rows != int(contract.summary["rows_total"]):
        raise ValueError("H1 parsed row count differs from artifact summary")
    assert_clean_audit(audit, "H1")
    return audit


def finalize_hour(
    connection: sqlite3.Connection,
    state: dict[str, Any],
    h1_batch: list[tuple[Any, ...]],
) -> None:
    if not state:
        return
    h1_batch.append(
        (
            state["timestamp"],
            state["open"],
            state["high"],
            state["low"],
            state["close"],
            state["volume"],
            state["count"],
        )
    )
    if len(h1_batch) >= 10_000:
        connection.executemany(
            "INSERT INTO dukascopy_h1_from_m5 VALUES (?, ?, ?, ?, ?, ?, ?)",
            h1_batch,
        )
        h1_batch.clear()


def ingest_m5_and_derive_h1(
    connection: sqlite3.Connection,
    contract: ArtifactContract,
    copy_root: Path,
) -> tuple[StreamAudit, int]:
    audit = StreamAudit()
    previous: int | None = None
    m5_batch: list[tuple[Any, ...]] = []
    h1_batch: list[tuple[Any, ...]] = []
    state: dict[str, Any] = {}

    for row in iter_artifact_rows(contract, copy_root=copy_root):
        timestamp, open_, high, low, close, volume = row
        audit_row(audit, row, previous_timestamp=previous)
        previous = timestamp
        m5_batch.append(row)
        if len(m5_batch) >= 25_000:
            connection.executemany(
                "INSERT INTO dukascopy_m5 VALUES (?, ?, ?, ?, ?, ?)", m5_batch
            )
            m5_batch.clear()

        hour_timestamp = (timestamp // H1_MS) * H1_MS
        if not state or state["timestamp"] != hour_timestamp:
            finalize_hour(connection, state, h1_batch)
            state = {
                "timestamp": hour_timestamp,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "count": 1,
            }
        else:
            state["high"] = max(state["high"], high)
            state["low"] = min(state["low"], low)
            state["close"] = close
            state["volume"] += volume
            state["count"] += 1

    finalize_hour(connection, state, h1_batch)
    if m5_batch:
        connection.executemany(
            "INSERT INTO dukascopy_m5 VALUES (?, ?, ?, ?, ?, ?)", m5_batch
        )
    if h1_batch:
        connection.executemany(
            "INSERT INTO dukascopy_h1_from_m5 VALUES (?, ?, ?, ?, ?, ?, ?)",
            h1_batch,
        )

    if audit.rows != int(contract.summary["rows_total"]):
        raise ValueError("M5 parsed row count differs from artifact summary")
    assert_clean_audit(audit, "M5")
    h1_derived_rows = int(
        connection.execute("SELECT COUNT(*) FROM dukascopy_h1_from_m5").fetchone()[0]
    )
    return audit, h1_derived_rows


def assert_clean_audit(audit: StreamAudit, label: str) -> None:
    failures = {
        "duplicates": audit.duplicate_timestamps,
        "non_monotonic": audit.non_monotonic_timestamps,
        "ohlc_violations": audit.ohlc_violations,
        "negative_volume": audit.negative_volume_rows,
        "null_rows": audit.null_rows,
    }
    if any(failures.values()):
        raise ValueError(f"{label} stream audit failed: {failures}")


def build_canonical_h1(connection: sqlite3.Connection) -> dict[str, Any]:
    bounds = connection.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM dukascopy_h1_from_m5"
    ).fetchone()
    if bounds[0] is None:
        raise ValueError("No H1 bars were derived from M5")
    m5_first_hour, m5_last_hour = int(bounds[0]), int(bounds[1])

    connection.execute(
        """
        INSERT INTO dukascopy_h1_canonical
        SELECT timestamp, open, high, low, close, volume, 'H1_DIRECT_OUTSIDE_M5', NULL
        FROM dukascopy_h1_direct
        WHERE timestamp < ? OR timestamp > ?
        """,
        (m5_first_hour, m5_last_hour),
    )
    connection.execute(
        """
        INSERT INTO dukascopy_h1_canonical
        SELECT timestamp, open, high, low, close, volume, 'M5_DERIVED', m5_bar_count
        FROM dukascopy_h1_from_m5
        """
    )
    connection.commit()

    direct_rows = int(
        connection.execute(
            "SELECT COUNT(*) FROM dukascopy_h1_canonical WHERE source='H1_DIRECT_OUTSIDE_M5'"
        ).fetchone()[0]
    )
    derived_rows = int(
        connection.execute(
            "SELECT COUNT(*) FROM dukascopy_h1_canonical WHERE source='M5_DERIVED'"
        ).fetchone()[0]
    )
    total_rows = int(
        connection.execute("SELECT COUNT(*) FROM dukascopy_h1_canonical").fetchone()[0]
    )
    canonical_bounds = connection.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM dukascopy_h1_canonical"
    ).fetchone()
    return {
        "rows_total": total_rows,
        "rows_h1_direct_outside_m5": direct_rows,
        "rows_m5_derived": derived_rows,
        "first_timestamp_ms": int(canonical_bounds[0]),
        "first_timestamp_utc": ms_to_iso(int(canonical_bounds[0])),
        "last_timestamp_ms": int(canonical_bounds[1]),
        "last_timestamp_utc": ms_to_iso(int(canonical_bounds[1])),
        "m5_primary_from_utc": ms_to_iso(m5_first_hour),
        "m5_primary_to_utc": ms_to_iso(m5_last_hour),
    }


def parity_analysis(
    connection: sqlite3.Connection,
    anomaly_csv: Path,
) -> dict[str, Any]:
    direct = {
        int(row[0]): tuple(float(value) for value in row[1:])
        for row in connection.execute(
            "SELECT timestamp, open, high, low, close, volume FROM dukascopy_h1_direct"
        )
    }
    derived = {
        int(row[0]): tuple(float(value) for value in row[1:6]) + (int(row[6]),)
        for row in connection.execute(
            "SELECT timestamp, open, high, low, close, volume, m5_bar_count "
            "FROM dukascopy_h1_from_m5"
        )
    }
    direct_keys = set(direct)
    derived_keys = set(derived)
    if not derived_keys:
        raise ValueError("No M5-derived H1 rows available for parity analysis")
    overlap_start = min(derived_keys)
    overlap_end = max(derived_keys)
    direct_overlap_keys = {
        timestamp for timestamp in direct_keys
        if overlap_start <= timestamp <= overlap_end
    }
    shared = sorted(direct_overlap_keys & derived_keys)
    direct_only = sorted(direct_overlap_keys - derived_keys)
    derived_only = sorted(derived_keys - direct_overlap_keys)

    ohlc_mismatch: list[tuple[Any, ...]] = []
    volume_mismatch = 0
    exact_ohlc = 0
    exact_volume = 0
    abs_differences: dict[str, list[float]] = {
        "open": [], "high": [], "low": [], "close": [], "volume": []
    }
    for timestamp in shared:
        d_open, d_high, d_low, d_close, d_volume = direct[timestamp]
        m_open, m_high, m_low, m_close, m_volume, m5_count = derived[timestamp]
        diffs = [
            d_open - m_open,
            d_high - m_high,
            d_low - m_low,
            d_close - m_close,
            d_volume - m_volume,
        ]
        for key, value in zip(abs_differences, diffs):
            abs_differences[key].append(abs(value))
        if all(abs(value) <= 1e-12 for value in diffs[:4]):
            exact_ohlc += 1
        else:
            ohlc_mismatch.append(
                (
                    "OHLC_MISMATCH", timestamp, ms_to_iso(timestamp), m5_count,
                    d_open, d_high, d_low, d_close, d_volume,
                    m_open, m_high, m_low, m_close, m_volume,
                    *diffs,
                )
            )
        if abs(diffs[4]) <= 1e-12:
            exact_volume += 1
        else:
            volume_mismatch += 1

    direct_only_ranges: list[float] = []
    direct_only_volumes: list[float] = []
    direct_only_hours: dict[int, int] = {}
    direct_only_years: dict[int, int] = {}
    anomaly_rows = list(ohlc_mismatch)
    for timestamp in direct_only:
        open_, high, low, close, volume = direct[timestamp]
        parsed = dt.datetime.fromtimestamp(timestamp / 1000, tz=dt.timezone.utc)
        direct_only_ranges.append(high - low)
        direct_only_volumes.append(volume)
        direct_only_hours[parsed.hour] = direct_only_hours.get(parsed.hour, 0) + 1
        direct_only_years[parsed.year] = direct_only_years.get(parsed.year, 0) + 1
        anomaly_rows.append(
            (
                "H1_DIRECT_ONLY", timestamp, ms_to_iso(timestamp), "",
                open_, high, low, close, volume,
                "", "", "", "", "", "", "", "", "", "",
            )
        )
    for timestamp in derived_only:
        open_, high, low, close, volume, m5_count = derived[timestamp]
        anomaly_rows.append(
            (
                "M5_DERIVED_ONLY", timestamp, ms_to_iso(timestamp), m5_count,
                "", "", "", "", "",
                open_, high, low, close, volume, "", "", "", "", "",
            )
        )

    anomaly_csv.parent.mkdir(parents=True, exist_ok=True)
    with anomaly_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "anomaly_type", "timestamp", "timestamp_utc", "m5_bar_count",
                "h1_open", "h1_high", "h1_low", "h1_close", "h1_volume",
                "m5_open", "m5_high", "m5_low", "m5_close", "m5_volume",
                "diff_open", "diff_high", "diff_low", "diff_close", "diff_volume",
            ]
        )
        writer.writerows(sorted(anomaly_rows, key=lambda row: (int(row[1]), str(row[0]))))

    shared_count = len(shared)
    exact_ohlc_pct = 100.0 * exact_ohlc / shared_count if shared_count else 0.0
    exact_volume_pct = 100.0 * exact_volume / shared_count if shared_count else 0.0

    def distribution(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {"median": None, "max": None}
        return {"median": float(statistics.median(values)), "max": float(max(values))}

    return {
        "shared_hours": shared_count,
        "h1_direct_only_hours": len(direct_only),
        "m5_derived_only_hours": len(derived_only),
        "exact_ohlc_hours": exact_ohlc,
        "exact_ohlc_pct": round(exact_ohlc_pct, 9),
        "ohlc_mismatch_hours": len(ohlc_mismatch),
        "exact_volume_hours": exact_volume,
        "exact_volume_pct": round(exact_volume_pct, 9),
        "volume_mismatch_hours": volume_mismatch,
        "absolute_difference": {
            key: distribution(values) for key, values in abs_differences.items()
        },
        "h1_direct_only_profile": {
            "hours_utc": {str(k): direct_only_hours[k] for k in sorted(direct_only_hours)},
            "years": {str(k): direct_only_years[k] for k in sorted(direct_only_years)},
            "volume": distribution(direct_only_volumes),
            "range": distribution(direct_only_ranges),
        },
        "anomaly_csv": str(anomaly_csv),
    }


def copy_metadata(contract: ArtifactContract, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(contract.path) as zf:
        for name in ("stage177a_dukascopy_manifest.json", "stage177a_dukascopy_summary.json"):
            (destination / name).write_bytes(zf.read(name))
    artifact_sha = hashlib.sha256(contract.path.read_bytes()).hexdigest()
    return {
        "artifact_path": str(contract.path),
        "artifact_sha256": artifact_sha,
        "preset": contract.preset,
        "timeframe": contract.timeframe,
        "price_type": contract.price_type,
    }


def write_decision(path: Path, summary: dict[str, Any]) -> None:
    parity = summary["h1_m5_parity"]
    passed = summary["decision"].startswith("PASS")
    lines = [
        "# Stage177B Extended History Integration Decision",
        "",
        f"Decision: `{summary['decision']}`",
        "",
        "## Core result",
        "",
        f"- M5 rows: {summary['m5_audit']['rows']:,}",
        f"- Canonical H1 rows: {summary['canonical_h1']['rows_total']:,}",
        f"- H1/M5 shared hours: {parity['shared_hours']:,}",
        f"- Exact OHLC parity: {parity['exact_ohlc_pct']:.6f}%",
        f"- H1-only hours inside overlap audit: {parity['h1_direct_only_hours']:,}",
        f"- M5-only derived hours: {parity['m5_derived_only_hours']:,}",
        "",
        "## Canonical policy",
        "",
        "- Direct H1 is used only outside M5 coverage.",
        "- M5-derived H1 is authoritative from 2010 onward.",
        "- Direct-H1-only rollover/sparse bars are not injected into the canonical overlap.",
        "- Dukascopy remains a research/reference feed; AMarkets remains the execution/cost feed.",
        "",
        "## Operational boundary",
        "",
        "No paper order, demo order, or live order is authorized by this stage.",
    ]
    if not passed:
        lines.extend(["", "Stage177B failed closed; do not use the generated database."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_latest(pattern: str, search_dirs: list[Path]) -> Path:
    candidates: list[Path] = []
    for directory in search_dirs:
        if directory.exists():
            candidates.extend(directory.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"No artifact matching {pattern} in {search_dirs}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h1-artifact", type=Path)
    parser.add_argument("--m5-artifact", type=Path)
    parser.add_argument(
        "--data-dir", type=Path,
        default=Path("data/local/stage177b_extended_history"),
    )
    parser.add_argument(
        "--report-dir", type=Path,
        default=Path("reports/stage177b_extended_history_integration"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    search_dirs = [Path.home() / "Downloads", Path.cwd()]
    h1_path = args.h1_artifact or resolve_latest(
        "stage177a-dukascopy-h1_full-bid-*.zip", search_dirs
    )
    m5_path = args.m5_artifact or resolve_latest(
        "stage177a-dukascopy-m5_full-bid-*.zip", search_dirs
    )

    h1_contract = validate_artifact(h1_path, "h1_full", "h1")
    m5_contract = validate_artifact(m5_path, "m5_full", "m5")

    data_dir = args.data_dir.resolve()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    data_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="stage177b_", dir=str(data_dir.parent)) as temp:
        temp_dir = Path(temp)
        build_data = temp_dir / data_dir.name
        build_data.mkdir(parents=True)
        (build_data / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
        raw_h1 = build_data / "raw" / "dukascopy" / "h1" / "chunks"
        raw_m5 = build_data / "raw" / "dukascopy" / "m5" / "chunks"
        raw_h1.mkdir(parents=True)
        raw_m5.mkdir(parents=True)

        h1_provenance = copy_metadata(h1_contract, raw_h1.parent)
        m5_provenance = copy_metadata(m5_contract, raw_m5.parent)

        db_path = build_data / "xauusd_extended_history.sqlite"
        connection = create_database(db_path)
        try:
            h1_audit = ingest_h1(connection, h1_contract, raw_h1)
            m5_audit, h1_derived_rows = ingest_m5_and_derive_h1(
                connection, m5_contract, raw_m5
            )
            connection.commit()
            canonical = build_canonical_h1(connection)
            parity = parity_analysis(
                connection,
                report_dir / "stage177b_h1_m5_parity_anomalies.csv",
            )
            provenance = {
                "h1": h1_provenance,
                "m5": m5_provenance,
                "canonical_policy": "H1_DIRECT_OUTSIDE_M5_PLUS_M5_DERIVED_INSIDE_OVERLAP",
            }
            for key, value in provenance.items():
                connection.execute(
                    "INSERT OR REPLACE INTO provenance VALUES (?, ?)",
                    (key, json.dumps(value, sort_keys=True)),
                )
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()

        # Conservative acceptance: artifacts clean and cross-timeframe parity above 99.9%.
        parity_pass = (
            parity["shared_hours"] > 50_000
            and parity["exact_ohlc_pct"] >= 99.9
            and parity["h1_direct_only_hours"] / max(parity["shared_hours"], 1) < 0.01
        )
        decision = (
            "PASS_REFERENCE_FEED_INTEGRATED_AMARKETS_PARITY_PENDING"
            if parity_pass
            else "FAIL_REFERENCE_FEED_INTEGRATION"
        )
        summary = {
            "stage": "177B",
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "decision": decision,
            "h1_artifact": h1_provenance,
            "m5_artifact": m5_provenance,
            "h1_audit": h1_audit.as_dict(),
            "m5_audit": m5_audit.as_dict(),
            "h1_derived_rows": h1_derived_rows,
            "canonical_h1": canonical,
            "h1_m5_parity": parity,
            "database_relative_path": str(
                Path("data/local/stage177b_extended_history/xauusd_extended_history.sqlite")
            ),
            "research_only": True,
            "execution_allowed": False,
        }

        summary_path = report_dir / "stage177b_summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_decision(report_dir / "stage177b_decision.md", summary)

        if data_dir.exists():
            shutil.rmtree(data_dir)
        shutil.move(str(build_data), str(data_dir))

    print(json.dumps({
        "decision": summary["decision"],
        "m5_rows": summary["m5_audit"]["rows"],
        "canonical_h1_rows": summary["canonical_h1"]["rows_total"],
        "exact_ohlc_pct": summary["h1_m5_parity"]["exact_ohlc_pct"],
        "summary": str(summary_path),
    }, indent=2))
    return 0 if summary["decision"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
