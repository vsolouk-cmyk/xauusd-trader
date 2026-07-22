#!/usr/bin/env python3
"""Controlled-paper logger for the frozen XAUUSD Stage178/Stage180 candidate.

This program never imports a broker API and never sends an order.  It consumes
only the already-frozen Stage180 observation, applies exact H1 row-position
entry/exit semantics, enforces the locked risk contract, and writes an
idempotent SQLite/CSV/JSON paper ledger.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

UTC = timezone.utc
PROGRAM_VERSION = "XAUUSD_CONTROLLED_PAPER_V1_3_EXECUTION_LEDGER_STATUS_PARSER_REPAIR"
ALLOWED_STAGE180_DECISIONS = {
    "STAGE180_FROZEN_MODEL_SHADOW_ACTIVE_NO_ORDER",
    "STAGE180_WAITING_FOR_POST_ACTIVATION_COMPLETE_BAR",
}
LOCKED_NUMERIC = {
    "threshold": 0.60,
    "entry_offset_h1_rows": 1,
    "exit_offset_h1_rows": 24,
    "maximum_notional_to_equity": 0.1570396406876166,
    "maximum_concurrent_positions": 1,
    "daily_new_positions_cap": 1,
    "weekly_loss_pause_equity_pct": 2.0,
    "hard_drawdown_kill_switch_equity_pct": 8.0,
    "normal_execution_cost_floor_bps": 3.0,
    "severe_execution_cost_floor_bps": 4.5,
    "observed_entry_spread_guard_bps": 3.0764778059487488,
    "expected_historical_signals": 168,
    "expected_execution_evaluated_trades": 146,
    "expected_missing_execution_signals": 22,
}


class ControlledPaperError(RuntimeError):
    """Blocking, fail-closed program error."""


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None = None) -> str:
    value = value or utc_now()
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if value is None:
        raise ValueError("timestamp is null")
    if isinstance(value, bool):
        raise ValueError("boolean is not a timestamp")
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("non-finite timestamp")
        if abs(numeric) >= 1e14:
            numeric /= 1_000_000.0
        elif abs(numeric) >= 1e11:
            numeric /= 1_000.0
        return datetime.fromtimestamp(numeric, tz=UTC)
    text = str(value).strip()
    if not text:
        raise ValueError("empty timestamp")
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None and math.isfinite(numeric):
        return parse_timestamp(numeric)
    normalized = text.replace("/", "-")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    )
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in formats:
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError(f"unparseable timestamp: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def timestamp_ms(value: Any) -> int:
    return int(round(parse_timestamp(value).timestamp() * 1000.0))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_name = handle.name
    os.replace(temp_name, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def atomic_write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        fieldnames = ordered
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: serialize_csv_value(row.get(key)) for key in fieldnames})
        temp_name = handle.name
    os.replace(temp_name, path)


def serialize_csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return int(value)
    return value


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def deep_values(payload: Any, key: str) -> Iterator[Any]:
    if isinstance(payload, Mapping):
        for k, value in payload.items():
            if str(k).lower() == key.lower():
                yield value
            yield from deep_values(value, key)
    elif isinstance(payload, list):
        for item in payload:
            yield from deep_values(item, key)


def deep_first(payload: Any, keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        for value in deep_values(payload, key):
            return value
    return default


def isclose(actual: Any, expected: float, tolerance: float = 1e-10) -> bool:
    try:
        return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlledPaperError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ControlledPaperError(f"JSON root must be an object: {path}")
    return payload


def resolve_existing(root: Path, candidates: Sequence[str]) -> Path:
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            return path.resolve()
    raise ControlledPaperError(f"required file not found; checked: {list(candidates)}")


def newest_glob(root: Path, patterns: Sequence[str]) -> Path:
    matches: dict[Path, float] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                matches[path.resolve()] = path.stat().st_mtime
    if not matches:
        raise ControlledPaperError(f"no files matched: {list(patterns)}")
    return max(matches, key=matches.get)


def dynamic_import_module(module_path: Path, module_name: str) -> Any:
    """Python 3.14-safe dynamic import.

    Inserting the module into sys.modules before exec_module is required for
    dataclasses and other introspection-heavy decorators.
    """
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ControlledPaperError(f"cannot create import spec: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


@dataclass(frozen=True)
class MarketTable:
    table: str
    timestamp_col: str
    open_col: str
    high_col: str
    low_col: str
    close_col: str
    spread_col: str | None
    where_sql: str
    where_params: tuple[Any, ...]
    cadence_seconds: float
    timestamp_storage: str


@dataclass(frozen=True)
class Bar:
    timestamp_ms: int
    dt_utc: str
    open: float
    high: float
    low: float
    close: float
    spread_points: float | None


@dataclass
class PreflightContext:
    config: dict[str, Any]
    stage180_path: Path
    stage180: dict[str, Any]
    commercial_summary_path: Path
    commercial_summary: dict[str, Any]
    risk_contract_path: Path
    risk_contract: dict[str, Any]
    frozen_contract_path: Path
    frozen_contract: dict[str, Any]
    frozen_model_path: Path
    aligned_db_path: Path
    market: "MarketDatabase"
    h1: MarketTable
    m5: MarketTable
    spread_provider: "SpreadProvider"
    spread_source_path: Path
    spread_time_contract_path: Path | None
    checks: dict[str, Any]


class MarketDatabase:
    TIMESTAMP_ALIASES = (
        "timestamp", "timestamp_ms", "time_utc", "utc_time", "datetime", "dt",
        "open_time", "bar_time", "time", "date_time",
    )
    OHLC_ALIASES = {
        "open": ("open", "o", "open_price"),
        "high": ("high", "h", "high_price"),
        "low": ("low", "l", "low_price"),
        "close": ("close", "c", "close_price"),
    }
    SPREAD_ALIASES = ("spread", "spread_points", "spread_pts")
    TF_ALIASES = ("timeframe", "interval", "tf", "period")

    def __init__(self, path: Path):
        self.path = path.resolve()
        if not self.path.is_file():
            raise ControlledPaperError(f"aligned market DB missing: {self.path}")
        uri = f"file:{self.path.as_posix()}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MarketDatabase":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def columns(self, table: str) -> list[str]:
        rows = self.conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
        return [str(row[1]) for row in rows]

    @staticmethod
    def _alias(columns: Sequence[str], aliases: Sequence[str]) -> str | None:
        lookup = {column.lower(): column for column in columns}
        for alias in aliases:
            if alias.lower() in lookup:
                return lookup[alias.lower()]
        return None

    def _storage_kind(self, values: Sequence[Any]) -> str:
        for value in values:
            if value is None:
                continue
            if isinstance(value, (int, float)):
                number = float(value)
                if abs(number) >= 1e14:
                    return "microseconds"
                if abs(number) >= 1e11:
                    return "milliseconds"
                return "seconds"
            text = str(value).strip()
            if not text:
                continue
            try:
                number = float(text)
            except ValueError:
                return "text"
            if abs(number) >= 1e14:
                return "microseconds"
            if abs(number) >= 1e11:
                return "milliseconds"
            return "seconds"
        return "text"

    def _cadence(self, table: str, timestamp_col: str, where_sql: str, where_params: tuple[Any, ...]) -> tuple[float, str]:
        sql = (
            f"SELECT {quote_ident(timestamp_col)} AS ts FROM {quote_ident(table)} "
            f"{where_sql} ORDER BY {quote_ident(timestamp_col)} DESC LIMIT 400"
        )
        raw = [row[0] for row in self.conn.execute(sql, where_params).fetchall()]
        parsed: list[float] = []
        for value in raw:
            try:
                parsed.append(parse_timestamp(value).timestamp())
            except (ValueError, OSError, OverflowError):
                continue
        parsed = sorted(set(parsed))
        diffs = [b - a for a, b in zip(parsed, parsed[1:]) if 0 < b - a <= 7 * 86400]
        if not diffs:
            return float("inf"), self._storage_kind(raw)
        return float(statistics.median(diffs)), self._storage_kind(raw)

    def discover(self) -> tuple[MarketTable, MarketTable, list[dict[str, Any]]]:
        specs: list[MarketTable] = []
        diagnostics: list[dict[str, Any]] = []
        for table in self.tables():
            columns = self.columns(table)
            timestamp_col = self._alias(columns, self.TIMESTAMP_ALIASES)
            ohlc = {name: self._alias(columns, aliases) for name, aliases in self.OHLC_ALIASES.items()}
            if timestamp_col is None or any(value is None for value in ohlc.values()):
                continue
            spread_col = self._alias(columns, self.SPREAD_ALIASES)
            tf_col = self._alias(columns, self.TF_ALIASES)
            variants: list[tuple[str, tuple[Any, ...], str | None]] = [("", (), None)]
            if tf_col:
                values = self.conn.execute(
                    f"SELECT DISTINCT {quote_ident(tf_col)} FROM {quote_ident(table)} "
                    f"WHERE {quote_ident(tf_col)} IS NOT NULL LIMIT 50"
                ).fetchall()
                variants = []
                for row in values:
                    tf_value = row[0]
                    text = str(tf_value).strip().lower()
                    if text in {"h1", "1h", "60", "60m", "hour", "hourly", "m5", "5m", "5", "5min"}:
                        variants.append((f"WHERE {quote_ident(tf_col)} = ?", (tf_value,), text))
                if not variants:
                    variants = [("", (), None)]
            for where_sql, where_params, tf_value in variants:
                cadence, storage = self._cadence(table, timestamp_col, where_sql, where_params)
                spec = MarketTable(
                    table=table,
                    timestamp_col=timestamp_col,
                    open_col=str(ohlc["open"]),
                    high_col=str(ohlc["high"]),
                    low_col=str(ohlc["low"]),
                    close_col=str(ohlc["close"]),
                    spread_col=spread_col,
                    where_sql=where_sql,
                    where_params=where_params,
                    cadence_seconds=cadence,
                    timestamp_storage=storage,
                )
                specs.append(spec)
                diagnostics.append({
                    "table": table,
                    "timeframe_value": tf_value,
                    "timestamp_col": timestamp_col,
                    "spread_col": spread_col,
                    "cadence_seconds": cadence,
                    "timestamp_storage": storage,
                    "columns": columns,
                })
        if not specs:
            raise ControlledPaperError("no OHLC tables discovered in aligned DB")

        def score(spec: MarketTable, target: float, tokens: Sequence[str]) -> float:
            cadence_error = abs(spec.cadence_seconds - target) / target if math.isfinite(spec.cadence_seconds) else 999.0
            name = spec.table.lower() + " " + spec.where_sql.lower() + " " + " ".join(map(str, spec.where_params)).lower()
            bonus = -0.25 if any(token in name for token in tokens) else 0.0
            return cadence_error + bonus

        h1 = min(specs, key=lambda item: score(item, 3600.0, ("h1", "1h", "hour")))
        m5 = min(specs, key=lambda item: score(item, 300.0, ("m5", "5m", "5min")))
        if abs(h1.cadence_seconds - 3600.0) > 900.0:
            raise ControlledPaperError(f"H1 table cadence invalid: {h1}")
        if abs(m5.cadence_seconds - 300.0) > 120.0:
            raise ControlledPaperError(f"M5 table cadence invalid: {m5}")
        return h1, m5, diagnostics

    @staticmethod
    def _bar_from_row(row: sqlite3.Row) -> Bar:
        ts = timestamp_ms(row["ts"])
        return Bar(
            timestamp_ms=ts,
            dt_utc=iso_utc(datetime.fromtimestamp(ts / 1000.0, tz=UTC)),
            open=float(row["o"]),
            high=float(row["h"]),
            low=float(row["l"]),
            close=float(row["c"]),
            spread_points=float(row["s"]) if row["s"] is not None else None,
        )

    def load_all(self, spec: MarketTable) -> list[Bar]:
        spread_expr = quote_ident(spec.spread_col) if spec.spread_col else "NULL"
        sql = (
            f"SELECT {quote_ident(spec.timestamp_col)} AS ts, {quote_ident(spec.open_col)} AS o, "
            f"{quote_ident(spec.high_col)} AS h, {quote_ident(spec.low_col)} AS l, "
            f"{quote_ident(spec.close_col)} AS c, {spread_expr} AS s "
            f"FROM {quote_ident(spec.table)} {spec.where_sql} "
            f"ORDER BY {quote_ident(spec.timestamp_col)}"
        )
        bars: list[Bar] = []
        for row in self.conn.execute(sql, spec.where_params):
            try:
                bar = self._bar_from_row(row)
            except (TypeError, ValueError, OverflowError, OSError):
                continue
            if min(bar.open, bar.high, bar.low, bar.close) <= 0:
                continue
            if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
                continue
            bars.append(bar)
        dedup = {bar.timestamp_ms: bar for bar in bars}
        return [dedup[key] for key in sorted(dedup)]

    def bucket(self, spec: MarketTable, start_ms: int, end_ms: int) -> list[Bar]:
        spread_expr = quote_ident(spec.spread_col) if spec.spread_col else "NULL"
        conditions = []
        params: list[Any] = list(spec.where_params)
        if spec.where_sql:
            conditions.append(spec.where_sql.removeprefix("WHERE "))
        tsq = quote_ident(spec.timestamp_col)
        if spec.timestamp_storage == "milliseconds":
            conditions.append(f"{tsq} >= ? AND {tsq} < ?")
            params.extend([start_ms, end_ms])
        elif spec.timestamp_storage == "microseconds":
            conditions.append(f"{tsq} >= ? AND {tsq} < ?")
            params.extend([start_ms * 1000, end_ms * 1000])
        elif spec.timestamp_storage == "seconds":
            conditions.append(f"{tsq} >= ? AND {tsq} < ?")
            params.extend([start_ms / 1000.0, end_ms / 1000.0])
        else:
            conditions.append(f"datetime({tsq}) >= datetime(?) AND datetime({tsq}) < datetime(?)")
            params.extend([
                datetime.fromtimestamp(start_ms / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
                datetime.fromtimestamp(end_ms / 1000.0, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
            ])
        where = "WHERE " + " AND ".join(f"({condition})" for condition in conditions)
        sql = (
            f"SELECT {tsq} AS ts, {quote_ident(spec.open_col)} AS o, {quote_ident(spec.high_col)} AS h, "
            f"{quote_ident(spec.low_col)} AS l, {quote_ident(spec.close_col)} AS c, {spread_expr} AS s "
            f"FROM {quote_ident(spec.table)} {where} ORDER BY {tsq}"
        )
        bars: list[Bar] = []
        for row in self.conn.execute(sql, tuple(params)):
            try:
                bars.append(self._bar_from_row(row))
            except (TypeError, ValueError, OverflowError, OSError):
                continue
        dedup = {bar.timestamp_ms: bar for bar in bars}
        return [dedup[key] for key in sorted(dedup)]

    def latest_timestamp_ms(self, spec: MarketTable) -> int:
        sql = (
            f"SELECT {quote_ident(spec.timestamp_col)} AS ts FROM {quote_ident(spec.table)} "
            f"{spec.where_sql} ORDER BY {quote_ident(spec.timestamp_col)} DESC LIMIT 1"
        )
        row = self.conn.execute(sql, spec.where_params).fetchone()
        if row is None:
            raise ControlledPaperError(f"market table is empty: {spec.table}")
        return timestamp_ms(row[0])


@dataclass(frozen=True)
class SpreadBucket:
    source: str
    row_count: int
    first_spread_points: float | None
    first_timestamp_ms: int | None
    last_timestamp_ms: int | None


class SpreadProvider:
    source_path: Path

    def bucket(self, start_ms: int, end_ms: int) -> SpreadBucket:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        raise NotImplementedError


class DatabaseSpreadProvider(SpreadProvider):
    def __init__(self, market: MarketDatabase, spec: MarketTable):
        if spec.spread_col is None:
            raise ControlledPaperError("database spread provider requires a spread column")
        self.market = market
        self.spec = spec
        self.source_path = market.path

    def bucket(self, start_ms: int, end_ms: int) -> SpreadBucket:
        rows = self.market.bucket(self.spec, start_ms, end_ms)
        first = next((row.spread_points for row in rows if row.spread_points is not None and row.spread_points >= 0), None)
        return SpreadBucket(
            source="ALIGNED_DB_M5_SPREAD",
            row_count=len(rows),
            first_spread_points=first,
            first_timestamp_ms=rows[0].timestamp_ms if rows else None,
            last_timestamp_ms=rows[-1].timestamp_ms if rows else None,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "ALIGNED_DB_M5_SPREAD",
            "path": str(self.source_path),
            "table": self.spec.table,
            "spread_column": self.spec.spread_col,
            "pass": True,
        }


def last_sunday(year: int, month: int) -> datetime:
    day = calendar.monthrange(year, month)[1]
    dt = datetime(year, month, day, tzinfo=UTC)
    return dt - timedelta(days=(dt.weekday() + 1) % 7)


def eu_dst_active_utc(dt_utc: datetime) -> bool:
    dt_utc = dt_utc.astimezone(UTC)
    start = last_sunday(dt_utc.year, 3).replace(hour=1)
    end = last_sunday(dt_utc.year, 10).replace(hour=1)
    return start <= dt_utc < end


def parse_amarkets_naive(date_value: Any, time_value: Any) -> datetime:
    text = f"{str(date_value).strip()} {str(time_value).strip()}".replace("/", ".").replace("-", ".")
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"unparseable AMarkets date/time: {date_value!r} {time_value!r}")


def broker_naive_to_utc(naive: datetime, standard_shift_minutes: int, dst_shift_minutes: int) -> datetime:
    if naive.tzinfo is not None:
        naive = naive.replace(tzinfo=None)
    dst_candidate = (naive + timedelta(minutes=dst_shift_minutes)).replace(tzinfo=UTC)
    if eu_dst_active_utc(dst_candidate):
        return dst_candidate
    return (naive + timedelta(minutes=standard_shift_minutes)).replace(tzinfo=UTC)


def detect_delimiter(header_line: str) -> str:
    counts = {"\t": header_line.count("\t"), ",": header_line.count(","), ";": header_line.count(";")}
    delimiter = max(counts, key=counts.get)
    if counts[delimiter] <= 0:
        raise ControlledPaperError("cannot detect AMarkets M5 CSV delimiter")
    return delimiter


def normalized_header(value: str) -> str:
    return value.strip().strip("<>").strip().lower().replace(" ", "_")


def tail_lines(path: Path, count: int = 600, block_size: int = 65536) -> list[str]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        chunks: list[bytes] = []
        newline_count = 0
        while position > 0 and newline_count <= count:
            take = min(block_size, position)
            position -= take
            handle.seek(position)
            chunk = handle.read(take)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")
    text = b"".join(reversed(chunks)).decode("utf-8-sig", errors="replace")
    return [line for line in text.splitlines() if line.strip()][-count:]


class AMarketsCsvSpreadProvider(SpreadProvider):
    REQUIRED = ("date", "time", "open", "high", "low", "close", "spread")

    def __init__(
        self,
        path: Path,
        *,
        standard_shift_minutes: int,
        dst_shift_minutes: int,
        dst_calendar: str,
    ):
        self.source_path = path.resolve()
        self.standard_shift_minutes = int(standard_shift_minutes)
        self.dst_shift_minutes = int(dst_shift_minutes)
        self.dst_calendar = str(dst_calendar).upper()
        if self.dst_calendar != "EU":
            raise ControlledPaperError(f"unsupported spread-source DST calendar: {dst_calendar}")
        if not self.source_path.is_file():
            raise ControlledPaperError(f"AMarkets M5 spread source missing: {self.source_path}")
        with self.source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            header_line = handle.readline().rstrip("\r\n")
        self.delimiter = detect_delimiter(header_line)
        raw_headers = next(csv.reader([header_line], delimiter=self.delimiter))
        self.header_map = {normalized_header(value): value for value in raw_headers}
        missing = [name for name in self.REQUIRED if name not in self.header_map]
        if missing:
            raise ControlledPaperError(f"AMarkets M5 spread source missing columns: {missing}")

    def _parse_row(self, row: Mapping[str, Any]) -> tuple[int, float, float] | None:
        try:
            naive = parse_amarkets_naive(row[self.header_map["date"]], row[self.header_map["time"]])
            dt_utc = broker_naive_to_utc(naive, self.standard_shift_minutes, self.dst_shift_minutes)
            spread = float(row[self.header_map["spread"]])
            close = float(row[self.header_map["close"]])
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(spread) or spread < 0 or not math.isfinite(close) or close <= 0:
            return None
        return int(round(dt_utc.timestamp() * 1000.0)), spread, close

    def _tail_records(self, count: int = 600) -> list[tuple[int, float, float]]:
        with self.source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            header_line = handle.readline().rstrip("\r\n")
        lines = tail_lines(self.source_path, count=count)
        if lines and lines[0].lstrip("\ufeff") == header_line.lstrip("\ufeff"):
            lines = lines[1:]
        reader = csv.DictReader([header_line, *lines], delimiter=self.delimiter)
        records = [parsed for row in reader if (parsed := self._parse_row(row)) is not None]
        dedup = {record[0]: record for record in records}
        return [dedup[key] for key in sorted(dedup)]

    def audit_against_market(self, market: MarketDatabase, m5: MarketTable, max_lag_minutes: float) -> dict[str, Any]:
        records = self._tail_records(600)
        if len(records) < 60:
            raise ControlledPaperError(f"insufficient valid tail rows in AMarkets M5 spread source: {len(records)}")
        timestamps = [record[0] for record in records]
        diffs = [(b - a) / 1000.0 for a, b in zip(timestamps, timestamps[1:]) if 0 < b - a <= 86400000]
        cadence = float(statistics.median(diffs)) if diffs else float("inf")
        start_ms, end_ms = timestamps[0], timestamps[-1] + 300000
        aligned = {bar.timestamp_ms: bar for bar in market.bucket(m5, start_ms, end_ms)}
        overlap = []
        for ts, _, close in records:
            bar = aligned.get(ts)
            if bar is not None:
                overlap.append(abs(close / bar.close - 1.0) * 10000.0)
        latest_aligned = market.latest_timestamp_ms(m5)
        latest_source = timestamps[-1]
        lag_minutes = abs(latest_source - latest_aligned) / 60000.0
        median_close_diff_bps = float(statistics.median(overlap)) if overlap else float("inf")
        audit = {
            "kind": "AMARKETS_M5_RAW_CSV_SPREAD",
            "path": str(self.source_path),
            "delimiter": "TAB" if self.delimiter == "\t" else self.delimiter,
            "standard_shift_minutes": self.standard_shift_minutes,
            "dst_shift_minutes": self.dst_shift_minutes,
            "dst_calendar": self.dst_calendar,
            "tail_valid_rows": len(records),
            "tail_cadence_seconds": cadence,
            "tail_overlap_rows": len(overlap),
            "tail_median_close_diff_bps": median_close_diff_bps,
            "latest_source_utc": iso_utc(datetime.fromtimestamp(latest_source / 1000.0, tz=UTC)),
            "latest_aligned_m5_utc": iso_utc(datetime.fromtimestamp(latest_aligned / 1000.0, tz=UTC)),
            "latest_lag_minutes": lag_minutes,
        }
        audit["checks"] = {
            "cadence_is_m5": abs(cadence - 300.0) <= 30.0,
            "minimum_tail_overlap": len(overlap) >= 50,
            "close_parity": median_close_diff_bps <= 0.10,
            "latest_alignment": lag_minutes <= float(max_lag_minutes),
        }
        audit["pass"] = all(audit["checks"].values())
        if not audit["pass"]:
            raise ControlledPaperError(f"AMarkets M5 spread source parity failed: {audit}")
        return audit

    def bucket(self, start_ms: int, end_ms: int) -> SpreadBucket:
        count = 0
        first_spread: float | None = None
        first_ts: int | None = None
        last_ts: int | None = None
        with self.source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=self.delimiter)
            for row in reader:
                parsed = self._parse_row(row)
                if parsed is None:
                    continue
                ts, spread, _ = parsed
                if ts < start_ms:
                    continue
                if ts >= end_ms:
                    break
                count += 1
                if first_spread is None:
                    first_spread = spread
                    first_ts = ts
                last_ts = ts
        return SpreadBucket(
            source="AMARKETS_M5_RAW_CSV_SPREAD",
            row_count=count,
            first_spread_points=first_spread,
            first_timestamp_ms=first_ts,
            last_timestamp_ms=last_ts,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "AMARKETS_M5_RAW_CSV_SPREAD",
            "path": str(self.source_path),
            "standard_shift_minutes": self.standard_shift_minutes,
            "dst_shift_minutes": self.dst_shift_minutes,
            "dst_calendar": self.dst_calendar,
            "pass": True,
        }


def normalized_contract_token(value: Any) -> str:
    return str(value or "").strip().upper()


def validate_spread_time_contract(time_contract: Mapping[str, Any]) -> dict[str, Any]:
    """Validate Stage177C by substantive semantics, not brittle raw-string equality.

    The primary route requires the canonical PASS decision.  A secondary route
    is allowed only when the JSON carries the exact Stage177C semantics used to
    derive the broker-to-UTC mapping.  This keeps the bridge fail-closed while
    tolerating harmless whitespace/casing or legacy omission of the decision
    field.
    """
    try:
        standard_shift = int(time_contract.get("standard_shift_minutes"))
        dst_shift = int(time_contract.get("dst_shift_minutes"))
    except (TypeError, ValueError):
        standard_shift = None
        dst_shift = None

    contract_token = normalized_contract_token(time_contract.get("contract"))
    calendar_token = normalized_contract_token(time_contract.get("dst_calendar"))
    decision_token = normalized_contract_token(time_contract.get("decision"))
    stage_token = normalized_contract_token(time_contract.get("stage"))
    shift_semantics = " ".join(str(time_contract.get("shift_semantics") or "").strip().lower().split())
    selection_used_holdout = time_contract.get("selection_used_holdout")

    structural_checks = {
        "contract": contract_token == "EU_DST_GMT_OFFSET_PAIR",
        "dst_calendar": calendar_token == "EU",
        "standard_shift_minutes": standard_shift == -120,
        "dst_shift_minutes": dst_shift == -180,
        "shift_semantics": shift_semantics == "timestamp_utc = timestamp_naive + shift_minutes",
        "selection_no_holdout": selection_used_holdout is False,
    }
    canonical_decision = decision_token == "PASS_AMARKETS_DST_AWARE_UTC_CONTRACT"
    semantic_evidence = stage_token in {"177C", "STAGE177C"}
    passed = all(structural_checks.values()) and (canonical_decision or semantic_evidence)
    return {
        "pass": passed,
        "evidence_route": (
            "CANONICAL_PASS_DECISION" if canonical_decision
            else "EXACT_STAGE177C_SEMANTICS" if semantic_evidence
            else "NONE"
        ),
        "checks": {
            **structural_checks,
            "canonical_pass_decision": canonical_decision,
            "exact_stage177c_semantics": semantic_evidence,
        },
        "contract": time_contract.get("contract"),
        "decision": time_contract.get("decision"),
        "stage": time_contract.get("stage"),
        "shift_semantics": time_contract.get("shift_semantics"),
        "selection_used_holdout": selection_used_holdout,
        "standard_shift_minutes": time_contract.get("standard_shift_minutes"),
        "dst_shift_minutes": time_contract.get("dst_shift_minutes"),
        "dst_calendar": time_contract.get("dst_calendar"),
    }


def stage180_m5_source_candidates(stage180: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    for value in deep_values(stage180, "sources"):
        if isinstance(value, list):
            for item in value:
                text = str(item)
                if "5m" in Path(text).name.lower() or "m5" in Path(text).name.lower():
                    found.append(text)
    return found


class EventGuard:
    def __init__(self, root: Path, config: Mapping[str, Any]):
        self.root = root
        self.config = dict(config)

    def evaluate(self, entry_ms: int) -> tuple[bool, str, dict[str, Any]]:
        csv_result = self._from_csv(entry_ms)
        if csv_result is not None:
            return csv_result
        db_result = self._from_macro_db(entry_ms)
        if db_result is not None:
            return db_result
        if bool(self.config.get("required", True)):
            return False, "EVENT_DATA_ABSENT_FAIL_CLOSED", {"entry_utc": iso_utc(datetime.fromtimestamp(entry_ms / 1000, tz=UTC))}
        return True, "EVENT_GUARD_NOT_REQUIRED", {}

    def _from_csv(self, entry_ms: int) -> tuple[bool, str, dict[str, Any]] | None:
        candidates = self.config.get("csv_candidates", [])
        for candidate in candidates:
            path = self.root / candidate
            if not path.is_file():
                continue
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            if not rows:
                continue
            for row in rows:
                event_value = first_present(row, ("event_time_utc", "event_utc", "timestamp", "time_utc"))
                if not event_value:
                    continue
                try:
                    event_ms = timestamp_ms(event_value)
                except ValueError:
                    continue
                before = float(row.get("blackout_before_minutes") or 60.0)
                after = float(row.get("blackout_after_minutes") or 60.0)
                if event_ms - int(before * 60000) <= entry_ms <= event_ms + int(after * 60000):
                    return False, "EVENT_BLACKOUT_ACTIVE", {
                        "source": str(path),
                        "title": row.get("title"),
                        "event_time_utc": iso_utc(datetime.fromtimestamp(event_ms / 1000, tz=UTC)),
                        "before_minutes": before,
                        "after_minutes": after,
                    }
            return True, "EVENT_CSV_PRESENT_NO_BLACKOUT", {"source": str(path), "rows": len(rows)}
        return None

    def _from_macro_db(self, entry_ms: int) -> tuple[bool, str, dict[str, Any]] | None:
        for candidate in self.config.get("macro_db_candidates", []):
            path = self.root / candidate
            if not path.is_file():
                continue
            uri = f"file:{path.resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            try:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in self.config.get("macro_table_candidates", ["macro_context_h1"]):
                    if table not in tables:
                        continue
                    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({quote_ident(table)})")]
                    ts_col = find_alias(columns, ("utc_time", "time_utc", "timestamp", "timestamp_ms", "dt"))
                    block_col = find_alias(columns, ("has_block_event", "block_event", "event_blackout", "is_blocked"))
                    if not ts_col or not block_col:
                        continue
                    sample = conn.execute(
                        f"SELECT {quote_ident(ts_col)} FROM {quote_ident(table)} WHERE {quote_ident(ts_col)} IS NOT NULL LIMIT 1"
                    ).fetchone()
                    storage = "text"
                    if sample is not None:
                        value = sample[0]
                        if isinstance(value, (int, float)):
                            storage = "milliseconds" if abs(float(value)) >= 1e11 else "seconds"
                    start_ms = entry_ms
                    end_ms = entry_ms + 3600 * 1000
                    if storage == "milliseconds":
                        where = f"{quote_ident(ts_col)} >= ? AND {quote_ident(ts_col)} < ?"
                        params = (start_ms, end_ms)
                    elif storage == "seconds":
                        where = f"{quote_ident(ts_col)} >= ? AND {quote_ident(ts_col)} < ?"
                        params = (start_ms / 1000.0, end_ms / 1000.0)
                    else:
                        where = f"datetime({quote_ident(ts_col)}) >= datetime(?) AND datetime({quote_ident(ts_col)}) < datetime(?)"
                        params = (
                            datetime.fromtimestamp(start_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
                            datetime.fromtimestamp(end_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
                        )
                    rows = conn.execute(
                        f"SELECT * FROM {quote_ident(table)} WHERE {where} ORDER BY {quote_ident(ts_col)} DESC LIMIT 5",
                        params,
                    ).fetchall()
                    if not rows:
                        return False, "EVENT_CONTEXT_ROW_MISSING_FAIL_CLOSED", {
                            "source": str(path), "table": table,
                            "entry_utc": iso_utc(datetime.fromtimestamp(entry_ms / 1000, tz=UTC)),
                        }
                    blocked = any(truthy(row[block_col]) for row in rows)
                    if blocked:
                        return False, "EVENT_BLACKOUT_ACTIVE", {"source": str(path), "table": table, "rows": len(rows)}
                    return True, "EVENT_CONTEXT_PRESENT_NO_BLOCK", {"source": str(path), "table": table, "rows": len(rows)}
            finally:
                conn.close()
        return None


def find_alias(columns: Sequence[str], aliases: Sequence[str]) -> str | None:
    lookup = {str(column).lower(): str(column) for column in columns}
    for alias in aliases:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    return None


def first_present(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    lookup = {str(key).lower(): value for key, value in row.items()}
    for alias in aliases:
        value = lookup.get(alias.lower())
        if value not in (None, ""):
            return value
    return None


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "block", "blocked"}


def load_config(root: Path, config_path: Path | None) -> dict[str, Any]:
    path = config_path or root / "config/xauusd_controlled_paper.json"
    if not path.is_absolute():
        path = root / path
    config = load_json(path.resolve())
    if config.get("program") != "XAUUSD_CONTROLLED_PAPER":
        raise ControlledPaperError("config program mismatch")
    if config.get("mode") != "PAPER_LOG_ONLY_NO_BROKER":
        raise ControlledPaperError("config mode must remain PAPER_LOG_ONLY_NO_BROKER")
    if config.get("candidate") != "logistic__direction_24h":
        raise ControlledPaperError("frozen candidate mismatch")
    if config.get("model") != "logistic" or config.get("target") != "direction_24h":
        raise ControlledPaperError("frozen model/target mismatch")
    for key, expected in LOCKED_NUMERIC.items():
        if not isclose(config.get(key), expected):
            raise ControlledPaperError(f"locked config mismatch {key}: {config.get(key)!r} != {expected!r}")
    if config.get("direction") != "LONG_ONLY":
        raise ControlledPaperError("direction must remain LONG_ONLY")
    if not bool(config.get("event_guard", {}).get("required", True)):
        raise ControlledPaperError("event guard cannot be disabled")
    return config


def validate_preflight(root: Path, config: dict[str, Any]) -> PreflightContext:
    checks: dict[str, Any] = {}
    stage180_path = newest_glob(root, config["stage180_summary_globs"])
    stage180 = load_json(stage180_path)
    decision = stage180.get("decision")
    checks["stage180_decision"] = decision in ALLOWED_STAGE180_DECISIONS
    checks["stage180_execution_forbidden"] = all(
        stage180.get(key) is False
        for key in ("broker_order_allowed", "demo_order_allowed", "live_order_allowed", "paper_order_allowed", "execution_allowed")
    )
    checks["stage180_shadow_allowed"] = stage180.get("shadow_observation_allowed") is True
    if not all((checks["stage180_decision"], checks["stage180_execution_forbidden"], checks["stage180_shadow_allowed"])):
        raise ControlledPaperError(f"Stage180 boundary invalid: {checks}")

    commercial_summary_path = newest_glob(root, config["commercial_summary_globs"])
    commercial_summary = load_json(commercial_summary_path)
    gates = commercial_summary.get("gates", {})
    false_gates = sorted(key for key, value in gates.items() if value is False)
    checks["commercial_only_coverage_failed"] = false_gates == ["minimum_execution_coverage"]
    checks["commercial_counts"] = (
        int(commercial_summary.get("signals_total", -1)) == int(config["expected_historical_signals"])
        and int(commercial_summary.get("execution_evaluated_trades", -1)) == int(config["expected_execution_evaluated_trades"])
    )
    checks["commercial_reference_parity"] = bool(commercial_summary.get("reference_parity", {}).get("pass"))
    if not all((checks["commercial_only_coverage_failed"], checks["commercial_counts"], checks["commercial_reference_parity"])):
        raise ControlledPaperError(f"commercial closure contract mismatch: {checks}")

    risk_contract_path = newest_glob(root, config["risk_contract_globs"])
    risk_contract = load_json(risk_contract_path)
    for key in (
        "maximum_notional_to_equity", "maximum_concurrent_positions", "daily_new_positions_cap",
        "weekly_loss_pause_equity_pct", "hard_drawdown_kill_switch_equity_pct",
        "normal_execution_cost_floor_bps", "severe_execution_cost_floor_bps",
    ):
        expected = config[key]
        if not isclose(risk_contract.get(key), expected):
            raise ControlledPaperError(f"risk contract mismatch {key}: {risk_contract.get(key)!r} != {expected!r}")
    checks["risk_demo_live_forbidden"] = risk_contract.get("demo_allowed") is False and risk_contract.get("live_allowed") is False
    checks["risk_paper_only"] = risk_contract.get("paper_only") is True
    if not checks["risk_demo_live_forbidden"] or not checks["risk_paper_only"]:
        raise ControlledPaperError("risk contract does not enforce paper-only boundary")

    frozen_model_path = resolve_existing(root, config["frozen_model_candidates"])
    frozen_contract_path = resolve_existing(root, config["frozen_contract_candidates"])
    frozen_contract = load_json(frozen_contract_path)
    contract_candidate = deep_first(frozen_contract, ("candidate", "candidate_name"))
    contract_model = deep_first(frozen_contract, ("model", "model_name", "estimator"))
    contract_target = deep_first(frozen_contract, ("target", "target_name"))
    contract_threshold = deep_first(frozen_contract, ("threshold", "probability_threshold", "signal_threshold"))
    contract_horizon = deep_first(frozen_contract, ("horizon_hours", "horizon_h1_rows", "horizon"))
    checks["contract_candidate"] = str(contract_candidate) == config["candidate"]
    checks["contract_model"] = "logistic" in str(contract_model).lower()
    checks["contract_target"] = str(contract_target) == config["target"]
    checks["contract_threshold"] = isclose(contract_threshold, config["threshold"])
    checks["contract_horizon"] = isclose(contract_horizon, config["exit_offset_h1_rows"])
    selection_used_holdout = deep_first(frozen_contract, ("selection_used_holdout",), default=False)
    checks["contract_selection_no_holdout"] = selection_used_holdout is False
    if not all(checks[key] for key in (
        "contract_candidate", "contract_model", "contract_target", "contract_threshold",
        "contract_horizon", "contract_selection_no_holdout",
    )):
        raise ControlledPaperError(f"frozen model contract mismatch: {checks}")

    summary_model_hash = stage180.get("model_sha256")
    summary_contract_hash = stage180.get("contract_sha256")
    checks["model_hash"] = bool(summary_model_hash) and sha256_file(frozen_model_path) == summary_model_hash
    checks["contract_hash"] = bool(summary_contract_hash) and sha256_file(frozen_contract_path) == summary_contract_hash
    if not checks["model_hash"] or not checks["contract_hash"]:
        raise ControlledPaperError("frozen model/contract hash mismatch against Stage180")

    aligned_candidates = list(config["aligned_db_candidates"])
    if stage180.get("aligned_db"):
        aligned_candidates.insert(0, str(stage180["aligned_db"]))
    aligned_db_path = resolve_existing(root, aligned_candidates)
    market = MarketDatabase(aligned_db_path)
    spread_time_contract_path: Path | None = None
    try:
        h1, m5, diagnostics = market.discover()
        checks["market_schema_introspection"] = diagnostics
        checks["h1_table"] = asdict(h1)
        checks["m5_table"] = asdict(m5)
        checks["m5_spread_present_in_aligned_db"] = m5.spread_col is not None
        if m5.spread_col is not None:
            spread_provider: SpreadProvider = DatabaseSpreadProvider(market, m5)
            spread_source_path = aligned_db_path
            checks["spread_source"] = spread_provider.describe()
        else:
            spread_cfg = dict(config.get("spread_source", {}))
            spread_time_contract_path = newest_glob(root, spread_cfg.get("time_contract_globs", []))
            time_contract = load_json(spread_time_contract_path)
            contract_audit = validate_spread_time_contract(time_contract)
            checks["spread_time_contract"] = {
                "path": str(spread_time_contract_path),
                **contract_audit,
            }
            if not contract_audit["pass"]:
                raise ControlledPaperError(f"spread-source time contract mismatch: {checks['spread_time_contract']}")
            spread_candidates = []
            if time_contract.get("source_amarkets_m5"):
                spread_candidates.append(str(time_contract["source_amarkets_m5"]))
            spread_candidates.extend(stage180_m5_source_candidates(stage180))
            spread_candidates.extend(spread_cfg.get("csv_candidates", []))
            spread_source_path = resolve_existing(root, spread_candidates)
            csv_provider = AMarketsCsvSpreadProvider(
                spread_source_path,
                standard_shift_minutes=int(time_contract["standard_shift_minutes"]),
                dst_shift_minutes=int(time_contract["dst_shift_minutes"]),
                dst_calendar=str(time_contract["dst_calendar"]),
            )
            checks["spread_source"] = csv_provider.audit_against_market(
                market, m5, float(spread_cfg.get("maximum_latest_lag_minutes", 15.0))
            )
            spread_provider = csv_provider
    except Exception:
        market.close()
        raise

    return PreflightContext(
        config=config,
        stage180_path=stage180_path,
        stage180=stage180,
        commercial_summary_path=commercial_summary_path,
        commercial_summary=commercial_summary,
        risk_contract_path=risk_contract_path,
        risk_contract=risk_contract,
        frozen_contract_path=frozen_contract_path,
        frozen_contract=frozen_contract,
        frozen_model_path=frozen_model_path,
        aligned_db_path=aligned_db_path,
        market=market,
        h1=h1,
        m5=m5,
        spread_provider=spread_provider,
        spread_source_path=spread_source_path,
        spread_time_contract_path=spread_time_contract_path,
        checks=checks,
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def signal_key_from_row(row: Mapping[str, Any]) -> str | None:
    value = first_present(row, (
        "signal_dt", "signal_time_utc", "signal_utc", "signal_time", "signal_timestamp",
        "feature_date", "timestamp", "time_utc", "utc_time",
    ))
    if value is None:
        return None
    try:
        return str(timestamp_ms(value))
    except (ValueError, OSError, OverflowError):
        return str(value).strip() or None


def normalized_status(value: Any) -> str:
    """Normalize a ledger status without substring ambiguity.

    In particular, ``UNEVALUATED`` must never be treated as ``EVALUATED`` merely
    because the latter is a substring of the former.
    """
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


def finite_field(row: Mapping[str, Any], aliases: Sequence[str]) -> bool:
    value = first_present(row, aliases)
    if value in (None, ""):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def coverage_row_classification(row: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Classify one commercial-closure ledger row.

    The Stage180 closure ledger carries all 168 signals in one file.  The 146
    execution-evaluated rows contain execution fields, while the 22 uncovered
    rows retain research fields but have a missing/unevaluated status and no
    complete execution outcome.  Status negatives are evaluated before
    positives, and research-only values are intentionally not accepted as
    execution evidence.
    """
    raw_status = first_present(row, ("execution_status", "status", "evaluation_status", "outcome_status"))
    status = normalized_status(raw_status)
    tokens = {token for token in status.split("_") if token}

    negative = (
        "UNEVALUATED" in tokens
        or "UNRESOLVED" in tokens
        or "MISSING" in tokens
        or "BLOCKED" in tokens
        or "UNAVAILABLE" in tokens
        or "INCOMPLETE" in tokens
        or "NO_COVERAGE" in status
        or "NO_EXECUTION" in status
        or "NOT_EVALUATED" in status
    )
    positive = bool(
        tokens.intersection({"EVALUATED", "RESOLVED", "EXECUTED", "COMPLETE", "COMPLETED"})
    )

    evidence = {
        "entry": finite_field(row, ("entry_open", "entry_price", "execution_entry_price")),
        "exit": finite_field(row, ("exit_close", "exit_price", "execution_exit_price")),
        "m5_gross": finite_field(row, ("m5_gross_bps", "execution_gross_bps", "gross_transfer_difference_bps")),
        "normal_net": finite_field(row, ("normal_net_bps", "net_normal_bps", "execution_net_bps", "net_bps")),
        "severe_net": finite_field(row, ("severe_net_bps", "net_severe_bps")),
        "observed_spread": finite_field(row, ("observed_spread_bps", "entry_spread_bps")),
    }
    complete_execution = evidence["normal_net"] or (
        evidence["entry"] and evidence["exit"] and evidence["m5_gross"]
    )
    any_execution = any(evidence.values())

    diagnostic = {
        "status_raw": "" if raw_status is None else str(raw_status),
        "status_normalized": status,
        "status_negative": negative,
        "status_positive": positive,
        "execution_evidence": evidence,
        "complete_execution_evidence": complete_execution,
    }

    # Negative status has precedence over positive-looking substrings such as
    # UNEVALUATED. Partial execution fields are expected for some coverage
    # failures and remain missing; a fully calculated net result conflicts with
    # a negative status and is therefore fail-closed.
    if negative:
        if complete_execution:
            return "CONFLICT", diagnostic
        return "MISSING", diagnostic

    if positive:
        if complete_execution:
            return "EVALUATED", diagnostic
        return "CONFLICT", diagnostic

    # Some historical ledgers used neutral status labels. Strong execution
    # evidence is sufficient; no execution evidence is a missing row. Partial
    # evidence without an explicit negative reason is ambiguous and blocks.
    if complete_execution:
        return "EVALUATED", diagnostic
    if not any_execution:
        return "MISSING", diagnostic
    return "CONFLICT", diagnostic


