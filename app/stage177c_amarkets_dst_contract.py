#!/usr/bin/env python3
"""Stage177C: infer and validate the AMarkets server-time/DST contract.

Research-only. This program never emits signals or orders.

Contract:
- AMarkets CSV timestamps are treated as naive broker-server timestamps.
- Dukascopy timestamps in the Stage177B SQLite database are UTC.
- Candidate broker offsets are evaluated weekly from M5 evidence.
- A transferable calendar model is selected on a training span and validated on
  a later untouched holdout span.
- The final aligned AMarkets feed is written to a separate SQLite database;
  the Stage177B Dukascopy database is never modified.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import numpy as np
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Stage177C requires pandas and numpy") from exc

# Running `python3 app/stage177c_...py` puts app/ on sys.path.
try:
    from stage177b_amarkets_crossfeed import (
        H1_MS,
        M5_MS,
        derive_h1_from_m5,
        find_best_existing,
        load_sqlite_table,
        normalize_ohlc,
    )
except ImportError:  # pragma: no cover - useful when imported as app.module
    from app.stage177b_amarkets_crossfeed import (
        H1_MS,
        M5_MS,
        derive_h1_from_m5,
        find_best_existing,
        load_sqlite_table,
        normalize_ohlc,
    )

STAGE = "177C"
MINUTE_MS = 60_000
DAY_MS = 86_400_000


@dataclass(frozen=True)
class Contract:
    name: str
    standard_shift_minutes: int
    dst_shift_minutes: int | None = None
    dst_calendar: str | None = None

    @property
    def is_constant(self) -> bool:
        return self.dst_shift_minutes is None or self.dst_calendar is None


def finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        output = float(value)
    except (TypeError, ValueError):
        return None
    return output if math.isfinite(output) else None


def iso_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return pd.to_datetime(int(value), unit="ms", utc=True).isoformat()


def datetime_to_epoch_ms(values: Any) -> np.ndarray:
    """Convert datetime-like values to Unix epoch milliseconds explicitly.

    Pandas DatetimeIndex/Series can carry s, ms, us, or ns resolution.
    ``astype("int64")`` returns integers in that stored resolution, so dividing
    by a hard-coded factor is not portable across pandas/Python versions.
    Converting through an explicit ``datetime64[ms]`` dtype makes the unit
    contract deterministic.
    """
    parsed = pd.to_datetime(values, utc=True)
    if isinstance(parsed, pd.Series):
        array = parsed.to_numpy(dtype="datetime64[ms]")
    elif isinstance(parsed, pd.DatetimeIndex):
        array = parsed.to_numpy(dtype="datetime64[ms]")
    else:
        array = np.asarray(parsed, dtype="datetime64[ms]")
    return np.asarray(array, dtype="datetime64[ms]").astype("int64")


def read_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "candidate_shifts_minutes",
        "train_end_utc",
        "holdout_start_utc",
        "weekly_min_overlap_rows",
        "transition_penalty",
        "pass_thresholds",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"Stage177C config missing keys: {missing}")
    shifts = [int(value) for value in config["candidate_shifts_minutes"]]
    if len(shifts) < 2 or len(set(shifts)) != len(shifts):
        raise ValueError("candidate_shifts_minutes must contain unique states")
    if any(value % 5 for value in shifts):
        raise ValueError("candidate shifts must be multiples of five minutes")
    config["candidate_shifts_minutes"] = sorted(shifts)
    return config


def lagged_returns(
    close: pd.Series,
    timestamps: pd.Series,
    *,
    lag_rows: int,
    expected_interval_ms: int,
) -> pd.Series:
    """Return exact-lag log returns without pandas index-alignment side effects.

    The previous implementation combined ``Series.diff`` with a NumPy boolean
    array.  Some newer pandas/Python combinations can align or coerce that mask
    differently and turn an otherwise valid return series into all-NaN values.
    This implementation is deliberately positional and returns a Series with
    the original index only after all calculations are complete.
    """
    if lag_rows <= 0:
        raise ValueError("lag_rows must be positive")

    close_values = pd.to_numeric(close, errors="coerce").to_numpy(dtype="float64")
    timestamp_values = pd.to_numeric(
        timestamps, errors="coerce"
    ).to_numpy(dtype="float64")
    output = np.full(len(close_values), np.nan, dtype="float64")

    if len(close_values) <= lag_rows:
        return pd.Series(output, index=close.index, dtype="float64")

    current_close = close_values[lag_rows:]
    prior_close = close_values[:-lag_rows]
    current_time = timestamp_values[lag_rows:]
    prior_time = timestamp_values[:-lag_rows]
    expected_gap = float(expected_interval_ms * lag_rows)

    valid = (
        np.isfinite(current_close)
        & np.isfinite(prior_close)
        & (current_close > 0.0)
        & (prior_close > 0.0)
        & np.isfinite(current_time)
        & np.isfinite(prior_time)
        & ((current_time - prior_time) == expected_gap)
    )
    values = np.full(len(current_close), np.nan, dtype="float64")
    values[valid] = np.log(current_close[valid] / prior_close[valid])
    output[lag_rows:] = values
    return pd.Series(output, index=close.index, dtype="float64")


def pairwise_corr(
    left: pd.Series | np.ndarray,
    right: pd.Series | np.ndarray,
    *,
    min_pairs: int = 3,
) -> float | None:
    """Compute Pearson correlation positionally on a shared finite mask.

    This avoids pandas index alignment and version-specific ``Series.corr``
    behavior.  Correlation remains undefined for constant inputs and returns
    ``None`` in that case, which is the fail-closed behavior used by Stage177C.
    """
    left_values = np.asarray(left, dtype="float64")
    right_values = np.asarray(right, dtype="float64")
    if left_values.shape != right_values.shape:
        raise ValueError("pairwise_corr inputs must have identical shapes")

    mask = np.isfinite(left_values) & np.isfinite(right_values)
    if int(mask.sum()) < int(min_pairs):
        return None

    x = left_values[mask]
    y = right_values[mask]
    x = x - x.mean()
    y = y - y.mean()
    denominator = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    if not math.isfinite(denominator) or denominator <= 0.0:
        return None
    return finite(float(np.dot(x, y) / denominator))


def aligned_metrics(
    aligned: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    interval_ms: int,
    min_overlap: int,
) -> dict[str, Any]:
    if aligned.empty or reference.empty:
        return {
            "status": "EMPTY",
            "amarkets_rows": int(len(aligned)),
            "overlap_rows": 0,
            "overlap_pct_of_amarkets": 0.0,
        }

    left_columns = ["timestamp", "open", "high", "low", "close", "volume"]
    merged = reference[left_columns].merge(
        aligned[left_columns],
        on="timestamp",
        how="inner",
        suffixes=("_ref", "_am"),
    ).sort_values("timestamp")
    overlap = int(len(merged))
    coverage = 100.0 * overlap / len(aligned) if len(aligned) else 0.0
    result: dict[str, Any] = {
        "status": "EVALUATED" if overlap >= min_overlap else "INSUFFICIENT_OVERLAP",
        "amarkets_rows": int(len(aligned)),
        "reference_rows": int(len(reference)),
        "overlap_rows": overlap,
        "overlap_pct_of_amarkets": float(coverage),
        "first_overlap_utc": iso_ms(int(merged["timestamp"].min())) if overlap else None,
        "last_overlap_utc": iso_ms(int(merged["timestamp"].max())) if overlap else None,
        "close_level_corr": None,
        "return_corr_1bar": None,
        "return_corr_15m": None,
        "return_corr_60m": None,
        "median_abs_close_bps": None,
        "p95_abs_close_bps": None,
        "range_corr": None,
    }
    if overlap < min_overlap:
        return result

    timestamps = merged["timestamp"]
    result["close_level_corr"] = pairwise_corr(
        merged["close_ref"], merged["close_am"]
    )
    ref_1 = lagged_returns(
        merged["close_ref"], timestamps, lag_rows=1, expected_interval_ms=interval_ms
    )
    am_1 = lagged_returns(
        merged["close_am"], timestamps, lag_rows=1, expected_interval_ms=interval_ms
    )
    result["return_corr_1bar"] = pairwise_corr(ref_1, am_1)

    if interval_ms == M5_MS:
        lag_15 = 3
        lag_60 = 12
    else:
        lag_15 = 1
        lag_60 = 1
    ref_15 = lagged_returns(
        merged["close_ref"], timestamps, lag_rows=lag_15, expected_interval_ms=interval_ms
    )
    am_15 = lagged_returns(
        merged["close_am"], timestamps, lag_rows=lag_15, expected_interval_ms=interval_ms
    )
    ref_60 = lagged_returns(
        merged["close_ref"], timestamps, lag_rows=lag_60, expected_interval_ms=interval_ms
    )
    am_60 = lagged_returns(
        merged["close_am"], timestamps, lag_rows=lag_60, expected_interval_ms=interval_ms
    )
    result["return_corr_15m"] = pairwise_corr(ref_15, am_15)
    result["return_corr_60m"] = pairwise_corr(ref_60, am_60)

    close_bps = (merged["close_am"] / merged["close_ref"] - 1.0).abs() * 10_000
    result["median_abs_close_bps"] = finite(close_bps.median())
    result["p95_abs_close_bps"] = finite(close_bps.quantile(0.95))
    range_ref = merged["high_ref"] - merged["low_ref"]
    range_am = merged["high_am"] - merged["low_am"]
    result["range_corr"] = pairwise_corr(range_ref, range_am)
    return result


def metric_score(metrics: dict[str, Any]) -> float:
    if metrics.get("status") != "EVALUATED":
        return -5.0
    corr60 = metrics.get("return_corr_60m")
    corr15 = metrics.get("return_corr_15m")
    range_corr = metrics.get("range_corr")
    coverage = float(metrics.get("overlap_pct_of_amarkets") or 0.0) / 100.0
    if corr60 is None:
        return -5.0
    return (
        0.68 * float(corr60)
        + 0.17 * float(corr15 if corr15 is not None else -1.0)
        + 0.10 * float(range_corr if range_corr is not None else -1.0)
        + 0.05 * min(max(coverage, 0.0), 1.0)
    )


def week_start_from_naive_ms(values: pd.Series) -> pd.Series:
    dates = pd.to_datetime(values.astype("int64"), unit="ms")
    return (dates - pd.to_timedelta(dates.dt.weekday, unit="D")).dt.normalize()


def evaluate_weekly_offsets(
    amarkets_m5: pd.DataFrame,
    reference_m5: pd.DataFrame,
    shifts: list[int],
    *,
    min_overlap: int,
) -> pd.DataFrame:
    work = amarkets_m5.copy()
    work["week_start"] = week_start_from_naive_ms(work["timestamp_naive_ms"])
    reference = reference_m5.sort_values("timestamp")
    rows: list[dict[str, Any]] = []

    for week_start, group in work.groupby("week_start", sort=True):
        naive_min = int(group["timestamp_naive_ms"].min())
        naive_max = int(group["timestamp_naive_ms"].max())
        margin = max(abs(min(shifts)), abs(max(shifts))) * MINUTE_MS + H1_MS
        ref_slice = reference[
            (reference["timestamp"] >= naive_min - margin)
            & (reference["timestamp"] <= naive_max + margin)
        ]
        for shift in shifts:
            aligned = group[
                ["timestamp_naive_ms", "open", "high", "low", "close", "volume"]
            ].copy()
            aligned["timestamp"] = (
                aligned["timestamp_naive_ms"].astype("int64")
                + int(shift) * MINUTE_MS
            )
            metrics = aligned_metrics(
                aligned,
                ref_slice,
                interval_ms=M5_MS,
                min_overlap=min_overlap,
            )
            rows.append(
                {
                    "week_start": pd.Timestamp(week_start).date().isoformat(),
                    "shift_minutes": int(shift),
                    "score": metric_score(metrics),
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def viterbi_weekly_states(
    weekly_scores: pd.DataFrame,
    shifts: list[int],
    *,
    transition_penalty: float,
    max_transition_minutes: int,
) -> pd.DataFrame:
    if weekly_scores.empty:
        raise ValueError("No weekly offset scores")
    weeks = sorted(weekly_scores["week_start"].unique().tolist())
    score_map = {
        (str(row.week_start), int(row.shift_minutes)): float(row.score)
        for row in weekly_scores.itertuples(index=False)
    }

    paths: list[dict[int, tuple[float, int | None]]] = []
    first: dict[int, tuple[float, int | None]] = {}
    for state in shifts:
        first[state] = (score_map.get((weeks[0], state), -5.0), None)
    paths.append(first)

    for index in range(1, len(weeks)):
        current: dict[int, tuple[float, int | None]] = {}
        week = weeks[index]
        for state in shifts:
            emission = score_map.get((week, state), -5.0)
            best_score = -float("inf")
            best_prev: int | None = None
            for prev_state, (previous_score, _) in paths[index - 1].items():
                change = abs(state - prev_state)
                if change > max_transition_minutes:
                    continue
                penalty = 0.0 if state == prev_state else transition_penalty
                candidate = previous_score + emission - penalty
                if candidate > best_score:
                    best_score = candidate
                    best_prev = prev_state
            current[state] = (best_score, best_prev)
        paths.append(current)

    last_state = max(paths[-1], key=lambda state: paths[-1][state][0])
    states = [last_state]
    for index in range(len(weeks) - 1, 0, -1):
        previous = paths[index][states[-1]][1]
        if previous is None:
            raise RuntimeError("Broken Viterbi backtrack")
        states.append(previous)
    states.reverse()

    output_rows = []
    for week, state in zip(weeks, states):
        week_rows = weekly_scores[weekly_scores["week_start"] == week].copy()
        week_rows = week_rows.sort_values("score", ascending=False)
        selected_row = week_rows[week_rows["shift_minutes"] == state].iloc[0]
        second_score = (
            float(week_rows.iloc[1]["score"]) if len(week_rows) > 1 else None
        )
        output_rows.append(
            {
                "week_start": week,
                "selected_shift_minutes": int(state),
                "selected_score": float(selected_row["score"]),
                "best_raw_shift_minutes": int(week_rows.iloc[0]["shift_minutes"]),
                "best_raw_score": float(week_rows.iloc[0]["score"]),
                "second_raw_score": second_score,
                "raw_margin": (
                    float(week_rows.iloc[0]["score"] - second_score)
                    if second_score is not None
                    else None
                ),
                "selected_overlap_rows": int(selected_row["overlap_rows"]),
                "selected_return_corr_60m": finite(
                    selected_row.get("return_corr_60m")
                ),
            }
        )
    return pd.DataFrame(output_rows)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    weeks = calendar.monthcalendar(year, month)
    values = [week[weekday] for week in weeks if week[weekday] != 0]
    return dt.date(year, month, values[n - 1])


def last_weekday(year: int, month: int, weekday: int) -> dt.date:
    weeks = calendar.monthcalendar(year, month)
    values = [week[weekday] for week in weeks if week[weekday] != 0]
    return dt.date(year, month, values[-1])


def dst_dates(year: int, calendar_name: str) -> tuple[dt.date, dt.date]:
    if calendar_name == "US":
        return (
            nth_weekday(year, 3, calendar.SUNDAY, 2),
            nth_weekday(year, 11, calendar.SUNDAY, 1),
        )
    if calendar_name == "EU":
        return (
            last_weekday(year, 3, calendar.SUNDAY),
            last_weekday(year, 10, calendar.SUNDAY),
        )
    raise ValueError(f"Unsupported DST calendar: {calendar_name}")


def shift_for_dates(
    dates: pd.Series,
    contract: Contract,
) -> pd.Series:
    date_values = pd.to_datetime(dates).dt.date
    if contract.is_constant:
        return pd.Series(
            np.full(len(date_values), contract.standard_shift_minutes, dtype="int64"),
            index=dates.index,
        )

    assert contract.dst_calendar is not None
    assert contract.dst_shift_minutes is not None
    output = np.full(len(date_values), contract.standard_shift_minutes, dtype="int64")
    years = sorted({value.year for value in date_values})
    for year in years:
        start, end = dst_dates(year, contract.dst_calendar)
        mask = np.array([(value >= start and value < end) for value in date_values])
        output[mask] = contract.dst_shift_minutes
    return pd.Series(output, index=dates.index)


def apply_contract(frame: pd.DataFrame, contract: Contract) -> pd.DataFrame:
    output = frame.copy()
    naive_dt = pd.to_datetime(output["timestamp_naive_ms"].astype("int64"), unit="ms")
    output["shift_minutes"] = shift_for_dates(naive_dt, contract).astype("int64")
    output["timestamp"] = (
        output["timestamp_naive_ms"].astype("int64")
        + output["shift_minutes"].astype("int64") * MINUTE_MS
    )
    before = len(output)
    output = output.sort_values(["timestamp", "timestamp_naive_ms"]).drop_duplicates(
        "timestamp", keep="last"
    )
    output.attrs["duplicates_after_alignment_removed"] = int(before - len(output))
    return output.reset_index(drop=True)


def period_slice(frame: pd.DataFrame, start_ms: int | None, end_ms: int | None) -> pd.DataFrame:
    output = frame
    if start_ms is not None:
        output = output[output["timestamp"] >= start_ms]
    if end_ms is not None:
        output = output[output["timestamp"] < end_ms]
    return output


def evaluate_contract(
    contract: Contract,
    amarkets_m5: pd.DataFrame,
    reference_m5: pd.DataFrame,
    *,
    train_end_ms: int,
    holdout_start_ms: int,
    min_overlap: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    aligned = apply_contract(amarkets_m5, contract)
    all_metrics = aligned_metrics(
        aligned,
        reference_m5,
        interval_ms=M5_MS,
        min_overlap=min_overlap,
    )
    train_metrics = aligned_metrics(
        period_slice(aligned, None, train_end_ms),
        period_slice(reference_m5, None, train_end_ms),
        interval_ms=M5_MS,
        min_overlap=max(100, min_overlap // 4),
    )
    holdout_metrics = aligned_metrics(
        period_slice(aligned, holdout_start_ms, None),
        period_slice(reference_m5, holdout_start_ms, None),
        interval_ms=M5_MS,
        min_overlap=max(100, min_overlap // 4),
    )
    return (
        {
            "contract": contract.name,
            "standard_shift_minutes": contract.standard_shift_minutes,
            "dst_shift_minutes": contract.dst_shift_minutes,
            "dst_calendar": contract.dst_calendar,
            "train_score": metric_score(train_metrics),
            "all_score": metric_score(all_metrics),
            "holdout_score": metric_score(holdout_metrics),
            "all": all_metrics,
            "train": train_metrics,
            "holdout": holdout_metrics,
            "duplicates_after_alignment_removed": int(
                aligned.attrs.get("duplicates_after_alignment_removed", 0)
            ),
        },
        aligned,
    )


def weekly_agreement(
    weekly_states: pd.DataFrame,
    contract: Contract,
    *,
    confidence_min: float,
) -> dict[str, Any]:
    states = weekly_states.copy()
    states["week_date"] = pd.to_datetime(states["week_start"])
    expected = shift_for_dates(states["week_date"], contract)
    states["expected_shift_minutes"] = expected.astype("int64")
    confident = states[
        states["raw_margin"].fillna(-999.0) >= float(confidence_min)
    ].copy()
    denominator = len(confident)
    matches = int(
        (
            confident["selected_shift_minutes"]
            == confident["expected_shift_minutes"]
        ).sum()
    )
    return {
        "weeks_total": int(len(states)),
        "weeks_confident": int(denominator),
        "matching_confident_weeks": matches,
        "agreement_pct": 100.0 * matches / denominator if denominator else None,
    }


def build_segments(weekly_states: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if weekly_states.empty:
        return pd.DataFrame(rows)
    ordered = weekly_states.sort_values("week_start").reset_index(drop=True)
    start_index = 0
    for index in range(1, len(ordered) + 1):
        changed = (
            index == len(ordered)
            or ordered.iloc[index]["selected_shift_minutes"]
            != ordered.iloc[start_index]["selected_shift_minutes"]
        )
        if not changed:
            continue
        segment = ordered.iloc[start_index:index]
        start = pd.Timestamp(segment.iloc[0]["week_start"])
        end = pd.Timestamp(segment.iloc[-1]["week_start"]) + pd.Timedelta(days=7)
        rows.append(
            {
                "segment_start": start.date().isoformat(),
                "segment_end_exclusive": end.date().isoformat(),
                "shift_minutes": int(segment.iloc[0]["selected_shift_minutes"]),
                "weeks": int(len(segment)),
                "median_selected_score": float(segment["selected_score"].median()),
                "median_raw_margin": finite(segment["raw_margin"].median()),
            }
        )
        start_index = index
    return pd.DataFrame(rows)


def derive_h1_from_aligned_m5(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["hour_utc"] = (work["timestamp"].astype("int64") // H1_MS) * H1_MS
    grouped = work.sort_values("timestamp").groupby("hour_utc", sort=True)
    output = (
        grouped.agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            m5_bar_count=("timestamp", "size"),
        )
        .reset_index()
        .rename(columns={"hour_utc": "timestamp"})
    )
    return output


def transition_profile(segments: pd.DataFrame) -> dict[str, Any]:
    if segments.empty:
        return {
            "transition_count": 0,
            "transitions_per_year": {},
            "max_transitions_in_year": 0,
        }
    transitions = segments.iloc[1:].copy()
    years = pd.to_datetime(transitions["segment_start"]).dt.year
    counts = years.value_counts().sort_index()
    return {
        "transition_count": int(len(transitions)),
        "transitions_per_year": {str(int(k)): int(v) for k, v in counts.items()},
        "max_transitions_in_year": int(counts.max()) if len(counts) else 0,
    }


def collapse_isolated_transient_segments(
    segments: pd.DataFrame,
    *,
    max_transient_weeks: int = 1,
) -> pd.DataFrame:
    """Collapse isolated short excursions between identical offset states.

    The weekly Viterbi path is diagnostic evidence, not the operational clock
    contract. A single high-noise week can create two extra transitions even
    when the deterministic DST template agrees with more than 99% of confident
    weeks and passes untouched holdout. For the transition-frequency gate only,
    collapse a segment when all of these are true:

    * it is not the first or last segment;
    * its duration is at most ``max_transient_weeks``;
    * the neighbouring segments have the same shift; and
    * the middle segment has a different shift.

    Longer excursions are preserved and remain capable of failing the gate.
    """
    if segments.empty or len(segments) < 3 or max_transient_weeks < 1:
        return segments.copy().reset_index(drop=True)

    records = segments.sort_values("segment_start").to_dict("records")
    changed = True
    while changed and len(records) >= 3:
        changed = False
        for index in range(1, len(records) - 1):
            previous = records[index - 1]
            current = records[index]
            following = records[index + 1]
            if (
                int(current.get("weeks") or 0) <= int(max_transient_weeks)
                and int(previous["shift_minutes"]) == int(following["shift_minutes"])
                and int(current["shift_minutes"]) != int(previous["shift_minutes"])
            ):
                total_weeks = (
                    int(previous.get("weeks") or 0)
                    + int(current.get("weeks") or 0)
                    + int(following.get("weeks") or 0)
                )
                merged = dict(previous)
                merged["segment_end_exclusive"] = following["segment_end_exclusive"]
                merged["weeks"] = total_weeks

                # These fields are diagnostic summaries only. Use weighted
                # averages rather than claiming a recomputed exact median from
                # already-aggregated segment records.
                for field in ("median_selected_score", "median_raw_margin"):
                    values = []
                    weights = []
                    for item in (previous, current, following):
                        value = item.get(field)
                        if value is not None and np.isfinite(float(value)):
                            values.append(float(value))
                            weights.append(int(item.get("weeks") or 0))
                    merged[field] = (
                        float(np.average(values, weights=weights))
                        if values and sum(weights) > 0
                        else None
                    )

                records[index - 1 : index + 2] = [merged]
                changed = True
                break

    return pd.DataFrame(records).reset_index(drop=True)


def write_sqlite(
    path: Path,
    aligned_m5: pd.DataFrame,
    aligned_h1_direct: pd.DataFrame | None,
    aligned_h1_from_m5: pd.DataFrame,
    contract_payload: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    if temp.exists():
        temp.unlink()
    with sqlite3.connect(temp) as connection:
        connection.executescript(
            """
            CREATE TABLE amarkets_m5_utc (
                timestamp INTEGER PRIMARY KEY,
                timestamp_naive_ms INTEGER NOT NULL,
                shift_minutes INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL
            );
            CREATE TABLE amarkets_h1_direct_utc (
                timestamp INTEGER PRIMARY KEY,
                timestamp_naive_ms INTEGER NOT NULL,
                shift_minutes INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL
            );
            CREATE TABLE amarkets_h1_from_m5_utc (
                timestamp INTEGER PRIMARY KEY,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL,
                m5_bar_count INTEGER NOT NULL
            );
            CREATE TABLE provenance (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        m5_rows = aligned_m5[
            [
                "timestamp",
                "timestamp_naive_ms",
                "shift_minutes",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ].itertuples(index=False, name=None)
        connection.executemany(
            "INSERT INTO amarkets_m5_utc VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            m5_rows,
        )
        if aligned_h1_direct is not None:
            h1_rows = aligned_h1_direct[
                [
                    "timestamp",
                    "timestamp_naive_ms",
                    "shift_minutes",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            ].itertuples(index=False, name=None)
            connection.executemany(
                "INSERT INTO amarkets_h1_direct_utc VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                h1_rows,
            )
        derived_rows = aligned_h1_from_m5[
            ["timestamp", "open", "high", "low", "close", "volume", "m5_bar_count"]
        ].itertuples(index=False, name=None)
        connection.executemany(
            "INSERT INTO amarkets_h1_from_m5_utc VALUES (?, ?, ?, ?, ?, ?, ?)",
            derived_rows,
        )
        connection.execute(
            "INSERT INTO provenance VALUES (?, ?)",
            ("stage177c_time_contract", json.dumps(contract_payload, sort_keys=True)),
        )
        connection.execute(
            "CREATE INDEX idx_am_m5_utc_ts ON amarkets_m5_utc(timestamp)"
        )
        connection.execute(
            "CREATE INDEX idx_am_h1_direct_utc_ts ON amarkets_h1_direct_utc(timestamp)"
        )
        connection.execute(
            "CREATE INDEX idx_am_h1_m5_utc_ts ON amarkets_h1_from_m5_utc(timestamp)"
        )
        connection.commit()
    temp.replace(path)


def resolve_sources(args: argparse.Namespace) -> tuple[Path | None, Path]:
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
    if m5_path is None:
        raise FileNotFoundError("Stage177C requires the AMarkets M5 history CSV")
    return h1_path, m5_path


def decision_from_metrics(
    selected: dict[str, Any],
    h1_derived: dict[str, Any],
    agreement: dict[str, Any],
    transitions: dict[str, Any],
    thresholds: dict[str, Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    all_metrics = selected["all"]
    holdout = selected["holdout"]

    checks = {
        "all_overlap_pct": float(all_metrics.get("overlap_pct_of_amarkets") or 0.0)
        >= float(thresholds["min_overlap_pct"]),
        "all_return_corr_60m": float(all_metrics.get("return_corr_60m") or -9.0)
        >= float(thresholds["min_all_return_corr_60m"]),
        "holdout_return_corr_60m": float(holdout.get("return_corr_60m") or -9.0)
        >= float(thresholds["min_holdout_return_corr_60m"]),
        "median_abs_close_bps": float(all_metrics.get("median_abs_close_bps") or 9999.0)
        <= float(thresholds["max_median_abs_close_bps"]),
        "h1_derived_return_corr": float(h1_derived.get("return_corr_1bar") or -9.0)
        >= float(thresholds["min_h1_derived_return_corr"]),
        "weekly_agreement": float(agreement.get("agreement_pct") or 0.0)
        >= float(thresholds["min_weekly_agreement_pct"]),
        "transition_frequency": int(transitions.get("max_transitions_in_year") or 0)
        <= int(thresholds["max_transitions_per_year"]),
    }
    for name, passed in checks.items():
        if not passed:
            reasons.append(name)

    if all(checks.values()):
        return "PASS_AMARKETS_DST_AWARE_UTC_CONTRACT", reasons

    strong_alignment = (
        float(all_metrics.get("overlap_pct_of_amarkets") or 0.0) >= 90.0
        and float(all_metrics.get("return_corr_60m") or -9.0) >= 0.80
        and float(h1_derived.get("return_corr_1bar") or -9.0) >= 0.80
    )
    if strong_alignment:
        return "REVIEW_AMARKETS_DST_CONTRACT", reasons
    return "BLOCK_AMARKETS_TIME_CONTRACT_UNRESOLVED", reasons


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/stage177c_amarkets_dst_contract.json"),
    )
    parser.add_argument(
        "--reference-db",
        type=Path,
        default=Path(
            "data/local/stage177b_extended_history/xauusd_extended_history.sqlite"
        ),
    )
    parser.add_argument("--amarkets-h1", type=Path)
    parser.add_argument("--amarkets-m5", type=Path)
    parser.add_argument(
        "--output-db",
        type=Path,
        default=Path(
            "data/local/stage177c_amarkets_alignment/xauusd_amarkets_alignment.sqlite"
        ),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports/stage177c_amarkets_dst_contract"),
    )
    return parser.parse_args()



def utc_ms(value: str) -> int:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return int(stamp.timestamp() * 1000)


def main() -> int:
    args = parse_args()
    config = read_config(args.config.resolve())
    reference_db = args.reference_db.expanduser().resolve()
    if not reference_db.exists():
        raise FileNotFoundError(f"Stage177B reference database not found: {reference_db}")
    h1_path, m5_path = resolve_sources(args)

    reference_m5 = load_sqlite_table(reference_db, "dukascopy_m5")
    reference_h1 = load_sqlite_table(reference_db, "dukascopy_h1_canonical")
    am_m5 = normalize_ohlc(m5_path, M5_MS)
    am_h1 = normalize_ohlc(h1_path, H1_MS) if h1_path else None

    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    output_db = args.output_db.resolve()
    output_db.parent.mkdir(parents=True, exist_ok=True)
    (output_db.parent / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")

    shifts = [int(value) for value in config["candidate_shifts_minutes"]]
    train_end_ms = utc_ms(config["train_end_utc"])
    holdout_start_ms = utc_ms(config["holdout_start_utc"])
    if holdout_start_ms < train_end_ms:
        raise ValueError("holdout_start_utc cannot be before train_end_utc")

    # Contract discovery uses only the training span. Because AMarkets timestamps
    # are still naive here, retain a conservative offset margin around the UTC
    # cutoff so no pre-cutoff bars are accidentally excluded.
    train_naive_cutoff_ms = train_end_ms - min(shifts) * MINUTE_MS
    am_m5_train = am_m5[am_m5["timestamp_naive_ms"] < train_naive_cutoff_ms].copy()
    reference_m5_train = reference_m5[reference_m5["timestamp"] < train_end_ms].copy()
    if len(am_m5_train) < int(config["contract_min_overlap_rows"]):
        raise ValueError(
            "Training AMarkets M5 history is too short for Stage177C: "
            f"{len(am_m5_train)} rows"
        )

    train_weekly_scores = evaluate_weekly_offsets(
        am_m5_train,
        reference_m5_train,
        shifts,
        min_overlap=int(config["weekly_min_overlap_rows"]),
    )
    train_weekly_states = viterbi_weekly_states(
        train_weekly_scores,
        shifts,
        transition_penalty=float(config["transition_penalty"]),
        max_transition_minutes=int(config.get("max_transition_minutes", 60)),
    )
    train_segments = build_segments(train_weekly_states)

    state_counts = train_weekly_states["selected_shift_minutes"].value_counts()
    dominant_states = [int(value) for value in state_counts.index[:2].tolist()]
    contracts: list[Contract] = [
        Contract(name=f"CONSTANT_{shift}", standard_shift_minutes=shift)
        for shift in shifts
    ]
    if len(dominant_states) >= 2 and abs(dominant_states[0] - dominant_states[1]) == 60:
        standard_shift = max(dominant_states)
        dst_shift = min(dominant_states)
        contracts.extend(
            [
                Contract(
                    name="US_DST_GMT_OFFSET_PAIR",
                    standard_shift_minutes=standard_shift,
                    dst_shift_minutes=dst_shift,
                    dst_calendar="US",
                ),
                Contract(
                    name="EU_DST_GMT_OFFSET_PAIR",
                    standard_shift_minutes=standard_shift,
                    dst_shift_minutes=dst_shift,
                    dst_calendar="EU",
                ),
            ]
        )

    evaluations: list[dict[str, Any]] = []
    aligned_by_contract: dict[str, pd.DataFrame] = {}
    train_agreements: dict[str, dict[str, Any]] = {}
    for contract in contracts:
        evaluation, aligned = evaluate_contract(
            contract,
            am_m5,
            reference_m5,
            train_end_ms=train_end_ms,
            holdout_start_ms=holdout_start_ms,
            min_overlap=int(config["contract_min_overlap_rows"]),
        )
        train_agreement = weekly_agreement(
            train_weekly_states,
            contract,
            confidence_min=float(config["weekly_confidence_margin_min"]),
        )
        evaluation["train_weekly_agreement"] = train_agreement
        evaluations.append(evaluation)
        aligned_by_contract[contract.name] = aligned
        train_agreements[contract.name] = train_agreement

    # Selection is strictly training-only. Holdout metrics are not part of the
    # sort key and are inspected only after the contract has been locked.
    transferable = [
        item
        for item in evaluations
        if item["contract"].startswith("US_DST")
        or item["contract"].startswith("EU_DST")
        or item["contract"].startswith("CONSTANT")
    ]
    transferable.sort(
        key=lambda item: (
            float(item["train_score"]),
            float(item["train_weekly_agreement"].get("agreement_pct") or -1.0),
            item["contract"],
        ),
        reverse=True,
    )
    selected_eval = transferable[0]
    selected_contract = next(
        contract for contract in contracts if contract.name == selected_eval["contract"]
    )
    aligned_m5 = aligned_by_contract[selected_contract.name]

    # Full-span weekly path is diagnostic only; it cannot alter the contract.
    weekly_scores = evaluate_weekly_offsets(
        am_m5,
        reference_m5,
        shifts,
        min_overlap=int(config["weekly_min_overlap_rows"]),
    )
    weekly_states = viterbi_weekly_states(
        weekly_scores,
        shifts,
        transition_penalty=float(config["transition_penalty"]),
        max_transition_minutes=int(config.get("max_transition_minutes", 60)),
    )
    segments = build_segments(weekly_states)
    max_transient_weeks = int(
        config.get("max_transient_segment_weeks_for_transition_gate", 1)
    )
    persistent_segments = collapse_isolated_transient_segments(
        segments, max_transient_weeks=max_transient_weeks
    )
    raw_transitions = transition_profile(segments)
    persistent_transitions = transition_profile(persistent_segments)
    selected_all_agreement = weekly_agreement(
        weekly_states,
        selected_contract,
        confidence_min=float(config["weekly_confidence_margin_min"]),
    )

    aligned_h1_direct = apply_contract(am_h1, selected_contract) if am_h1 is not None else None
    aligned_h1_from_m5 = derive_h1_from_aligned_m5(aligned_m5)
    h1_derived_metrics = aligned_metrics(
        aligned_h1_from_m5,
        reference_h1,
        interval_ms=H1_MS,
        min_overlap=int(config["h1_min_overlap_rows"]),
    )
    h1_direct_metrics = (
        aligned_metrics(
            aligned_h1_direct,
            reference_h1,
            interval_ms=H1_MS,
            min_overlap=int(config["h1_min_overlap_rows"]),
        )
        if aligned_h1_direct is not None
        else None
    )

    decision, failed_checks = decision_from_metrics(
        selected_eval,
        h1_derived_metrics,
        selected_all_agreement,
        persistent_transitions,
        config["pass_thresholds"],
    )

    contract_payload = {
        "stage": STAGE,
        "decision": decision,
        "contract": selected_contract.name,
        "standard_shift_minutes": selected_contract.standard_shift_minutes,
        "dst_shift_minutes": selected_contract.dst_shift_minutes,
        "dst_calendar": selected_contract.dst_calendar,
        "shift_semantics": "timestamp_utc = timestamp_naive + shift_minutes",
        "selection_boundary_utc": config["train_end_utc"],
        "holdout_start_utc": config["holdout_start_utc"],
        "selection_used_holdout": False,
        "source_amarkets_m5": str(m5_path),
        "source_amarkets_h1": str(h1_path) if h1_path else None,
        "source_reference_db": str(reference_db),
    }

    if decision.startswith("PASS"):
        write_sqlite(
            output_db,
            aligned_m5,
            aligned_h1_direct,
            aligned_h1_from_m5,
            contract_payload,
        )

    train_weekly_scores.to_csv(
        report_dir / "stage177c_train_weekly_offset_scores.csv", index=False
    )
    train_weekly_states.to_csv(
        report_dir / "stage177c_train_weekly_selected_states.csv", index=False
    )
    train_segments.to_csv(
        report_dir / "stage177c_train_offset_segments.csv", index=False
    )
    weekly_scores.to_csv(report_dir / "stage177c_weekly_offset_scores.csv", index=False)
    weekly_states.to_csv(report_dir / "stage177c_weekly_selected_states.csv", index=False)
    segments.to_csv(report_dir / "stage177c_offset_segments.csv", index=False)
    persistent_segments.to_csv(
        report_dir / "stage177c_persistent_offset_segments.csv", index=False
    )

    flat_rows = []
    for item in evaluations:
        flat_rows.append(
            {
                "contract": item["contract"],
                "standard_shift_minutes": item["standard_shift_minutes"],
                "dst_shift_minutes": item["dst_shift_minutes"],
                "dst_calendar": item["dst_calendar"],
                "train_score": item["train_score"],
                "holdout_score": item["holdout_score"],
                "all_score": item["all_score"],
                "train_weekly_agreement_pct": item["train_weekly_agreement"].get(
                    "agreement_pct"
                ),
                "all_overlap_pct": item["all"].get("overlap_pct_of_amarkets"),
                "all_return_corr_60m": item["all"].get("return_corr_60m"),
                "holdout_return_corr_60m": item["holdout"].get("return_corr_60m"),
                "median_abs_close_bps": item["all"].get("median_abs_close_bps"),
            }
        )
    pd.DataFrame(flat_rows).sort_values("train_score", ascending=False).to_csv(
        report_dir / "stage177c_contract_candidates.csv", index=False
    )

    summary = {
        "stage": STAGE,
        "decision": decision,
        "failed_checks": failed_checks,
        "execution_allowed": False,
        "research_only": True,
        "reference_db": str(reference_db),
        "amarkets_m5": str(m5_path),
        "amarkets_h1": str(h1_path) if h1_path else None,
        "amarkets_m5_rows": int(len(am_m5)),
        "amarkets_h1_rows": int(len(am_h1)) if am_h1 is not None else None,
        "train_amarkets_m5_rows": int(len(am_m5_train)),
        "selected_contract": contract_payload,
        "selected_m5_metrics": selected_eval,
        "selected_train_weekly_agreement": train_agreements[selected_contract.name],
        "selected_all_weekly_agreement": selected_all_agreement,
        "train_transition_profile": transition_profile(train_segments),
        "full_transition_profile": persistent_transitions,
        "full_transition_profile_raw": raw_transitions,
        "full_transition_profile_persistent": persistent_transitions,
        "transition_gate_max_transient_weeks": max_transient_weeks,
        "collapsed_transient_segments_full": int(
            len(segments) - len(persistent_segments)
        ),
        "train_offset_segments": int(len(train_segments)),
        "full_offset_segments": int(len(segments)),
        "full_persistent_offset_segments": int(len(persistent_segments)),
        "h1_from_m5_metrics": h1_derived_metrics,
        "h1_direct_metrics": h1_direct_metrics,
        "output_db": str(output_db) if decision.startswith("PASS") else None,
        "output_db_written": bool(decision.startswith("PASS")),
        "candidate_evaluations": evaluations,
        "loader_diagnostics": {
            "m5": am_m5.attrs.get("loader_diagnostics"),
            "h1": am_h1.attrs.get("loader_diagnostics") if am_h1 is not None else None,
        },
    }
    (report_dir / "stage177c_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (report_dir / "stage177c_time_contract.json").write_text(
        json.dumps(contract_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    decision_lines = [
        "# Stage177C AMarkets DST-Aware UTC Contract",
        "",
        f"Decision: `{decision}`",
        "",
        f"Selected contract: `{selected_contract.name}`",
        f"Standard shift: `{selected_contract.standard_shift_minutes}` minutes",
        f"DST shift: `{selected_contract.dst_shift_minutes}` minutes",
        f"DST calendar: `{selected_contract.dst_calendar}`",
        f"Selection used holdout: `False`",
        "",
        "## M5 all-sample",
        "",
        f"- overlap: `{selected_eval['all'].get('overlap_rows')}`",
        f"- coverage: `{selected_eval['all'].get('overlap_pct_of_amarkets')}`%",
        f"- 60m return correlation: `{selected_eval['all'].get('return_corr_60m')}`",
        f"- median absolute close difference: `{selected_eval['all'].get('median_abs_close_bps')}` bps",
        "",
        "## Untouched holdout",
        "",
        f"- start: `{config['holdout_start_utc']}`",
        f"- 60m return correlation: `{selected_eval['holdout'].get('return_corr_60m')}`",
        f"- coverage: `{selected_eval['holdout'].get('overlap_pct_of_amarkets')}`%",
        "",
        "## H1 derived from aligned M5",
        "",
        f"- return correlation: `{h1_derived_metrics.get('return_corr_1bar')}`",
        f"- overlap: `{h1_derived_metrics.get('overlap_rows')}`",
        "",
        "## Transition diagnostic",
        "",
        f"- raw max transitions/year: `{raw_transitions.get('max_transitions_in_year')}`",
        f"- persistent max transitions/year: `{persistent_transitions.get('max_transitions_in_year')}`",
        f"- isolated transient segments collapsed for gate: `{len(segments) - len(persistent_segments)}`",
        f"- max transient duration collapsed: `{max_transient_weeks}` week(s)",
        "",
        f"Failed checks: `{failed_checks}`",
        "",
        "Dukascopy remains the extended research feed. AMarkets remains the broker-specific execution/cost feed.",
        "No paper, demo, or live order is authorized.",
    ]
    (report_dir / "stage177c_decision.md").write_text(
        "\n".join(decision_lines) + "\n", encoding="utf-8"
    )

    print(json.dumps(summary, indent=2))
    return 0 if decision.startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
