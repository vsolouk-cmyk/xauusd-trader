#!/usr/bin/env python3
"""Stage177B: compare canonical Dukascopy history with AMarkets broker CSVs.

This script is diagnostic only. It discovers the timestamp offset and reports
cross-feed price/return/range agreement. It never emits trade signals or orders.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import pandas as pd
except ImportError as exc:  # pragma: no cover - explicit operational error
    raise SystemExit("Stage177B cross-feed comparison requires pandas and numpy") from exc

H1_MS = 3_600_000
M5_MS = 300_000


def normalize_name(value: str) -> str:
    value = str(value).strip().lower()
    value = value.replace("<", "").replace(">", "")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def find_existing(candidates: list[str]) -> Path | None:
    for raw in candidates:
        path = Path(raw).expanduser()
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def read_flexible_csv(path: Path) -> pd.DataFrame:
    attempts: list[tuple[dict[str, Any], str]] = [
        ({"sep": None, "engine": "python"}, "sniffed"),
        ({"sep": "\t"}, "tab"),
        ({"sep": ","}, "comma"),
        ({"sep": ";"}, "semicolon"),
    ]
    last_error: Exception | None = None
    for kwargs, _label in attempts:
        try:
            frame = pd.read_csv(path, low_memory=False, **kwargs)
            if frame.shape[1] >= 5:
                frame.columns = [normalize_name(col) for col in frame.columns]
                return frame
        except Exception as exc:  # try next delimiter
            last_error = exc
    raise ValueError(f"Could not parse {path}: {last_error}")


def pick_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def parse_timestamp(frame: pd.DataFrame) -> pd.Series:
    columns = list(frame.columns)
    date_col = pick_column(columns, ("date", "day"))
    time_col = pick_column(columns, ("time", "hour"))
    direct = pick_column(
        columns,
        (
            "timestamp", "datetime", "date_time", "time_stamp", "open_time",
            "time_utc", "datetime_utc",
        ),
    )

    if date_col and time_col and date_col != time_col:
        raw = frame[date_col].astype(str).str.strip() + " " + frame[time_col].astype(str).str.strip()
    elif direct:
        raw = frame[direct]
    elif date_col:
        raw = frame[date_col]
    elif time_col:
        raw = frame[time_col]
    else:
        raise ValueError(f"No timestamp/date column found: {columns}")

    numeric = pd.to_numeric(raw, errors="coerce")
    if numeric.notna().mean() > 0.98:
        median = float(numeric.dropna().abs().median())
        if median > 1e14:
            parsed = pd.to_datetime(numeric, unit="ns", errors="coerce")
        elif median > 1e11:
            parsed = pd.to_datetime(numeric, unit="ms", errors="coerce")
        elif median > 1e9:
            parsed = pd.to_datetime(numeric, unit="s", errors="coerce")
        else:
            # Excel serial-day fallback.
            parsed = pd.to_datetime(numeric, unit="D", origin="1899-12-30", errors="coerce")
    else:
        try:
            parsed = pd.to_datetime(raw, errors="coerce", format="mixed")
        except TypeError:  # pandas < 2.0
            parsed = pd.to_datetime(raw, errors="coerce", infer_datetime_format=True)

    if parsed.notna().mean() < 0.90:
        raise ValueError(
            f"Timestamp parse success below 90%: {parsed.notna().mean():.3f}"
        )

    # Keep timezone-aware input in UTC; leave naive broker/server timestamps naive
    # so candidate shifts can be tested explicitly.
    try:
        timezone = parsed.dt.tz
    except AttributeError:
        timezone = None
    if timezone is not None:
        parsed = parsed.dt.tz_convert("UTC").dt.tz_localize(None)
    return parsed


def normalize_ohlc(path: Path, timeframe_ms: int) -> pd.DataFrame:
    frame = read_flexible_csv(path)
    columns = list(frame.columns)
    mapping: dict[str, str] = {}
    for target, candidates in {
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c", "last"),
        "volume": ("volume", "tick_volume", "tickvolume", "vol", "real_volume"),
    }.items():
        picked = pick_column(columns, candidates)
        if target != "volume" and picked is None:
            raise ValueError(f"Missing {target} column in {path}: {columns}")
        if picked:
            mapping[target] = picked

    timestamp = parse_timestamp(frame)
    output = pd.DataFrame({"datetime_naive": timestamp})
    for target in ("open", "high", "low", "close"):
        output[target] = pd.to_numeric(frame[mapping[target]], errors="coerce")
    if "volume" in mapping:
        output["volume"] = pd.to_numeric(frame[mapping["volume"]], errors="coerce")
    else:
        output["volume"] = np.nan

    output = output.dropna(subset=["datetime_naive", "open", "high", "low", "close"])
    output = output[(output[["open", "high", "low", "close"]] > 0).all(axis=1)]
    output["timestamp_naive_ms"] = (
        output["datetime_naive"].astype("int64") // 1_000_000
    ).astype("int64")
    output["timestamp_naive_ms"] = (
        output["timestamp_naive_ms"] // timeframe_ms
    ) * timeframe_ms
    output = output.sort_values("timestamp_naive_ms").drop_duplicates(
        "timestamp_naive_ms", keep="last"
    )
    return output.reset_index(drop=True)


def load_sqlite_table(db_path: Path, table: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as connection:
        frame = pd.read_sql_query(
            f"SELECT timestamp, open, high, low, close, volume FROM {table} ORDER BY timestamp",
            connection,
        )
    return frame


def valid_log_returns(close: pd.Series, timestamps: pd.Series, interval_ms: int) -> pd.Series:
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
    shifted["timestamp"] = shifted["timestamp_naive_ms"] + shift_minutes * 60_000
    merged = reference.merge(
        shifted[["timestamp", "open", "high", "low", "close", "volume"]],
        on="timestamp",
        suffixes=("_ref", "_am"),
        how="inner",
    ).sort_values("timestamp")

    overlap = len(merged)
    if overlap < 100:
        return {
            "shift_minutes": shift_minutes,
            "overlap_rows": overlap,
            "close_level_corr": None,
            "return_corr": None,
            "median_abs_close_bps": None,
            "p95_abs_close_bps": None,
            "range_corr": None,
        }

    close_level_corr = merged["close_ref"].corr(merged["close_am"])
    ret_ref = valid_log_returns(merged["close_ref"], merged["timestamp"], interval_ms)
    ret_am = valid_log_returns(merged["close_am"], merged["timestamp"], interval_ms)
    return_corr = ret_ref.corr(ret_am)
    close_bps = (merged["close_am"] / merged["close_ref"] - 1.0).abs() * 10_000
    range_ref = merged["high_ref"] - merged["low_ref"]
    range_am = merged["high_am"] - merged["low_am"]
    range_corr = range_ref.corr(range_am)

    def finite_or_none(value: float) -> float | None:
        return float(value) if value is not None and math.isfinite(float(value)) else None

    return {
        "shift_minutes": shift_minutes,
        "overlap_rows": overlap,
        "close_level_corr": finite_or_none(close_level_corr),
        "return_corr": finite_or_none(return_corr),
        "median_abs_close_bps": finite_or_none(close_bps.median()),
        "p95_abs_close_bps": finite_or_none(close_bps.quantile(0.95)),
        "range_corr": finite_or_none(range_corr),
    }


def score_candidate(item: dict[str, Any]) -> tuple[float, float, int]:
    return (
        item["return_corr"] if item["return_corr"] is not None else -2.0,
        item["close_level_corr"] if item["close_level_corr"] is not None else -2.0,
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
    best = max(results, key=score_candidate)
    ordered = sorted(results, key=score_candidate, reverse=True)
    if len(ordered) > 1:
        best["return_corr_margin_vs_second"] = (
            (best["return_corr"] or -2.0) - (ordered[1]["return_corr"] or -2.0)
        )
    else:
        best["return_corr_margin_vs_second"] = None
    return best, results


def derive_h1_from_m5(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["hour_naive_ms"] = (work["timestamp_naive_ms"] // H1_MS) * H1_MS
    grouped = work.groupby("hour_naive_ms", sort=True)
    result = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index().rename(columns={"hour_naive_ms": "timestamp_naive_ms"})
    return result


def write_candidates(path: Path, rows: list[dict[str, Any]], label: str) -> None:
    frame = pd.DataFrame(rows)
    frame.insert(0, "timeframe", label)
    frame.sort_values(["return_corr", "overlap_rows"], ascending=[False, False]).to_csv(
        path, index=False
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/local/stage177b_extended_history/xauusd_extended_history.sqlite"),
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
    h1_path = args.amarkets_h1.expanduser().resolve() if args.amarkets_h1 else find_existing(h1_candidates)
    m5_path = args.amarkets_m5.expanduser().resolve() if args.amarkets_m5 else find_existing(m5_candidates)

    if h1_path is None and m5_path is None:
        raise FileNotFoundError(
            "No AMarkets H1 or M5 CSV found in the configured Downloads paths"
        )

    reference_h1 = load_sqlite_table(db_path, "dukascopy_h1_canonical")
    reference_m5 = load_sqlite_table(db_path, "dukascopy_m5") if m5_path else None

    am_h1 = normalize_ohlc(h1_path, H1_MS) if h1_path else None
    am_m5 = normalize_ohlc(m5_path, M5_MS) if m5_path else None
    if am_h1 is None and am_m5 is not None:
        am_h1 = derive_h1_from_m5(am_m5)

    h1_shifts = list(range(-14 * 60, 14 * 60 + 1, 60))
    h1_best, h1_grid = candidate_grid(am_h1, reference_h1, h1_shifts, H1_MS)

    m5_best = None
    m5_grid: list[dict[str, Any]] = []
    if am_m5 is not None and reference_m5 is not None:
        center = int(h1_best["shift_minutes"])
        m5_shifts = list(range(center - 60, center + 60 + 1, 5))
        m5_best, m5_grid = candidate_grid(am_m5, reference_m5, m5_shifts, M5_MS)

    h1_pass = (
        h1_best["overlap_rows"] >= 5_000
        and (h1_best["close_level_corr"] or 0.0) >= 0.999
        and (h1_best["return_corr"] or 0.0) >= 0.98
    )
    m5_pass = True
    if m5_best is not None:
        m5_pass = (
            m5_best["overlap_rows"] >= 20_000
            and (m5_best["close_level_corr"] or 0.0) >= 0.999
            and (m5_best["return_corr"] or 0.0) >= 0.90
        )

    decision = (
        "PASS_AMARKETS_CROSSFEED_ALIGNMENT"
        if h1_pass and m5_pass
        else "REVIEW_AMARKETS_CROSSFEED_ALIGNMENT"
    )

    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    write_candidates(report_dir / "stage177b_h1_shift_candidates.csv", h1_grid, "H1")
    if m5_grid:
        write_candidates(report_dir / "stage177b_m5_shift_candidates.csv", m5_grid, "M5")

    summary = {
        "stage": "177B",
        "decision": decision,
        "database": str(db_path),
        "amarkets_h1": str(h1_path) if h1_path else None,
        "amarkets_m5": str(m5_path) if m5_path else None,
        "h1_rows_loaded": int(len(am_h1)),
        "m5_rows_loaded": int(len(am_m5)) if am_m5 is not None else None,
        "h1_best_alignment": h1_best,
        "m5_best_alignment": m5_best,
        "timestamp_shift_semantics": (
            "Add shift_minutes to the naive AMarkets timestamp to align it with UTC."
        ),
        "research_only": True,
        "execution_allowed": False,
    }
    summary_path = report_dir / "stage177b_amarkets_crossfeed_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    decision_md = [
        "# Stage177B AMarkets Cross-Feed Decision",
        "",
        f"Decision: `{decision}`",
        "",
        f"Best H1 timestamp shift: `{h1_best['shift_minutes']}` minutes",
        f"H1 overlap: `{h1_best['overlap_rows']}` rows",
        f"H1 close correlation: `{h1_best['close_level_corr']}`",
        f"H1 return correlation: `{h1_best['return_corr']}`",
        f"H1 median absolute close difference: `{h1_best['median_abs_close_bps']}` bps",
    ]
    if m5_best is not None:
        decision_md.extend(
            [
                "",
                f"Best M5 timestamp shift: `{m5_best['shift_minutes']}` minutes",
                f"M5 overlap: `{m5_best['overlap_rows']}` rows",
                f"M5 close correlation: `{m5_best['close_level_corr']}`",
                f"M5 return correlation: `{m5_best['return_corr']}`",
                f"M5 median absolute close difference: `{m5_best['median_abs_close_bps']}` bps",
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