def row_has_execution(row: Mapping[str, Any]) -> bool:
    """Compatibility wrapper used by external callers and tests."""
    classification, _ = coverage_row_classification(row)
    return classification == "EVALUATED"


def coverage_candidate_rank(path: Path) -> tuple[int, int, str]:
    text = str(path).lower()
    penalty = 0
    if any(token in text for token in ("invalid", "archive", "backup", "old", "tmp")):
        penalty += 100
    if path.name == "commercial_closure_execution_ledger.csv":
        penalty -= 20
    elif "execution_ledger" in path.name:
        penalty -= 10
    return penalty, len(path.parts), text


def locate_coverage_rows(root: Path, config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    files: list[Path] = []
    for pattern in config["commercial_csv_globs"]:
        files.extend(path.resolve() for path in root.glob(pattern) if path.is_file())
    unique = sorted(set(files), key=coverage_candidate_rank)
    candidates: list[tuple[Path, list[dict[str, str]]]] = []
    inventory: list[dict[str, Any]] = []
    for path in unique:
        try:
            rows = read_csv(path)
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
        headers = list(rows[0].keys()) if rows else []
        item: dict[str, Any] = {"path": str(path), "rows": len(rows), "headers": headers}
        if rows and any(alias in headers for alias in ("status", "execution_status", "evaluation_status", "outcome_status")):
            status_counts: dict[str, int] = {}
            for row in rows:
                status = normalized_status(first_present(row, ("execution_status", "status", "evaluation_status", "outcome_status"))) or "<EMPTY>"
                status_counts[status] = status_counts.get(status, 0) + 1
            item["status_counts"] = status_counts
        inventory.append(item)
        if rows:
            candidates.append((path, rows))

    expected_signals = int(config["expected_historical_signals"])
    expected_evaluated = int(config["expected_execution_evaluated_trades"])
    expected_missing = int(config["expected_missing_execution_signals"])
    signal_candidates = [(path, rows) for path, rows in candidates if len(rows) == expected_signals]
    trade_candidates = [(path, rows) for path, rows in candidates if len(rows) == expected_evaluated]
    candidate_diagnostics: list[dict[str, Any]] = []

    # Preferred and production schema: one 168-row execution ledger containing
    # both the 146 evaluated rows and the 22 uncovered rows.
    for path, rows in signal_candidates:
        evaluated: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        classification_counts = {"EVALUATED": 0, "MISSING": 0, "CONFLICT": 0}
        for index, row in enumerate(rows):
            classification, diagnostic = coverage_row_classification(row)
            classification_counts[classification] += 1
            if classification == "EVALUATED":
                evaluated.append(dict(row))
            elif classification == "MISSING":
                missing.append(dict(row))
            else:
                if len(conflicts) < 10:
                    conflicts.append({"row_index": index, **diagnostic})
        candidate_diagnostics.append({
            "path": str(path),
            "classification_counts": classification_counts,
            "conflict_examples": conflicts,
        })
        if (
            not conflicts
            and len(evaluated) == expected_evaluated
            and len(missing) == expected_missing
        ):
            return evaluated, missing, {
                "mode": "single_execution_ledger_status_and_fields",
                "signal_source": str(path),
                "classification_counts": classification_counts,
                "inventory": inventory,
            }

    # Alternative legacy shape: a 168-row signal file and a separate 146-row
    # execution file, diffed by timestamp key.
    for signal_path, signals in signal_candidates:
        signal_keys = {signal_key_from_row(row) for row in signals}
        if None in signal_keys or len(signal_keys) != len(signals):
            continue
        for trade_path, trades in trade_candidates:
            trade_keys = {signal_key_from_row(row) for row in trades}
            if None in trade_keys:
                continue
            if trade_keys.issubset(signal_keys):
                missing_keys = signal_keys - trade_keys
                missing = [dict(row) for row in signals if signal_key_from_row(row) in missing_keys]
                evaluated = [dict(row) for row in trades]
                if len(missing) == expected_signals - expected_evaluated:
                    return evaluated, missing, {
                        "mode": "signal_execution_diff",
                        "signal_source": str(signal_path),
                        "execution_source": str(trade_path),
                        "inventory": inventory,
                    }
    raise ControlledPaperError(
        "bounded missing-coverage audit found candidate ledgers but could not prove the locked "
        f"{expected_signals}/{expected_evaluated}/{expected_missing} split; "
        f"candidate_diagnostics={candidate_diagnostics}; inventory={inventory}"
    )

def classify_missing_row(
    row: Mapping[str, Any],
    floor_ms: int,
    h1_bars: Sequence[Bar],
    h1_index: Mapping[int, int],
    market: MarketDatabase,
    m5: MarketTable,
    min_m5_rows: int,
) -> dict[str, Any]:
    key = signal_key_from_row(row)
    result: dict[str, Any] = {"signal_key": key, "classification": "UNCLASSIFIED_MISSING_EXECUTION_EVIDENCE"}
    if key is None:
        result["detail"] = "signal timestamp unavailable"
        return result
    try:
        signal_ms = int(key)
    except ValueError:
        result["detail"] = "signal timestamp unparseable"
        return result
    result["signal_utc"] = iso_utc(datetime.fromtimestamp(signal_ms / 1000, tz=UTC))
    if signal_ms < floor_ms:
        result["classification"] = "PRE_OPERATIONAL_FLOOR"
        result["detail"] = "signal predates validated AMarkets operational floor"
        return result
    index = h1_index.get(signal_ms)
    if index is None:
        result["classification"] = "H1_SIGNAL_ROW_UNAVAILABLE"
        result["detail"] = "signal timestamp not present in aligned H1 rows"
        return result
    entry_i = index + 1
    exit_i = index + 24
    if exit_i >= len(h1_bars):
        result["classification"] = "H1_FUTURE_ROWS_UNAVAILABLE"
        result["detail"] = "entry or exact 24th future H1 row unavailable"
        return result
    entry_ms = h1_bars[entry_i].timestamp_ms
    exit_ms = h1_bars[exit_i].timestamp_ms
    entry_count = len(market.bucket(m5, entry_ms, entry_ms + 3600 * 1000))
    exit_count = len(market.bucket(m5, exit_ms, exit_ms + 3600 * 1000))
    result.update({
        "entry_utc": h1_bars[entry_i].dt_utc,
        "exit_utc": h1_bars[exit_i].dt_utc,
        "entry_m5_rows": entry_count,
        "exit_m5_rows": exit_count,
    })
    entry_bad = entry_count < min_m5_rows
    exit_bad = exit_count < min_m5_rows
    if entry_bad and exit_bad:
        result["classification"] = "BOTH_M5_BUCKETS_INCOMPLETE"
    elif entry_bad:
        result["classification"] = "ENTRY_M5_BUCKET_INCOMPLETE"
    elif exit_bad:
        result["classification"] = "EXIT_M5_BUCKET_INCOMPLETE"
    else:
        result["classification"] = "UNCLASSIFIED_MISSING_EXECUTION_EVIDENCE"
        result["detail"] = "H1 and M5 rows exist; source ledger must expose its blocking reason"
    return result


def run_missing_coverage_audit(root: Path, context: PreflightContext, h1_bars: Sequence[Bar]) -> dict[str, Any]:
    config = context.config
    evaluated, missing, source = locate_coverage_rows(root, config)
    floor_ms = timestamp_ms(config["operational_history_floor_utc"])
    h1_index = {bar.timestamp_ms: idx for idx, bar in enumerate(h1_bars)}
    rows = [
        classify_missing_row(
            row=row,
            floor_ms=floor_ms,
            h1_bars=h1_bars,
            h1_index=h1_index,
            market=context.market,
            m5=context.m5,
            min_m5_rows=int(config["minimum_m5_rows_per_complete_h1_bucket"]),
        )
        for row in missing
    ]
    classification_counts: dict[str, int] = {}
    current_period_defects = 0
    unclassified = 0
    for row in rows:
        label = str(row["classification"])
        classification_counts[label] = classification_counts.get(label, 0) + 1
        if label == "UNCLASSIFIED_MISSING_EXECUTION_EVIDENCE":
            unclassified += 1
        signal_utc = row.get("signal_utc")
        if signal_utc and timestamp_ms(signal_utc) >= timestamp_ms("2025-01-01T00:00:00Z"):
            if label not in {"H1_FUTURE_ROWS_UNAVAILABLE"}:
                current_period_defects += 1
    expected_signals = int(config["expected_historical_signals"])
    expected_evaluated = int(config["expected_execution_evaluated_trades"])
    expected_missing = int(config["expected_missing_execution_signals"])
    count_checks = {
        "signals": len(evaluated) + len(missing) == expected_signals,
        "evaluated": len(evaluated) == expected_evaluated,
        "missing": len(missing) == expected_missing,
    }
    allowed = {
        "PRE_OPERATIONAL_FLOOR",
        "ENTRY_M5_BUCKET_INCOMPLETE",
        "EXIT_M5_BUCKET_INCOMPLETE",
        "BOTH_M5_BUCKETS_INCOMPLETE",
        "H1_SIGNAL_ROW_UNAVAILABLE",
    }
    classifications_bounded = all(str(row["classification"]) in allowed for row in rows)
    passed = all(count_checks.values()) and classifications_bounded and current_period_defects == 0 and unclassified == 0
    decision = (
        "PASS_BOUNDED_MISSING_COVERAGE_NOT_CURRENT_SYSTEMATIC_DEFECT"
        if passed
        else "BLOCK_CONTROLLED_PAPER_MISSING_COVERAGE_DEFECT_OR_UNRESOLVED"
    )
    report_dir = root / config["report_dir"]
    atomic_write_csv(report_dir / "missing_coverage_audit.csv", rows)
    summary = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(),
        "decision": decision,
        "pass": passed,
        "source": source,
        "counts": {
            "signals": len(evaluated) + len(missing),
            "execution_evaluated": len(evaluated),
            "missing": len(missing),
        },
        "count_checks": count_checks,
        "classification_counts": classification_counts,
        "current_period_defects": current_period_defects,
        "unclassified": unclassified,
        "operational_floor_utc": config["operational_history_floor_utc"],
        "rows_csv": str(report_dir / "missing_coverage_audit.csv"),
    }
    atomic_write_json(report_dir / "missing_coverage_audit_summary.json", summary)
    return summary


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._schema()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def _schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_utc TEXT NOT NULL,
                finished_utc TEXT,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                decision TEXT,
                error TEXT,
                stage180_summary_path TEXT,
                stage180_summary_sha256 TEXT,
                aligned_db_path TEXT,
                missing_coverage_decision TEXT,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signals (
                signal_key TEXT PRIMARY KEY,
                signal_timestamp_ms INTEGER NOT NULL,
                signal_utc TEXT NOT NULL,
                probability_up REAL NOT NULL,
                direction INTEGER NOT NULL,
                observation_status TEXT NOT NULL,
                stage180_created_utc TEXT,
                ingested_utc TEXT NOT NULL,
                raw_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS blocked_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_key TEXT NOT NULL,
                blocked_utc TEXT NOT NULL,
                reason TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                UNIQUE(signal_key, reason)
            );
            CREATE TABLE IF NOT EXISTS positions (
                position_id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                updated_utc TEXT NOT NULL,
                signal_timestamp_ms INTEGER NOT NULL,
                signal_utc TEXT NOT NULL,
                entry_row_index INTEGER,
                entry_timestamp_ms INTEGER,
                entry_utc TEXT,
                entry_price REAL,
                entry_spread_points REAL,
                entry_spread_bps REAL,
                exit_row_index INTEGER,
                exit_timestamp_ms INTEGER,
                exit_utc TEXT,
                exit_price REAL,
                notional_to_equity REAL NOT NULL,
                gross_bps REAL,
                observed_cost_bps REAL,
                normal_cost_bps REAL,
                severe_cost_bps REAL,
                stress_8_cost_bps REAL,
                stress_10_cost_bps REAL,
                normal_net_bps REAL,
                severe_net_bps REAL,
                stress_8_net_bps REAL,
                stress_10_net_bps REAL,
                equity_before REAL,
                equity_after REAL,
                equity_pnl_pct REAL,
                block_reason TEXT,
                detail_json TEXT NOT NULL,
                FOREIGN KEY(signal_key) REFERENCES signals(signal_key)
            );
            CREATE TABLE IF NOT EXISTS risk_state (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                updated_utc TEXT NOT NULL,
                equity REAL NOT NULL,
                peak_equity REAL NOT NULL,
                drawdown_pct REAL NOT NULL,
                hard_kill_latched INTEGER NOT NULL,
                weekly_pause_active INTEGER NOT NULL,
                weekly_loss_pct REAL NOT NULL,
                current_iso_week TEXT NOT NULL,
                resolved_positions INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def start_run(self, command: str, metadata: Mapping[str, Any]) -> int:
        cursor = self.conn.execute(
            "INSERT INTO runs(started_utc, command, status, metadata_json) VALUES(?,?,?,?)",
            (iso_utc(), command, "RUNNING", json.dumps(metadata, ensure_ascii=False, sort_keys=True)),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, *, status: str, decision: str, error: str | None, context: PreflightContext | None, audit: Mapping[str, Any] | None) -> None:
        self.conn.execute(
            """UPDATE runs SET finished_utc=?, status=?, decision=?, error=?,
               stage180_summary_path=?, stage180_summary_sha256=?, aligned_db_path=?,
               missing_coverage_decision=? WHERE run_id=?""",
            (
                iso_utc(), status, decision, error,
                str(context.stage180_path) if context else None,
                sha256_file(context.stage180_path) if context else None,
                str(context.aligned_db_path) if context else None,
                audit.get("decision") if audit else None,
                run_id,
            ),
        )
        self.conn.commit()

    def signal_exists(self, signal_key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM signals WHERE signal_key=?", (signal_key,)).fetchone() is not None

    def insert_signal(self, observation: Mapping[str, Any]) -> str:
        signal_ms = timestamp_ms(observation["signal_timestamp"] if observation.get("signal_timestamp") is not None else observation["signal_dt"])
        key = str(signal_ms)
        self.conn.execute(
            """INSERT OR IGNORE INTO signals(signal_key, signal_timestamp_ms, signal_utc, probability_up,
               direction, observation_status, stage180_created_utc, ingested_utc, raw_json)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                key, signal_ms, iso_utc(datetime.fromtimestamp(signal_ms / 1000, tz=UTC)),
                float(observation["probability_up"]), int(observation.get("direction") or 0),
                str(observation.get("observation_status") or "UNKNOWN"), observation.get("created_utc"),
                iso_utc(), json.dumps(dict(observation), ensure_ascii=False, sort_keys=True),
            ),
        )
        self.conn.commit()
        return key

    def block(self, signal_key: str, reason: str, detail: Mapping[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO blocked_signals(signal_key, blocked_utc, reason, detail_json) VALUES(?,?,?,?)",
            (signal_key, iso_utc(), reason, json.dumps(dict(detail), ensure_ascii=False, sort_keys=True)),
        )
        position = self.conn.execute("SELECT position_id FROM positions WHERE signal_key=?", (signal_key,)).fetchone()
        if position:
            self.conn.execute(
                "UPDATE positions SET status='BLOCKED', updated_utc=?, block_reason=?, detail_json=? WHERE signal_key=?",
                (iso_utc(), reason, json.dumps(dict(detail), ensure_ascii=False, sort_keys=True), signal_key),
            )
        self.conn.commit()

    def ensure_waiting_position(self, signal_key: str, signal_ms: int, signal_utc: str, notional: float) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO positions(signal_key,status,created_utc,updated_utc,signal_timestamp_ms,
               signal_utc,notional_to_equity,detail_json) VALUES(?,?,?,?,?,?,?,?)""",
            (signal_key, "WAIT_ENTRY", iso_utc(), iso_utc(), signal_ms, signal_utc, notional, "{}"),
        )
        self.conn.commit()

    def waiting(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM positions WHERE status='WAIT_ENTRY' ORDER BY signal_timestamp_ms").fetchall()

    def open_positions(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM positions WHERE status='OPEN' ORDER BY entry_timestamp_ms").fetchall()

    def count_open_or_waiting(self, excluding_signal: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM positions WHERE status IN ('WAIT_ENTRY','OPEN')"
        params: tuple[Any, ...] = ()
        if excluding_signal is not None:
            sql += " AND signal_key<>?"
            params = (excluding_signal,)
        return int(self.conn.execute(sql, params).fetchone()[0])

    def entries_on_date(self, date_utc: str, excluding_signal: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM positions WHERE entry_utc LIKE ? AND status IN ('OPEN','RESOLVED')"
        params: list[Any] = [date_utc + "%"]
        if excluding_signal:
            sql += " AND signal_key<>?"
            params.append(excluding_signal)
        return int(self.conn.execute(sql, tuple(params)).fetchone()[0])

    def open_position(self, signal_key: str, payload: Mapping[str, Any]) -> None:
        self.conn.execute(
            """UPDATE positions SET status='OPEN', updated_utc=?, entry_row_index=?, entry_timestamp_ms=?,
               entry_utc=?, entry_price=?, entry_spread_points=?, entry_spread_bps=?, exit_row_index=?,
               exit_timestamp_ms=?, exit_utc=?, detail_json=? WHERE signal_key=?""",
            (
                iso_utc(), payload["entry_row_index"], payload["entry_timestamp_ms"], payload["entry_utc"],
                payload["entry_price"], payload["entry_spread_points"], payload["entry_spread_bps"],
                payload["exit_row_index"], payload["exit_timestamp_ms"], payload["exit_utc"],
                json.dumps(dict(payload.get("detail", {})), ensure_ascii=False, sort_keys=True), signal_key,
            ),
        )
        self.conn.commit()

    def resolve_position(self, signal_key: str, payload: Mapping[str, Any]) -> None:
        columns = [
            "exit_price", "gross_bps", "observed_cost_bps", "normal_cost_bps", "severe_cost_bps",
            "stress_8_cost_bps", "stress_10_cost_bps", "normal_net_bps", "severe_net_bps",
            "stress_8_net_bps", "stress_10_net_bps", "equity_before", "equity_after", "equity_pnl_pct",
        ]
        assignments = ", ".join(f"{column}=?" for column in columns)
        self.conn.execute(
            f"UPDATE positions SET status='RESOLVED', updated_utc=?, {assignments}, detail_json=? WHERE signal_key=?",
            (
                iso_utc(), *(payload[column] for column in columns),
                json.dumps(dict(payload.get("detail", {})), ensure_ascii=False, sort_keys=True), signal_key,
            ),
        )
        self.conn.commit()

    def current_risk(self) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM risk_state WHERE singleton=1").fetchone()
        if row is None:
            return {
                "equity": 1.0, "peak_equity": 1.0, "drawdown_pct": 0.0,
                "hard_kill_latched": False, "weekly_pause_active": False,
                "weekly_loss_pct": 0.0, "current_iso_week": iso_week(utc_now()), "resolved_positions": 0,
            }
        payload = dict(row)
        payload["hard_kill_latched"] = bool(payload["hard_kill_latched"])
        payload["weekly_pause_active"] = bool(payload["weekly_pause_active"])
        return payload

    def recompute_risk(self, config: Mapping[str, Any]) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT position_id, exit_utc, normal_net_bps, notional_to_equity FROM positions "
            "WHERE status='RESOLVED' ORDER BY exit_timestamp_ms, position_id"
        ).fetchall()
        equity = 1.0
        peak = 1.0
        hard_kill = False
        weekly_pnls: dict[str, list[float]] = {}
        for row in rows:
            pnl_fraction = float(row["normal_net_bps"]) / 10000.0 * float(row["notional_to_equity"])
            equity *= 1.0 + pnl_fraction
            peak = max(peak, equity)
            drawdown_pct = max(0.0, (peak - equity) / peak * 100.0)
            if drawdown_pct >= float(config["hard_drawdown_kill_switch_equity_pct"]):
                hard_kill = True
            week = iso_week(parse_timestamp(row["exit_utc"]))
            weekly_pnls.setdefault(week, []).append(pnl_fraction)
        previous = self.conn.execute("SELECT hard_kill_latched FROM risk_state WHERE singleton=1").fetchone()
        if previous and bool(previous[0]):
            hard_kill = True
        current_week = iso_week(utc_now())
        weekly_loss_pct = sum(weekly_pnls.get(current_week, [])) * 100.0
        weekly_pause = weekly_loss_pct <= -float(config["weekly_loss_pause_equity_pct"])
        drawdown_pct = max(0.0, (peak - equity) / peak * 100.0)
        payload = {
            "equity": equity,
            "peak_equity": peak,
            "drawdown_pct": drawdown_pct,
            "hard_kill_latched": hard_kill,
            "weekly_pause_active": weekly_pause,
            "weekly_loss_pct": weekly_loss_pct,
            "current_iso_week": current_week,
            "resolved_positions": len(rows),
        }
        self.conn.execute(
            """INSERT INTO risk_state(singleton,updated_utc,equity,peak_equity,drawdown_pct,hard_kill_latched,
               weekly_pause_active,weekly_loss_pct,current_iso_week,resolved_positions,metadata_json)
               VALUES(1,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(singleton) DO UPDATE SET updated_utc=excluded.updated_utc,equity=excluded.equity,
               peak_equity=excluded.peak_equity,drawdown_pct=excluded.drawdown_pct,
               hard_kill_latched=excluded.hard_kill_latched,weekly_pause_active=excluded.weekly_pause_active,
               weekly_loss_pct=excluded.weekly_loss_pct,current_iso_week=excluded.current_iso_week,
               resolved_positions=excluded.resolved_positions,metadata_json=excluded.metadata_json""",
            (
                iso_utc(), equity, peak, drawdown_pct, int(hard_kill), int(weekly_pause), weekly_loss_pct,
                current_week, len(rows), json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        self.conn.commit()
        return payload

    def rows(self, table: str, where: str = "", params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        allowed = {"runs", "signals", "blocked_signals", "positions", "risk_state"}
        if table not in allowed:
            raise ValueError("invalid export table")
        sql = f"SELECT * FROM {quote_ident(table)}"
        if where:
            sql += " WHERE " + where
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def iso_week(dt: datetime) -> str:
    dt = dt.astimezone(UTC)
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def first_spread_bps(spread_points: float | None, point_size: float, entry_price: float) -> tuple[float | None, float | None]:
    if spread_points is None or spread_points < 0:
        return spread_points, None
    return spread_points, spread_points * point_size / entry_price * 10000.0


def advance_waiting(
    ledger: Ledger,
    context: PreflightContext,
    h1_bars: Sequence[Bar],
    h1_index: Mapping[int, int],
    audit_pass: bool,
) -> None:
    config = context.config
    event_guard = EventGuard(Path(context.config["_root"]), config["event_guard"])
    risk = ledger.recompute_risk(config)
    for position in ledger.waiting():
        signal_key = str(position["signal_key"])
        if not audit_pass:
            ledger.block(signal_key, "MISSING_COVERAGE_AUDIT_NOT_PASSED", {})
            continue
        if risk["hard_kill_latched"]:
            ledger.block(signal_key, "HARD_DRAWDOWN_KILL_SWITCH_ACTIVE", risk)
            continue
        if risk["weekly_pause_active"]:
            ledger.block(signal_key, "WEEKLY_LOSS_PAUSE_ACTIVE", risk)
            continue
        if ledger.count_open_or_waiting(excluding_signal=signal_key) >= int(config["maximum_concurrent_positions"]):
            ledger.block(signal_key, "MAX_CONCURRENT_POSITION_GUARD", {})
            continue
        signal_ms = int(position["signal_timestamp_ms"])
        signal_i = h1_index.get(signal_ms)
        if signal_i is None:
            ledger.block(signal_key, "SIGNAL_H1_ROW_NOT_FOUND", {"signal_utc": position["signal_utc"]})
            continue
        entry_i = signal_i + int(config["entry_offset_h1_rows"])
        exit_i = signal_i + int(config["exit_offset_h1_rows"])
        if entry_i >= len(h1_bars):
            continue
        entry_bar = h1_bars[entry_i]
        if ledger.entries_on_date(entry_bar.dt_utc[:10], excluding_signal=signal_key) >= int(config["daily_new_positions_cap"]):
            ledger.block(signal_key, "DAILY_NEW_POSITION_CAP", {"entry_date": entry_bar.dt_utc[:10]})
            continue
        if exit_i >= len(h1_bars):
            exit_bar = None
            exit_utc = None
            exit_ms = None
        else:
            exit_bar = h1_bars[exit_i]
            exit_utc = exit_bar.dt_utc
            exit_ms = exit_bar.timestamp_ms
        m5_rows = context.market.bucket(context.m5, entry_bar.timestamp_ms, entry_bar.timestamp_ms + 3600 * 1000)
        if len(m5_rows) < int(config["minimum_m5_rows_per_complete_h1_bucket"]):
            # The H1 entry row is not execution-complete yet. Keep pending rather than infer a spread.
            continue
        spread_bucket = context.spread_provider.bucket(entry_bar.timestamp_ms, entry_bar.timestamp_ms + 3600 * 1000)
        if spread_bucket.row_count < int(config["minimum_m5_rows_per_complete_h1_bucket"]):
            ledger.block(signal_key, "ENTRY_SPREAD_BUCKET_INCOMPLETE_FAIL_CLOSED", {
                "aligned_m5_rows": len(m5_rows),
                "spread_source_rows": spread_bucket.row_count,
                "spread_source": spread_bucket.source,
            })
            continue
        spread_points, spread_bps = first_spread_bps(
            spread_bucket.first_spread_points, float(config["point_size"]), entry_bar.open
        )
        if spread_bps is None:
            ledger.block(signal_key, "ENTRY_SPREAD_MISSING_FAIL_CLOSED", {
                "aligned_m5_rows": len(m5_rows),
                "spread_source_rows": spread_bucket.row_count,
                "spread_source": spread_bucket.source,
            })
            continue
        if spread_bps > float(config["observed_entry_spread_guard_bps"]):
            ledger.block(signal_key, "ENTRY_SPREAD_GUARD", {"entry_spread_bps": spread_bps, "limit_bps": config["observed_entry_spread_guard_bps"]})
            continue
        event_ok, event_reason, event_detail = event_guard.evaluate(entry_bar.timestamp_ms)
        if not event_ok:
            ledger.block(signal_key, event_reason, event_detail)
            continue
        ledger.open_position(signal_key, {
            "entry_row_index": entry_i,
            "entry_timestamp_ms": entry_bar.timestamp_ms,
            "entry_utc": entry_bar.dt_utc,
            "entry_price": entry_bar.open,
            "entry_spread_points": spread_points,
            "entry_spread_bps": spread_bps,
            "exit_row_index": exit_i,
            "exit_timestamp_ms": exit_ms,
            "exit_utc": exit_utc,
            "detail": {
                "entry_semantics": "open of aligned AMarkets H1 row i+1",
                "exit_semantics": "close of aligned AMarkets H1 row i+24",
                "event_guard": event_reason,
                "event_detail": event_detail,
                "entry_m5_rows": len(m5_rows),
                "spread_source_rows": spread_bucket.row_count,
                "spread_source": spread_bucket.source,
                "spread_source_path": str(context.spread_source_path),
                "broker_order_sent": False,
            },
        })


def resolve_open(ledger: Ledger, context: PreflightContext, h1_bars: Sequence[Bar]) -> None:
    config = context.config
    for position in ledger.open_positions():
        exit_i = int(position["exit_row_index"])
        if exit_i >= len(h1_bars):
            continue
        exit_bar = h1_bars[exit_i]
        if exit_bar.timestamp_ms != int(position["exit_timestamp_ms"]):
            ledger.block(str(position["signal_key"]), "EXACT_EXIT_ROW_IDENTITY_MISMATCH", {
                "expected": int(position["exit_timestamp_ms"]), "actual": exit_bar.timestamp_ms,
            })
            continue
        exit_m5 = context.market.bucket(context.m5, exit_bar.timestamp_ms, exit_bar.timestamp_ms + 3600 * 1000)
        if len(exit_m5) < int(config["minimum_m5_rows_per_complete_h1_bucket"]):
            continue
        entry_price = float(position["entry_price"])
        exit_price = float(exit_bar.close)
        gross_bps = (exit_price / entry_price - 1.0) * 10000.0
        observed_cost = float(position["entry_spread_bps"])
        normal_cost = max(float(config["normal_execution_cost_floor_bps"]), observed_cost)
        severe_cost = max(float(config["severe_execution_cost_floor_bps"]), observed_cost)
        stress_8_cost = max(8.0, observed_cost)
        stress_10_cost = max(10.0, observed_cost)
        normal_net = gross_bps - normal_cost
        severe_net = gross_bps - severe_cost
        stress_8_net = gross_bps - stress_8_cost
        stress_10_net = gross_bps - stress_10_cost
        risk_before = ledger.recompute_risk(config)
        equity_before = float(risk_before["equity"])
        pnl_fraction = normal_net / 10000.0 * float(position["notional_to_equity"])
        equity_after = equity_before * (1.0 + pnl_fraction)
        ledger.resolve_position(str(position["signal_key"]), {
            "exit_price": exit_price,
            "gross_bps": gross_bps,
            "observed_cost_bps": observed_cost,
            "normal_cost_bps": normal_cost,
            "severe_cost_bps": severe_cost,
            "stress_8_cost_bps": stress_8_cost,
            "stress_10_cost_bps": stress_10_cost,
            "normal_net_bps": normal_net,
            "severe_net_bps": severe_net,
            "stress_8_net_bps": stress_8_net,
            "stress_10_net_bps": stress_10_net,
            "equity_before": equity_before,
            "equity_after": equity_after,
            "equity_pnl_pct": pnl_fraction * 100.0,
            "detail": {
                "exit_semantics": "close of exact aligned AMarkets H1 row i+24",
                "exit_m5_rows": len(exit_m5),
                "normal_cost_semantics": "max(3.0 bps, observed entry spread bps)",
                "broker_order_sent": False,
            },
        })
    ledger.recompute_risk(config)


def ingest_latest_observation(ledger: Ledger, context: PreflightContext, audit_pass: bool) -> dict[str, Any]:
    observation = context.stage180.get("latest_observation")
    if not observation:
        return {"status": "NO_STAGE180_OBSERVATION", "new_signal": False}
    if not isinstance(observation, Mapping):
        raise ControlledPaperError("Stage180 latest_observation must be an object")
    required = ("probability_up", "direction", "observation_status")
    missing = [key for key in required if key not in observation]
    if missing or ("signal_timestamp" not in observation and "signal_dt" not in observation):
        raise ControlledPaperError(f"Stage180 latest_observation missing fields: {missing}")
    signal_ms = timestamp_ms(observation.get("signal_timestamp") if observation.get("signal_timestamp") is not None else observation.get("signal_dt"))
    signal_key = str(signal_ms)
    if ledger.signal_exists(signal_key):
        return {"status": "OBSERVATION_ALREADY_INGESTED", "signal_key": signal_key, "new_signal": False}
    signal_key = ledger.insert_signal(observation)
    probability = float(observation["probability_up"])
    direction = int(observation.get("direction") or 0)
    status = str(observation.get("observation_status") or "UNKNOWN").upper()
    threshold = float(context.config["threshold"])
    is_signal = probability >= threshold and direction == 1
    if ("NO_SIGNAL" in status) and is_signal:
        ledger.block(signal_key, "STAGE180_OBSERVATION_CONTRADICTION", {
            "probability_up": probability, "threshold": threshold, "direction": direction, "status": status,
        })
        return {"status": "BLOCKED_CONTRADICTORY_OBSERVATION", "signal_key": signal_key, "new_signal": False}
    if not is_signal:
        return {"status": "NO_SIGNAL", "signal_key": signal_key, "new_signal": False}
    ledger.ensure_waiting_position(
        signal_key=signal_key,
        signal_ms=signal_ms,
        signal_utc=iso_utc(datetime.fromtimestamp(signal_ms / 1000, tz=UTC)),
        notional=float(context.config["maximum_notional_to_equity"]),
    )
    if not audit_pass:
        ledger.block(signal_key, "MISSING_COVERAGE_AUDIT_NOT_PASSED", {})
        return {"status": "SIGNAL_BLOCKED_AUDIT", "signal_key": signal_key, "new_signal": True}
    return {"status": "SIGNAL_QUEUED", "signal_key": signal_key, "new_signal": True}


def export_reports(root: Path, config: Mapping[str, Any], ledger: Ledger, audit: Mapping[str, Any], context: PreflightContext, run_result: Mapping[str, Any]) -> dict[str, Any]:
    report_dir = root / config["report_dir"]
    report_dir.mkdir(parents=True, exist_ok=True)
    signals = ledger.rows("signals")
    blocked = ledger.rows("blocked_signals")
    pending = ledger.rows("positions", "status IN ('WAIT_ENTRY','OPEN')")
    resolved = ledger.rows("positions", "status='RESOLVED'")
    all_positions = ledger.rows("positions")
    risk = ledger.current_risk()
    atomic_write_csv(report_dir / "signals.csv", signals)
    atomic_write_csv(report_dir / "blocked_signals.csv", blocked)
    atomic_write_csv(report_dir / "pending_positions.csv", pending)
    atomic_write_csv(report_dir / "resolved_positions.csv", resolved)
    atomic_write_csv(report_dir / "all_positions.csv", all_positions)
    atomic_write_json(report_dir / "risk_state.json", risk)
    if risk["hard_kill_latched"]:
        decision = "CONTROLLED_PAPER_HARD_DRAWDOWN_KILL_SWITCH_ACTIVE"
    elif not audit.get("pass"):
        decision = "CONTROLLED_PAPER_FAIL_CLOSED_MISSING_COVERAGE_AUDIT"
    else:
        decision = "CONTROLLED_PAPER_ACTIVE_PAPER_LOG_ONLY_NO_BROKER"
    summary = {
        "program": PROGRAM_VERSION,
        "generated_utc": iso_utc(),
        "decision": decision,
        "paper_log_only": True,
        "broker_api_present": False,
        "broker_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "candidate": config["candidate"],
        "model": config["model"],
        "target": config["target"],
        "threshold": config["threshold"],
        "entry_semantics": "open of aligned AMarkets H1 row i+1",
        "exit_semantics": "close of aligned AMarkets H1 row i+24",
        "stage180_summary": str(context.stage180_path),
        "stage180_decision": context.stage180.get("decision"),
        "aligned_db": str(context.aligned_db_path),
        "spread_source": context.spread_provider.describe(),
        "missing_coverage_audit": dict(audit),
        "run_result": dict(run_result),
        "counts": {
            "signals": len(signals),
            "blocked_signals": len(blocked),
            "pending_positions": len(pending),
            "resolved_positions": len(resolved),
        },
        "risk_state": risk,
        "risk_contract": {
            key: config[key] for key in (
                "maximum_notional_to_equity", "maximum_concurrent_positions", "daily_new_positions_cap",
                "weekly_loss_pause_equity_pct", "hard_drawdown_kill_switch_equity_pct",
                "normal_execution_cost_floor_bps", "severe_execution_cost_floor_bps",
                "observed_entry_spread_guard_bps",
            )
        },
        "outputs": {
            "ledger": str(ledger.path),
            "signals_csv": str(report_dir / "signals.csv"),
            "blocked_signals_csv": str(report_dir / "blocked_signals.csv"),
            "pending_positions_csv": str(report_dir / "pending_positions.csv"),
            "resolved_positions_csv": str(report_dir / "resolved_positions.csv"),
            "risk_state_json": str(report_dir / "risk_state.json"),
        },
    }
    atomic_write_json(report_dir / "controlled_paper_summary.json", summary)
    md = f"""# XAUUSD Controlled Paper\n\nDecision: `{decision}`\n\n- Candidate: `{config['candidate']}`\n- Frozen threshold: `{config['threshold']}`\n- Signals logged: `{len(signals)}`\n- Blocked signals: `{len(blocked)}`\n- Pending positions: `{len(pending)}`\n- Resolved positions: `{len(resolved)}`\n- Normalized equity: `{risk['equity']:.8f}`\n- Drawdown: `{risk['drawdown_pct']:.6f}%`\n- Weekly pause: `{risk['weekly_pause_active']}`\n- Hard kill latched: `{risk['hard_kill_latched']}`\n\n## Boundary\n\nNo broker API is imported. No demo or live order is authorized.\n"""
    atomic_write_text(report_dir / "controlled_paper_decision.md", md)
    return summary


def execute(root: Path, config_path: Path | None, command: str) -> tuple[int, dict[str, Any]]:
    root = root.expanduser().resolve()
    config = load_config(root, config_path)
    config["_root"] = str(root)
    ledger_path = root / config["ledger_path"]
    ledger = Ledger(ledger_path)
    run_id = ledger.start_run(command, {"program": PROGRAM_VERSION, "root": str(root)})
    context: PreflightContext | None = None
    audit: dict[str, Any] | None = None
    try:
        context = validate_preflight(root, config)
        h1_bars = context.market.load_all(context.h1)
        if len(h1_bars) < 1000:
            raise ControlledPaperError(f"insufficient aligned H1 rows: {len(h1_bars)}")
        h1_index = {bar.timestamp_ms: idx for idx, bar in enumerate(h1_bars)}
        audit = run_missing_coverage_audit(root, context, h1_bars)
        preflight_payload = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(),
            "decision": "PASS_CONTROLLED_PAPER_PREFLIGHT" if audit["pass"] else "BLOCK_CONTROLLED_PAPER_PREFLIGHT",
            "pass": bool(audit["pass"]),
            "checks": context.checks,
            "paths": {
                "stage180_summary": str(context.stage180_path),
                "commercial_summary": str(context.commercial_summary_path),
                "risk_contract": str(context.risk_contract_path),
                "frozen_contract": str(context.frozen_contract_path),
                "frozen_model": str(context.frozen_model_path),
                "aligned_db": str(context.aligned_db_path),
                "spread_source": str(context.spread_source_path),
                "spread_time_contract": str(context.spread_time_contract_path) if context.spread_time_contract_path else None,
            },
            "hashes": {
                "stage180_summary": sha256_file(context.stage180_path),
                "commercial_summary": sha256_file(context.commercial_summary_path),
                "risk_contract": sha256_file(context.risk_contract_path),
                "frozen_contract": sha256_file(context.frozen_contract_path),
                "frozen_model": sha256_file(context.frozen_model_path),
                "aligned_db": sha256_file(context.aligned_db_path),
                "spread_source": sha256_file(context.spread_source_path),
                "spread_time_contract": sha256_file(context.spread_time_contract_path) if context.spread_time_contract_path else None,
            },
            "missing_coverage_audit": audit,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
        }
        report_dir = root / config["report_dir"]
        atomic_write_json(report_dir / "controlled_paper_preflight.json", preflight_payload)
        if command == "preflight":
            decision = preflight_payload["decision"]
            ledger.finish_run(run_id, status="PASS" if audit["pass"] else "BLOCKED", decision=decision, error=None, context=context, audit=audit)
            context.market.close()
            return (0 if audit["pass"] else 2), preflight_payload

        resolve_open(ledger, context, h1_bars)
        advance_waiting(ledger, context, h1_bars, h1_index, bool(audit["pass"]))
        ingest = ingest_latest_observation(ledger, context, bool(audit["pass"]))
        advance_waiting(ledger, context, h1_bars, h1_index, bool(audit["pass"]))
        resolve_open(ledger, context, h1_bars)
        run_result = {"ingest": ingest, "h1_rows": len(h1_bars), "latest_h1_utc": h1_bars[-1].dt_utc}
        summary = export_reports(root, config, ledger, audit, context, run_result)
        ledger.finish_run(run_id, status="PASS" if audit["pass"] else "BLOCKED", decision=summary["decision"], error=None, context=context, audit=audit)
        context.market.close()
        return (0 if audit["pass"] else 2), summary
    except Exception as exc:
        if context is not None:
            context.market.close()
        error = f"{type(exc).__name__}: {exc}"
        decision = "CONTROLLED_PAPER_FAIL_CLOSED"
        ledger.finish_run(run_id, status="ERROR", decision=decision, error=error, context=context, audit=audit)
        report_dir = root / config.get("report_dir", "reports/xauusd_controlled_paper")
        payload = {
            "program": PROGRAM_VERSION,
            "generated_utc": iso_utc(),
            "decision": decision,
            "error": error,
            "broker_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
        }
        atomic_write_json(report_dir / "controlled_paper_failure.json", payload)
        return 2, payload
    finally:
        ledger.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "run"), nargs="?", default="run")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code, payload = execute(args.root, args.config, args.command)
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
