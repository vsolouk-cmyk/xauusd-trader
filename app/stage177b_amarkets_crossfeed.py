#!/usr/bin/env python3
"""Stage177B repair: robust AMarkets ↔ Dukascopy cross-feed audit.

Research-only diagnostic. This script never emits trade signals or orders.

Repairs versus the first Stage177B version:
- deterministic delimiter detection instead of accepting a weak sniff result;
- explicit MT5 date/time parsing;
- raw/accepted row and date-range diagnostics;
- fail-closed retention checks;
- no fabricated "best shift" when every candidate has zero/insufficient overlap;
- prefer M5-derived AMarkets H1 if the direct H1 source is truncated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Stage177B cross-feed comparison requires pandas and numpy") from exc

H1_MS = 3_600_000
M5_MS = 300_000
MIN_EVALUATION_OVERLAP = 100


def normalize_name(value: str) -> str:
    value = str(value).strip().lower().replace("<", "").replace(">", "")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def existing_candidates(candidates: list[str]) -> list[Path]:
    output: list[Path] = []
    for raw in candidates:
        path = Path(raw).expanduser()
        if path.exists() and path.is_file():
            output.append(path.resolve())
    return output


def find_best_existing(candidates: list[str]) -> Path | None:
    existing = existing_candidates(candidates)
    if not existing:
        return None
    # Historical AMarkets exports are large. Prefer the largest source; mtime is
    # only a tie-breaker so a tiny rolling tail cannot shadow a full archive.
    return max(existing, key=lambda path: (path.stat().st_size, path.stat().st_mtime))


def detect_separator(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        lines = []
        for line in handle:
            if line.strip():
                lines.append(line.rstrip("\r\n"))
            if len(lines) >= 8:
                break
    if not lines:
        raise ValueError(f"Empty AMarkets file: {path}")

    candidates = ["\t", ",", ";", "|"]
    header = lines[0]
    counts = {sep: header.count(sep) for sep in candidates}
    best = max(candidates, key=lambda sep: counts[sep])
    if counts[best] <= 0:
        raise ValueError(
            f"Could not detect delimiter in {path}; header={header[:300]!r}"
        )
    return best


def read_flexible_csv(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    separator = detect_separator(path)
    frame = pd.read_csv(
        path,
        sep=separator,
        encoding="utf-8-sig",
        low_memory=False,
        dtype=str,
    )
    original_columns = [str(column) for column in frame.columns]
    frame.columns = [normalize_name(column) for column in frame.columns]
    if frame.shape[1] < 5:
        raise ValueError(
            f"AMarkets schema has fewer than five columns: {original_columns}"
        )
    diagnostics = {
        "path": str(path),
        "file_size_bytes": int(path.stat().st_size),
        "sha256": sha256_file(path),
        "separator": "TAB" if separator == "\t" else separator,
        "raw_rows": int(len(frame)),
        "original_columns": original_columns,
        "normalized_columns": list(frame.columns),
    }
    return frame, diagnostics


def pick_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _parse_string_timestamp(raw: pd.Series) -> pd.Series:
    text = raw.astype(str).str.strip()
    timezone_marked = text.str.contains(
        r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True, na=False
    ).mean() > 0.50

    if timezone_marked:
        aware = pd.to_datetime(text, errors="coerce", utc=True)
        return aware.dt.tz_convert("UTC").dt.tz_localize(None)

    parsed = pd.Series(pd.NaT, index=text.index, dtype="datetime64[ns]")
    formats = (
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d %H:%M",
    )
    for fmt in formats:
        missing = parsed.isna()
        if not missing.any():
            break
        candidate = pd.to_datetime(text[missing], format=fmt, errors="coerce")
        parsed.loc[candidate.index] = candidate

    missing = parsed.isna()
    if missing.any():
        try:
            candidate = pd.to_datetime(text[missing], errors="coerce", format="mixed")
        except TypeError:  # pandas < 2
            candidate = pd.to_datetime(
                text[missing], errors="coerce", infer_datetime_format=True
            )
        parsed.loc[candidate.index] = candidate
    return parsed


def parse_timestamp(frame: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    columns = list(frame.columns)
    date_col = pick_column(columns, ("date", "day"))
    time_col = pick_column(columns, ("time", "hour"))
    direct = pick_column(
        columns,
        (
            "timestamp",
            "datetime",
            "date_time",
            "time_stamp",
            "open_time",
            "time_utc",
            "datetime_utc",
        ),
    )

    source_columns: list[str]
    if date_col and time_col and date_col != time_col:
        raw = (
            frame[date_col].astype(str).str.strip()
            + " "
            + frame[time_col].astype(str).str.strip()
        )
        source_columns = [date_col, time_col]
    elif direct:
        raw = frame[direct]
        source_columns = [direct]
    elif date_col:
        raw = frame[date_col]
        source_columns = [date_col]
    elif time_col:
        raw = frame[time_col]
        source_columns = [time_col]
    else:
        raise ValueError(f"No timestamp/date column found: {columns}")

    # Numeric epoch parsing is allowed only for a direct timestamp column. A
    # split MT5 DATE/TIME pair such as 2026.07.20 must never be treated as a
    # decimal number.
    numeric = pd.to_numeric(raw, errors="coerce") if len(source_columns) == 1 else None
    if numeric is not None and numeric.notna().mean() > 0.98:
        median = float(numeric.dropna().abs().median())
        if median > 1e14:
            parsed = pd.to_datetime(numeric, unit="ns", errors="coerce")
            mode = "epoch_ns"
        elif median > 1e11:
            parsed = pd.to_datetime(numeric, unit="ms", errors="coerce")
            mode = "epoch_ms"
        elif median > 1e9:
            parsed = pd.to_datetime(numeric, unit="s", errors="coerce")
            mode = "epoch_s"
        else:
            parsed = pd.to_datetime(
                numeric, unit="D", origin="1899-12-30", errors="coerce"
            )
            mode = "excel_serial_day"
    else:
        parsed = _parse_string_timestamp(raw)
        mode = "explicit_string_formats"

    success = float(parsed.notna().mean()) if len(parsed) else 0.0
    diagnostics = {
        "timestamp_source_columns": source_columns,
        "timestamp_parse_mode": mode,
        "timestamp_parse_success_pct": success * 100.0,
        "timestamp_parse_failures": int(parsed.isna().sum()),
    }
    if success < 0.90:
        sample = raw[parsed.isna()].head(10).astype(str).tolist()
        raise ValueError(
            f"Timestamp parse success below 90% ({success:.3f}); "
            f"source_columns={source_columns}; failed_sample={sample}"
        )
    return parsed, diagnostics


def normalize_ohlc(path: Path, timeframe_ms: int) -> pd.DataFrame:
    frame, diagnostics = read_flexible_csv(path)
    columns = list(frame.columns)
    mapping: dict[str, str] = {}
    for target, candidates in {
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c", "last"),
        "volume": (
            "volume",
            "tick_volume",
            "tickvolume",
            "tickvol",
            "vol",
            "real_volume",
        ),
    }.items():
        picked = pick_column(columns, candidates)
        if target != "volume" and picked is None:
            raise ValueError(f"Missing {target} column in {path}: {columns}")
        if picked:
            mapping[target] = picked

    timestamp, timestamp_diag = parse_timestamp(frame)
    output = pd.DataFrame({"datetime_naive": timestamp})
    for target in ("open", "high", "low", "close"):
        output[target] = pd.to_numeric(frame[mapping[target]], errors="coerce")
    if "volume" in mapping:
        output["volume"] = pd.to_numeric(frame[mapping["volume"]], errors="coerce")
    else:
        output["volume"] = np.nan

    diagnostics.update(timestamp_diag)
    diagnostics["column_mapping"] = mapping
    diagnostics["rows_before_quality_filters"] = int(len(output))
    diagnostics["rows_missing_required"] = int(
        output[["datetime_naive", "open", "high", "low", "close"]]
        .isna()
        .any(axis=1)
        .sum()
    )

    output = output.dropna(
        subset=["datetime_naive", "open", "high", "low", "close"]
    )
    positive = (output[["open", "high", "low", "close"]] > 0).all(axis=1)
    diagnostics["rows_non_positive_price"] = int((~positive).sum())
    output = output[positive].copy()

    invariant = (
        (output["high"] >= output[["open", "close", "low"]].max(axis=1))
        & (output["low"] <= output[["open", "close", "high"]].min(axis=1))
    )
    diagnostics["rows_ohlc_invariant_failed"] = int((~invariant).sum())
    output = output[invariant].copy()

    output["timestamp_naive_ms"] = (
        output["datetime_naive"].astype("int64") // 1_000_000
    ).astype("int64")
    output["timestamp_naive_ms"] = (
        output["timestamp_naive_ms"] // timeframe_ms
    ) * timeframe_ms

    before_dedup = len(output)
    output = output.sort_values("timestamp_naive_ms").drop_duplicates(
        "timestamp_naive_ms", keep="last"
    )
    diagnostics["duplicate_bucket_rows_removed"] = int(before_dedup - len(output))
    diagnostics["normalized_rows"] = int(len(output))
    diagnostics["retained_pct_of_raw"] = (
        100.0 * len(output) / diagnostics["raw_rows"]
        if diagnostics["raw_rows"]
        else 0.0
    )
    if len(output):
        diagnostics["first_timestamp_naive"] = pd.to_datetime(
            int(output.iloc[0]["timestamp_naive_ms"]), unit="ms"
        ).isoformat()
        diagnostics["last_timestamp_naive"] = pd.to_datetime(
            int(output.iloc[-1]["timestamp_naive_ms"]), unit="ms"
        ).isoformat()
    else:
        diagnostics["first_timestamp_naive"] = None
        diagnostics["last_timestamp_naive"] = None

    # A large source collapsing to a tiny tail is a loader/schema failure, not
    # a valid cross-feed result.
    if diagnostics["raw_rows"] >= 1_000 and diagnostics["retained_pct_of_raw"] < 95.0:
        raise ValueError(
            "AMarkets loader retained less than 95% of a large source: "
            + json.dumps(diagnostics, sort_keys=True)
        )

    output = output.reset_index(drop=True)
    output.attrs["loader_diagnostics"] = diagnostics
    return output


def load_sqlite_table(db_path: Path, table: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as connection:
        frame = pd.read_sql_query(
            f"SELECT timestamp, open, high, low, close, volume "
            f"FROM {table} ORDER BY timestamp",
            connection,
        )
    return frame


def valid_log_returns(
    close: pd.Series, timestamps: pd.Series, interval_ms: int
) -> pd.Series:
    returns = np.log(close).diff()
    gap = timestamps.diff()
    returns[(gap <= 0) | (gap > interval_ms * 2)] = np.nan
    return returns


def evaluate_shift(
    amarkets: pd.DataFrame,
    reference: pd.DataFrame,
    shift_minutes: int,
    interval_ms: int,
) -> dict[str, Any]:
    shifted = amarkets.copy()
    shifted["timestamp"] = (
        shifted["timestamp_naive_ms"] + shift_minutes * 60_000
    )
    merged = reference.merge(
        shifted[["timestamp", "open", "high", "low", "close", "volume"]],
        on="timestamp",
        suffixes=("_ref", "_am"),
        how="inner",
    ).sort_values("timestamp")

    overlap = len(merged)
    result: dict[str, Any] = {
        "shift_minutes": shift_minutes,
        "overlap_rows": overlap,
        "close_level_corr": None,
        "return_corr": None,
        "median_abs_close_bps": None,
        "p95_abs_close_bps": None,
        "range_corr": None,
    }
    if overlap < MIN_EVALUATION_OVERLAP:
        return result

    close_level_corr = merged["close_ref"].corr(merged["close_am"])
    ret_ref = valid_log_returns(
        merged["close_ref"], merged["timestamp"], interval_ms
    )
    ret_am = valid_log_returns(
        merged["close_am"], merged["timestamp"], interval_ms
    )
    return_corr = ret_ref.corr(ret_am)
    close_bps = (
        (merged["close_am"] / merged["close_ref"] - 1.0).abs() * 10_000
    )
    range_ref = merged["high_ref"] - merged["low_ref"]
    range_am = merged["high_am"] - merged["low_am"]
    range_corr = range_ref.corr(range_am)

    def finite_or_none(value: float) -> float | None:
        return (
            float(value)
            if value is not None and math.isfinite(float(value))
            else None
        )

    result.update(
        {
            "close_level_corr": finite_or_none(close_level_corr),
            "return_corr": finite_or_none(return_corr),
            "median_abs_close_bps": finite_or_none(close_bps.median()),
            "p95_abs_close_bps": finite_or_none(close_bps.quantile(0.95)),
            "range_corr": finite_or_none(range_corr),
        }
    )
    return result


def score_candidate(item: dict[str, Any]) -> tuple[float, float, int]:
    return (
        item["return_corr"] if item["return_corr"] is not None else -2.0,
        item["close_level_corr"]
        if item["close_level_corr"] is not None
        else -2.0,
        int(item["overlap_rows"]),
    )


def candidate_grid(
    amarkets: pd.DataFrame,
    reference: pd.DataFrame,
    shifts_minutes: list[int],
    interval_ms: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    results = [
        evaluate_shift(amarkets, reference, shift, interval_ms)
        for shift in shifts_minutes
    ]
    eligible = [
        item
        for item in results
        if item["overlap_rows"] >= MIN_EVALUATION_OVERLAP
        and item["return_corr"] is not None
    ]
    if not eligible:
        max_overlap = max((int(item["overlap_rows"]) for item in results), default=0)
        return (
            {
                "status": "INSUFFICIENT_OVERLAP",
                "shift_minutes": None,
                "overlap_rows": max_overlap,
                "close_level_corr": None,
                "return_corr": None,
                "median_abs_close_bps": None,
                "p95_abs_close_bps": None,
                "range_corr": None,
                "return_corr_margin_vs_second": None,
            },
            results,
        )

    ordered = sorted(eligible, key=score_candidate, reverse=True)
    best = dict(ordered[0])
    best["status"] = "EVALUATED"
    if len(ordered) > 1:
        best["return_corr_margin_vs_second"] = (
            float(best["return_corr"]) - float(ordered[1]["return_corr"])
        )
    else:
        best["return_corr_margin_vs_second"] = None
    return best, results


def derive_h1_from_m5(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["hour_naive_ms"] = (
        work["timestamp_naive_ms"] // H1_MS
    ) * H1_MS
    grouped = work.groupby("hour_naive_ms", sort=True)
    result = (
        grouped.agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
        .rename(columns={"hour_naive_ms": "timestamp_naive_ms"})
    )
    return result


def frame_range(frame: pd.DataFrame, timestamp_column: str) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {"rows": 0, "first": None, "last": None}
    first = int(frame[timestamp_column].min())
    last = int(frame[timestamp_column].max())
    return {
        "rows": int(len(frame)),
        "first": pd.to_datetime(first, unit="ms", utc=True).isoformat(),
        "last": pd.to_datetime(last, unit="ms", utc=True).isoformat(),
    }


def has_possible_overlap(
    amarkets: pd.DataFrame,
    reference: pd.DataFrame,
    max_abs_shift_minutes: int,
) -> bool:
    am_first = int(amarkets["timestamp_naive_ms"].min())
    am_last = int(amarkets["timestamp_naive_ms"].max())
    ref_first = int(reference["timestamp"].min())
    ref_last = int(reference["timestamp"].max())
    margin = max_abs_shift_minutes * 60_000
    return not ((am_last + margin) < ref_first or (am_first - margin) > ref_last)


def write_candidates(path: Path, rows: list[dict[str, Any]], label: str) -> None:
    frame = pd.DataFrame(rows)
    frame.insert(0, "timeframe", label)
    if not frame.empty:
        frame = frame.sort_values(
            ["return_corr", "overlap_rows"], ascending=[False, False], na_position="last"
        )
    frame.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(
            "data/local/stage177b_extended_history/xauusd_extended_history.sqlite"
        ),
    )
    parser.add_argument("--amarkets-h1", type=Path)
    parser.add_argument("--amarkets-m5", type=Path)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports/stage177b_extended_history_integration"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.database.expanduser().resolve()
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    h1_candidates = [
        "~/Downloads/amarkets_xauusd_1h.csv",
        "~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_1h.csv",
        "~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_h1.csv",
    ]
    m5_candidates = [
        "~/Downloads/amarkets_xauusd_5m.csv",
        "~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_5m.csv",
        "~/Downloads/xauusd_fundamental_event_inbox/amarkets_xauusd_m5.csv",
    ]

    h1_path = (
        args.amarkets_h1.expanduser().resolve()
        if args.amarkets_h1
        else find_best_existing(h1_candidates)
    )
    m5_path = (
        args.amarkets_m5.expanduser().resolve()
        if args.amarkets_m5
        else find_best_existing(m5_candidates)
    )
    if h1_path is None and m5_path is None:
        raise FileNotFoundError(
            "No AMarkets H1 or M5 CSV found in configured Downloads paths"
        )

    reference_h1 = load_sqlite_table(db_path, "dukascopy_h1_canonical")
    reference_m5 = load_sqlite_table(db_path, "dukascopy_m5") if m5_path else None

    am_h1_direct = normalize_ohlc(h1_path, H1_MS) if h1_path else None
    am_m5 = normalize_ohlc(m5_path, M5_MS) if m5_path else None
    am_h1_from_m5 = derive_h1_from_m5(am_m5) if am_m5 is not None else None

    h1_source_used = "DIRECT_H1"
    if am_h1_direct is None and am_h1_from_m5 is not None:
        am_h1 = am_h1_from_m5
        h1_source_used = "M5_DERIVED_H1"
    elif am_h1_direct is not None and am_h1_from_m5 is not None:
        # A direct H1 source with far fewer rows than M5-derived H1 is almost
        # certainly truncated or mis-exported; do not silently use it.
        if len(am_h1_direct) < max(1_000, int(0.80 * len(am_h1_from_m5))):
            am_h1 = am_h1_from_m5
            h1_source_used = "M5_DERIVED_H1_DIRECT_H1_REJECTED_AS_TRUNCATED"
        else:
            am_h1 = am_h1_direct
    else:
        am_h1 = am_h1_direct

    assert am_h1 is not None

    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    source_diagnostics = {
        "h1_selected_path": str(h1_path) if h1_path else None,
        "m5_selected_path": str(m5_path) if m5_path else None,
        "h1_existing_candidates": [str(path) for path in existing_candidates(h1_candidates)],
        "m5_existing_candidates": [str(path) for path in existing_candidates(m5_candidates)],
        "h1_direct_loader": (
            am_h1_direct.attrs.get("loader_diagnostics")
            if am_h1_direct is not None
            else None
        ),
        "m5_loader": (
            am_m5.attrs.get("loader_diagnostics") if am_m5 is not None else None
        ),
        "h1_source_used": h1_source_used,
        "h1_evaluation_range": frame_range(am_h1, "timestamp_naive_ms"),
        "m5_evaluation_range": (
            frame_range(am_m5, "timestamp_naive_ms") if am_m5 is not None else None
        ),
        "reference_h1_range": frame_range(reference_h1, "timestamp"),
        "reference_m5_range": (
            frame_range(reference_m5, "timestamp")
            if reference_m5 is not None
            else None
        ),
    }
    (report_dir / "stage177b_amarkets_source_diagnostics.json").write_text(
        json.dumps(source_diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    h1_history_too_short = len(am_h1) < 1_000
    m5_history_too_short = am_m5 is not None and len(am_m5) < 5_000
    h1_possible_overlap = has_possible_overlap(am_h1, reference_h1, 14 * 60)
    m5_possible_overlap = (
        has_possible_overlap(am_m5, reference_m5, 14 * 60)
        if am_m5 is not None and reference_m5 is not None
        else True
    )

    h1_best: dict[str, Any]
    h1_grid: list[dict[str, Any]]
    if h1_history_too_short or not h1_possible_overlap:
        h1_best = {
            "status": (
                "SOURCE_HISTORY_TOO_SHORT"
                if h1_history_too_short
                else "DATE_RANGE_NO_OVERLAP"
            ),
            "shift_minutes": None,
            "overlap_rows": 0,
            "close_level_corr": None,
            "return_corr": None,
            "median_abs_close_bps": None,
            "p95_abs_close_bps": None,
            "range_corr": None,
            "return_corr_margin_vs_second": None,
        }
        h1_grid = []
    else:
        h1_shifts = list(range(-14 * 60, 14 * 60 + 1, 60))
        h1_best, h1_grid = candidate_grid(
            am_h1, reference_h1, h1_shifts, H1_MS
        )

    m5_best = None
    m5_grid: list[dict[str, Any]] = []
    if am_m5 is not None and reference_m5 is not None:
        if m5_history_too_short or not m5_possible_overlap:
            m5_best = {
                "status": (
                    "SOURCE_HISTORY_TOO_SHORT"
                    if m5_history_too_short
                    else "DATE_RANGE_NO_OVERLAP"
                ),
                "shift_minutes": None,
                "overlap_rows": 0,
                "close_level_corr": None,
                "return_corr": None,
                "median_abs_close_bps": None,
                "p95_abs_close_bps": None,
                "range_corr": None,
                "return_corr_margin_vs_second": None,
            }
        else:
            if h1_best.get("shift_minutes") is not None:
                center = int(h1_best["shift_minutes"])
            else:
                coarse_shifts = list(range(-14 * 60, 14 * 60 + 1, 60))
                coarse_best, _ = candidate_grid(
                    am_m5, reference_m5, coarse_shifts, M5_MS
                )
                center = int(coarse_best.get("shift_minutes") or 0)
            m5_shifts = list(range(center - 60, center + 60 + 1, 5))
            m5_best, m5_grid = candidate_grid(
                am_m5, reference_m5, m5_shifts, M5_MS
            )

    h1_pass = (
        h1_best.get("status") == "EVALUATED"
        and int(h1_best["overlap_rows"]) >= 5_000
        and float(h1_best["close_level_corr"] or 0.0) >= 0.999
        and float(h1_best["return_corr"] or 0.0) >= 0.98
    )
    m5_pass = True
    if m5_best is not None:
        m5_pass = (
            m5_best.get("status") == "EVALUATED"
            and int(m5_best["overlap_rows"]) >= 20_000
            and float(m5_best["close_level_corr"] or 0.0) >= 0.999
            and float(m5_best["return_corr"] or 0.0) >= 0.90
        )

    if h1_history_too_short or m5_history_too_short:
        decision = "BLOCK_AMARKETS_SOURCE_HISTORY_TOO_SHORT"
    elif not h1_possible_overlap or not m5_possible_overlap:
        decision = "BLOCK_AMARKETS_DATE_RANGE_NO_OVERLAP"
    elif h1_pass and m5_pass:
        decision = "PASS_AMARKETS_CROSSFEED_ALIGNMENT"
    else:
        decision = "REVIEW_AMARKETS_CROSSFEED_ALIGNMENT"

    write_candidates(
        report_dir / "stage177b_h1_shift_candidates.csv", h1_grid, "H1"
    )
    if m5_grid:
        write_candidates(
            report_dir / "stage177b_m5_shift_candidates.csv", m5_grid, "M5"
        )

    summary = {
        "stage": "177B",
        "repair": "AMARKETS_CROSSFEED_LOADER_AND_ALIGNMENT",
        "decision": decision,
        "database": str(db_path),
        "amarkets_h1": str(h1_path) if h1_path else None,
        "amarkets_m5": str(m5_path) if m5_path else None,
        "h1_source_used": h1_source_used,
        "h1_rows_loaded_direct": (
            int(len(am_h1_direct)) if am_h1_direct is not None else None
        ),
        "h1_rows_evaluated": int(len(am_h1)),
        "m5_rows_loaded": int(len(am_m5)) if am_m5 is not None else None,
        "h1_possible_date_overlap": h1_possible_overlap,
        "m5_possible_date_overlap": m5_possible_overlap,
        "h1_best_alignment": h1_best,
        "m5_best_alignment": m5_best,
        "source_diagnostics": str(
            report_dir / "stage177b_amarkets_source_diagnostics.json"
        ),
        "timestamp_shift_semantics": (
            "Add shift_minutes to the naive AMarkets timestamp to align it with UTC."
        ),
        "research_only": True,
        "execution_allowed": False,
    }
    summary_path = report_dir / "stage177b_amarkets_crossfeed_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    decision_md = [
        "# Stage177B AMarkets Cross-Feed Decision — Loader Repair",
        "",
        f"Decision: `{decision}`",
        "",
        f"H1 source used: `{h1_source_used}`",
        f"Direct H1 rows loaded: `{summary['h1_rows_loaded_direct']}`",
        f"H1 rows evaluated: `{summary['h1_rows_evaluated']}`",
        f"M5 rows loaded: `{summary['m5_rows_loaded']}`",
        "",
        f"H1 alignment status: `{h1_best.get('status')}`",
        f"Best H1 timestamp shift: `{h1_best.get('shift_minutes')}` minutes",
        f"H1 overlap: `{h1_best.get('overlap_rows')}` rows",
        f"H1 close correlation: `{h1_best.get('close_level_corr')}`",
        f"H1 return correlation: `{h1_best.get('return_corr')}`",
        f"H1 median absolute close difference: `{h1_best.get('median_abs_close_bps')}` bps",
    ]
    if m5_best is not None:
        decision_md.extend(
            [
                "",
                f"M5 alignment status: `{m5_best.get('status')}`",
                f"Best M5 timestamp shift: `{m5_best.get('shift_minutes')}` minutes",
                f"M5 overlap: `{m5_best.get('overlap_rows')}` rows",
                f"M5 close correlation: `{m5_best.get('close_level_corr')}`",
                f"M5 return correlation: `{m5_best.get('return_corr')}`",
                f"M5 median absolute close difference: `{m5_best.get('median_abs_close_bps')}` bps",
            ]
        )
    decision_md.extend(
        [
            "",
            "Dukascopy remains the extended research feed. AMarkets remains the broker-specific execution/cost feed.",
            "No paper, demo, or live order is authorized.",
        ]
    )
    (report_dir / "stage177b_amarkets_crossfeed_decision.md").write_text(
        "\n".join(decision_md) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))
    return 0 if decision.startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
