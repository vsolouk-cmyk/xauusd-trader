#!/usr/bin/env python3
"""Controlled-paper logger for the frozen XAUUSD Stage178/Stage180 candidate.

This program never imports a broker API and never sends an order.  It consumes
only the already-frozen Stage180 observation, applies exact H1 row-position
entry/exit semantics, enforces the locked risk contract, and writes an
idempotent SQLite/CSV/JSON paper ledger.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import sqlite3
import statistics
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

UTC = timezone.utc
PROGRAM_VERSION = "XAUUSD_CONTROLLED_PAPER_V1"
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
    try:
        h1, m5, diagnostics = market.discover()
        checks["market_schema_introspection"] = diagnostics
        checks["h1_table"] = asdict(h1)
        checks["m5_table"] = asdict(m5)
        checks["m5_spread_present"] = m5.spread_col is not None
        if m5.spread_col is None:
            raise ControlledPaperError("M5 spread column missing; spread guard cannot operate")
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


def row_has_execution(row: Mapping[str, Any]) -> bool:
    status = str(first_present(row, ("execution_status", "status", "evaluation_status", "outcome_status")) or "").upper()
    if any(token in status for token in ("EVALUATED", "RESOLVED", "EXECUTED", "COMPLETE")):
        return True
    if any(token in status for token in ("MISSING", "UNEVALUATED", "NO_COVERAGE", "BLOCKED")):
        return False
    for alias in (
        "normal_net_bps", "net_normal_bps", "execution_net_bps", "net_bps", "gross_bps",
        "entry_price", "exit_price",
    ):
        value = first_present(row, (alias,))
        if value not in (None, ""):
            try:
                if math.isfinite(float(value)):
                    return True
            except (TypeError, ValueError):
                continue
    return False


def locate_coverage_rows(root: Path, config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    files: list[Path] = []
    for pattern in config["commercial_csv_globs"]:
        files.extend(path.resolve() for path in root.glob(pattern) if path.is_file())
    unique = sorted(set(files))
    candidates: list[tuple[Path, list[dict[str, str]]]] = []
    inventory: list[dict[str, Any]] = []
    for path in unique:
        try:
            rows = read_csv(path)
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
        headers = list(rows[0].keys()) if rows else []
        inventory.append({"path": str(path), "rows": len(rows), "headers": headers})
        if rows:
            candidates.append((path, rows))

    expected_signals = int(config["expected_historical_signals"])
    expected_evaluated = int(config["expected_execution_evaluated_trades"])
    signal_candidates = [(path, rows) for path, rows in candidates if len(rows) == expected_signals]
    trade_candidates = [(path, rows) for path, rows in candidates if len(rows) == expected_evaluated]

    # Preferred: a single 168-row ledger containing evaluated and missing rows.
    for path, rows in signal_candidates:
        evaluated = [dict(row) for row in rows if row_has_execution(row)]
        missing = [dict(row) for row in rows if not row_has_execution(row)]
        if len(evaluated) == expected_evaluated and len(missing) == expected_signals - expected_evaluated:
            return evaluated, missing, {"mode": "single_ledger", "signal_source": str(path), "inventory": inventory}

    # Alternative: a 168-row signal file and a 146-row execution file, diffed by timestamp key.
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
        "bounded missing-coverage audit could not locate a 168-row signal ledger and 146 evaluated rows; "
        f"inventory={inventory}"
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


def first_spread_bps(m5_rows: Sequence[Bar], point_size: float, entry_price: float) -> tuple[float | None, float | None]:
    if not m5_rows:
        return None, None
    spread_points = m5_rows[0].spread_points
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
        spread_points, spread_bps = first_spread_bps(m5_rows, float(config["point_size"]), entry_bar.open)
        if spread_bps is None:
            ledger.block(signal_key, "ENTRY_SPREAD_MISSING_FAIL_CLOSED", {"m5_rows": len(m5_rows)})
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
            },
            "hashes": {
                "stage180_summary": sha256_file(context.stage180_path),
                "commercial_summary": sha256_file(context.commercial_summary_path),
                "risk_contract": sha256_file(context.risk_contract_path),
                "frozen_contract": sha256_file(context.frozen_contract_path),
                "frozen_model": sha256_file(context.frozen_model_path),
                "aligned_db": sha256_file(context.aligned_db_path),
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
