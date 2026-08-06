#!/usr/bin/env python3
"""Compact, holdout-locked successor formulation scan for XAUUSD.

This program evaluates a fixed set of materially different, deterministic H1
formulations on AMarkets-aligned history. Candidate selection uses only the
pre-2025 reference window. A frozen, family-diverse shortlist is then evaluated
once on the untouched 2025+ holdout. No order, broker, MT5, demo, or live path
exists in this program.
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
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

UTC = timezone.utc
MS_HOUR = 3_600_000
PROGRAM_VERSION = "XAUUSD_SUCCESSOR_PARALLEL_SCAN_V1_2_DYNAMIC_FEATURE_CONTRACT_REPAIR"
DECISION_SURVIVOR = "SUCCESSOR_SHORTLIST_SURVIVOR_READY_FOR_STRICT_PROMOTION_AUDIT"
DECISION_HOLDOUT_FAIL = "NO_COMMERCIAL_SURVIVOR_CHANGE_FAMILY_OR_DATA"
DECISION_REFERENCE_FAIL = "NO_REFERENCE_SURVIVOR_REJECT_SUCCESSOR_SET"
DECISION_LOCKED = "SUCCESSOR_SCAN_HOLDOUT_ALREADY_ACCESSED_FAIL_CLOSED"


class ScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateSpec:
    key: str
    family: str
    horizon_hours: int
    parameters: dict[str, Any]
    event_policy: str = "blackout"


def now_utc() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = handle.name
    os.replace(temporary, path)


def write_json(path: Path, payload: Any) -> None:
    atomic_write(
        path,
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=json_default)
        + "\n",
    )


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(os.path.expanduser(str(value)))
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def load_h1(path: Path, table: str, minimum_m5_bar_count: int) -> pd.DataFrame:
    if not path.is_file():
        raise ScanError(f"alignment database missing: {path}")
    with closing(sqlite3.connect(path)) as connection:
        columns = [
            row[1]
            for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        ]
        required = {"timestamp", "open", "high", "low", "close"}
        missing = sorted(required - set(columns))
        if missing:
            raise ScanError(f"{table} missing required columns: {missing}")
        volume_expr = "volume" if "volume" in columns else "NULL AS volume"
        where = ""
        parameters: tuple[Any, ...] = ()
        if "m5_bar_count" in columns:
            where = "WHERE m5_bar_count >= ?"
            parameters = (int(minimum_m5_bar_count),)
        frame = pd.read_sql_query(
            f"""
            SELECT timestamp, open, high, low, close, {volume_expr}
            FROM \"{table}\"
            {where}
            ORDER BY timestamp
            """,
            connection,
            params=parameters,
        )
    if frame.empty:
        raise ScanError("no complete H1 rows found")
    for column in ["timestamp", "open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    frame["dt"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    invariant = (
        (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
    )
    if not bool(invariant.all()):
        raise ScanError("OHLC invariant failure")
    if frame["timestamp"].duplicated().any() or not frame["timestamp"].is_monotonic_increasing:
        raise ScanError("invalid H1 timestamps")
    return frame.reset_index(drop=True)


def read_alignment_contract(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ScanError(f"time contract missing: {path}")
    payload = read_json(path)
    expected = {
        "contract": "EU_DST_GMT_OFFSET_PAIR",
        "standard_shift_minutes": -120,
        "dst_shift_minutes": -180,
        "dst_calendar": "EU",
    }
    checks = {key: payload.get(key) == value for key, value in expected.items()}
    checks["selection_used_holdout_false"] = not bool(payload.get("selection_used_holdout", True))
    if not all(checks.values()):
        raise ScanError(f"AMarkets time contract mismatch: {checks}")
    return {"path": str(path), "checks": checks, "pass": True, "contract": payload}


def datetime_to_epoch_ms(values: Any) -> Any:
    """Convert timezone-aware datetimes to Unix epoch milliseconds.

    Pandas 3 may preserve microsecond datetime resolution while pandas 2 commonly
    uses nanoseconds. Raw ``astype("int64")`` therefore cannot be divided by a
    fixed constant safely. Normalize explicitly to nanoseconds first.
    """
    converted = pd.to_datetime(values, utc=True, errors="raise")
    if isinstance(converted, pd.Series):
        index = pd.DatetimeIndex(converted.array)
    elif isinstance(converted, pd.DatetimeIndex):
        index = converted
    else:
        stamp = pd.Timestamp(converted)
        if hasattr(stamp, "as_unit"):
            stamp = stamp.as_unit("ns")
        return int(stamp.value // 1_000_000)
    if hasattr(index, "as_unit"):
        index = index.as_unit("ns")
    return np.asarray(index.asi8, dtype=np.int64) // 1_000_000


BASE_RETURN_LAGS = frozenset({1, 3, 6, 12, 24, 48, 72, 120, 240})
BASE_ROLLING_WINDOWS = frozenset({24, 72, 120, 240})
SUPPORTED_FAMILIES = frozenset(
    {
        "trend_continuation",
        "trend_pullback",
        "range_breakout",
        "volatility_expansion",
        "low_vol_range_reversion",
        "zscore_reversion",
        "failed_breakout_reversion",
        "post_event_momentum",
        "post_event_breakout",
        "session_breakout",
    }
)


def positive_window(value: Any, label: str, candidate_key: str) -> int:
    try:
        window = int(value)
    except (TypeError, ValueError) as exc:
        raise ScanError(
            f"candidate {candidate_key} has invalid {label}: {value!r}"
        ) from exc
    if window <= 0:
        raise ScanError(
            f"candidate {candidate_key} has non-positive {label}: {window}"
        )
    return window


def candidate_feature_plan(candidates: Sequence[CandidateSpec]) -> dict[str, list[int]]:
    """Derive every lag/window required by the frozen candidate registry.

    The original V1/V1.1 implementation hard-coded rolling windows and omitted
    the 12-hour prior range required by the London/New York session candidates.
    Deriving the plan from candidate parameters prevents future registry/feature
    drift and keeps the holdout untouched during configuration validation.
    """
    return_lags = set(BASE_RETURN_LAGS)
    rolling_windows = set(BASE_ROLLING_WINDOWS)

    for spec in candidates:
        if spec.family not in SUPPORTED_FAMILIES:
            raise ScanError(f"unknown family in candidate registry: {spec.family}")
        p = spec.parameters
        if spec.family == "trend_continuation":
            return_lags.add(positive_window(p.get("lookback_hours"), "lookback_hours", spec.key))
            rolling_windows.add(positive_window(p.get("trend_window"), "trend_window", spec.key))
        elif spec.family == "trend_pullback":
            return_lags.add(positive_window(p.get("pullback_hours"), "pullback_hours", spec.key))
            rolling_windows.add(positive_window(p.get("trend_window"), "trend_window", spec.key))
        elif spec.family in {
            "range_breakout",
            "low_vol_range_reversion",
            "failed_breakout_reversion",
            "post_event_breakout",
            "session_breakout",
        }:
            rolling_windows.add(positive_window(p.get("range_window"), "range_window", spec.key))
        elif spec.family == "volatility_expansion":
            rolling_windows.add(positive_window(p.get("trend_window"), "trend_window", spec.key))
        elif spec.family == "zscore_reversion":
            rolling_windows.add(positive_window(p.get("window"), "window", spec.key))

    return {
        "return_lags": sorted(return_lags),
        "rolling_windows": sorted(rolling_windows),
    }


def candidate_required_columns(spec: CandidateSpec) -> set[str]:
    p = spec.parameters
    required = {"signal_dow"}
    if spec.family == "trend_continuation":
        required.update(
            {
                f"ret_{positive_window(p.get('lookback_hours'), 'lookback_hours', spec.key)}h",
                f"sma_gap_{positive_window(p.get('trend_window'), 'trend_window', spec.key)}",
            }
        )
    elif spec.family == "trend_pullback":
        required.update(
            {
                f"ret_{positive_window(p.get('pullback_hours'), 'pullback_hours', spec.key)}h",
                f"sma_gap_{positive_window(p.get('trend_window'), 'trend_window', spec.key)}",
            }
        )
    elif spec.family == "range_breakout":
        window = positive_window(p.get("range_window"), "range_window", spec.key)
        required.update({f"prior_high_{window}", f"prior_low_{window}", "atr_14", "close"})
    elif spec.family == "volatility_expansion":
        window = positive_window(p.get("trend_window"), "trend_window", spec.key)
        required.update({"high", "low", "atr_14", "body_pct", f"sma_gap_{window}"})
    elif spec.family == "low_vol_range_reversion":
        window = positive_window(p.get("range_window"), "range_window", spec.key)
        required.update({"atr_14_pct", "atr_120_pct", f"prior_range_pos_{window}"})
    elif spec.family == "zscore_reversion":
        window = positive_window(p.get("window"), "window", spec.key)
        required.add(f"zclose_{window}")
    elif spec.family == "failed_breakout_reversion":
        window = positive_window(p.get("range_window"), "range_window", spec.key)
        required.update({"high", "low", "close", f"prior_high_{window}", f"prior_low_{window}"})
    elif spec.family == "post_event_momentum":
        recent = "recent_event_3h" if int(p.get("event_window_hours")) <= 3 else "recent_event_6h"
        required.update({recent, "open", "close", "atr_14"})
    elif spec.family in {"post_event_breakout", "session_breakout"}:
        window = positive_window(p.get("range_window"), "range_window", spec.key)
        required.update({"close", f"prior_high_{window}", f"prior_low_{window}"})
        if spec.family == "post_event_breakout":
            recent = "recent_event_3h" if int(p.get("event_window_hours")) <= 3 else "recent_event_6h"
            required.add(recent)
        else:
            required.add("signal_hour_utc")
    else:
        raise ScanError(f"unknown family: {spec.family}")

    if spec.event_policy == "blackout":
        required.add("event_blackout")
    elif spec.event_policy == "require_recent":
        required.add("recent_event_6h")
    elif spec.event_policy != "ignore":
        raise ScanError(f"unknown event policy: {spec.event_policy}")
    return required


def validate_candidate_feature_contract(
    frame: pd.DataFrame, candidates: Sequence[CandidateSpec]
) -> dict[str, Any]:
    missing_by_candidate: dict[str, list[str]] = {}
    all_required: set[str] = set()
    available = set(frame.columns)
    for spec in candidates:
        required = candidate_required_columns(spec)
        all_required.update(required)
        missing = sorted(required - available)
        if missing:
            missing_by_candidate[spec.key] = missing
    if missing_by_candidate:
        raise ScanError(
            "candidate feature contract missing columns: "
            + json.dumps(missing_by_candidate, sort_keys=True)
        )
    return {
        "candidate_count": len(candidates),
        "required_columns": sorted(all_required),
        "feature_plan": candidate_feature_plan(candidates),
        "pass": True,
    }


def load_events(path: Path) -> pd.DataFrame:
    columns = [
        "event_time_utc",
        "source",
        "category",
        "title",
        "blackout_before_minutes",
        "blackout_after_minutes",
    ]
    if not path.is_file():
        return pd.DataFrame(columns=columns)
    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "official_events" not in tables:
            return pd.DataFrame(columns=columns)
        frame = pd.read_sql_query(
            """
            SELECT event_time_utc, source, category, title,
                   blackout_before_minutes, blackout_after_minutes
            FROM official_events
            ORDER BY event_time_utc
            """,
            connection,
        )
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["event_dt"] = pd.to_datetime(frame["event_time_utc"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["event_dt"]).drop_duplicates(
        ["event_dt", "source", "category"], keep="last"
    )
    frame["blackout_before_minutes"] = pd.to_numeric(
        frame["blackout_before_minutes"], errors="coerce"
    ).fillna(60.0)
    frame["blackout_after_minutes"] = pd.to_numeric(
        frame["blackout_after_minutes"], errors="coerce"
    ).fillna(60.0)
    return frame.sort_values("event_dt").reset_index(drop=True)


def build_features(
    frame: pd.DataFrame,
    events: pd.DataFrame,
    candidates: Sequence[CandidateSpec] | None = None,
) -> pd.DataFrame:
    x = frame.copy()
    close = x["close"].astype(float)
    open_ = x["open"].astype(float)
    high = x["high"].astype(float)
    low = x["low"].astype(float)
    log_close = np.log(close)
    ret1 = log_close.diff()
    candidate_list = list(candidates or [])
    feature_plan = candidate_feature_plan(candidate_list)

    x["body_pct"] = close / open_ - 1.0
    x["range_pct"] = (high - low) / close
    for lag in feature_plan["return_lags"]:
        x[f"ret_{lag}h"] = log_close.diff(lag)

    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    for window in [14, 48, 120]:
        x[f"atr_{window}"] = true_range.rolling(window, min_periods=window).mean()
        x[f"atr_{window}_pct"] = x[f"atr_{window}"] / close

    for window in feature_plan["rolling_windows"]:
        mean = close.rolling(window, min_periods=window).mean()
        std = close.rolling(window, min_periods=window).std().replace(0.0, np.nan)
        x[f"sma_gap_{window}"] = close / mean - 1.0
        x[f"zclose_{window}"] = (close - mean) / std
        x[f"rv_{window}"] = ret1.rolling(window, min_periods=window).std() * math.sqrt(24.0)
        prior_high = high.shift(1).rolling(window, min_periods=window).max()
        prior_low = low.shift(1).rolling(window, min_periods=window).min()
        x[f"prior_high_{window}"] = prior_high
        x[f"prior_low_{window}"] = prior_low
        denominator = (prior_high - prior_low).replace(0.0, np.nan)
        x[f"prior_range_pos_{window}"] = (close - prior_low) / denominator

    x["signal_time"] = x["dt"] + pd.Timedelta(hours=1)
    x["entry_timestamp"] = x["timestamp"] + MS_HOUR
    x["signal_hour_utc"] = x["signal_time"].dt.hour
    x["signal_dow"] = x["signal_time"].dt.dayofweek
    x["event_blackout"] = False
    x["minutes_since_event"] = np.nan
    x["recent_event_3h"] = False
    x["recent_event_6h"] = False

    if not events.empty:
        event_times = datetime_to_epoch_ms(events["event_dt"])
        before = events["blackout_before_minutes"].to_numpy(float) * 60_000.0
        after = events["blackout_after_minutes"].to_numpy(float) * 60_000.0
        signal_ms = datetime_to_epoch_ms(x["signal_time"])
        blackout = np.zeros(len(x), dtype=bool)
        since = np.full(len(x), np.nan, dtype=float)
        for position, value in enumerate(signal_ms):
            insertion = int(np.searchsorted(event_times, value, side="right"))
            candidates: list[int] = []
            if insertion > 0:
                candidates.append(insertion - 1)
                since[position] = (value - event_times[insertion - 1]) / 60_000.0
            if insertion < len(event_times):
                candidates.append(insertion)
            for event_position in candidates:
                if (
                    value >= event_times[event_position] - before[event_position]
                    and value <= event_times[event_position] + after[event_position]
                ):
                    blackout[position] = True
                    break
        x["event_blackout"] = blackout
        x["minutes_since_event"] = since
        x["recent_event_3h"] = (since >= 60.0) & (since <= 180.0)
        x["recent_event_6h"] = (since >= 60.0) & (since <= 360.0)

    if candidate_list:
        validate_candidate_feature_contract(x, candidate_list)
    return x


def directional_signal(frame: pd.DataFrame, spec: CandidateSpec) -> pd.Series:
    p = spec.parameters
    direction = pd.Series(0, index=frame.index, dtype="int8")
    family = spec.family

    if family == "trend_continuation":
        lookback = int(p["lookback_hours"])
        trend_window = int(p["trend_window"])
        minimum_move = float(p["minimum_move"])
        ret = frame[f"ret_{lookback}h"]
        gap = frame[f"sma_gap_{trend_window}"]
        direction[(ret >= minimum_move) & (gap > 0)] = 1
        direction[(ret <= -minimum_move) & (gap < 0)] = -1

    elif family == "trend_pullback":
        trend_window = int(p["trend_window"])
        pullback_hours = int(p["pullback_hours"])
        pullback = frame[f"ret_{pullback_hours}h"]
        gap = frame[f"sma_gap_{trend_window}"]
        maximum_pullback = float(p["maximum_pullback"])
        direction[(gap > 0) & (pullback < 0) & (pullback >= -maximum_pullback)] = 1
        direction[(gap < 0) & (pullback > 0) & (pullback <= maximum_pullback)] = -1

    elif family == "range_breakout":
        window = int(p["range_window"])
        buffer_atr = float(p["buffer_atr"])
        upper = frame[f"prior_high_{window}"] + buffer_atr * frame["atr_14"]
        lower = frame[f"prior_low_{window}"] - buffer_atr * frame["atr_14"]
        direction[frame["close"] > upper] = 1
        direction[frame["close"] < lower] = -1

    elif family == "volatility_expansion":
        range_multiple = float(p["range_atr_multiple"])
        trend_window = int(p["trend_window"])
        expanding = (frame["high"] - frame["low"]) >= range_multiple * frame["atr_14"]
        gap = frame[f"sma_gap_{trend_window}"]
        direction[expanding & (frame["body_pct"] > 0) & (gap > 0)] = 1
        direction[expanding & (frame["body_pct"] < 0) & (gap < 0)] = -1

    elif family == "low_vol_range_reversion":
        window = int(p["range_window"])
        edge = float(p["edge_fraction"])
        low_vol = frame["atr_14_pct"] <= float(p["atr_ratio"]) * frame["atr_120_pct"]
        position = frame[f"prior_range_pos_{window}"]
        direction[low_vol & (position <= edge)] = 1
        direction[low_vol & (position >= 1.0 - edge)] = -1

    elif family == "zscore_reversion":
        window = int(p["window"])
        threshold = float(p["z_threshold"])
        zscore = frame[f"zclose_{window}"]
        direction[zscore <= -threshold] = 1
        direction[zscore >= threshold] = -1

    elif family == "failed_breakout_reversion":
        window = int(p["range_window"])
        prior_high = frame[f"prior_high_{window}"]
        prior_low = frame[f"prior_low_{window}"]
        direction[(frame["high"] > prior_high) & (frame["close"] < prior_high)] = -1
        direction[(frame["low"] < prior_low) & (frame["close"] > prior_low)] = 1

    elif family == "post_event_momentum":
        minimum_atr = float(p["minimum_atr_move"])
        recent_column = "recent_event_3h" if int(p["event_window_hours"]) <= 3 else "recent_event_6h"
        move = frame["close"] - frame["open"]
        recent = frame[recent_column]
        direction[recent & (move >= minimum_atr * frame["atr_14"])] = 1
        direction[recent & (move <= -minimum_atr * frame["atr_14"])] = -1

    elif family == "post_event_breakout":
        window = int(p["range_window"])
        recent_column = "recent_event_3h" if int(p["event_window_hours"]) <= 3 else "recent_event_6h"
        recent = frame[recent_column]
        direction[recent & (frame["close"] > frame[f"prior_high_{window}"])] = 1
        direction[recent & (frame["close"] < frame[f"prior_low_{window}"])] = -1

    elif family == "session_breakout":
        start_hour = int(p["start_hour_utc"])
        end_hour = int(p["end_hour_utc"])
        window = int(p["range_window"])
        hour = frame["signal_hour_utc"]
        in_session = (hour >= start_hour) & (hour <= end_hour)
        direction[in_session & (frame["close"] > frame[f"prior_high_{window}"])] = 1
        direction[in_session & (frame["close"] < frame[f"prior_low_{window}"])] = -1

    else:
        raise ScanError(f"unknown family: {family}")

    if spec.event_policy == "blackout":
        direction[frame["event_blackout"].fillna(False)] = 0
    elif spec.event_policy == "require_recent":
        direction[~frame["recent_event_6h"].fillna(False)] = 0
    elif spec.event_policy != "ignore":
        raise ScanError(f"unknown event policy: {spec.event_policy}")

    direction[frame["signal_dow"] >= 5] = 0
    return direction


def outcome_arrays(frame: pd.DataFrame, horizon_hours: int) -> pd.DataFrame:
    timestamps = frame["timestamp"].to_numpy(np.int64)
    opens = frame["open"].to_numpy(float)
    closes = frame["close"].to_numpy(float)
    timestamp_to_position = {int(value): position for position, value in enumerate(timestamps)}
    records: list[dict[str, Any]] = []
    for position, timestamp in enumerate(timestamps):
        entry_timestamp = int(timestamp + MS_HOUR)
        exit_bar_timestamp = int(entry_timestamp + (horizon_hours - 1) * MS_HOUR)
        entry_position = timestamp_to_position.get(entry_timestamp)
        exit_position = timestamp_to_position.get(exit_bar_timestamp)
        if entry_position is None or exit_position is None:
            continue
        records.append(
            {
                "signal_timestamp": int(timestamp),
                "entry_timestamp": entry_timestamp,
                "exit_bar_timestamp": exit_bar_timestamp,
                "exit_time": exit_bar_timestamp + MS_HOUR,
                "entry_open": float(opens[entry_position]),
                "exit_close": float(closes[exit_position]),
            }
        )
    return pd.DataFrame(records)


TRADE_COLUMNS = [
    "candidate", "family", "horizon_hours", "signal_timestamp",
    "entry_timestamp", "exit_time", "signal_utc", "entry_utc", "exit_utc",
    "direction", "entry_open", "exit_close", "gross_bps",
    "normal_net_bps", "severe_net_bps",
]


def empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=TRADE_COLUMNS)


def candidate_trades(
    frame: pd.DataFrame,
    spec: CandidateSpec,
    normal_cost_bps: float,
    severe_cost_bps: float,
) -> pd.DataFrame:
    direction = directional_signal(frame, spec)
    outcomes = outcome_arrays(frame, spec.horizon_hours)
    if outcomes.empty:
        return empty_trades()
    signal_map = dict(zip(frame["timestamp"].astype(int), direction.astype(int)))
    records: list[dict[str, Any]] = []
    next_allowed_entry = -2**63
    for row in outcomes.itertuples(index=False):
        side = int(signal_map.get(int(row.signal_timestamp), 0))
        if side == 0 or int(row.entry_timestamp) < next_allowed_entry:
            continue
        gross = side * (float(row.exit_close) / float(row.entry_open) - 1.0) * 10_000.0
        records.append(
            {
                "candidate": spec.key,
                "family": spec.family,
                "horizon_hours": spec.horizon_hours,
                "signal_timestamp": int(row.signal_timestamp),
                "entry_timestamp": int(row.entry_timestamp),
                "exit_time": int(row.exit_time),
                "signal_utc": pd.to_datetime(row.signal_timestamp, unit="ms", utc=True),
                "entry_utc": pd.to_datetime(row.entry_timestamp, unit="ms", utc=True),
                "exit_utc": pd.to_datetime(row.exit_time, unit="ms", utc=True),
                "direction": side,
                "entry_open": float(row.entry_open),
                "exit_close": float(row.exit_close),
                "gross_bps": gross,
                "normal_net_bps": gross - normal_cost_bps,
                "severe_net_bps": gross - severe_cost_bps,
            }
        )
        next_allowed_entry = int(row.exit_time)
    return pd.DataFrame(records, columns=TRADE_COLUMNS)


def profit_factor(values: Iterable[float]) -> float | None:
    array = np.asarray(list(values), dtype=float)
    gains = float(array[array > 0].sum())
    losses = float(-array[array < 0].sum())
    if losses == 0:
        return None if gains == 0 else 999.0
    return gains / losses


def max_drawdown_bps(values: Sequence[float]) -> float:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return 0.0
    equity = np.cumsum(array)
    peaks = np.maximum.accumulate(np.r_[0.0, equity])
    return float(np.max(peaks[1:] - equity))


def equity_curve_cagr(
    trades: pd.DataFrame,
    risk_notional_ratio: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[float | None, float]:
    equity = 1.0
    if not trades.empty:
        for value in trades.sort_values("exit_time")["severe_net_bps"].to_numpy(float):
            equity *= max(0.000001, 1.0 + value / 10_000.0 * risk_notional_ratio)
    years = max((end - start).total_seconds() / (365.2425 * 86400.0), 1e-9)
    cagr = equity ** (1.0 / years) - 1.0 if equity > 0 else None
    return (float(cagr) if cagr is not None else None, float(equity))


def moving_block_bootstrap(
    values: Sequence[float],
    block_length: int,
    replications: int,
    random_state: int,
) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return {"p10_mean_bps": None, "probability_mean_le_zero": None, "replications": 0}
    block = max(1, min(int(block_length), len(array)))
    rng = np.random.default_rng(int(random_state))
    replications = int(replications)
    means = np.empty(replications, dtype=float)
    blocks_needed = int(math.ceil(len(array) / block))
    offsets = np.arange(block, dtype=np.int64)
    batch_size = 256
    for batch_start in range(0, replications, batch_size):
        batch_end = min(replications, batch_start + batch_size)
        starts = rng.integers(
            0, len(array), size=(batch_end - batch_start, blocks_needed), dtype=np.int64
        )
        indices = (starts[:, :, None] + offsets[None, None, :]) % len(array)
        indices = indices.reshape(batch_end - batch_start, -1)[:, : len(array)]
        means[batch_start:batch_end] = array[indices].mean(axis=1)
    return {
        "p10_mean_bps": float(np.quantile(means, 0.10)),
        "probability_mean_le_zero": float(np.mean(means <= 0.0)),
        "replications": int(replications),
        "block_length": block,
    }


def year_profit_concentration(trades: pd.DataFrame, column: str) -> float | None:
    if trades.empty:
        return None
    grouped = trades.assign(year=trades["entry_utc"].dt.year).groupby("year")[column].sum()
    positive = grouped[grouped > 0]
    total = float(positive.sum())
    if total <= 0:
        return None
    return float(positive.max() / total)


def metrics(
    trades: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    risk_notional_ratio: float,
    bootstrap_config: Mapping[str, Any],
) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0,
            "mean_normal_net_bps": None,
            "mean_severe_net_bps": None,
            "median_severe_net_bps": None,
            "profit_factor_severe": None,
            "win_rate_severe": None,
            "max_drawdown_severe_bps": None,
            "bootstrap_p10_mean_bps": None,
            "bootstrap_probability_mean_le_zero": None,
            "remove_largest_winner_mean_bps": None,
            "remove_largest_winner_profit_factor": None,
            "maximum_single_year_positive_profit_share": None,
            "strict_replay_cagr": None,
            "final_equity": 1.0,
            "first_trade_utc": None,
            "last_trade_utc": None,
        }
    severe = trades["severe_net_bps"].to_numpy(float)
    normal = trades["normal_net_bps"].to_numpy(float)
    bootstrap = moving_block_bootstrap(
        severe,
        int(bootstrap_config["block_length"]),
        int(bootstrap_config["replications"]),
        int(bootstrap_config["random_state"]),
    )
    largest_position = int(np.argmax(severe))
    without_largest = np.delete(severe, largest_position)
    cagr, equity = equity_curve_cagr(trades, risk_notional_ratio, start, end)
    return {
        "trades": int(len(trades)),
        "mean_normal_net_bps": float(np.mean(normal)),
        "mean_severe_net_bps": float(np.mean(severe)),
        "median_severe_net_bps": float(np.median(severe)),
        "profit_factor_severe": profit_factor(severe),
        "win_rate_severe": float(np.mean(severe > 0)),
        "max_drawdown_severe_bps": max_drawdown_bps(severe),
        "bootstrap_p10_mean_bps": bootstrap["p10_mean_bps"],
        "bootstrap_probability_mean_le_zero": bootstrap["probability_mean_le_zero"],
        "remove_largest_winner_mean_bps": (
            float(np.mean(without_largest)) if without_largest.size else None
        ),
        "remove_largest_winner_profit_factor": profit_factor(without_largest),
        "maximum_single_year_positive_profit_share": year_profit_concentration(
            trades, "severe_net_bps"
        ),
        "strict_replay_cagr": cagr,
        "final_equity": equity,
        "first_trade_utc": trades["entry_utc"].min().isoformat(),
        "last_trade_utc": trades["entry_utc"].max().isoformat(),
    }


def fold_metrics(
    trades: pd.DataFrame,
    folds: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    means: list[float] = []
    for fold in folds:
        start = pd.Timestamp(fold["start"])
        end = pd.Timestamp(fold["end"])
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        if end.tzinfo is None:
            end = end.tz_localize("UTC")
        subset = trades[(trades["entry_utc"] >= start) & (trades["entry_utc"] < end)]
        values = subset["severe_net_bps"].to_numpy(float) if not subset.empty else np.array([])
        mean = float(np.mean(values)) if values.size else None
        if mean is not None:
            means.append(mean)
        rows.append(
            {
                "fold": fold["name"],
                "start": start.isoformat(),
                "end": end.isoformat(),
                "trades": int(len(subset)),
                "mean_severe_net_bps": mean,
                "profit_factor_severe": profit_factor(values),
            }
        )
    return rows, {
        "positive_fold_share": float(np.mean(np.asarray(means) > 0)) if means else None,
        "minimum_fold_mean_severe_bps": float(np.min(means)) if means else None,
        "median_fold_mean_severe_bps": float(np.median(means)) if means else None,
    }


def gate_results(metric: Mapping[str, Any], gates: Mapping[str, Any], *, reference: bool) -> dict[str, bool]:
    results = {
        "minimum_trades": int(metric.get("trades") or 0) >= int(gates["minimum_trades"]),
        "severe_mean_positive": metric.get("mean_severe_net_bps") is not None
        and float(metric["mean_severe_net_bps"]) > float(gates.get("minimum_severe_mean_bps", 0.0)),
        "profit_factor": metric.get("profit_factor_severe") is not None
        and float(metric["profit_factor_severe"]) >= float(gates["minimum_profit_factor"]),
        "bootstrap_p10_positive": metric.get("bootstrap_p10_mean_bps") is not None
        and float(metric["bootstrap_p10_mean_bps"]) > float(gates.get("minimum_bootstrap_p10_bps", 0.0)),
        "positive_without_largest_winner": metric.get("remove_largest_winner_mean_bps") is not None
        and float(metric["remove_largest_winner_mean_bps"]) > 0.0,
    }
    if reference:
        results["positive_fold_share"] = metric.get("positive_fold_share") is not None and float(
            metric["positive_fold_share"]
        ) >= float(gates["minimum_positive_fold_share"])
        results["strict_replay_cagr"] = metric.get("strict_replay_cagr") is not None and float(
            metric["strict_replay_cagr"]
        ) >= float(gates["minimum_strict_replay_cagr"])
    return results


def robust_score(metric: Mapping[str, Any]) -> float:
    values = [
        metric.get("median_fold_mean_severe_bps"),
        metric.get("minimum_fold_mean_severe_bps"),
        metric.get("bootstrap_p10_mean_bps"),
        metric.get("profit_factor_severe"),
        metric.get("strict_replay_cagr"),
    ]
    if any(value is None or not np.isfinite(float(value)) for value in values):
        return -1e12
    return float(
        float(values[0])
        + 0.35 * float(values[1])
        + 0.50 * float(values[2])
        + 8.0 * math.log(max(float(values[3]), 1e-6))
        + 100.0 * float(values[4])
    )


def select_family_diverse_shortlist(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (bool(row["reference_pass"]), float(row["robust_score"])),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    families: set[str] = set()
    for row in ordered:
        if row["family"] in families:
            continue
        selected.append(row)
        families.add(row["family"])
        if len(selected) >= count:
            return selected
    for row in ordered:
        if row in selected:
            continue
        selected.append(row)
        if len(selected) >= count:
            break
    return selected


def parse_candidates(config: Mapping[str, Any]) -> list[CandidateSpec]:
    candidates = [
        CandidateSpec(
            key=item["key"],
            family=item["family"],
            horizon_hours=int(item["horizon_hours"]),
            parameters=dict(item.get("parameters") or {}),
            event_policy=item.get("event_policy", "blackout"),
        )
        for item in config["candidates"]
    ]
    keys = [item.key for item in candidates]
    if len(keys) != len(set(keys)):
        raise ScanError("duplicate candidate key")
    return candidates


def flatten_for_csv(row: Mapping[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            flattened[key] = json.dumps(value, sort_keys=True)
        else:
            flattened[key] = value
    return flattened


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flattened = [flatten_for_csv(row) for row in rows]
    keys: list[str] = []
    for row in flattened:
        for key in row:
            if key not in keys:
                keys.append(key)
    keys = keys or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(flattened)


def markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# XAUUSD Successor Parallel Scan",
        "",
        f"Decision: `{summary['decision']}`",
        "",
        "## Holdout discipline",
        "",
        "- Candidate selection used only the pre-2025 reference window.",
        "- The shortlist was frozen before 2025+ holdout evaluation.",
        "- The holdout access lock prevents silent reruns in the same output directory.",
        "- No order path exists in this program.",
        "",
        "## Frozen shortlist",
        "",
    ]
    for candidate in summary["shortlist"]:
        lines.append(
            f"- `{candidate['key']}` — family `{candidate['family']}`, "
            f"reference pass `{candidate['reference_pass']}`, holdout pass `{candidate['holdout_pass']}`"
        )
    lines.extend(
        [
            "",
            "## Commercial gates",
            "",
            "Final promotion requires holdout PF and severe mean, positive block-bootstrap p10,",
            "positive result after removing the largest winner, full-history positive-year",
            "concentration no greater than 40%, and at least 2% strict replay CAGR under",
            "the locked notional-to-equity contract.",
            "",
            "Live, demo and paper-order authorization remain false.",
            "",
        ]
    )
    return "\n".join(lines)


def data_fingerprint(path: Path, frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "rows": int(len(frame)),
        "first_utc": frame["dt"].iloc[0].isoformat(),
        "last_utc": frame["dt"].iloc[-1].isoformat(),
    }


def run(root: Path, config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = read_json(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / "successor_holdout_access_lock.json"
    if lock_path.exists():
        existing = read_json(lock_path)
        raise ScanError(
            f"{DECISION_LOCKED}: holdout already accessed at {existing.get('generated_utc')}"
        )

    alignment_db = resolve_path(root, config["alignment_db"])
    event_db = resolve_path(root, config["event_db"])
    time_contract_path = resolve_path(root, config["time_contract"])
    time_contract = read_alignment_contract(time_contract_path)
    h1 = load_h1(
        alignment_db,
        config["h1_table"],
        int(config["minimum_m5_bar_count"]),
    )
    events = load_events(event_db)
    candidates = parse_candidates(config)
    features = build_features(h1, events, candidates)
    feature_contract = validate_candidate_feature_contract(features, candidates)

    reference_start = pd.Timestamp(config["reference_start"])
    holdout_start = pd.Timestamp(config["holdout_start"])
    if reference_start.tzinfo is None:
        reference_start = reference_start.tz_localize("UTC")
    if holdout_start.tzinfo is None:
        holdout_start = holdout_start.tz_localize("UTC")
    data_end = features["dt"].max() + pd.Timedelta(hours=1)
    if data_end <= holdout_start:
        raise ScanError("dataset has no holdout rows")

    normal_cost = float(config["normal_cost_bps"])
    severe_cost = float(config["severe_cost_bps"])
    risk_ratio = float(config["maximum_notional_to_equity"])
    bootstrap_config = config["bootstrap"]

    reference_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    reference_trades_by_key: dict[str, pd.DataFrame] = {}
    full_trades_by_key: dict[str, pd.DataFrame] = {}

    for spec in candidates:
        trades = candidate_trades(features, spec, normal_cost, severe_cost)
        full_trades_by_key[spec.key] = trades
        reference_trades = trades[
            (trades["entry_utc"] >= reference_start)
            & (trades["entry_utc"] < holdout_start)
        ].copy() if not trades.empty else empty_trades()
        reference_trades_by_key[spec.key] = reference_trades
        metric = metrics(
            reference_trades,
            reference_start,
            holdout_start,
            risk_ratio,
            bootstrap_config,
        )
        folds, fold_summary = fold_metrics(reference_trades, config["reference_folds"])
        metric.update(fold_summary)
        gates = gate_results(metric, config["reference_gates"], reference=True)
        row = {
            "key": spec.key,
            "family": spec.family,
            "horizon_hours": spec.horizon_hours,
            "event_policy": spec.event_policy,
            "parameters": spec.parameters,
            **metric,
            "reference_gates": gates,
            "reference_pass": all(gates.values()),
        }
        row["robust_score"] = robust_score(row)
        reference_rows.append(row)
        for fold in folds:
            fold_rows.append({"candidate": spec.key, "family": spec.family, **fold})

    shortlist = select_family_diverse_shortlist(
        reference_rows, int(config["shortlist_size"])
    )
    shortlist_keys = [row["key"] for row in shortlist]
    shortlist_contract = {
        "program": PROGRAM_VERSION,
        "generated_utc": now_utc(),
        "selection_boundary_utc": holdout_start.isoformat(),
        "selection_used_holdout": False,
        "shortlist": shortlist_keys,
        "reference_ranking": [row["key"] for row in sorted(reference_rows, key=lambda r: r["robust_score"], reverse=True)],
        "config_sha256": sha256_file(config_path),
        "alignment_fingerprint": data_fingerprint(alignment_db, h1),
        "feature_contract": feature_contract,
        "execution_allowed": False,
    }
    write_json(output_dir / "successor_shortlist_contract.json", shortlist_contract)

    # The lock is written before any holdout metric is persisted. A crash cannot
    # silently turn the holdout into a reusable tuning set.
    holdout_lock = {
        "program": PROGRAM_VERSION,
        "generated_utc": now_utc(),
        "decision": "HOLDOUT_ACCESS_CONSUMED_SHORTLIST_FROZEN",
        "shortlist": shortlist_keys,
        "selection_used_holdout": False,
        "config_sha256": shortlist_contract["config_sha256"],
        "alignment_sha256": shortlist_contract["alignment_fingerprint"]["sha256"],
        "rerun_in_same_output_dir_allowed": False,
    }
    write_json(lock_path, holdout_lock)

    holdout_rows: list[dict[str, Any]] = []
    holdout_trade_frames: list[pd.DataFrame] = []
    final_shortlist: list[dict[str, Any]] = []
    for selected in shortlist:
        key = selected["key"]
        full_trades = full_trades_by_key[key]
        holdout_trades = full_trades[full_trades["entry_utc"] >= holdout_start].copy()
        holdout_metric = metrics(
            holdout_trades,
            holdout_start,
            data_end,
            risk_ratio,
            bootstrap_config,
        )
        holdout_gates = gate_results(
            holdout_metric, config["holdout_gates"], reference=False
        )
        combined_trades = full_trades[
            (full_trades["entry_utc"] >= reference_start)
            & (full_trades["entry_utc"] < data_end)
        ].copy()
        combined_metric = metrics(
            combined_trades,
            reference_start,
            data_end,
            risk_ratio,
            bootstrap_config,
        )
        full_history_gates = {
            "maximum_single_year_profit_share": combined_metric.get(
                "maximum_single_year_positive_profit_share"
            )
            is not None
            and float(combined_metric["maximum_single_year_positive_profit_share"])
            <= float(config["full_history_gates"]["maximum_single_year_profit_share"]),
            "strict_replay_cagr": combined_metric.get("strict_replay_cagr") is not None
            and float(combined_metric["strict_replay_cagr"])
            >= float(config["full_history_gates"]["minimum_strict_replay_cagr"]),
        }
        final_pass = bool(selected["reference_pass"]) and all(holdout_gates.values()) and all(
            full_history_gates.values()
        )
        holdout_row = {
            "key": key,
            "family": selected["family"],
            **holdout_metric,
            "holdout_gates": holdout_gates,
            "holdout_pass": all(holdout_gates.values()),
            "combined_full_history": combined_metric,
            "full_history_gates": full_history_gates,
            "final_pass": final_pass,
        }
        holdout_rows.append(holdout_row)
        final_shortlist.append(
            {
                "key": key,
                "family": selected["family"],
                "reference_pass": bool(selected["reference_pass"]),
                "holdout_pass": bool(holdout_row["holdout_pass"]),
                "full_history_pass": all(full_history_gates.values()),
                "final_pass": final_pass,
            }
        )
        if not holdout_trades.empty:
            holdout_trade_frames.append(holdout_trades.assign(shortlist_candidate=key))

    any_reference_pass = any(bool(row["reference_pass"]) for row in reference_rows)
    any_final_pass = any(bool(row["final_pass"]) for row in holdout_rows)
    if any_final_pass:
        decision = DECISION_SURVIVOR
    elif any_reference_pass:
        decision = DECISION_HOLDOUT_FAIL
    else:
        decision = DECISION_REFERENCE_FAIL

    summary = {
        "program": PROGRAM_VERSION,
        "generated_utc": now_utc(),
        "decision": decision,
        "pass": any_final_pass,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "selection_used_holdout": False,
        "reference_start_utc": reference_start.isoformat(),
        "holdout_start_utc": holdout_start.isoformat(),
        "data_end_utc": data_end.isoformat(),
        "time_contract": time_contract,
        "data_quality": {
            "rows": int(len(h1)),
            "first_utc": h1["dt"].iloc[0].isoformat(),
            "last_utc": h1["dt"].iloc[-1].isoformat(),
            "official_event_rows": int(len(events)),
            "feature_contract": feature_contract,
        },
        "commercial_contract": {
            "normal_cost_bps": normal_cost,
            "severe_cost_bps": severe_cost,
            "maximum_notional_to_equity": risk_ratio,
            "maximum_single_year_profit_share_applies_to": "FULL_REFERENCE_PLUS_HOLDOUT_REPLAY",
            "minimum_strict_replay_cagr_applies_to": "FULL_REFERENCE_PLUS_HOLDOUT_REPLAY",
        },
        "candidate_count": len(reference_rows),
        "reference_pass_count": int(sum(bool(row["reference_pass"]) for row in reference_rows)),
        "shortlist": final_shortlist,
        "holdout_access_lock": str(lock_path),
        "required_next_action": (
            "RUN_STRICT_PROMOTION_AUDIT_ON_FINAL_SURVIVOR"
            if any_final_pass
            else "CHANGE_FORMULATION_FAMILY_OR_DATA_AND_DO_NOT_TUNE_ON_2025_PLUS"
        ),
    }

    write_json(output_dir / "successor_scan_summary.json", summary)
    write_csv(output_dir / "successor_reference_candidate_metrics.csv", reference_rows)
    write_csv(output_dir / "successor_reference_fold_metrics.csv", fold_rows)
    write_csv(output_dir / "successor_holdout_metrics.csv", holdout_rows)
    write_csv(
        output_dir / "successor_reference_trades.csv",
        [
            flatten_for_csv(record)
            for key, trades in reference_trades_by_key.items()
            for record in (
                trades.assign(shortlist_candidate=key).to_dict("records")
                if not trades.empty
                else []
            )
        ],
    )
    combined_holdout = (
        pd.concat(holdout_trade_frames, ignore_index=True)
        if holdout_trade_frames
        else pd.DataFrame()
    )
    combined_holdout.to_csv(output_dir / "successor_holdout_trades.csv", index=False)
    atomic_write(output_dir / "successor_decision.md", markdown(summary) + "\n")
    stale_failure = output_dir / "successor_scan_failure.json"
    if stale_failure.is_file():
        stale_failure.unlink()
    return summary



def collect_results(root: Path, config_path: Path, output_dir: Path, destination: Path) -> dict[str, Any]:
    summary_path = output_dir / "successor_scan_summary.json"
    if not summary_path.is_file():
        raise ScanError(f"successor scan summary missing: {summary_path}")
    names = [
        "successor_scan_summary.json",
        "successor_shortlist_contract.json",
        "successor_holdout_access_lock.json",
        "successor_reference_candidate_metrics.csv",
        "successor_reference_fold_metrics.csv",
        "successor_reference_trades.csv",
        "successor_holdout_metrics.csv",
        "successor_holdout_trades.csv",
        "successor_decision.md",
        "successor_scan_failure.json",
    ]
    files = [output_dir / name for name in names if (output_dir / name).is_file()]
    if config_path.is_file():
        files.append(config_path)
    import zipfile

    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "program": PROGRAM_VERSION,
        "generated_utc": now_utc(),
        "source_output_dir": str(output_dir),
        "files": [],
    }
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            arcname = (
                f"reports/{path.name}" if path.parent == output_dir else f"config/{path.name}"
            )
            archive.write(path, arcname)
            manifest["files"].append(
                {
                    "archive_path": arcname,
                    "source_path": str(path),
                    "sha256": sha256_file(path),
                    "size": path.stat().st_size,
                }
            )
        archive.writestr(
            "RESULTS_MANIFEST.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
    return {
        "program": PROGRAM_VERSION,
        "generated_utc": now_utc(),
        "decision": "PASS_SUCCESSOR_SCAN_RESULTS_PACK_CREATED",
        "pass": True,
        "paper_order_allowed": False,
        "demo_order_allowed": False,
        "live_order_allowed": False,
        "output_zip": str(destination),
        "sha256": sha256_file(destination),
        "files": len(files),
    }

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "preflight", "collect"])
    parser.add_argument("--root", default=str(repo_root()))
    parser.add_argument(
        "--config", default="configs/xauusd_successor_parallel_scan_v1.json"
    )
    parser.add_argument("--out", default="reports/xauusd_successor_parallel_scan")
    parser.add_argument(
        "--results-zip",
        default="~/Downloads/XAUUSD_SUCCESSOR_PARALLEL_SCAN_RESULTS.zip",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    config_path = resolve_path(root, args.config)
    output_dir = resolve_path(root, args.out)
    try:
        config = read_json(config_path)
        if args.command == "collect":
            destination = Path(os.path.expanduser(args.results_zip)).resolve()
            result = collect_results(root, config_path, output_dir, destination)
            print(json.dumps(result, indent=2, default=json_default))
            return 0
        alignment_db = resolve_path(root, config["alignment_db"])
        time_contract = read_alignment_contract(resolve_path(root, config["time_contract"]))
        h1 = load_h1(alignment_db, config["h1_table"], int(config["minimum_m5_bar_count"]))
        candidates = parse_candidates(config)
        feature_plan = candidate_feature_plan(candidates)
        preflight = {
            "program": PROGRAM_VERSION,
            "generated_utc": now_utc(),
            "decision": "PASS_SUCCESSOR_SCAN_PREFLIGHT_NO_HOLDOUT_ACCESS",
            "pass": True,
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "time_contract": time_contract,
            "alignment": data_fingerprint(alignment_db, h1),
            "candidate_count": len(candidates),
            "candidate_feature_plan": feature_plan,
            "candidate_feature_contract_config_valid": True,
        }
        if args.command == "preflight":
            print(json.dumps(preflight, indent=2, default=json_default))
            return 0
        summary = run(root, config_path, output_dir)
        print(json.dumps(summary, indent=2, default=json_default))
        return 0 if summary["decision"] != DECISION_LOCKED else 2
    except Exception as exc:
        failure = {
            "program": PROGRAM_VERSION,
            "generated_utc": now_utc(),
            "decision": (
                DECISION_LOCKED if DECISION_LOCKED in str(exc) else "SUCCESSOR_SCAN_FAIL_CLOSED"
            ),
            "pass": False,
            "paper_order_allowed": False,
            "demo_order_allowed": False,
            "live_order_allowed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "successor_scan_failure.json", failure)
        print(json.dumps(failure, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
